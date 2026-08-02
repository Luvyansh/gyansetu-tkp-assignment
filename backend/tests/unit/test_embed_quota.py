"""Tests for provider quota humanization."""

from __future__ import annotations

import pytest

from backend.app.llm.errors import (
    DAILY_EMBED_QUOTA_MESSAGE,
    DailyEmbedQuotaError,
    humanize_provider_error,
    is_daily_embed_quota_error,
)

_DAILY_RAW = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota...', 'status': 'RESOURCE_EXHAUSTED', 'details': "
    "[{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': "
    "[{'quotaMetric': 'generativelanguage.googleapis.com/embed_content_free_tier_requests', "
    "'quotaId': 'EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier', "
    "'quotaValue': '1000'}]}]}}"
)


def test_detects_daily_embed_quota() -> None:
    assert is_daily_embed_quota_error(_DAILY_RAW)
    assert is_daily_embed_quota_error(Exception(_DAILY_RAW))


def test_ignores_rpm_or_unrelated_429() -> None:
    rpm = (
        "429 RESOURCE_EXHAUSTED. quotaId': "
        "'EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier'"
    )
    assert not is_daily_embed_quota_error(rpm)
    assert not is_daily_embed_quota_error("429 on generate_content PerDay Flash")


def test_humanize_daily_embed_message() -> None:
    assert humanize_provider_error(_DAILY_RAW) == DAILY_EMBED_QUOTA_MESSAGE
    assert "midnight Pacific" in humanize_provider_error(_DAILY_RAW)


def test_humanize_passthrough_other_errors() -> None:
    assert humanize_provider_error(RuntimeError("boom")) == "boom"


@pytest.mark.asyncio
async def test_gemini_embed_raises_daily_quota_error() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.app.llm.gemini_client import GeminiClient

    client = GeminiClient.__new__(GeminiClient)
    aio_models = MagicMock()
    aio_models.embed_content = AsyncMock(side_effect=Exception(_DAILY_RAW))
    client._client = MagicMock()
    client._client.aio.models = aio_models

    with patch("backend.app.llm.gemini_client.rate_limited") as rl:
        rl.return_value.__aenter__ = AsyncMock(return_value=None)
        rl.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(DailyEmbedQuotaError, match="midnight Pacific"):
            await client.embed(["chunk text"])
