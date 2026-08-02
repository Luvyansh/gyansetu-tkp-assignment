"""Gemini multimodal fallback for diagrams/equations/scanned pages."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.llm.router import LLMRouter
from backend.app.parsing.pdf_text import render_page_png
from backend.app.schemas.document import EquationInfo, FigureInfo


class MultimodalPageResult(BaseModel):
    page_summary: str = ""
    figures: list[FigureInfo] = Field(default_factory=list)
    equations: list[EquationInfo] = Field(default_factory=list)
    extra_text: str = ""


_SYSTEM = """You analyze educational document page images.
Extract readable text that OCR might miss, describe figures/diagrams,
and transcribe equations as LaTeX or plain math text.
Only describe what is visible — do not invent curriculum content.
Return structured JSON."""


async def enrich_with_multimodal(
    path: Path | str,
    router: LLMRouter,
    page_indices: list[int] | None = None,
    max_pages: int = 5,
) -> MultimodalPageResult:
    path = Path(path)
    import fitz

    doc = fitz.open(path)
    indices = page_indices or list(range(min(len(doc), max_pages)))
    doc.close()

    images = [render_page_png(path, i) for i in indices]
    if not images:
        return MultimodalPageResult()

    response = await router.multimodal(
        stage_name="multimodal_fallback",
        system_prompt=_SYSTEM,
        user_prompt=(
            f"Analyze {len(images)} page image(s). Extract text gaps, "
            "figure descriptions, and equations."
        ),
        image_bytes_list=images,
        response_model=MultimodalPageResult,
        temperature=0.2,
    )
    return MultimodalPageResult.model_validate(response.content)
