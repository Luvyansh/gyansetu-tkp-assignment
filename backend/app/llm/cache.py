"""Postgres-backed LLM response cache keyed by content hash."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import LLMCache


def cache_key(stage_name: str, input_payload: Any, model: str) -> str:
    payload = json.dumps(
        {"stage": stage_name, "input": input_payload, "model": model},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_cached(
    session: AsyncSession, content_hash: str
) -> dict[str, Any] | None:
    result = await session.execute(
        select(LLMCache).where(LLMCache.content_hash == content_hash)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    await session.execute(
        update(LLMCache)
        .where(LLMCache.content_hash == content_hash)
        .values(hit_count=LLMCache.hit_count + 1)
    )
    await session.commit()
    return dict(row.response)


async def put_cached(
    session: AsyncSession,
    content_hash: str,
    stage_name: str,
    response: dict[str, Any],
) -> None:
    existing = await session.get(LLMCache, content_hash)
    if existing is not None:
        return
    session.add(
        LLMCache(content_hash=content_hash, stage_name=stage_name, response=response, hit_count=0)
    )
    await session.commit()
