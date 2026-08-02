"""LangGraph shared state — single source of truth through the pipeline."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.document import DocTypeHint, DocumentStructure
from backend.app.schemas.gap_analysis import GapAnalysis
from backend.app.schemas.knowledge import ExtractedKnowledge
from backend.app.schemas.lesson import ActivityBundle, ClassroomContentBundle, TeachingPlan
from backend.app.schemas.tkp import TeacherKnowledgePackage
from backend.app.schemas.validation import ValidationReport


def _replace(_left: Any, right: Any) -> Any:
    """Last-write-wins reducer for LangGraph channels (including explicit ``None``)."""
    return right


class TKPState(BaseModel):
    """Typed state flowing through all 10 nodes (Pydantic view for docs/validation)."""

    model_config = {"arbitrary_types_allowed": True}

    job_id: UUID
    document_id: UUID
    source_filename: str = ""
    doc_type_hint: DocTypeHint | None = None
    file_path: str | None = None

    document_structure: DocumentStructure | None = None
    classification: EducationalClassification | None = None
    knowledge: ExtractedKnowledge | None = None
    knowledge_chunk_texts: list[str] = Field(default_factory=list)
    knowledge_chunk_embeddings: list[list[float]] = Field(default_factory=list)

    teaching_plan: TeachingPlan | None = None
    classroom_content: ClassroomContentBundle | None = None
    activities: ActivityBundle | None = None
    assessments: AssessmentBundle | None = None
    gap_analysis: GapAnalysis | None = None

    validation: ValidationReport | None = None
    validation_retry_count: int = 0
    max_validation_retries: int = 2
    retry_targets: list[str] = Field(default_factory=list)
    validation_feedback: str = ""

    tkp: TeacherKnowledgePackage | None = None
    pdf_artifacts: dict[str, str] = Field(default_factory=dict)

    current_stage: str = "pending"
    progress_pct: float = 0.0
    error: str | None = None
    stage_meta: dict[str, Any] = Field(default_factory=dict)
    grounding_scores: dict[str, float] = Field(default_factory=dict)


class TKPGraphState(TypedDict, total=False):
    """LangGraph channel schema — each key uses last-write-wins merge.

    Plain ``StateGraph(dict)`` replaces the entire state on each node return;
    Annotated channels keep identity fields (``job_id``, ``document_id``, …)
    across partial updates.
    """

    job_id: Annotated[Any, _replace]
    document_id: Annotated[Any, _replace]
    source_filename: Annotated[Any, _replace]
    doc_type_hint: Annotated[Any, _replace]
    file_path: Annotated[Any, _replace]

    document_structure: Annotated[Any, _replace]
    classification: Annotated[Any, _replace]
    knowledge: Annotated[Any, _replace]
    knowledge_chunk_texts: Annotated[Any, _replace]
    knowledge_chunk_embeddings: Annotated[Any, _replace]

    teaching_plan: Annotated[Any, _replace]
    classroom_content: Annotated[Any, _replace]
    activities: Annotated[Any, _replace]
    assessments: Annotated[Any, _replace]
    gap_analysis: Annotated[Any, _replace]

    validation: Annotated[Any, _replace]
    validation_retry_count: Annotated[Any, _replace]
    max_validation_retries: Annotated[Any, _replace]
    retry_targets: Annotated[Any, _replace]
    validation_feedback: Annotated[Any, _replace]

    tkp: Annotated[Any, _replace]
    pdf_artifacts: Annotated[Any, _replace]

    current_stage: Annotated[Any, _replace]
    progress_pct: Annotated[Any, _replace]
    error: Annotated[Any, _replace]
    stage_meta: Annotated[Any, _replace]
    grounding_scores: Annotated[Any, _replace]
