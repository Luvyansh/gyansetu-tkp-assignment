"""Gemini client via google-genai SDK."""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar, cast

from google import genai
from google.genai import types
from pydantic import BaseModel

from backend.app.llm.base import LLMResponse
from backend.app.llm.errors import DailyEmbedQuotaError, is_daily_embed_quota_error
from backend.app.llm.rate_limit import rate_limited
from backend.app.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)

# Gemini 2.0 Flash / Flash-Lite retired 2026-06-01 (free-tier quota limit:0).
# Gemini 2.5 Flash / Flash-Lite return 404 for new API keys ("no longer available
# to new users"). Use current stable 3.x IDs — see ISSUES.md.
DEFAULT_FLASH_LITE = "gemini-3.5-flash-lite"
DEFAULT_FLASH = "gemini-3.5-flash"
DEFAULT_EMBED = "gemini-embedding-001"


class GeminiClient:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.2,
        model: str | None = None,
    ) -> LLMResponse:
        model_name = model or DEFAULT_FLASH
        started = time.perf_counter()
        schema = response_model.model_json_schema()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        async with rate_limited(model_name):
            response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=config,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = response.text or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("gemini_json_parse_failed", model=model_name)
            parsed = {}
        # Validate against schema — raises if malformed
        validated = response_model.model_validate(parsed)
        usage = {}
        if response.usage_metadata is not None:
            meta = response.usage_metadata
            usage = {
                "prompt_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
                "completion_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
            }
        return LLMResponse(
            content=validated.model_dump(mode="json"),
            model=model_name,
            latency_ms=latency_ms,
            token_usage=usage,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts via Gemini batch ``embed_content`` (one RPM slot per batch).

        The google-genai SDK accepts a list of strings as ``contents`` and returns
        one embedding per input. We still chunk oversized lists to stay within
        API batch limits, and wrap each request in the shared RPM limiter.
        """
        if not texts:
            return []

        result: list[list[float]] = []
        embed_config = types.EmbedContentConfig(output_dimensionality=768)
        # Free-tier embed RPM counts per text (~100/min). Batch for latency, but
        # keep each HTTP call within the limiter budget (80/min with headroom).
        max_batch = 40

        for i in range(0, len(texts), max_batch):
            batch = texts[i : i + max_batch]
            try:
                async with rate_limited(DEFAULT_EMBED, weight=len(batch)):
                    response = await self._client.aio.models.embed_content(
                        model=DEFAULT_EMBED,
                        contents=cast(Any, batch),
                        config=embed_config,
                    )
            except Exception as exc:
                if is_daily_embed_quota_error(exc):
                    raise DailyEmbedQuotaError() from exc
                raise
            result.extend(self._parse_embeddings(response, expected=len(batch)))
        return result

    @staticmethod
    def _parse_embeddings(response: Any, *, expected: int) -> list[list[float]]:
        """Normalize SDK embed response into ``expected`` float vectors of dim 768."""
        embedding = getattr(response, "embeddings", None) or getattr(response, "embedding", None)
        raw_items: list[Any]
        if embedding is None:
            values = list(getattr(response, "values", []) or [])
            raw_items = [values] if values else []
        elif isinstance(embedding, list):
            raw_items = list(embedding)
        else:
            raw_items = [embedding]

        vectors: list[list[float]] = []
        for item in raw_items:
            if isinstance(item, (list, tuple)):
                values = list(item)
            else:
                values = list(getattr(item, "values", item) or [])
            if len(values) > 768:
                values = values[:768]
            elif len(values) < 768:
                values = list(values) + [0.0] * (768 - len(values))
            vectors.append([float(v) for v in values])

        if len(vectors) < expected:
            # Pad missing slots with zeros so callers keep index alignment.
            zero = [0.0] * 768
            vectors.extend(zero for _ in range(expected - len(vectors)))
        elif len(vectors) > expected:
            vectors = vectors[:expected]
        return vectors

    async def generate_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes_list: list[bytes],
        response_model: type[T],
        temperature: float = 0.2,
        model: str | None = None,
    ) -> LLMResponse:
        model_name = model or DEFAULT_FLASH
        started = time.perf_counter()
        parts: list[types.Part | str] = [user_prompt]
        for img in image_bytes_list:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=response_model.model_json_schema(),
        )
        async with rate_limited(model_name):
            response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=cast(Any, parts),
                config=config,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = response.text or "{}"
        parsed = json.loads(raw)
        validated = response_model.model_validate(parsed)
        return LLMResponse(
            content=validated.model_dump(mode="json"),
            model=model_name,
            latency_ms=latency_ms,
            token_usage={},
        )
