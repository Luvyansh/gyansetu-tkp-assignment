"""DOCX parser."""

from __future__ import annotations

from pathlib import Path

from docx import Document

from backend.app.schemas.document import DocumentStructure, Section


def extract_docx(path: Path | str) -> DocumentStructure:
    doc = Document(str(path))
    sections: list[Section] = []
    current_heading = "Document"
    current_level = 1
    buffer: list[str] = []
    full: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if buffer:
            sections.append(
                Section(heading=current_heading, level=current_level, text="\n".join(buffer))
            )
            buffer = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "") if para.style else ""
        if style.startswith("Heading"):
            flush()
            try:
                current_level = int(style.replace("Heading", "").strip() or "1")
            except ValueError:
                current_level = 1
            current_heading = text
        else:
            buffer.append(text)
            full.append(text)
    flush()

    if not sections:
        sections.append(Section(heading="Document", level=1, text="\n".join(full)))

    return DocumentStructure(
        title=sections[0].heading,
        page_count=1,
        sections=sections,
        full_text="\n\n".join(full),
        parser_route="python_docx",
    )
