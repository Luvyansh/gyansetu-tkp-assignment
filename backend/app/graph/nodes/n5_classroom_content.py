"""Stage 5 — Classroom Content Generation (per-period, parallel)."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import coerce_model, dump_model, dumps_compact, truncate
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.lesson import ClassroomContentBundle, PeriodContent, TeachingPlan

logger = get_logger(__name__)

STAGE = "classroom_content"
GROUNDING_CHUNK_LIMIT = 12


async def _generate_period(
    *,
    period: dict[str, Any],
    classification: Any,
    knowledge: Any,
    grounding: str,
    system_prompt: str,
) -> PeriodContent:
    router = get_llm_router()
    user_prompt = (
        f"Classification:\n{dumps_compact(classification)}\n\n"
        f"Extracted knowledge:\n{dumps_compact(knowledge)}\n\n"
        f"Period plan:\n{dumps_compact(period)}\n\n"
        f"Grounding chunks from source:\n{grounding}\n\n"
        f"Generate classroom content for period_number={period.get('period_number')}."
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=PeriodContent,
            temperature=0.35,
            session=session,
            input_payload={
                "period_number": period.get("period_number"),
                "period_title": period.get("title"),
                "concepts": period.get("concepts_covered"),
            },
        )

    content = PeriodContent.model_validate(resp.content)
    content.period_number = int(period.get("period_number") or content.period_number)
    content.grounding_score = None
    logger.info(
        "n5_period_content_done",
        period_number=content.period_number,
        grounding_score=content.grounding_score,
        model=resp.model,
    )
    return content


async def run(state: dict[str, Any]) -> dict[str, Any]:
    plan = coerce_model(TeachingPlan, state["teaching_plan"])
    system_prompt = load_prompt("n5_classroom_content.md")

    chunk_texts = state.get("knowledge_chunk_texts") or []
    grounding = truncate("\n\n---\n\n".join(chunk_texts[:GROUNDING_CHUNK_LIMIT]), 8000)

    tasks = [
        _generate_period(
            period=dump_model(p) if hasattr(p, "model_dump") else dict(p),
            classification=state.get("classification"),
            knowledge=state.get("knowledge"),
            grounding=grounding,
            system_prompt=system_prompt,
        )
        for p in plan.periods
    ]

    if tasks:
        periods = list(await asyncio.gather(*tasks))
        periods.sort(key=lambda p: p.period_number)
    else:
        periods = []

    bundle = ClassroomContentBundle(periods=periods)
    logger.info("n5_classroom_content_done", periods=len(periods))

    return {
        "classroom_content": dump_model(bundle),
        "current_stage": STAGE,
        "progress_pct": 60.0,
        "error": None,
    }
