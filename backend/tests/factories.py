"""Shared factories for schema fixtures used across tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.app.schemas.assessment import AssessmentBundle, AssessmentQuestion, QuestionType
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.document import DocumentStructure, Section
from backend.app.schemas.gap_analysis import GapAnalysis, LearningGap, Severity
from backend.app.schemas.knowledge import (
    Concept,
    Definition,
    ExtractedKnowledge,
    SourceRef,
)
from backend.app.schemas.lesson import (
    ActivityBundle,
    ClassroomActivity,
    ClassroomContentBundle,
    PeriodContent,
    PeriodPlan,
    TeachingPlan,
)
from backend.app.schemas.tkp import TeacherKnowledgePackage
from backend.app.schemas.validation import CheckStatus, ValidationCheck, ValidationReport

STEM_EXCERPT = (
    "Newton's first law states that an object at rest stays at rest. "
    "Newton's second law: F = ma. "
    "Newton's third law: for every action there is an equal and opposite reaction."
)


def make_source_ref(**overrides: Any) -> SourceRef:
    data = {"section": "Introduction", "page": 1, "quote": "object at rest stays at rest"}
    data.update(overrides)
    return SourceRef(**data)


def make_document_structure(**overrides: Any) -> DocumentStructure:
    data: dict[str, Any] = {
        "title": "Newton's Laws of Motion",
        "page_count": 1,
        "sections": [
            Section(
                heading="Newton's Laws of Motion",
                level=1,
                text=STEM_EXCERPT,
                page_start=1,
                page_end=1,
            )
        ],
        "full_text": STEM_EXCERPT,
        "parser_route": "pymupdf_text",
        "metadata": {"image_count": 0},
    }
    data.update(overrides)
    return DocumentStructure(**data)


def make_classification(**overrides: Any) -> EducationalClassification:
    data = {
        "subject": "Physics",
        "grade": "Class 9",
        "difficulty": "introductory",
        "topic": "Laws of Motion",
        "chapter": "Newton's Laws",
        "category": "STEM",
        "language": "English",
        "rationale": "Document discusses Newton's three laws.",
    }
    data.update(overrides)
    return EducationalClassification(**data)


def make_knowledge(**overrides: Any) -> ExtractedKnowledge:
    ref = make_source_ref()
    data = {
        "concepts": [
            Concept(
                name="inertia",
                explanation="Tendency of objects to resist changes in motion",
                source_ref=ref,
            ),
            Concept(
                name="force",
                explanation="A push or pull that can change motion; F = ma",
                source_ref=ref,
            ),
        ],
        "definitions": [
            Definition(
                term="Newton's second law",
                definition="Force equals mass times acceleration",
                source_ref=ref,
            )
        ],
        "keywords": [],
        "learning_objectives": [],
        "prerequisites": [],
        "formulae": [],
        "examples": [],
        "applications": [],
        "common_misconceptions": [],
    }
    data.update(overrides)
    return ExtractedKnowledge(**data)


def make_teaching_plan(**overrides: Any) -> TeachingPlan:
    data = {
        "total_periods": 2,
        "periods": [
            PeriodPlan(
                period_number=1,
                title="Inertia and First Law",
                duration_minutes=40,
                objectives=["Explain inertia"],
                concepts_covered=["inertia"],
                pacing_rationale="Introduce foundational idea",
            ),
            PeriodPlan(
                period_number=2,
                title="Force and Second Law",
                duration_minutes=40,
                objectives=["Apply F = ma"],
                concepts_covered=["force"],
                pacing_rationale="Build quantitative understanding",
            ),
        ],
        "overall_rationale": "Two periods cover core Newtonian mechanics.",
    }
    data.update(overrides)
    return TeachingPlan(**data)


def make_period_content(period_number: int = 1, **overrides: Any) -> PeriodContent:
    data = {
        "period_number": period_number,
        "entry_ticket": "What keeps a ball rolling?",
        "teacher_script": (
            "Today we study inertia and force. An object at rest stays at rest "
            "unless acted on by an unbalanced force."
        ),
        "blackboard_notes": "Inertia; F = ma; action-reaction",
        "classroom_activities": [
            ClassroomActivity(
                name="Push the book",
                activity_type="demo",
                duration_minutes=10,
                materials=["book"],
                instructions="Push a book gently and discuss inertia and force.",
                success_criteria="Students link force to acceleration",
            )
        ],
        "checkpoint_questions": ["State Newton's first law."],
        "exit_ticket": "Define inertia in one sentence.",
        "homework": "Find one everyday example of inertia.",
        "mentor_moment": "Encourage curiosity about motion.",
    }
    data.update(overrides)
    return PeriodContent(**data)


def make_classroom_content(**overrides: Any) -> ClassroomContentBundle:
    data = {
        "periods": [
            make_period_content(1),
            make_period_content(
                2,
                entry_ticket="What is force?",
                teacher_script="Force equals mass times acceleration. Apply F = ma.",
                blackboard_notes="F = ma; force",
            ),
        ]
    }
    data.update(overrides)
    return ClassroomContentBundle(**data)


def make_activities(**overrides: Any) -> ActivityBundle:
    data = {
        "activities": [
            ClassroomActivity(
                name="Balloon rocket",
                activity_type="experiment",
                duration_minutes=15,
                materials=["balloon", "string"],
                instructions="Demonstrate action-reaction with a balloon rocket about inertia.",
                success_criteria="Students connect third law to motion",
            )
        ]
    }
    data.update(overrides)
    return ActivityBundle(**data)


def make_assessments(**overrides: Any) -> AssessmentBundle:
    data = {
        "formative": [
            AssessmentQuestion(
                question_type=QuestionType.SHORT,
                prompt="State Newton's first law.",
                answer_key="An object at rest stays at rest unless acted on by a force.",
                marks=2.0,
                concepts_tested=["inertia"],
            )
        ],
        "summative": [
            AssessmentQuestion(
                question_type=QuestionType.MCQ,
                prompt="F = ma is which law?",
                options=["First", "Second", "Third", "None"],
                answer_key="Second",
                marks=1.0,
                concepts_tested=["force"],
            )
        ],
        "total_marks": 3.0,
    }
    data.update(overrides)
    return AssessmentBundle(**data)


def make_gap_analysis(**overrides: Any) -> GapAnalysis:
    data = {
        "gaps": [
            LearningGap(
                misconception="Moving objects need continuous force",
                diagnostic_question="Does a hockey puck need constant force on ice?",
                severity=Severity.MEDIUM,
                remedial_actions=["Demo low-friction motion"],
                related_concepts=["inertia"],
            )
        ],
        "summary": "Common inertia misconceptions.",
    }
    data.update(overrides)
    return GapAnalysis(**data)


def make_validation_report(*, passed: bool = True, **overrides: Any) -> ValidationReport:
    ok = ValidationCheck(
        name="schema_check",
        status=CheckStatus.PASS,
        details="ok",
        score=1.0,
    )
    ground = ValidationCheck(
        name="groundedness_check",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        details="avg=0.900",
        score=0.9 if passed else 0.4,
        retry_target=None if passed else "classroom_content",
    )
    cons = ValidationCheck(
        name="consistency_check",
        status=CheckStatus.PASS,
        details="ok",
        score=1.0,
    )
    data = {
        "schema_check": ok,
        "groundedness_check": ground,
        "consistency_check": cons,
        "overall_passed": passed,
        "grounding_scores": {"period_1": 0.9, "period_2": 0.9},
    }
    data.update(overrides)
    return ValidationReport(**data)


def make_tkp(**overrides: Any) -> TeacherKnowledgePackage:
    job_id = uuid4()
    data = {
        "schema_version": "1.0",
        "package_id": uuid4(),
        "job_id": job_id,
        "document_id": uuid4(),
        "source_filename": "stem_excerpt.pdf",
        "created_at": datetime.now(UTC),
        "classification": make_classification(),
        "knowledge": make_knowledge(),
        "teaching_plan": make_teaching_plan(),
        "classroom_content": make_classroom_content(),
        "activities": make_activities(),
        "assessments": make_assessments(),
        "gap_analysis": make_gap_analysis(),
        "validation": make_validation_report(passed=True),
        "metadata": {"parser_route": "pymupdf_text"},
    }
    data.update(overrides)
    return TeacherKnowledgePackage(**data)


def canned_llm_payloads() -> dict[str, dict[str, Any]]:
    """Stage-name → model_dump dict used by the mock LLM router."""
    return {
        "educational_classification": make_classification().model_dump(mode="json"),
        "knowledge_extraction": make_knowledge().model_dump(mode="json"),
        "teaching_planner": make_teaching_plan().model_dump(mode="json"),
        "classroom_content": make_period_content().model_dump(mode="json"),
        "activity_generation": make_activities().model_dump(mode="json"),
        "assessment_generation": make_assessments().model_dump(mode="json"),
        "gap_analysis": make_gap_analysis().model_dump(mode="json"),
        "validation_judge": {
            "passed": True,
            "score": 0.92,
            "rationale": "Content is grounded in Newton's laws excerpt.",
        },
    }
