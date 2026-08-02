"""Stage 6 — Activity Generation."""

from __future__ import annotations

from typing import Any

from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import dump_model, dumps_compact, truncate
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.lesson import ActivityBundle

logger = get_logger(__name__)

STAGE = "activity_generation"


async def run(state: dict[str, Any]) -> dict[str, Any]:
    router = get_llm_router()
    system_prompt = load_prompt("n6_activity_generation.md")

    chunk_texts = state.get("knowledge_chunk_texts") or []
    grounding = truncate("\n\n---\n\n".join(chunk_texts[:10]), 6000)

    user_prompt = (
        f"Classification:\n{dumps_compact(state.get('classification'))}\n\n"
        f"Teaching plan:\n{dumps_compact(state.get('teaching_plan'))}\n\n"
        f"Extracted knowledge:\n{dumps_compact(state.get('knowledge'))}\n\n"
        f"Grounding chunks:\n{grounding}\n\n"
        "Generate a diverse activity bundle for this unit."
    )

    async with AsyncSessionLocal() as session:
        resp = await router.generate(
            stage_name=STAGE,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=ActivityBundle,
            temperature=0.35,
            session=session,
            input_payload={
                "classification": state.get("classification"),
                "plan_periods": (state.get("teaching_plan") or {}).get("total_periods")
                if isinstance(state.get("teaching_plan"), dict)
                else None,
            },
        )

    bundle = ActivityBundle.model_validate(resp.content)
    logger.info("n6_activity_generation_done", activities=len(bundle.activities), model=resp.model)

    return {
        "activities": dump_model(bundle),
        "current_stage": STAGE,
        "progress_pct": 70.0,
        "error": None,
    }
