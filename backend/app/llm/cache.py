"""Postgres-backed LLM / embedding cache keyed by content hash."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import LLMCache

EMBED_CACHE_STAGE = "embedding"


def cache_key(stage_name: str, input_payload: Any, model: str) -> str:
    payload = json.dumps(
        {"stage": stage_name, "input": input_payload, "model": model},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def embed_cache_key(text: str, model: str) -> str:
    """Stable key for a single embeddable string under ``model``."""
    return cache_key(EMBED_CACHE_STAGE, {"text": text}, model)


async def get_cached(session: AsyncSession, content_hash: str) -> dict[str, Any] | None:
    result = await session.execute(select(LLMCache).where(LLMCache.content_hash == content_hash))
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


async def get_cached_embeddings(
    session: AsyncSession, content_hashes: list[str]
) -> dict[str, list[float]]:
    """Bulk-fetch cached embedding vectors keyed by content hash."""
    if not content_hashes:
        return {}
    result = await session.execute(
        select(LLMCache).where(LLMCache.content_hash.in_(content_hashes))
    )
    rows = list(result.scalars().all())
    found: dict[str, list[float]] = {}
    hit_ids: list[str] = []
    for row in rows:
        embedding = row.response.get("embedding") if isinstance(row.response, dict) else None
        if isinstance(embedding, list) and embedding:
            found[row.content_hash] = [float(v) for v in embedding]
            hit_ids.append(row.content_hash)
    if hit_ids:
        await session.execute(
            update(LLMCache)
            .where(LLMCache.content_hash.in_(hit_ids))
            .values(hit_count=LLMCache.hit_count + 1)
        )
        await session.commit()
    return found


async def put_cached_embeddings(
    session: AsyncSession,
    items: list[tuple[str, list[float]]],
) -> None:
    """Store ``(content_hash, embedding)`` pairs; skip hashes already present."""
    if not items:
        return
    hashes = [h for h, _ in items]
    existing = await session.execute(
        select(LLMCache.content_hash).where(LLMCache.content_hash.in_(hashes))
    )
    already = {row[0] for row in existing.all()}
    for content_hash, embedding in items:
        if content_hash in already:
            continue
        session.add(
            LLMCache(
                content_hash=content_hash,
                stage_name=EMBED_CACHE_STAGE,
                response={"embedding": embedding},
                hit_count=0,
            )
        )
        already.add(content_hash)
    await session.commit()
