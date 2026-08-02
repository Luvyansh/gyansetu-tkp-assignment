"""Stage 10 — Publish TKP JSON + PDF artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.app.db.models import TKPPackage
from backend.app.db.session import AsyncSessionLocal
from backend.app.graph.nodes.helpers import as_uuid, coerce_model, dump_model
from backend.app.logging_config import get_logger
from backend.app.pdf_export.render import render_all_pdfs
from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.gap_analysis import GapAnalysis
from backend.app.schemas.knowledge import ExtractedKnowledge
from backend.app.schemas.lesson import ActivityBundle, ClassroomContentBundle, TeachingPlan
from backend.app.schemas.tkp import TeacherKnowledgePackage
from backend.app.schemas.validation import ValidationReport

logger = get_logger(__name__)

STAGE = "publish"


def _parser_route(state: dict[str, Any]) -> str:
    structure = state.get("document_structure")
    if structure is None:
        return ""
    if isinstance(structure, dict):
        return str(structure.get("parser_route") or "")
    return str(getattr(structure, "parser_route", "") or "")


async def run(state: dict[str, Any]) -> dict[str, Any]:
    job_id = as_uuid(state["job_id"])
    document_id = as_uuid(state["document_id"])
    package_id = uuid4()

    tkp = TeacherKnowledgePackage(
        schema_version="1.0",
        package_id=package_id,
        job_id=job_id,
        document_id=document_id,
        source_filename=state.get("source_filename") or None,
        created_at=datetime.now(UTC),
        classification=coerce_model(EducationalClassification, state["classification"]),
        knowledge=coerce_model(ExtractedKnowledge, state["knowledge"]),
        teaching_plan=coerce_model(TeachingPlan, state["teaching_plan"]),
        classroom_content=coerce_model(ClassroomContentBundle, state["classroom_content"]),
        activities=coerce_model(ActivityBundle, state["activities"]),
        assessments=coerce_model(AssessmentBundle, state["assessments"]),
        gap_analysis=coerce_model(GapAnalysis, state["gap_analysis"]),
        validation=coerce_model(ValidationReport, state["validation"])
        if state.get("validation")
        else None,
        metadata={"parser_route": _parser_route(state)},
    )

    validated = TeacherKnowledgePackage.model_validate(tkp.model_dump(mode="json"))
    tkp_json = validated.model_dump(mode="json")

    async with AsyncSessionLocal() as session:
        session.add(TKPPackage(job_id=job_id, tkp_json=tkp_json))
        await session.commit()

    pdf_artifacts = await render_all_pdfs(validated)
    logger.info(
        "n10_publish_done",
        job_id=str(job_id),
        package_id=str(package_id),
        pdf_keys=list(pdf_artifacts.keys()),
    )

    return {
        "tkp": dump_model(validated),
        "pdf_artifacts": dict(pdf_artifacts),
        "current_stage": STAGE,
        "progress_pct": 100.0,
        "error": None,
    }
