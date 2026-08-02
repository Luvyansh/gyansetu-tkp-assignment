"""Stage 4 — Teaching Planner."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import dump_model, dumps_compact
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.lesson import TeachingPlan

logger = get_logger(__name__)

STAGE = "teaching_planner"


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n4_teaching_planner.md")

    user_parts = [
        "Classification:",
        dumps_compact(state.get("classification")),
        "",
        "Extracted knowledge:",
        dumps_compact(state.get("knowledge")),
    ]
    feedback = (state.get("validation_feedback") or "").strip()
    if feedback:
        user_parts.extend(
            [
                "",
                "Validation feedback from a previous attempt — revise the plan to address:",
                feedback,
            ]
        )
    retry_targets = state.get("retry_targets") or []
    if retry_targets:
        user_parts.extend(["", f"Retry targets: {', '.join(retry_targets)}"])

    user_prompt = "\n".join(user_parts)

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=TeachingPlan,
            temperature=0.3,
            session=session,
            input_payload={
                "classification": state.get("classification"),
                "knowledge_preview": dumps_compact(state.get("knowledge"))[:3000],
                "validation_feedback": feedback,
            },
        )

    plan = TeachingPlan.model_validate(resp.content)
    if plan.total_periods != len(plan.periods):
        plan.total_periods = len(plan.periods)

    logger.info(
        "n4_teaching_planner_done",
        total_periods=plan.total_periods,
        model=resp.model,
        had_feedback=bool(feedback),
    )

    return {
        "teaching_plan": dump_model(plan),
        "current_stage": STAGE,
        "progress_pct": 45.0,
        "error": None,
    }
