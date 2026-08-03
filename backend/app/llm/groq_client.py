"""Groq client — OpenAI-compatible fallback for rate-limit overflow."""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar, cast

from groq import AsyncGroq
from pydantic import BaseModel

from backend.app.llm.base import LLMResponse
from backend.app.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncGroq(api_key=api_key)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.2,
        model: str | None = None,
    ) -> LLMResponse:
        model_name = model or DEFAULT_GROQ_MODEL
        started = time.perf_counter()
        schema = response_model.model_json_schema()
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_prompt}\n\nRespond with JSON matching this schema:\n"
                    f"{json.dumps(schema)}"
                ),
            },
        ]
        response = await self._client.chat.completions.create(
            model=model_name,
            messages=cast(Any, messages),
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        validated = response_model.model_validate(parsed)
        usage = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": int(response.usage.prompt_tokens or 0),
                "completion_tokens": int(response.usage.completion_tokens or 0),
            }
        return LLMResponse(
            content=validated.model_dump(mode="json"),
            model=model_name,
            latency_ms=latency_ms,
            token_usage=usage,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Embeddings are local (sentence-transformers/all-MiniLM-L6-v2); "
            "use LLMRouter.embed — Groq has no embedding path."
        )

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
        raise NotImplementedError("Groq client does not support multimodal; use Gemini.")
