"""Parser router — user hint + heuristics → cheapest sufficient parser (FAQ Q7)."""

from __future__ import annotations

from pathlib import Path

from backend.app.llm.router import LLMRouter, get_llm_router
from backend.app.logging_config import get_logger
from backend.app.parsing.docx_parser import extract_docx
from backend.app.parsing.multimodal_fallback import enrich_with_multimodal
from backend.app.parsing.pdf_tables import extract_tables
from backend.app.parsing.pdf_text import extract_pdf_text, pdf_heuristics
from backend.app.parsing.pptx_parser import extract_pptx
from backend.app.schemas.document import DocTypeHint, DocumentStructure

logger = get_logger(__name__)

MULTIMODAL_HINTS = {
    DocTypeHint.TEXT_WITH_DIAGRAMS,
    DocTypeHint.TEXT_WITH_EQUATIONS,
    DocTypeHint.SCANNED,
    DocTypeHint.UNSURE,
}


def _ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


async def parse_document(
    path: Path | str,
    hint: DocTypeHint | None = None,
    router: LLMRouter | None = None,
) -> DocumentStructure:
    path = Path(path)
    extension = _ext(path)
    hint = hint or DocTypeHint.UNSURE

    if extension in {"docx"}:
        return extract_docx(path)
    if extension in {"pptx"}:
        return extract_pptx(path)
    if extension not in {"pdf"}:
        raise ValueError(f"Unsupported file type: .{extension}")

    heuristics = pdf_heuristics(path)
    effective = _resolve_route(hint, heuristics)
    logger.info(
        "parser_route_selected",
        hint=hint.value,
        route=effective,
        heuristics=heuristics,
    )

    structure = extract_pdf_text(path)
    structure.metadata.update(heuristics)

    if effective in {"tables", "multimodal"}:
        structure.tables = extract_tables(path)
        structure.parser_route = "pymupdf+pdfplumber"

    if effective == "multimodal":
        llm = router or get_llm_router()
        # Prefer pages with images or sparse text
        page_count = int(heuristics.get("page_count", 1))
        indices = list(range(min(page_count, 5)))
        enrichment = await enrich_with_multimodal(path, llm, page_indices=indices)
        if enrichment.figures:
            structure.figures.extend(enrichment.figures)
        if enrichment.equations:
            structure.equations.extend(enrichment.equations)
        if enrichment.extra_text:
            structure.full_text = f"{structure.full_text}\n\n{enrichment.extra_text}"
        structure.parser_route = "pymupdf+gemini_multimodal"
        structure.metadata["page_summary"] = enrichment.page_summary

    return structure


def _resolve_route(hint: DocTypeHint, heuristics: dict[str, int | float]) -> str:
    """Return 'text' | 'tables' | 'multimodal'."""
    image_count = int(heuristics.get("image_count", 0))
    chars_per_page = float(heuristics.get("chars_per_page", 0))

    if hint == DocTypeHint.MOSTLY_TEXT:
        return "text"
    if hint == DocTypeHint.TEXT_WITH_TABLES:
        return "tables"
    if hint in MULTIMODAL_HINTS:
        # Still use multimodal for unsure/scanned/diagrams/equations
        if hint == DocTypeHint.UNSURE:
            if image_count >= 2 or chars_per_page < 200:
                return "multimodal"
            if image_count == 0 and chars_per_page > 500:
                return "text"
            return "tables" if chars_per_page > 300 else "multimodal"
        return "multimodal"

    # Heuristic fallback if hint somehow missing
    if image_count >= 2 or chars_per_page < 200:
        return "multimodal"
    return "text"
