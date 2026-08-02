"""API auth tests — missing/invalid X-API-Key → 401."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_api_key(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 401
    assert "API key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_api_key(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000001",
        headers={"X-API-Key": "definitely-wrong-key"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key_reaches_handler(client: AsyncClient, auth_headers: dict) -> None:
    # Job won't exist — expect 404 rather than 401
    from unittest.mock import AsyncMock, MagicMock

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]

    resp = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000001",
        headers=auth_headers,
    )
    assert resp.status_code == 404
