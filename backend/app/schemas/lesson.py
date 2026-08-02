"""Teaching plan and classroom content schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PeriodPlan(BaseModel):
    """One teaching period — count/length are flexible (FAQ Q3)."""

    period_number: int
    title: str
    duration_minutes: int = Field(..., ge=15, le=120)
    objectives: list[str] = Field(default_factory=list)
    concepts_covered: list[str] = Field(default_factory=list)
    pacing_rationale: str = ""


class TeachingPlan(BaseModel):
    """Stage 4 output."""

    total_periods: int
    periods: list[PeriodPlan] = Field(default_factory=list)
    overall_rationale: str = ""


class ClassroomActivity(BaseModel):
    name: str
    activity_type: str = Field(
        ..., description="demo | role_play | experiment | discussion | other"
    )
    duration_minutes: int = 10
    materials: list[str] = Field(default_factory=list)
    instructions: str = ""
    success_criteria: str = ""


class PeriodContent(BaseModel):
    """Stage 5 output for a single period."""

    period_number: int
    entry_ticket: str = ""
    teacher_script: str = ""
    blackboard_notes: str = ""
    classroom_activities: list[ClassroomActivity] = Field(default_factory=list)
    checkpoint_questions: list[str] = Field(default_factory=list)
    exit_ticket: str = ""
    homework: str = ""
    mentor_moment: str = ""
    grounding_score: float | None = Field(
        default=None, description="Faithfulness score logged for evals"
    )


class ClassroomContentBundle(BaseModel):
    periods: list[PeriodContent] = Field(default_factory=list)


class ActivityBundle(BaseModel):
    """Stage 6 — additional diverse activities across the unit."""

    activities: list[ClassroomActivity] = Field(default_factory=list)
