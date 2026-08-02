"""FastAPI dependency for X-API-Key authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from backend.app.config import get_settings


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Verify the ``X-API-Key`` header against ``settings.backend_api_key``.

    Raises:
        HTTPException: 401 when the header is missing or does not match.
    """
    settings = get_settings()
    if not x_api_key or x_api_key != settings.backend_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key
