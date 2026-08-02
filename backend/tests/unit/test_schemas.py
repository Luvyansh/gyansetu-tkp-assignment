"""Pydantic schema edge-case tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas.assessment import AssessmentQuestion, QuestionType
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.document import DocTypeHint, DocumentStructure, Section
from backend.app.schemas.knowledge import Concept, ExtractedKnowledge, SourceRef
from backend.app.schemas.lesson import PeriodPlan, TeachingPlan
from backend.app.schemas.validation import CheckStatus, ValidationCheck, ValidationReport
from backend.tests.factories import make_classification, make_tkp


def test_classification_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        EducationalClassification(subject="Physics")  # type: ignore[call-arg]


def test_classification_roundtrip() -> None:
    c = make_classification()
    assert EducationalClassification.model_validate(c.model_dump()).topic == c.topic


def test_period_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        PeriodPlan(period_number=1, title="Too short", duration_minutes=5)
    with pytest.raises(ValidationError):
        PeriodPlan(period_number=1, title="Too long", duration_minutes=200)
    ok = PeriodPlan(period_number=1, title="Ok", duration_minutes=40)
    assert ok.duration_minutes == 40


def test_document_structure_defaults() -> None:
    d = DocumentStructure()
    assert d.page_count == 0
    assert d.sections == []
    assert d.parser_route == "pymupdf_text"


def test_section_nested() -> None:
    nested = Section(heading="Child", text="x")
    parent = Section(heading="Parent", subsections=[nested])
    assert parent.subsections[0].heading == "Child"


def test_doc_type_hint_values() -> None:
    assert DocTypeHint.MOSTLY_TEXT.value == "mostly_text"
    assert DocTypeHint("scanned") is DocTypeHint.SCANNED


def test_knowledge_requires_source_ref_on_concepts() -> None:
    with pytest.raises(ValidationError):
        Concept(name="inertia", explanation="x")  # type: ignore[call-arg]


def test_extracted_knowledge_empty_ok() -> None:
    k = ExtractedKnowledge()
    assert k.concepts == []


def test_assessment_question_types() -> None:
    q = AssessmentQuestion(
        question_type=QuestionType.MCQ,
        prompt="Q?",
        options=["a", "b"],
        answer_key="a",
    )
    assert q.marks == 1.0


def test_validation_report_failed_retry_targets() -> None:
    report = ValidationReport(
        schema_check=ValidationCheck(name="schema_check", status=CheckStatus.PASS),
        groundedness_check=ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.FAIL,
            retry_target="classroom_content",
        ),
        consistency_check=ValidationCheck(
            name="consistency_check",
            status=CheckStatus.FAIL,
            retry_target="teaching_planner",
        ),
        overall_passed=False,
    )
    assert report.failed_retry_targets() == ["classroom_content", "teaching_planner"]


def test_tkp_schema_version() -> None:
    tkp = make_tkp()
    assert tkp.schema_version == "1.0"
    assert tkp.classification.category == "STEM"


def test_source_ref_optional_fields() -> None:
    ref = SourceRef()
    assert ref.page is None
    assert ref.quote is None


def test_teaching_plan_periods_list() -> None:
    plan = TeachingPlan(total_periods=0, periods=[])
    assert plan.total_periods == 0
