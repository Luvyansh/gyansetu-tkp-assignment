"""LLM router: Flash-Lite → Groq → Flash last-resort + local embed cache."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.llm.base import LLMResponse
from backend.app.llm.gemini_client import DEFAULT_FLASH, DEFAULT_FLASH_LITE
from backend.app.llm.local_embeddings import LOCAL_EMBED_DIM, LOCAL_EMBED_MODEL
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
async def test_rate_limit_falls_back_via_gemini_once() -> None:
    """Eligible stages call Lite once; first 429 must hit Groq (no retry burn)."""
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
    assert gemini.generate_structured.await_args.kwargs["model"] == DEFAULT_FLASH_LITE


@pytest.mark.asyncio
async def test_groq_failure_falls_back_to_flash() -> None:
    """Lite 429 → Groq fail → full Flash last-resort."""
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(
        side_effect=[
            Exception("429 lite exhausted"),
            LLMResponse(content={"value": "from-flash"}, model=DEFAULT_FLASH, latency_ms=9),
        ]
    )
    groq = AsyncMock()
    groq.generate_structured = AsyncMock(side_effect=Exception("groq down"))
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    resp = await router.generate(
        stage_name="knowledge_extraction",
        system_prompt="sys",
        user_prompt="user",
        response_model=_Tiny,
    )
    assert resp.content["value"] == "from-flash"
    assert gemini.generate_structured.await_count == 2
    assert gemini.generate_structured.await_args_list[1].kwargs["model"] == DEFAULT_FLASH


@pytest.mark.asyncio
async def test_rate_limit_without_groq_falls_back_to_flash() -> None:
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(
        side_effect=[
            RateLimitError("429 lite"),
            RateLimitError("429 lite"),
            RateLimitError("429 lite"),
            RateLimitError("429 lite"),
            RateLimitError("429 lite"),
            RateLimitError("429 lite"),
            LLMResponse(content={"value": "flash-last"}, model=DEFAULT_FLASH, latency_ms=3),
        ]
    )
    router = LLMRouter(settings=_settings(groq_api_key=None), gemini=gemini, groq=None)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        resp = await router.generate(
            stage_name="activity_generation",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
        )
    assert resp.content["value"] == "flash-last"
    # 6 Lite retries exhausted, then Flash succeeds on first try
    assert any(
        c.kwargs.get("model") == DEFAULT_FLASH for c in gemini.generate_structured.await_args_list
    )


@pytest.mark.asyncio
async def test_non_eligible_stage_does_not_call_groq() -> None:
    """Unknown / non-eligible stages never touch Groq (Flash last-resort only)."""
    gemini = AsyncMock()
    gemini.generate_structured = AsyncMock(side_effect=Exception("429 rate limit"))
    groq = AsyncMock()
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=groq)
    assert "not_a_real_stage" not in GROQ_ELIGIBLE
    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch.object(
            router,
            "_call_gemini_with_retries",
            AsyncMock(
                side_effect=[
                    RateLimitError("429 lite"),
                    LLMResponse(content={"value": "flash"}, model=DEFAULT_FLASH, latency_ms=1),
                ]
            ),
        ),
    ):
        resp = await router.generate(
            stage_name="not_a_real_stage",
            system_prompt="s",
            user_prompt="u",
            response_model=_Tiny,
        )
    assert resp.content["value"] == "flash"
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


def test_model_for_stage_is_flash_lite() -> None:
    router = LLMRouter(settings=_settings(), gemini=MagicMock(), groq=None)
    assert router.model_for_stage("knowledge_extraction") == DEFAULT_FLASH_LITE
    assert router.model_for_stage("teaching_planner") == DEFAULT_FLASH_LITE
    assert router.model_for_stage("validation_judge") == DEFAULT_FLASH_LITE
    assert router.model_for_stage("unknown_stage") == DEFAULT_FLASH_LITE
    for stage in (
        "knowledge_extraction",
        "teaching_planner",
        "validation_judge",
    ):
        assert stage in GROQ_ELIGIBLE


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


@pytest.mark.asyncio
async def test_embed_uses_content_hash_cache() -> None:
    """Identical texts must not call the local model when the hash is already cached."""
    from backend.app.llm.cache import embed_cache_key

    gemini = AsyncMock()
    gemini.embed = AsyncMock(return_value=[[0.5] * LOCAL_EMBED_DIM])
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=None)
    session = AsyncMock()
    key = embed_cache_key("dup", LOCAL_EMBED_MODEL)

    with (
        patch(
            "backend.app.llm.router.get_cached_embeddings",
            AsyncMock(return_value={key: [0.9] * LOCAL_EMBED_DIM}),
        ),
        patch("backend.app.llm.router.put_cached_embeddings", AsyncMock()) as put,
        patch("backend.app.llm.router.embed_texts", AsyncMock()) as local_embed,
    ):
        vectors = await router.embed(["dup"], session=session, stage="test")

    assert vectors == [[0.9] * LOCAL_EMBED_DIM]
    local_embed.assert_not_called()
    gemini.embed.assert_not_called()
    put.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_uses_local_model_on_cache_miss() -> None:
    gemini = AsyncMock()
    gemini.embed = AsyncMock()
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=None)
    session = AsyncMock()
    fake = [[0.2] * LOCAL_EMBED_DIM, [0.3] * LOCAL_EMBED_DIM]

    with (
        patch("backend.app.llm.router.get_cached_embeddings", AsyncMock(return_value={})),
        patch("backend.app.llm.router.put_cached_embeddings", AsyncMock()) as put,
        patch("backend.app.llm.router.embed_texts", AsyncMock(return_value=fake)) as local_embed,
    ):
        vectors = await router.embed(["a", "b"], session=session, stage="knowledge_extraction")

    assert len(vectors) == 2
    local_embed.assert_awaited_once_with(["a", "b"])
    gemini.embed.assert_not_called()
    put.assert_awaited_once()
    stored = put.await_args.args[1]
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_multimodal_falls_back_to_flash_on_lite_429() -> None:
    gemini = AsyncMock()
    gemini.generate_multimodal = AsyncMock(
        side_effect=[
            Exception("429 lite multimodal"),
            LLMResponse(content={"value": "mm"}, model=DEFAULT_FLASH, latency_ms=4),
        ]
    )
    router = LLMRouter(settings=_settings(), gemini=gemini, groq=None)
    resp = await router.multimodal(
        stage_name="multimodal_fallback",
        system_prompt="s",
        user_prompt="u",
        image_bytes_list=[b"img"],
        response_model=_Tiny,
    )
    assert resp.content["value"] == "mm"
    assert gemini.generate_multimodal.await_count == 2
    assert gemini.generate_multimodal.await_args_list[0].kwargs["model"] == DEFAULT_FLASH_LITE
    assert gemini.generate_multimodal.await_args_list[1].kwargs["model"] == DEFAULT_FLASH
