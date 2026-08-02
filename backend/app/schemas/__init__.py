"""Schema package exports."""

from backend.app.schemas.assessment import AssessmentBundle, AssessmentQuestion, QuestionType
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.document import DocTypeHint, DocumentStructure, DocumentUploadResponse
from backend.app.schemas.gap_analysis import GapAnalysis, LearningGap
from backend.app.schemas.knowledge import ExtractedKnowledge
from backend.app.schemas.lesson import (
    ActivityBundle,
    ClassroomContentBundle,
    PeriodContent,
    TeachingPlan,
)
from backend.app.schemas.tkp import (
    EvalReportSummary,
    HealthResponse,
    JobStatus,
    StreamEvent,
    TeacherKnowledgePackage,
)
from backend.app.schemas.validation import CheckStatus, ValidationCheck, ValidationReport

__all__ = [
    "ActivityBundle",
    "AssessmentBundle",
    "AssessmentQuestion",
    "CheckStatus",
    "ClassroomContentBundle",
    "DocTypeHint",
    "DocumentStructure",
    "DocumentUploadResponse",
    "EducationalClassification",
    "EvalReportSummary",
    "ExtractedKnowledge",
    "GapAnalysis",
    "HealthResponse",
    "JobStatus",
    "LearningGap",
    "PeriodContent",
    "QuestionType",
    "StreamEvent",
    "TeacherKnowledgePackage",
    "TeachingPlan",
    "ValidationCheck",
    "ValidationReport",
]
