"""Local sentence-transformers embeddings — no external API.

Model is lazy-loaded on first ``embed`` call and reused thereafter (not at
FastAPI startup — eager load + CUDA torch exceeds Render free-tier 512MB).
Dimension must stay in sync with ``Settings.embedding_dim`` and the pgvector
column (Alembic ``0002_embed_dim_384``).
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.logging_config import get_logger

logger = get_logger(__name__)

LOCAL_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_EMBED_DIM = 384

_model: Any | None = None
_lock = asyncio.Lock()


def load_embedding_model() -> Any:
    """Load ``all-MiniLM-L6-v2`` once (sync — call under a lock from async path)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("local_embed_model_loading", model=LOCAL_EMBED_MODEL, dim=LOCAL_EMBED_DIM)
        # device="cpu" avoids accidental CUDA init if a CUDA wheel slips in.
        _model = SentenceTransformer(LOCAL_EMBED_MODEL, device="cpu")
        logger.info("local_embed_model_ready", model=LOCAL_EMBED_MODEL)
    return _model


async def ensure_embedding_model_loaded() -> None:
    """Idempotent async warm-up (optional; preferred path is lazy first embed)."""
    async with _lock:
        if _model is None:
            await asyncio.to_thread(load_embedding_model)


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Encode texts to 384-d float vectors on the calling thread."""
    if not texts:
        return []
    model = load_embedding_model()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    result: list[list[float]] = []
    for row in vectors:
        values = [float(v) for v in row.tolist()]
        if len(values) > LOCAL_EMBED_DIM:
            values = values[:LOCAL_EMBED_DIM]
        elif len(values) < LOCAL_EMBED_DIM:
            values = values + [0.0] * (LOCAL_EMBED_DIM - len(values))
        result.append(values)
    return result


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Async wrapper — runs CPU encode off the event loop."""
    if not texts:
        return []
    return await asyncio.to_thread(embed_texts_sync, texts)


def reset_embedding_model_for_tests() -> None:
    """Drop the singleton (unit tests only)."""
    global _model
    _model = None
