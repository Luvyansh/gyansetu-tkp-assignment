"""Schema presence and Pydantic validity checks for pipeline stage outputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.gap_analysis import GapAnalysis
from backend.app.schemas.knowledge import ExtractedKnowledge
from backend.app.schemas.lesson import ActivityBundle, ClassroomContentBundle, TeachingPlan
from backend.app.schemas.validation import CheckStatus, ValidationCheck

# state field → graph node retry target
_STAGE_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("classification", "educational_classification", EducationalClassification),
    ("knowledge", "knowledge_extraction", ExtractedKnowledge),
    ("teaching_plan", "teaching_planner", TeachingPlan),
    ("classroom_content", "classroom_content", ClassroomContentBundle),
    ("activities", "activity_generation", ActivityBundle),
    ("assessments", "assessment_generation", AssessmentBundle),
    ("gap_analysis", "gap_analysis", GapAnalysis),
]


def _coerce(model_cls: type[BaseModel], value: Any) -> BaseModel:
    if isinstance(value, model_cls):
        return value
    if isinstance(value, BaseModel):
        return model_cls.model_validate(value.model_dump())
    return model_cls.model_validate(value)


async def check_schema(state: dict[str, Any]) -> ValidationCheck:
    """Validate required stage outputs are present and Pydantic-valid.

    On the first missing/invalid field, sets ``retry_target`` to that stage's
    graph node name so Stage 9 can route retries.
    """
    failures: list[str] = []
    retry_target: str | None = None

    for field_name, node_name, model_cls in _STAGE_SPECS:
        raw = state.get(field_name)
        if raw is None:
            failures.append(f"{field_name}: missing")
            if retry_target is None:
                retry_target = node_name
            continue
        try:
            _coerce(model_cls, raw)
        except (ValidationError, TypeError, ValueError) as exc:
            failures.append(f"{field_name}: invalid ({exc})")
            if retry_target is None:
                retry_target = node_name

    if failures:
        return ValidationCheck(
            name="schema_check",
            status=CheckStatus.FAIL,
            details="; ".join(failures),
            score=0.0,
            retry_target=retry_target,
        )

    return ValidationCheck(
        name="schema_check",
        status=CheckStatus.PASS,
        details="All required stage outputs are present and valid",
        score=1.0,
        retry_target=None,
    )
