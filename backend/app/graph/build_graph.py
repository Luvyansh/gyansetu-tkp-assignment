"""Wire LangGraph nodes into the TKP pipeline."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
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

NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _logged_node(stage: str, fn: NodeFn) -> NodeFn:
    """Wrap a node so every stage leaves enter/exit (or error) breadcrumbs in logs."""

    async def _wrap(state: dict[str, Any]) -> dict[str, Any]:
        job_id = str(state.get("job_id") or "")
        logger.info("pipeline_stage_enter", stage=stage, job_id=job_id)
        started = time.perf_counter()
        try:
            result = await fn(state)
        except Exception:
            logger.exception(
                "pipeline_stage_error",
                stage=stage,
                job_id=job_id,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        logger.info(
            "pipeline_stage_exit",
            stage=stage,
            job_id=job_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            next_stage=result.get("current_stage") if isinstance(result, dict) else None,
            error=result.get("error") if isinstance(result, dict) else None,
        )
        return result

    return _wrap


async def parallel_generation(state: dict[str, Any]) -> dict[str, Any]:
    """Run stages 5–8 concurrently and merge partial state updates."""
    job_id = str(state.get("job_id") or "")
    logger.info(
        "pipeline_stage_enter",
        stage="parallel_generation",
        job_id=job_id,
        children=[
            "classroom_content",
            "activity_generation",
            "assessment_generation",
            "gap_analysis",
        ],
    )
    started = time.perf_counter()
    results = await asyncio.gather(
        _logged_node("classroom_content", n5_classroom_content.run)(state),
        _logged_node("activity_generation", n6_activity_generation.run)(state),
        _logged_node("assessment_generation", n7_assessment_generation.run)(state),
        _logged_node("gap_analysis", n8_gap_analysis.run)(state),
    )
    merged: dict[str, Any] = {}
    for partial in results:
        merged.update(partial)
    merged["current_stage"] = "gap_analysis"
    merged["progress_pct"] = 80.0
    merged["error"] = None
    logger.info(
        "pipeline_stage_exit",
        stage="parallel_generation",
        job_id=job_id,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        next_stage="gap_analysis",
    )
    return merged


_PIPELINE_STAGES = frozenset(
    {
        "document_intelligence",
        "educational_classification",
        "knowledge_extraction",
        "teaching_planner",
        "classroom_content",
        "activity_generation",
        "assessment_generation",
        "gap_analysis",
        "validation",
        "publish",
    }
)


def _terminal_failure_stage(state: dict[str, Any]) -> str:
    """Resolve the real last-active stage for a validation-exhaust failure.

    Never return the sentinel ``failed`` / ``error`` — the progress stepper cannot
    map those and historically coerced them onto Document Intelligence (index 0).
    """
    prior = str(state.get("current_stage") or "").strip().lower().replace(" ", "_")
    if prior in _PIPELINE_STAGES:
        return prior
    targets = state.get("retry_targets") or []
    if targets:
        target = str(targets[0]).strip().lower().replace(" ", "_")
        if target in _PIPELINE_STAGES:
            return target
    return "validation"


async def fail_job(state: dict[str, Any]) -> dict[str, Any]:
    feedback = (state.get("validation_feedback") or "").strip()
    message = feedback or "Validation failed after maximum retry attempts"
    stage = _terminal_failure_stage(state)
    logger.error(
        "tkp_pipeline_failed_validation",
        job_id=str(state.get("job_id")),
        retry_count=state.get("validation_retry_count"),
        stage=stage,
        message=message[:500],
    )
    return {
        "error": message,
        "current_stage": stage,
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

    graph.add_node(
        "n1_document_intelligence",
        cast(Any, _logged_node("document_intelligence", n1_document_intelligence.run)),
    )
    graph.add_node(
        "n2_educational_classification",
        cast(Any, _logged_node("educational_classification", n2_educational_classification.run)),
    )
    graph.add_node(
        "n3_knowledge_extraction",
        cast(Any, _logged_node("knowledge_extraction", n3_knowledge_extraction.run)),
    )
    graph.add_node(
        "n4_teaching_planner",
        cast(Any, _logged_node("teaching_planner", n4_teaching_planner.run)),
    )
    graph.add_node("parallel_generation", cast(Any, parallel_generation))
    graph.add_node("n9_validation", cast(Any, _logged_node("validation", n9_validation.run)))
    graph.add_node("n10_publish", cast(Any, _logged_node("publish", n10_publish.run)))
    graph.add_node("fail_job", cast(Any, _logged_node("fail_job", fail_job)))

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


async def run_pipeline(
    initial_state: dict[str, Any],
    *,
    on_stage: Callable[[str, float], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Execute the compiled TKP graph from an initial state dict.

    When ``on_stage`` is provided it is awaited after each node as
    ``await on_stage(current_stage: str, progress_pct: float)`` so the job
    row / SSE stream can track the real stage (e.g. knowledge_extraction)
    instead of freezing on the pre-run ``document_intelligence`` placeholder.
    """
    app = build_tkp_graph()
    logger.info(
        "tkp_pipeline_start",
        job_id=str(initial_state.get("job_id")),
        document_id=str(initial_state.get("document_id")),
    )
    final_state: dict[str, Any] | None = None
    async for values in app.astream(initial_state, stream_mode="values"):
        final_state = cast(dict[str, Any], values)
        if on_stage is not None:
            stage = final_state.get("current_stage")
            if stage is not None:
                await on_stage(str(stage), float(final_state.get("progress_pct") or 0.0))
    if final_state is None:
        final_state = dict(initial_state)
    logger.info(
        "tkp_pipeline_end",
        job_id=str(initial_state.get("job_id")),
        stage=final_state.get("current_stage"),
        progress=final_state.get("progress_pct"),
        error=final_state.get("error"),
    )
    return final_state
