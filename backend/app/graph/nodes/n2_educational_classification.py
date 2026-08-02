"""Stage 2 — Educational Classification."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import dump_model, full_document_text, truncate
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.classification import EducationalClassification

logger = get_logger(__name__)

STAGE = "educational_classification"


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n2_classification.md")
    text = truncate(full_document_text(state), 14000)
    title = ""
    structure = state.get("document_structure") or {}
    if isinstance(structure, dict):
        title = structure.get("title") or ""
    else:
        title = getattr(structure, "title", "") or ""

    user_prompt = (
        f"Source filename: {state.get('source_filename') or 'unknown'}\n"
        f"Document title: {title or 'unknown'}\n"
        f"Doc type hint: {state.get('doc_type_hint') or 'unsure'}\n\n"
        f"Document text:\n{text}"
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=EducationalClassification,
            temperature=0.2,
            session=session,
            input_payload={
                "filename": state.get("source_filename"),
                "title": title,
                "text_preview": text[:2000],
            },
        )

    classification = EducationalClassification.model_validate(resp.content)
    logger.info(
        "n2_classification_done",
        subject=classification.subject,
        grade=classification.grade,
        topic=classification.topic,
        model=resp.model,
        cached=resp.cached,
    )

    return {
        "classification": dump_model(classification),
        "current_stage": STAGE,
        "progress_pct": 20.0,
        "error": None,
    }
