"""Unit tests for Gemini per-model RPM limiter."""

from __future__ import annotations

import pytest

from backend.app.llm.rate_limit import ModelRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_records_window_and_concurrency() -> None:
    limiter = ModelRateLimiter()
    model = "gemini-3.5-flash-test"

    await limiter.acquire(model)
    assert len(limiter._windows[model]) == 1
    assert limiter._sems[model]._value == 0  # concurrency 1 for non-lite
    limiter.release(model)
    assert limiter._sems[model]._value == 1


@pytest.mark.asyncio
async def test_lite_allows_higher_concurrency() -> None:
    limiter = ModelRateLimiter()
    model = "gemini-3.5-flash-lite-test"
    await limiter.acquire(model)
    await limiter.acquire(model)
    assert limiter._sems[model]._value == 0
    limiter.release(model)
    limiter.release(model)


def test_embed_model_uses_higher_rpm_budget() -> None:
    limiter = ModelRateLimiter()
    assert limiter._max_per_minute("gemini-embedding-001") == 80
    assert limiter._concurrency("gemini-embedding-001") == 2
    assert limiter._max_per_minute("gemini-3.5-flash") == 4


@pytest.mark.asyncio
async def test_embed_weight_consumes_multiple_rpm_slots() -> None:
    limiter = ModelRateLimiter()
    model = "gemini-embedding-weight-test"
    await limiter.acquire(model, weight=10)
    assert len(limiter._windows[model]) == 10
    limiter.release(model)


def test_classroom_and_assessment_use_flash_lite() -> None:
    from backend.app.llm.gemini_client import DEFAULT_FLASH_LITE
    from backend.app.llm.router import STAGE_MODELS

    assert STAGE_MODELS["classroom_content"] == DEFAULT_FLASH_LITE
    assert STAGE_MODELS["assessment_generation"] == DEFAULT_FLASH_LITE
