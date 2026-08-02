"""TeacherKnowledgePackage — the final published artifact schema."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.gap_analysis import GapAnalysis
from backend.app.schemas.knowledge import ExtractedKnowledge
from backend.app.schemas.lesson import ActivityBundle, ClassroomContentBundle, TeachingPlan
from backend.app.schemas.validation import ValidationReport


class TeacherKnowledgePackage(BaseModel):
    """Canonical TKP JSON produced by Stage 10."""

    schema_version: str = "1.0"
    package_id: UUID | None = None
    job_id: UUID | None = None
    document_id: UUID | None = None
    source_filename: str | None = None
    created_at: datetime | None = None

    classification: EducationalClassification
    knowledge: ExtractedKnowledge
    teaching_plan: TeachingPlan
    classroom_content: ClassroomContentBundle
    activities: ActivityBundle
    assessments: AssessmentBundle
    gap_analysis: GapAnalysis
    validation: ValidationReport | None = None

    metadata: dict[str, str] = Field(default_factory=dict)


class JobStatus(BaseModel):
    job_id: UUID
    document_id: UUID
    status: str
    current_stage: str | None = None
    progress_pct: float = 0.0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StreamEvent(BaseModel):
    stage: str
    progress: float
    message: str
    status: str = "running"


class EvalReportSummary(BaseModel):
    job_id: UUID
    faithfulness: float | None = None
    relevancy: float | None = None
    grounding_scores: dict[str, float] = Field(default_factory=dict)
    details: dict[str, object] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    database: str
    gemini_key_present: bool
    groq_key_present: bool
    environment: str
