"""LLM router: Gemini rate-limit → Groq fallback + cache hit path."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.llm.base import LLMResponse
from backend.app.llm.router import GROQ_ELIGIBLE, LLMRouter, RateLimitError


class _Tiny(BaseModel):
    value: str = Field(default="ok")


def _settings(**overrides: Any) -> Settings:
    data = {
        "gemini_api_key": "g-test",
        "groq_api_key": "groq-test",
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "backend_api_key": "test-backend-api-key-32chars!!",
    }
    data.update(overrides)
    return Settings(**data)


@pytest.mark.asyncio
async def test_rate_limit_falls_back_to_groq() -> None:
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(side_effect=Exception("429 rate limit exceeded"))
    groq = AsyncMock()
    groq.generate_structured = AsyncMock(
        return_value=LLMResponse(content={"value": "from-groq"}, model="groq", latency_ms=5)
    )
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)

    # Bypass tenacity retries on RateLimitError by making _call_gemini raise non-RateLimit
    # that still matches _is_rate_limit in the outer generate() except block.
    # Outer path: prefer gemini → exception with "429" → groq.
    with patch.object(
        router,
        "_call_gemini",
        AsyncMock(side_effect=Exception("429 Too Many Requests")),
    ):
        resp = await router.generate(
            stage_name="activity_generation",  # GROQ_ELIGIBLE
            system_prompt="sys",
            user_prompt="user",
            response_model=_Tiny,
        )
    assert resp.content["value"] == "from-groq"
    groq.generate_structured.assert_awaited()


@pytest.mark.asyncio
async def test_rate_limit_falls_back_via_gemini_once() -> None:
    """Eligible stages call _call_gemini_once; first 429 must hit Groq (no retry burn)."""
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(
        side_effect=Exception("429 RESOURCE_EXHAUSTED quota exceeded")
    )
    groq = AsyncMock()
    groq.generate_structured = AsyncMock(
        return_value=LLMResponse(
            content={"value": "groq-after-429"},
            model="llama-3.3-70b-versatile",
            latency_ms=12,
        )
    )
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    resp = await router.generate(
        stage_name="educational_classification",
        system_prompt="sys",
        user_prompt="user",
        response_model=_Tiny,
    )
    assert resp.content["value"] == "groq-after-429"
    assert resp.model == "llama-3.3-70b-versatile"
    assert gemini.generate_structured.await_count == 1
    groq.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_without_groq_reraises() -> None:
    gemini = AsyncMock()
    router = LLMRouter(settings=_settings(groq_api_key=None), gemini=gemini, groq=None)
    with (
        patch.object(
            router,
            "_call_gemini_with_retries",
            AsyncMock(side_effect=Exception("429 rate limit")),
        ),
        pytest.raises(Exception, match="429"),
    ):
        await router.generate(
            stage_name="activity_generation",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
        )


@pytest.mark.asyncio
async def test_non_eligible_stage_does_not_fallback() -> None:
    gemini = AsyncMock()
    groq = AsyncMock()
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    assert "teaching_planner" not in GROQ_ELIGIBLE
    with (
        patch.object(
            router,
            "_call_gemini_with_retries",
            AsyncMock(side_effect=Exception("429 rate limit")),
        ),
        pytest.raises(Exception, match="429"),
    ):
        await router.generate(
            stage_name="teaching_planner",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
        )
    groq.generate_structured.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_skips_providers() -> None:
    gemini = AsyncMock()
    groq = AsyncMock()
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    session = AsyncMock()
    cached = {
        "content": {"value": "cached"},
        "model": "cached-model",
        "token_usage": {"prompt": 1},
    }
    with patch("backend.app.llm.router.get_cached", AsyncMock(return_value=cached)):
        resp = await router.generate(
            stage_name="educational_classification",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
            session=session,
        )
    assert resp.cached is True
    assert resp.content["value"] == "cached"
    assert resp.latency_ms == 0
    gemini.generate_structured.assert_not_called()


@pytest.mark.asyncio
async def test_prefer_groq_path() -> None:
    gemini = AsyncMock()
    groq = AsyncMock()
    groq.generate_structured = AsyncMock(
        return_value=LLMResponse(content={"value": "g"}, model="groq", latency_ms=2)
    )
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    with patch("backend.app.llm.router.put_cached", AsyncMock()):
        resp = await router.generate(
            stage_name="gap_analysis",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
            prefer_groq=True,
        )
    assert resp.content["value"] == "g"


def test_model_for_stage() -> None:
    router = LLMRouter(settings=_settings(), gemini=MagicMock(), groq=None)
    assert "flash" in router.model_for_stage("knowledge_extraction")
    assert router.model_for_stage("unknown_stage")  # default


def test_is_rate_limit_tokens() -> None:
    assert LLMRouter._is_rate_limit(Exception("RESOURCE_EXHAUSTED"))
    assert LLMRouter._is_rate_limit(Exception("quota exceeded"))
    assert not LLMRouter._is_rate_limit(Exception("timeout"))


@pytest.mark.asyncio
async def test_call_gemini_wraps_rate_limit() -> None:
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(side_effect=Exception("429"))
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=None)
    with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(RateLimitError):
        await router._call_gemini(
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
            temperature=0.1,
            model="m",
        )
