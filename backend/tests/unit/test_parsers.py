"""Parser unit tests — PDF extract + router heuristics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.parsing.pdf_text import extract_pdf_text, pdf_heuristics
from backend.app.parsing.router import _resolve_route, parse_document
from backend.app.schemas.document import DocTypeHint


def test_extract_pdf_text_stem(stem_pdf_path: Path) -> None:
    structure = extract_pdf_text(stem_pdf_path)
    assert structure.page_count >= 1
    assert "Newton" in structure.full_text or "Newton" in (structure.title or "")
    assert structure.parser_route == "pymupdf_text"
    assert isinstance(structure.sections, list)


def test_pdf_heuristics_stem(stem_pdf_path: Path) -> None:
    h = pdf_heuristics(stem_pdf_path)
    assert h["page_count"] >= 1
    assert h["text_chars"] > 50
    assert h["chars_per_page"] > 0


@pytest.mark.parametrize(
    ("hint", "heuristics", "expected"),
    [
        (DocTypeHint.MOSTLY_TEXT, {"image_count": 5, "chars_per_page": 50}, "text"),
        (DocTypeHint.TEXT_WITH_TABLES, {"image_count": 0, "chars_per_page": 800}, "tables"),
        (DocTypeHint.TEXT_WITH_DIAGRAMS, {"image_count": 0, "chars_per_page": 800}, "multimodal"),
        (DocTypeHint.SCANNED, {"image_count": 0, "chars_per_page": 800}, "multimodal"),
        (DocTypeHint.UNSURE, {"image_count": 3, "chars_per_page": 100}, "multimodal"),
        (DocTypeHint.UNSURE, {"image_count": 0, "chars_per_page": 600}, "text"),
        (DocTypeHint.UNSURE, {"image_count": 1, "chars_per_page": 350}, "tables"),
    ],
)
def test_resolve_route(
    hint: DocTypeHint, heuristics: dict[str, int | float], expected: str
) -> None:
    assert _resolve_route(hint, heuristics) == expected


@pytest.mark.asyncio
async def test_parse_document_pdf_text_route(stem_pdf_path: Path) -> None:
    structure = await parse_document(stem_pdf_path, hint=DocTypeHint.MOSTLY_TEXT)
    assert structure.page_count >= 1
    assert "force" in structure.full_text.lower() or "newton" in structure.full_text.lower()


@pytest.mark.asyncio
async def test_parse_document_unsupported(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        await parse_document(bad)


@pytest.mark.asyncio
async def test_parse_docx_route(tmp_path: Path) -> None:
    # Minimal fake: patch extract_docx rather than crafting a real docx
    from backend.app.schemas.document import DocumentStructure

    fake = DocumentStructure(title="Docx", full_text="from docx", parser_route="python-docx")
    docx = tmp_path / "chapter.docx"
    docx.write_bytes(b"PK\x03\x04fake")
    with patch("backend.app.parsing.router.extract_docx", return_value=fake):
        result = await parse_document(docx)
    assert result.parser_route == "python-docx"


@pytest.mark.asyncio
async def test_parse_pptx_route(tmp_path: Path) -> None:
    from backend.app.schemas.document import DocumentStructure

    fake = DocumentStructure(title="Pptx", full_text="from pptx", parser_route="python-pptx")
    pptx = tmp_path / "slides.pptx"
    pptx.write_bytes(b"PK\x03\x04fake")
    with patch("backend.app.parsing.router.extract_pptx", return_value=fake):
        result = await parse_document(pptx)
    assert result.full_text == "from pptx"


@pytest.mark.asyncio
async def test_parse_multimodal_enrichment(stem_pdf_path: Path) -> None:
    from backend.app.schemas.document import EquationInfo, FigureInfo

    enrichment = AsyncMock()
    enrichment.figures = [FigureInfo(page=1, description="diagram")]
    enrichment.equations = [EquationInfo(latex_or_text="F=ma", page=1)]
    enrichment.extra_text = "Extra multimodal text"
    enrichment.page_summary = "summary"

    router = AsyncMock()
    with patch(
        "backend.app.parsing.router.enrich_with_multimodal",
        new_callable=AsyncMock,
        return_value=enrichment,
    ):
        structure = await parse_document(
            stem_pdf_path, hint=DocTypeHint.TEXT_WITH_EQUATIONS, router=router
        )
    assert structure.parser_route == "pymupdf+gemini_multimodal"
    assert any(e.latex_or_text == "F=ma" for e in structure.equations)
