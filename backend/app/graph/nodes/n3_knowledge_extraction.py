"""Stage 3 — Knowledge Extraction + chunk embedding into pgvector."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.db.vector_store import insert_chunks
from backend.app.graph.nodes.helpers import (
    as_uuid,
    chunk_text,
    dump_model,
    full_document_text,
    truncate,
)
from backend.app.graph.nodes.scope_filter import filter_knowledge_to_scope
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.knowledge import ExtractedKnowledge

logger = get_logger(__name__)

STAGE = "knowledge_extraction"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBED_BATCH = 32


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n3_knowledge_extraction.md")
    full_text = full_document_text(state)
    text_for_llm = truncate(full_text, 16000)
    classification = state.get("classification") or {}

    user_prompt = (
        f"Classification context (authoritative scope — extract ONLY within this "
        f"subject/topic/chapter; ignore unrelated source passages):\n"
        f"{classification}\n\n"
        f"Extract grounded knowledge from this document:\n{text_for_llm}"
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=ExtractedKnowledge,
            temperature=0.2,
            session=session,
            input_payload={
                "document_id": str(state.get("document_id")),
                "text_preview": text_for_llm[:2000],
            },
        )
        knowledge = ExtractedKnowledge.model_validate(resp.content)
        knowledge = filter_knowledge_to_scope(
            knowledge,
            classification if isinstance(classification, dict) else None,
        )

        chunks = chunk_text(full_text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        embeddings: list[list[float]] = []
        if chunks:
            for i in range(0, len(chunks), EMBED_BATCH):
                batch = chunks[i : i + EMBED_BATCH]
                embeddings.extend(await router.embed(batch))

        document_id = as_uuid(state["document_id"])
        chunk_rows: list[tuple[str, str | None, list[float] | None]] = []
        for idx, chunk in enumerate(chunks):
            emb = embeddings[idx] if idx < len(embeddings) else None
            chunk_rows.append((chunk, f"chunk_{idx}", emb))

        if chunk_rows:
            await insert_chunks(session, document_id, chunk_rows)
            await session.commit()

    logger.info(
        "n3_knowledge_extraction_done",
        concepts=len(knowledge.concepts),
        definitions=len(knowledge.definitions),
        chunks=len(chunks),
        model=resp.model,
    )

    return {
        "knowledge": dump_model(knowledge),
        "knowledge_chunk_texts": chunks,
        "current_stage": STAGE,
        "progress_pct": 35.0,
        "error": None,
    }
