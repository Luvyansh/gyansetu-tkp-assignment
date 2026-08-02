"""Shared FastAPI dependencies, rate limiter, and SSE progress bus."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.security.api_key_auth import verify_api_key

limiter = Limiter(key_func=get_remote_address)

# In-memory SSE progress bus: job_id → queue of StreamEvent-like dicts
_progress_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session."""
    async for session in get_db_session():
        yield session


# Re-export for route Depends(...)
RequireApiKey = Depends(verify_api_key)


def get_progress_queue(job_id: uuid.UUID | str) -> asyncio.Queue[dict[str, Any] | None]:
    """Return (creating if needed) the progress queue for a job."""
    key = str(job_id)
    if key not in _progress_queues:
        _progress_queues[key] = asyncio.Queue()
    return _progress_queues[key]


async def publish_progress(job_id: uuid.UUID | str, event: dict[str, Any]) -> None:
    """Push a progress event to the job's SSE queue (no-op if no listeners yet)."""
    key = str(job_id)
    queue = _progress_queues.get(key)
    if queue is None:
        queue = get_progress_queue(key)
    await queue.put(event)


def close_progress_queue(job_id: uuid.UUID | str) -> None:
    """Signal end-of-stream and drop the queue reference."""
    key = str(job_id)
    queue = _progress_queues.pop(key, None)
    if queue is not None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(None)


__all__ = [
    "RequireApiKey",
    "close_progress_queue",
    "get_db",
    "get_progress_queue",
    "limiter",
    "publish_progress",
    "verify_api_key",
]
