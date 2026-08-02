"""Cross-stage consistency checks (periods, concepts, assessments)."""

from __future__ import annotations

from typing import Any

from backend.app.logging_config import get_logger
from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.lesson import ClassroomContentBundle, TeachingPlan
from backend.app.schemas.validation import CheckStatus, ValidationCheck

logger = get_logger(__name__)


def _coerce_plan(raw: Any) -> TeachingPlan | None:
    if raw is None:
        return None
    if isinstance(raw, TeachingPlan):
        return raw
    return TeachingPlan.model_validate(raw)


def _coerce_classroom(raw: Any) -> ClassroomContentBundle | None:
    if raw is None:
        return None
    if isinstance(raw, ClassroomContentBundle):
        return raw
    return ClassroomContentBundle.model_validate(raw)


def _coerce_assessments(raw: Any) -> AssessmentBundle | None:
    if raw is None:
        return None
    if isinstance(raw, AssessmentBundle):
        return raw
    return AssessmentBundle.model_validate(raw)


def check_consistency(state: dict[str, Any]) -> ValidationCheck:
    """Ensure teaching plan, classroom content, and assessments align.

    Checks:
    - Period numbers in classroom_content match teaching_plan
    - Plan ``concepts_covered`` are referenced somewhere in content/activities
    - Assessment ``concepts_tested`` nonempty when questions exist

    On failure, ``retry_target`` is ``teaching_planner``.
    """
    issues: list[str] = []

    plan = _coerce_plan(state.get("teaching_plan"))
    classroom = _coerce_classroom(state.get("classroom_content"))
    assessments = _coerce_assessments(state.get("assessments"))

    if plan is None or classroom is None:
        return ValidationCheck(
            name="consistency_check",
            status=CheckStatus.FAIL,
            details="teaching_plan or classroom_content missing",
            score=0.0,
            retry_target="teaching_planner",
        )

    plan_periods = {p.period_number for p in plan.periods}
    content_periods = {p.period_number for p in classroom.periods}

    if plan.total_periods and len(plan.periods) != plan.total_periods:
        issues.append(f"total_periods={plan.total_periods} but len(periods)={len(plan.periods)}")

    missing_in_content = plan_periods - content_periods
    extra_in_content = content_periods - plan_periods
    if missing_in_content:
        issues.append(f"classroom_content missing periods: {sorted(missing_in_content)}")
    if extra_in_content:
        issues.append(f"classroom_content extra periods: {sorted(extra_in_content)}")

    planned_concepts: set[str] = set()
    for plan_period in plan.periods:
        planned_concepts.update(
            c.strip().lower() for c in plan_period.concepts_covered if c.strip()
        )

    referenced: set[str] = set()
    for content in classroom.periods:
        blob = " ".join(
            [
                content.teacher_script,
                content.blackboard_notes,
                content.entry_ticket,
                content.exit_ticket,
                " ".join(content.checkpoint_questions),
                " ".join(a.name + " " + a.instructions for a in content.classroom_activities),
            ]
        ).lower()
        for concept in planned_concepts:
            if concept and concept in blob:
                referenced.add(concept)

    # Also scan activities bundle if present
    activities_raw = state.get("activities")
    if activities_raw is not None:
        try:
            from backend.app.schemas.lesson import ActivityBundle

            bundle = (
                activities_raw
                if isinstance(activities_raw, ActivityBundle)
                else ActivityBundle.model_validate(activities_raw)
            )
            for act in bundle.activities:
                blob = f"{act.name} {act.instructions}".lower()
                for concept in planned_concepts:
                    if concept and concept in blob:
                        referenced.add(concept)
        except Exception:
            logger.warning(
                "consistency_activities_scan_failed",
                exc_info=True,
                planned_concept_count=len(planned_concepts),
            )

    if planned_concepts:
        uncovered = planned_concepts - referenced
        # Soft: warn only if majority missing
        if len(uncovered) > max(1, len(planned_concepts) // 2):
            issues.append(
                "concepts_covered poorly referenced in content: " + ", ".join(sorted(uncovered)[:8])
            )

    if assessments is not None:
        questions = [*assessments.formative, *assessments.summative]
        if questions:
            empty_concepts = sum(1 for q in questions if not q.concepts_tested)
            if empty_concepts == len(questions):
                issues.append("all assessment questions have empty concepts_tested")
            elif empty_concepts > len(questions) // 2:
                issues.append(
                    f"{empty_concepts}/{len(questions)} assessment questions lack concepts_tested"
                )

    if issues:
        return ValidationCheck(
            name="consistency_check",
            status=CheckStatus.FAIL,
            details="; ".join(issues),
            score=0.0,
            retry_target="teaching_planner",
        )

    return ValidationCheck(
        name="consistency_check",
        status=CheckStatus.PASS,
        details="Period numbers and concept references are consistent",
        score=1.0,
        retry_target=None,
    )
