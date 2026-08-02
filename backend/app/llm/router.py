"""Model router: stage → model choice, cache, retry, Gemini→Groq fallback."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.app.config import Settings, get_settings
from backend.app.llm.base import LLMResponse
from backend.app.llm.cache import (
    cache_key,
    embed_cache_key,
    get_cached,
    get_cached_embeddings,
    put_cached,
    put_cached_embeddings,
)
from backend.app.llm.gemini_client import (
    DEFAULT_EMBED,
    DEFAULT_FLASH,
    DEFAULT_FLASH_LITE,
    GeminiClient,
)
from backend.app.llm.groq_client import DEFAULT_GROQ_MODEL, GroqClient
from backend.app.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)

# Stage → preferred Gemini model
STAGE_MODELS: dict[str, str] = {
    "educational_classification": DEFAULT_FLASH_LITE,
    "knowledge_extraction": DEFAULT_FLASH,
    "teaching_planner": DEFAULT_FLASH,
    # Per-period fan-out: prefer lite so free-tier Flash RPM (≈5) is not saturated.
    "classroom_content": DEFAULT_FLASH_LITE,
    "activity_generation": DEFAULT_FLASH_LITE,
    "assessment_generation": DEFAULT_FLASH_LITE,
    "gap_analysis": DEFAULT_FLASH_LITE,
    "validation_judge": DEFAULT_FLASH,
    "multimodal_fallback": DEFAULT_FLASH,
}

# Stages that may fall back to Groq for speed/overflow
GROQ_ELIGIBLE = {
    "educational_classification",
    "activity_generation",
    "gap_analysis",
    "classroom_content",
    "assessment_generation",
}


class RateLimitError(Exception):
    """Raised when the primary provider is rate-limited."""


class LLMRouter:
    def __init__(
        self,
        settings: Settings | None = None,
        gemini: GeminiClient | None = None,
        groq: GroqClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.gemini = gemini or GeminiClient(self.settings.gemini_api_key)
        self.groq = groq
        if self.groq is None and self.settings.groq_enabled and self.settings.groq_api_key:
            self.groq = GroqClient(self.settings.groq_api_key)

    def model_for_stage(self, stage_name: str) -> str:
        return STAGE_MODELS.get(stage_name, DEFAULT_FLASH)

    def _groq_fallback_available(self, stage_name: str) -> bool:
        return self.groq is not None and stage_name in GROQ_ELIGIBLE

    async def generate(
        self,
        *,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.2,
        session: AsyncSession | None = None,
        input_payload: Any | None = None,
        prefer_groq: bool = False,
    ) -> LLMResponse:
        model = self.model_for_stage(stage_name)
        payload = input_payload if input_payload is not None else user_prompt
        key = cache_key(stage_name, payload, model)

        if session is not None:
            cached = await get_cached(session, key)
            if cached is not None:
                logger.info("llm_cache_hit", stage=stage_name, model=model)
                return LLMResponse(
                    content=cached.get("content", cached),
                    model=str(cached.get("model", model)),
                    latency_ms=0,
                    token_usage=cached.get("token_usage", {}),
                    cached=True,
                )

        try:
            if prefer_groq and self._groq_fallback_available(stage_name):
                response = await self._call_groq(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                )
            elif self._groq_fallback_available(stage_name):
                # Fail fast into Groq on 429 — do not burn retry budget on Gemini.
                response = await self._call_gemini_once(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                    model=model,
                )
            else:
                response = await self._call_gemini_with_retries(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                    model=model,
                )
        except Exception as exc:
            if self._is_rate_limit(exc) and self._groq_fallback_available(stage_name):
                logger.warning("gemini_rate_limited_falling_back_groq", stage=stage_name)
                response = await self._call_groq(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                )
            else:
                raise

        if session is not None:
            await put_cached(
                session,
                key,
                stage_name,
                {
                    "content": response.content,
                    "model": response.model,
                    "token_usage": response.token_usage,
                },
            )
        return response

    async def embed(
        self,
        texts: list[str],
        *,
        session: AsyncSession | None = None,
        stage: str | None = None,
    ) -> list[list[float]]:
        """Embed texts with Postgres content-hash cache (identical strings skip the API)."""
        if not texts:
            return []

        from backend.app.db.session import AsyncSessionLocal

        async def _embed_with_cache(db: AsyncSession) -> list[list[float]]:
            keys = [embed_cache_key(t, DEFAULT_EMBED) for t in texts]
            cached = await get_cached_embeddings(db, keys)
            results: list[list[float] | None] = [None] * len(texts)
            miss_indices: list[int] = []
            miss_texts: list[str] = []
            for i, key in enumerate(keys):
                hit = cached.get(key)
                if hit is not None:
                    results[i] = hit
                else:
                    miss_indices.append(i)
                    miss_texts.append(texts[i])

            api_count = 0
            if miss_texts:
                fresh = await self.gemini.embed(miss_texts)
                api_count = len(miss_texts)
                to_store: list[tuple[str, list[float]]] = []
                for idx, vector in zip(miss_indices, fresh, strict=True):
                    results[idx] = vector
                    to_store.append((keys[idx], vector))
                await put_cached_embeddings(db, to_store)

            logger.info(
                "embed_cache_lookup",
                stage=stage or "unspecified",
                requested=len(texts),
                cache_hits=len(texts) - api_count,
                api_texts=api_count,
                model=DEFAULT_EMBED,
            )
            return [v if v is not None else [0.0] * 768 for v in results]

        if session is not None:
            return await _embed_with_cache(session)
        async with AsyncSessionLocal() as db:
            return await _embed_with_cache(db)

    async def multimodal(
        self,
        *,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        image_bytes_list: list[bytes],
        response_model: type[T],
        temperature: float = 0.2,
    ) -> LLMResponse:
        model = self.model_for_stage(stage_name)
        return await self.gemini.generate_multimodal(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_bytes_list=image_bytes_list,
            response_model=response_model,
            temperature=temperature,
            model=model,
        )

    async def _call_gemini_once(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float,
        model: str,
    ) -> LLMResponse:
        try:
            return await self.gemini.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                temperature=temperature,
                model=model,
            )
        except Exception as exc:
            if self._is_rate_limit(exc):
                raise RateLimitError(str(exc)) from exc
            raise

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def _call_gemini_with_retries(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float,
        model: str,
    ) -> LLMResponse:
        return await self._call_gemini_once(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature=temperature,
            model=model,
        )

    # Back-compat alias used by older tests / callers.
    async def _call_gemini(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float,
        model: str,
    ) -> LLMResponse:
        return await self._call_gemini_with_retries(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature=temperature,
            model=model,
        )

    async def _call_groq(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float,
    ) -> LLMResponse:
        assert self.groq is not None
        return await self.groq.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature=temperature,
            model=DEFAULT_GROQ_MODEL,
        )

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(tok in text for tok in ("429", "rate limit", "resource_exhausted", "quota"))


_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
