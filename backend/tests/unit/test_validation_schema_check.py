"""Schema check validation tests."""

from __future__ import annotations

import pytest

from backend.app.schemas.validation import CheckStatus
from backend.app.validation.schema_check import check_schema
from backend.tests.factories import (
    make_activities,
    make_assessments,
    make_classification,
    make_classroom_content,
    make_gap_analysis,
    make_knowledge,
    make_teaching_plan,
)


def _complete_state() -> dict:
    return {
        "classification": make_classification().model_dump(mode="json"),
        "knowledge": make_knowledge().model_dump(mode="json"),
        "teaching_plan": make_teaching_plan().model_dump(mode="json"),
        "classroom_content": make_classroom_content().model_dump(mode="json"),
        "activities": make_activities().model_dump(mode="json"),
        "assessments": make_assessments().model_dump(mode="json"),
        "gap_analysis": make_gap_analysis().model_dump(mode="json"),
    }


@pytest.mark.asyncio
async def test_schema_check_pass() -> None:
    result = await check_schema(_complete_state())
    assert result.status == CheckStatus.PASS
    assert result.score == 1.0
    assert result.retry_target is None


@pytest.mark.asyncio
async def test_schema_check_missing_field() -> None:
    state = _complete_state()
    del state["knowledge"]
    result = await check_schema(state)
    assert result.status == CheckStatus.FAIL
    assert "knowledge: missing" in result.details
    assert result.retry_target == "knowledge_extraction"


@pytest.mark.asyncio
async def test_schema_check_invalid_payload() -> None:
    state = _complete_state()
    state["classification"] = {"subject": "only"}
    result = await check_schema(state)
    assert result.status == CheckStatus.FAIL
    assert "classification: invalid" in result.details
    assert result.retry_target == "educational_classification"


@pytest.mark.asyncio
async def test_schema_check_accepts_model_instances() -> None:
    state = {
        "classification": make_classification(),
        "knowledge": make_knowledge(),
        "teaching_plan": make_teaching_plan(),
        "classroom_content": make_classroom_content(),
        "activities": make_activities(),
        "assessments": make_assessments(),
        "gap_analysis": make_gap_analysis(),
    }
    result = await check_schema(state)
    assert result.status == CheckStatus.PASS
