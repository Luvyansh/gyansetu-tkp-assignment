"""Assessment schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    MCQ = "mcq"
    SHORT = "short"
    LONG = "long"
    NUMERICAL = "numerical"


class AssessmentQuestion(BaseModel):
    question_type: QuestionType
    prompt: str
    options: list[str] | None = None
    answer_key: str
    rubric: str | None = None
    marks: float = 1.0
    concepts_tested: list[str] = Field(default_factory=list)
    source_ref_hint: str | None = None


class AssessmentBundle(BaseModel):
    """Stage 7 output."""

    formative: list[AssessmentQuestion] = Field(default_factory=list)
    summative: list[AssessmentQuestion] = Field(default_factory=list)
    total_marks: float = 0.0
