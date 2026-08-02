"""Integration: run_pipeline with fully mocked LLM / DB / parse."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.graph.build_graph import route_after_validation, run_pipeline
from backend.tests.factories import (
    make_document_structure,
    make_validation_report,
)


def _initial_state(file_path: str) -> dict[str, Any]:
    return {
        "job_id": uuid4(),
        "document_id": uuid4(),
        "source_filename": "stem_excerpt.pdf",
        "doc_type_hint": "mostly_text",
        "file_path": file_path,
        "document_structure": None,
        "classification": None,
        "knowledge": None,
        "knowledge_chunk_texts": [],
        "teaching_plan": None,
        "classroom_content": None,
        "activities": None,
        "assessments": None,
        "gap_analysis": None,
        "validation": None,
        "validation_retry_count": 0,
        "max_validation_retries": 2,
        "retry_targets": [],
        "validation_feedback": "",
        "tkp": None,
        "pdf_artifacts": {},
        "current_stage": "pending",
        "progress_pct": 0.0,
        "error": None,
        "stage_meta": {},
        "grounding_scores": {},
    }


@pytest.mark.asyncio
async def test_run_pipeline_mocked_to_publish(
    stem_pdf_path, patch_llm_router, mock_session_factory, sample_tkp
) -> None:
    """Full graph with mocked parse, LLM, DB, groundedness, and PDF render."""

    structure = make_document_structure()

    async def high_sim(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    patch_llm_router.embed = AsyncMock(side_effect=high_sim)

    node_session_targets = [
        "backend.app.graph.nodes.n2_educational_classification.AsyncSessionLocal",
        "backend.app.graph.nodes.n3_knowledge_extraction.AsyncSessionLocal",
        "backend.app.graph.nodes.n4_teaching_planner.AsyncSessionLocal",
        "backend.app.graph.nodes.n5_classroom_content.AsyncSessionLocal",
        "backend.app.graph.nodes.n6_activity_generation.AsyncSessionLocal",
        "backend.app.graph.nodes.n7_assessment_generation.AsyncSessionLocal",
        "backend.app.graph.nodes.n8_gap_analysis.AsyncSessionLocal",
        "backend.app.graph.nodes.n10_publish.AsyncSessionLocal",
    ]

    patches = [patch(t, mock_session_factory) for t in node_session_targets]
    for p in patches:
        p.start()

    try:
        with (
            patch(
                "backend.app.graph.nodes.n1_document_intelligence.parse_document",
                new_callable=AsyncMock,
                return_value=structure,
            ),
            patch(
                "backend.app.graph.nodes.n3_knowledge_extraction.insert_chunks",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.app.graph.nodes.n10_publish.render_all_pdfs",
                new_callable=AsyncMock,
                return_value={
                    "lesson-plan": "/tmp/lp.pdf",
                    "teacher-guide": "/tmp/tg.pdf",
                    "assessment-book": "/tmp/ab.pdf",
                },
            ),
        ):
            final = await run_pipeline(_initial_state(str(stem_pdf_path)))
    finally:
        for p in patches:
            p.stop()

    assert final.get("error") in (None, "")
    assert final.get("current_stage") == "publish"
    assert final.get("tkp") is not None
    assert final["tkp"]["classification"]["subject"] == "Physics"
    assert final.get("progress_pct") == 100.0


def test_route_after_validation_publish() -> None:
    state = {"validation": make_validation_report(passed=True).model_dump(mode="json")}
    assert route_after_validation(state) == "publish"


def test_route_after_validation_retry() -> None:
    state = {
        "validation": make_validation_report(passed=False).model_dump(mode="json"),
        "validation_retry_count": 1,
        "max_validation_retries": 2,
        "retry_targets": ["classroom_content"],
    }
    assert route_after_validation(state) == "retry"


def test_route_after_validation_fail() -> None:
    state = {
        "validation": make_validation_report(passed=False).model_dump(mode="json"),
        "validation_retry_count": 2,
        "max_validation_retries": 2,
    }
    assert route_after_validation(state) == "fail"
