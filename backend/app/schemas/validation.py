"""Stage 9 validation report schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


class ValidationCheck(BaseModel):
    name: str
    status: CheckStatus
    details: str = ""
    score: float | None = None
    retry_target: str | None = Field(
        default=None,
        description="Graph node to retry on failure, e.g. classroom_content",
    )


class ValidationReport(BaseModel):
    """Stage 9 output."""

    schema_check: ValidationCheck
    groundedness_check: ValidationCheck
    consistency_check: ValidationCheck
    overall_passed: bool = False
    grounding_scores: dict[str, float] = Field(default_factory=dict)

    def failed_retry_targets(self) -> list[str]:
        targets: list[str] = []
        for check in (self.schema_check, self.groundedness_check, self.consistency_check):
            if check.status == CheckStatus.FAIL and check.retry_target:
                targets.append(check.retry_target)
        return targets
