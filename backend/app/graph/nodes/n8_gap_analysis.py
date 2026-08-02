"""Stage 8 — Learning Gap Analysis."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import dump_model, dumps_compact
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.gap_analysis import GapAnalysis

logger = get_logger(__name__)

STAGE = "gap_analysis"


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n8_gap_analysis.md")

    user_prompt = (
        f"Classification:\n{dumps_compact(state.get('classification'))}\n\n"
        f"Extracted knowledge (primary input for gap analysis):\n"
        f"{dumps_compact(state.get('knowledge'))}\n\n"
        f"Teaching plan (for sequencing context):\n"
        f"{dumps_compact(state.get('teaching_plan'))}\n\n"
        "Identify learning gaps, diagnostics, and remedial actions."
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=GapAnalysis,
            temperature=0.3,
            session=session,
            input_payload={
                "knowledge_preview": dumps_compact(state.get("knowledge"))[:3000],
            },
        )

    analysis = GapAnalysis.model_validate(resp.content)
    logger.info("n8_gap_analysis_done", gaps=len(analysis.gaps), model=resp.model)

    return {
        "gap_analysis": dump_model(analysis),
        "current_stage": STAGE,
        "progress_pct": 80.0,
        "error": None,
    }
