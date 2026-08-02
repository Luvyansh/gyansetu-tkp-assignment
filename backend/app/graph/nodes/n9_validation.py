"""Stage 9 — Validation (schema, groundedness, consistency)."""

from __future__ import annotations

import json
from typing import Any

from backend.app.graph.nodes.helpers import dump_model
from backend.app.logging_config import get_logger
from backend.app.schemas.validation import CheckStatus, ValidationCheck, ValidationReport
from backend.app.validation.consistency import check_consistency
from backend.app.validation.groundedness import check_groundedness
from backend.app.validation.schema_check import check_schema

logger = get_logger(__name__)

STAGE = "validation"


def _extract_grounding_scores(check: ValidationCheck) -> dict[str, float]:
    scores: dict[str, float] = {}
    if check.score is not None:
        scores["overall"] = float(check.score)
    details = (check.details or "").strip()
    if not details:
        return scores
    try:
        parsed = json.loads(details)
    except json.JSONDecodeError:
        return scores
    if isinstance(parsed, dict):
        nested = parsed.get("scores", parsed)
        if isinstance(nested, dict):
            for key, value in nested.items():
                if isinstance(value, (int, float)):
                    scores[str(key)] = float(value)
    return scores


def _feedback_from_checks(*checks: ValidationCheck) -> str:
    parts: list[str] = []
    for check in checks:
        if check.status == CheckStatus.FAIL:
            target = f" (retry -> {check.retry_target})" if check.retry_target else ""
            parts.append(f"[{check.name}] FAIL{target}: {check.details}")
        elif check.status == CheckStatus.WARN:
            parts.append(f"[{check.name}] WARN: {check.details}")
    return "\n".join(parts)


async def run(state: dict[str, Any]) -> dict[str, Any]:
    schema_check = await check_schema(state)
    groundedness_check = await check_groundedness(state)
    consistency_check = check_consistency(state)

    overall_passed = all(
        c.status != CheckStatus.FAIL for c in (schema_check, groundedness_check, consistency_check)
    )

    report = ValidationReport(
        schema_check=schema_check,
        groundedness_check=groundedness_check,
        consistency_check=consistency_check,
        overall_passed=overall_passed,
        grounding_scores=_extract_grounding_scores(groundedness_check),
    )

    update: dict[str, Any] = {
        "validation": dump_model(report),
        "current_stage": STAGE,
        "progress_pct": 90.0,
    }

    if overall_passed:
        update["validation_feedback"] = ""
        update["retry_targets"] = []
        update["error"] = None
        logger.info("n9_validation_passed", grounding_scores=report.grounding_scores)
        return update

    retry_count = int(state.get("validation_retry_count") or 0) + 1
    feedback = _feedback_from_checks(schema_check, groundedness_check, consistency_check)
    targets = report.failed_retry_targets()
    if not targets:
        targets = ["teaching_planner"]

    update.update(
        {
            "validation_retry_count": retry_count,
            "validation_feedback": feedback,
            "retry_targets": targets,
        }
    )
    logger.warning(
        "n9_validation_failed",
        retry_count=retry_count,
        retry_targets=targets,
        feedback=feedback[:500],
    )
    return update
