"""Stage 1 — Document Intelligence: parse uploaded file into structure."""

from __future__ import annotations

from typing import Any

from backend.app.graph.nodes.helpers import dump_model
from backend.app.logging_config import get_logger
from backend.app.parsing.router import parse_document
from backend.app.schemas.document import DocTypeHint

logger = get_logger(__name__)


async def run(state: dict[str, Any]) -> dict[str, Any]:
    file_path = state.get("file_path")
    if not file_path:
        raise ValueError("file_path is required for document intelligence")

    hint_raw = state.get("doc_type_hint")
    hint: DocTypeHint | None = None
    if hint_raw is not None:
        hint = hint_raw if isinstance(hint_raw, DocTypeHint) else DocTypeHint(hint_raw)

    logger.info("n1_document_intelligence_start", file_path=file_path, hint=hint)
    structure = await parse_document(file_path, hint=hint)
    logger.info(
        "n1_document_intelligence_done",
        pages=structure.page_count,
        route=structure.parser_route,
        chars=len(structure.full_text or ""),
    )

    return {
        "document_structure": dump_model(structure),
        "current_stage": "document_intelligence",
        "progress_pct": 10.0,
        "error": None,
    }
