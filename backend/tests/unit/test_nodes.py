"""Graph node unit tests with mocked LLM + DB session."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.graph.nodes import (
    n2_educational_classification,
    n3_knowledge_extraction,
    n4_teaching_planner,
    n5_classroom_content,
    n6_activity_generation,
    n7_assessment_generation,
    n8_gap_analysis,
    n9_validation,
)
from backend.app.graph.nodes.helpers import chunk_text, truncate
from backend.app.schemas.classification import EducationalClassification
from backend.tests.factories import (
    make_activities,
    make_assessments,
    make_classification,
    make_classroom_content,
    make_document_structure,
    make_gap_analysis,
    make_knowledge,
    make_teaching_plan,
)


def _base_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "job_id": uuid4(),
        "document_id": uuid4(),
        "source_filename": "stem_excerpt.pdf",
        "doc_type_hint": "mostly_text",
        "document_structure": make_document_structure().model_dump(mode="json"),
        "classification": make_classification().model_dump(mode="json"),
        "knowledge": make_knowledge().model_dump(mode="json"),
        "knowledge_chunk_texts": [make_document_structure().full_text],
        "teaching_plan": make_teaching_plan().model_dump(mode="json"),
        "classroom_content": None,
        "activities": None,
        "assessments": None,
        "gap_analysis": None,
        "validation": None,
        "validation_retry_count": 0,
        "max_validation_retries": 2,
        "retry_targets": [],
        "validation_feedback": "",
    }
    state.update(overrides)
    return state


@pytest.fixture
def session_patches(mock_session_factory: MagicMock):
    modules = [
        "backend.app.graph.nodes.n2_educational_classification.AsyncSessionLocal",
        "backend.app.graph.nodes.n3_knowledge_extraction.AsyncSessionLocal",
        "backend.app.graph.nodes.n4_teaching_planner.AsyncSessionLocal",
        "backend.app.graph.nodes.n5_classroom_content.AsyncSessionLocal",
        "backend.app.graph.nodes.n6_activity_generation.AsyncSessionLocal",
        "backend.app.graph.nodes.n7_assessment_generation.AsyncSessionLocal",
        "backend.app.graph.nodes.n8_gap_analysis.AsyncSessionLocal",
    ]
    stack = [patch(m, mock_session_factory) for m in modules]
    for p in stack:
        p.start()
    yield mock_session_factory
    for p in stack:
        p.stop()


@pytest.mark.asyncio
async def test_n2_classification(patch_llm_router: AsyncMock, session_patches: MagicMock) -> None:
    out = await n2_educational_classification.run(_base_state())
    cls = EducationalClassification.model_validate(out["classification"])
    assert cls.subject == "Physics"
    assert out["current_stage"] == "educational_classification"
    assert out["progress_pct"] == 20.0


@pytest.mark.asyncio
async def test_n3_knowledge_extraction(
    patch_llm_router: AsyncMock, session_patches: MagicMock
) -> None:
    with patch(
        "backend.app.graph.nodes.n3_knowledge_extraction.insert_chunks",
        new_callable=AsyncMock,
    ) as insert:
        out = await n3_knowledge_extraction.run(_base_state())
    assert "concepts" in out["knowledge"]
    assert isinstance(out["knowledge_chunk_texts"], list)
    assert out["progress_pct"] == 35.0
    insert.assert_awaited()


@pytest.mark.asyncio
async def test_n4_teaching_planner(patch_llm_router: AsyncMock, session_patches: MagicMock) -> None:
    out = await n4_teaching_planner.run(_base_state())
    assert out["teaching_plan"]["total_periods"] == 2
    assert len(out["teaching_plan"]["periods"]) == 2


@pytest.mark.asyncio
async def test_n5_classroom_content(
    patch_llm_router: AsyncMock, session_patches: MagicMock
) -> None:
    out = await n5_classroom_content.run(_base_state())
    periods = out["classroom_content"]["periods"]
    assert len(periods) == 2
    assert {p["period_number"] for p in periods} == {1, 2}


@pytest.mark.asyncio
async def test_n6_activity_generation(
    patch_llm_router: AsyncMock, session_patches: MagicMock
) -> None:
    out = await n6_activity_generation.run(_base_state())
    assert len(out["activities"]["activities"]) >= 1


@pytest.mark.asyncio
async def test_n7_assessment_generation(
    patch_llm_router: AsyncMock, session_patches: MagicMock
) -> None:
    out = await n7_assessment_generation.run(_base_state())
    assert out["assessments"]["total_marks"] > 0
    assert out["assessments"]["formative"]


@pytest.mark.asyncio
async def test_n8_gap_analysis(patch_llm_router: AsyncMock, session_patches: MagicMock) -> None:
    out = await n8_gap_analysis.run(_base_state())
    assert out["gap_analysis"]["gaps"]


@pytest.mark.asyncio
async def test_n9_validation_pass(patch_llm_router: AsyncMock) -> None:
    async def high_sim(texts: list[str], **_kwargs: object) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    patch_llm_router.embed = AsyncMock(side_effect=high_sim)
    state = _base_state(
        classroom_content=make_classroom_content().model_dump(mode="json"),
        activities=make_activities().model_dump(mode="json"),
        assessments=make_assessments().model_dump(mode="json"),
        gap_analysis=make_gap_analysis().model_dump(mode="json"),
    )
    out = await n9_validation.run(state)
    assert out["validation"]["overall_passed"] is True
    assert out["retry_targets"] == []


@pytest.mark.asyncio
async def test_n9_validation_fail_increments_retry(patch_llm_router: AsyncMock) -> None:
    state = _base_state(
        classroom_content=None,
        activities=None,
        assessments=None,
        gap_analysis=None,
    )
    out = await n9_validation.run(state)
    assert out["validation"]["overall_passed"] is False
    assert out["validation_retry_count"] == 1
    assert out["retry_targets"]


@pytest.mark.asyncio
async def test_malformed_llm_response_raises(
    session_patches: MagicMock, mock_llm_router: AsyncMock
) -> None:
    mock_llm_router.generate = AsyncMock(
        return_value=MagicMock(
            content={"not": "a classification"},
            model="mock",
            cached=False,
        )
    )
    with (
        patch(
            "backend.app.graph.nodes.n2_educational_classification.get_llm_router",
            return_value=mock_llm_router,
        ),
        pytest.raises(ValidationError),
    ):
        await n2_educational_classification.run(_base_state())


def test_helpers_chunk_and_truncate() -> None:
    assert truncate("abc", 10) == "abc"
    assert truncate("abcdefghij", 5).startswith("abcde")
    chunks = chunk_text("a" * 1200, size=500, overlap=50)
    assert len(chunks) >= 2
    assert chunk_text("") == []


@pytest.mark.asyncio
async def test_n1_requires_file_path() -> None:
    from backend.app.graph.nodes import n1_document_intelligence

    with pytest.raises(ValueError, match="file_path"):
        await n1_document_intelligence.run({})


@pytest.mark.asyncio
async def test_n1_with_mocked_parse(stem_pdf_path, document_structure) -> None:
    from backend.app.graph.nodes import n1_document_intelligence

    with patch(
        "backend.app.graph.nodes.n1_document_intelligence.parse_document",
        new_callable=AsyncMock,
        return_value=document_structure,
    ):
        out = await n1_document_intelligence.run(
            {"file_path": str(stem_pdf_path), "doc_type_hint": "mostly_text"}
        )
    assert out["document_structure"]["title"] == document_structure.title
    assert out["progress_pct"] == 10.0
