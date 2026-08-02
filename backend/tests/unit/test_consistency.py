"""Cross-stage consistency check tests."""

from __future__ import annotations

from backend.app.schemas.lesson import ClassroomContentBundle
from backend.app.schemas.validation import CheckStatus
from backend.app.validation.consistency import check_consistency
from backend.tests.factories import (
    make_activities,
    make_assessments,
    make_classroom_content,
    make_period_content,
    make_teaching_plan,
)


def _good_state() -> dict:
    return {
        "teaching_plan": make_teaching_plan().model_dump(mode="json"),
        "classroom_content": make_classroom_content().model_dump(mode="json"),
        "activities": make_activities().model_dump(mode="json"),
        "assessments": make_assessments().model_dump(mode="json"),
    }


def test_consistency_pass() -> None:
    result = check_consistency(_good_state())
    assert result.status == CheckStatus.PASS
    assert result.score == 1.0


def test_consistency_missing_plan() -> None:
    result = check_consistency({"classroom_content": make_classroom_content().model_dump()})
    assert result.status == CheckStatus.FAIL
    assert result.retry_target == "teaching_planner"


def test_consistency_period_mismatch() -> None:
    state = _good_state()
    # Only period 1 in classroom
    state["classroom_content"] = ClassroomContentBundle(
        periods=[make_period_content(1)]
    ).model_dump(mode="json")
    result = check_consistency(state)
    assert result.status == CheckStatus.FAIL
    assert "missing periods" in result.details


def test_consistency_empty_assessment_concepts() -> None:
    from backend.app.schemas.assessment import AssessmentBundle, AssessmentQuestion, QuestionType

    state = _good_state()
    state["assessments"] = AssessmentBundle(
        formative=[
            AssessmentQuestion(
                question_type=QuestionType.SHORT,
                prompt="Q",
                answer_key="A",
                concepts_tested=[],
            )
        ],
        summative=[],
        total_marks=1.0,
    ).model_dump(mode="json")
    result = check_consistency(state)
    assert result.status == CheckStatus.FAIL
    assert "concepts_tested" in result.details
