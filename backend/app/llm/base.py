"""LLM client protocol and shared types."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel):
    content: dict[str, Any]
    model: str
    latency_ms: int
    token_usage: dict[str, int] = {}
    cached: bool = False


class LLMClient(Protocol):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.2,
        model: str | None = None,
    ) -> LLMResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def generate_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes_list: list[bytes],
        response_model: type[T],
        temperature: float = 0.2,
        model: str | None = None,
    ) -> LLMResponse: ...
