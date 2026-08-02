"""Learning gap analysis schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LearningGap(BaseModel):
    misconception: str
    diagnostic_question: str
    severity: Severity
    remedial_actions: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    """Stage 8 output."""

    gaps: list[LearningGap] = Field(default_factory=list)
    summary: str = ""
