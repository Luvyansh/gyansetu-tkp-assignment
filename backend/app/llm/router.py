"""Model router: stage → Flash-Lite primary, Groq fallback, Flash last-resort.

Embeddings are always local (``sentence-transformers/all-MiniLM-L6-v2``) —
never Gemini or Groq.
"""

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
    DEFAULT_FLASH,
    DEFAULT_FLASH_LITE,
    GeminiClient,
)
from backend.app.llm.groq_client import DEFAULT_GROQ_MODEL, GroqClient
from backend.app.llm.local_embeddings import (
    LOCAL_EMBED_DIM,
    LOCAL_EMBED_MODEL,
    embed_texts,
)
from backend.app.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)

# All generation stages prefer Flash-Lite (Flash is last-resort only).
STAGE_MODELS: dict[str, str] = {
    "educational_classification": DEFAULT_FLASH_LITE,
    "knowledge_extraction": DEFAULT_FLASH_LITE,
    "teaching_planner": DEFAULT_FLASH_LITE,
    "classroom_content": DEFAULT_FLASH_LITE,
    "activity_generation": DEFAULT_FLASH_LITE,
    "assessment_generation": DEFAULT_FLASH_LITE,
    "gap_analysis": DEFAULT_FLASH_LITE,
    "validation_judge": DEFAULT_FLASH_LITE,
    "multimodal_fallback": DEFAULT_FLASH_LITE,
}

# Text stages may fall back to Groq before last-resort Flash.
# Multimodal stays Gemini-only (Groq has no vision path).
GROQ_ELIGIBLE = {
    "educational_classification",
    "knowledge_extraction",
    "teaching_planner",
    "classroom_content",
    "activity_generation",
    "assessment_generation",
    "gap_analysis",
    "validation_judge",
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
        return STAGE_MODELS.get(stage_name, DEFAULT_FLASH_LITE)

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

        response = await self._generate_with_cascade(
            stage_name=stage_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature=temperature,
            primary_model=model,
            prefer_groq=prefer_groq,
        )

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

    async def _generate_with_cascade(
        self,
        *,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float,
        primary_model: str,
        prefer_groq: bool,
    ) -> LLMResponse:
        """Flash-Lite → Groq (eligible) → full Flash last-resort."""
        if prefer_groq and self._groq_fallback_available(stage_name):
            try:
                return await self._call_groq(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                )
            except Exception as exc:
                logger.warning(
                    "prefer_groq_failed_trying_lite",
                    stage=stage_name,
                    error=str(exc)[:200],
                )

        if self._groq_fallback_available(stage_name):
            # Fail fast into Groq on Lite 429 — do not burn retry budget.
            try:
                return await self._call_gemini_once(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                    model=primary_model,
                )
            except Exception as exc:
                if not self._is_rate_limit(exc):
                    raise
                logger.warning("lite_rate_limited_falling_back_groq", stage=stage_name)
                try:
                    return await self._call_groq(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=response_model,
                        temperature=temperature,
                    )
                except Exception as groq_exc:
                    logger.warning(
                        "groq_failed_falling_back_flash",
                        stage=stage_name,
                        error=str(groq_exc)[:200],
                    )
                    return await self._call_gemini_with_retries(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=response_model,
                        temperature=temperature,
                        model=DEFAULT_FLASH,
                    )

        # No Groq: Lite with retries, then Flash last-resort on rate limit.
        try:
            return await self._call_gemini_with_retries(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                temperature=temperature,
                model=primary_model,
            )
        except Exception as exc:
            if self._is_rate_limit(exc) or isinstance(exc, RateLimitError):
                logger.warning("lite_exhausted_falling_back_flash", stage=stage_name)
                return await self._call_gemini_with_retries(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    temperature=temperature,
                    model=DEFAULT_FLASH,
                )
            raise

    async def embed(
        self,
        texts: list[str],
        *,
        session: AsyncSession | None = None,
        stage: str | None = None,
    ) -> list[list[float]]:
        """Embed texts locally (MiniLM) with Postgres content-hash cache."""
        if not texts:
            return []

        from backend.app.db.session import AsyncSessionLocal

        dim = self.settings.embedding_dim or LOCAL_EMBED_DIM

        async def _embed_with_cache(db: AsyncSession) -> list[list[float]]:
            keys = [embed_cache_key(t, LOCAL_EMBED_MODEL) for t in texts]
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

            local_count = 0
            if miss_texts:
                fresh = await embed_texts(miss_texts)
                local_count = len(miss_texts)
                to_store: list[tuple[str, list[float]]] = []
                for idx, vector in zip(miss_indices, fresh, strict=True):
                    results[idx] = vector
                    to_store.append((keys[idx], vector))
                await put_cached_embeddings(db, to_store)

            logger.info(
                "embed_cache_lookup",
                stage=stage or "unspecified",
                requested=len(texts),
                cache_hits=len(texts) - local_count,
                local_texts=local_count,
                model=LOCAL_EMBED_MODEL,
            )
            return [v if v is not None else [0.0] * dim for v in results]

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
        """Flash-Lite first; full Flash only if Lite is rate-limited (no Groq vision)."""
        primary = self.model_for_stage(stage_name)
        try:
            return await self.gemini.generate_multimodal(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_bytes_list=image_bytes_list,
                response_model=response_model,
                temperature=temperature,
                model=primary,
            )
        except Exception as exc:
            if not self._is_rate_limit(exc):
                raise
            logger.warning("multimodal_lite_rate_limited_falling_back_flash", stage=stage_name)
            return await self.gemini.generate_multimodal(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_bytes_list=image_bytes_list,
                response_model=response_model,
                temperature=temperature,
                model=DEFAULT_FLASH,
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
