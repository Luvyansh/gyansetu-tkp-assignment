"""API health endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_root_ok() -> None:
    with patch("backend.app.main.check_db_connection", new_callable=AsyncMock) as db:
        db.return_value = True
        from backend.app.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["gemini_key_present"] is True


@pytest.mark.asyncio
async def test_health_v1_degraded() -> None:
    with patch("backend.app.main.check_db_connection", new_callable=AsyncMock) as db:
        db.return_value = False
        from backend.app.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["database"] == "down"
