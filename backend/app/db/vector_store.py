"""pgvector helpers for grounding checks and RAG traceability."""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import KnowledgeChunk


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def ensure_pgvector(session: AsyncSession) -> None:
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await session.commit()


async def insert_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    chunks: list[tuple[str, str | None, list[float] | None]],
) -> list[KnowledgeChunk]:
    """Insert (chunk_text, section_ref, embedding) tuples."""
    rows: list[KnowledgeChunk] = []
    for text_value, section_ref, embedding in chunks:
        row = KnowledgeChunk(
            document_id=document_id,
            chunk_text=text_value,
            section_ref=section_ref,
            embedding=embedding,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def fetch_chunks_for_document(
    session: AsyncSession, document_id: uuid.UUID
) -> list[KnowledgeChunk]:
    result = await session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    )
    return list(result.scalars().all())


async def similarity_search(
    session: AsyncSession,
    document_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[KnowledgeChunk, float]]:
    """Nearest-neighbor search via pgvector cosine distance."""
    # <=> is cosine distance in pgvector; similarity = 1 - distance
    stmt = (
        select(
            KnowledgeChunk,
            (1 - KnowledgeChunk.embedding.cosine_distance(query_embedding)).label("score"),
        )
        .where(KnowledgeChunk.document_id == document_id)
        .where(KnowledgeChunk.embedding.is_not(None))
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row[0], float(row[1])) for row in result.all()]
