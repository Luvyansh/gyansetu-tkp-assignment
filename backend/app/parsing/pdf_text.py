"""PyMuPDF text + structure extraction."""

from __future__ import annotations

from pathlib import Path

import fitz

from backend.app.schemas.document import DocumentStructure, FigureInfo, Section


def extract_pdf_text(path: Path | str) -> DocumentStructure:
    doc = fitz.open(path)
    sections: list[Section] = []
    figures: list[FigureInfo] = []
    full_parts: list[str] = []
    current_heading = "Document"
    current_text: list[str] = []
    current_level = 1
    page_start = 1

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") == 1:  # image
                figures.append(FigureInfo(page=page_num, caption=None, description=None))
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                sizes = [float(s.get("size", 12)) for s in spans]
                avg_size = sum(sizes) / len(sizes)
                is_bold = any("bold" in str(s.get("font", "")).lower() for s in spans)
                if avg_size >= 14 or (is_bold and avg_size >= 12 and len(text) < 120):
                    if current_text:
                        sections.append(
                            Section(
                                heading=current_heading,
                                level=current_level,
                                text="\n".join(current_text),
                                page_start=page_start,
                                page_end=page_num,
                            )
                        )
                        current_text = []
                    current_heading = text
                    current_level = 1 if avg_size >= 16 else 2
                    page_start = page_num
                else:
                    current_text.append(text)
                    full_parts.append(text)

        # image count already via type==1; also count xref images
        for img in page.get_images(full=True):
            _ = img  # counted via blocks; keep loop for side-effect free enumeration

    if current_text or not sections:
        sections.append(
            Section(
                heading=current_heading,
                level=current_level,
                text="\n".join(current_text) if current_text else "\n".join(full_parts),
                page_start=page_start,
                page_end=len(doc),
            )
        )

    title = sections[0].heading if sections else None
    structure = DocumentStructure(
        title=title,
        page_count=len(doc),
        sections=sections,
        figures=figures,
        full_text="\n\n".join(full_parts) if full_parts else "\n\n".join(s.text for s in sections),
        parser_route="pymupdf_text",
        metadata={"image_count": len(figures)},
    )
    doc.close()
    return structure


def pdf_heuristics(path: Path | str) -> dict[str, int | float]:
    doc = fitz.open(path)
    image_count = 0
    text_chars = 0
    for page in doc:
        text_chars += len(page.get_text("text"))
        image_count += len(page.get_images(full=True))
    page_count = len(doc)
    doc.close()
    return {
        "page_count": page_count,
        "image_count": image_count,
        "text_chars": text_chars,
        "chars_per_page": text_chars / max(page_count, 1),
    }


def render_page_png(path: Path | str, page_index: int, zoom: float = 2.0) -> bytes:
    doc = fitz.open(path)
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    data = pix.tobytes("png")
    doc.close()
    return bytes(data)
