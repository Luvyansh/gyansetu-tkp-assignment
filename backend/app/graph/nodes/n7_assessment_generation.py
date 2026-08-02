"""Stage 7 — Assessment Generation."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import dump_model, dumps_compact, truncate
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.assessment import AssessmentBundle

logger = get_logger(__name__)

STAGE = "assessment_generation"


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n7_assessment_generation.md")

    chunk_texts = state.get("knowledge_chunk_texts") or []
    grounding = truncate("\n\n---\n\n".join(chunk_texts[:10]), 6000)

    user_prompt = (
        f"Classification:\n{dumps_compact(state.get('classification'))}\n\n"
        f"Teaching plan:\n{dumps_compact(state.get('teaching_plan'))}\n\n"
        f"Extracted knowledge:\n{dumps_compact(state.get('knowledge'))}\n\n"
        f"Grounding chunks:\n{grounding}\n\n"
        "Generate formative and summative assessments grounded in the source."
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=AssessmentBundle,
            temperature=0.25,
            session=session,
            input_payload={
                "classification": state.get("classification"),
                "knowledge_preview": dumps_compact(state.get("knowledge"))[:2500],
            },
        )

    bundle = AssessmentBundle.model_validate(resp.content)
    if not bundle.total_marks:
        bundle.total_marks = float(
            sum(q.marks for q in bundle.summative) + sum(q.marks for q in bundle.formative)
        )

    logger.info(
        "n7_assessment_generation_done",
        formative=len(bundle.formative),
        summative=len(bundle.summative),
        total_marks=bundle.total_marks,
        model=resp.model,
    )

    return {
        "assessments": dump_model(bundle),
        "current_stage": STAGE,
        "progress_pct": 75.0,
        "error": None,
    }
