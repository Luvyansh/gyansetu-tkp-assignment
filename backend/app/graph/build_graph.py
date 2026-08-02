"""Wire LangGraph nodes into the TKP pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph

from backend.app.graph.nodes import (
    n1_document_intelligence,
    n2_educational_classification,
    n3_knowledge_extraction,
    n4_teaching_planner,
    n5_classroom_content,
    n6_activity_generation,
    n7_assessment_generation,
    n8_gap_analysis,
    n9_validation,
    n10_publish,
)
from backend.app.graph.state import TKPGraphState
from backend.app.logging_config import get_logger

logger = get_logger(__name__)

RouteDecision = Literal["publish", "retry", "fail"]


async def parallel_generation(state: dict[str, Any]) -> dict[str, Any]:
    """Run stages 5–8 concurrently and merge partial state updates."""
    results = await asyncio.gather(
        n5_classroom_content.run(state),
        n6_activity_generation.run(state),
        n7_assessment_generation.run(state),
        n8_gap_analysis.run(state),
    )
    merged: dict[str, Any] = {}
    for partial in results:
        merged.update(partial)
    merged["current_stage"] = "gap_analysis"
    merged["progress_pct"] = 80.0
    merged["error"] = None
    return merged


async def fail_job(state: dict[str, Any]) -> dict[str, Any]:
    feedback = (state.get("validation_feedback") or "").strip()
    message = feedback or "Validation failed after maximum retry attempts"
    logger.error(
        "tkp_pipeline_failed_validation",
        job_id=str(state.get("job_id")),
        retry_count=state.get("validation_retry_count"),
        message=message[:500],
    )
    return {
        "error": message,
        "current_stage": "failed",
        "progress_pct": float(state.get("progress_pct") or 90.0),
    }


def _overall_passed(state: dict[str, Any]) -> bool:
    validation = state.get("validation")
    if validation is None:
        return False
    if isinstance(validation, dict):
        return bool(validation.get("overall_passed"))
    return bool(getattr(validation, "overall_passed", False))


def route_after_validation(state: dict[str, Any]) -> RouteDecision:
    if _overall_passed(state):
        return "publish"

    retry_count = int(state.get("validation_retry_count") or 0)
    max_retries = int(state.get("max_validation_retries") or 2)
    # n9 increments retry_count on each failure; retry while under the cap
    if retry_count < max_retries:
        targets = state.get("retry_targets") or []
        logger.info(
            "tkp_validation_retry",
            retry_count=retry_count,
            max_retries=max_retries,
            targets=targets,
        )
        return "retry"

    return "fail"


def build_tkp_graph() -> Any:
    """Compile the Teacher Knowledge Package LangGraph."""
    graph = StateGraph(TKPGraphState)

    graph.add_node("n1_document_intelligence", n1_document_intelligence.run)  # type: ignore[type-var]
    graph.add_node("n2_educational_classification", n2_educational_classification.run)  # type: ignore[type-var]
    graph.add_node("n3_knowledge_extraction", n3_knowledge_extraction.run)  # type: ignore[type-var]
    graph.add_node("n4_teaching_planner", n4_teaching_planner.run)  # type: ignore[type-var]
    graph.add_node("parallel_generation", parallel_generation)  # type: ignore[type-var]
    graph.add_node("n9_validation", n9_validation.run)  # type: ignore[type-var]
    graph.add_node("n10_publish", n10_publish.run)  # type: ignore[type-var]
    graph.add_node("fail_job", fail_job)  # type: ignore[type-var]

    graph.add_edge(START, "n1_document_intelligence")
    graph.add_edge("n1_document_intelligence", "n2_educational_classification")
    graph.add_edge("n2_educational_classification", "n3_knowledge_extraction")
    graph.add_edge("n3_knowledge_extraction", "n4_teaching_planner")
    graph.add_edge("n4_teaching_planner", "parallel_generation")
    graph.add_edge("parallel_generation", "n9_validation")
    graph.add_conditional_edges(
        "n9_validation",
        route_after_validation,
        {
            "publish": "n10_publish",
            "retry": "n4_teaching_planner",
            "fail": "fail_job",
        },
    )
    graph.add_edge("n10_publish", END)
    graph.add_edge("fail_job", END)

    return graph.compile()


async def run_pipeline(initial_state: dict[str, Any]) -> dict[str, Any]:
    """Execute the compiled TKP graph from an initial state dict."""
    app = build_tkp_graph()
    logger.info(
        "tkp_pipeline_start",
        job_id=str(initial_state.get("job_id")),
        document_id=str(initial_state.get("document_id")),
    )
    final_state = await app.ainvoke(initial_state)
    logger.info(
        "tkp_pipeline_end",
        job_id=str(initial_state.get("job_id")),
        stage=final_state.get("current_stage"),
        progress=final_state.get("progress_pct"),
        error=final_state.get("error"),
    )
    return cast(dict[str, Any], final_state)
