"""Background pipeline runner for TKP jobs."""

from __future__ import annotations

import contextlib
import traceback
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import close_progress_queue, publish_progress
from backend.app.db.models import Document, Job, StageOutput, TKPPackage
from backend.app.db.session import AsyncSessionLocal
from backend.app.logging_config import get_logger
from backend.app.pdf_export.render import render_all_pdfs
from backend.app.schemas.tkp import TeacherKnowledgePackage

logger = get_logger(__name__)


def _model_dump_safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def _update_job(
    session: AsyncSession,
    job: Job,
    *,
    status: str | None = None,
    current_stage: str | None = None,
    progress_pct: float | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        job.status = status
    if current_stage is not None:
        job.current_stage = current_stage
    if progress_pct is not None:
        job.progress_pct = float(progress_pct)
    if error is not None:
        job.error = error
    await session.commit()
    await publish_progress(
        job.id,
        {
            "stage": job.current_stage or "unknown",
            "progress": job.progress_pct,
            "message": error or f"Job {job.status}",
            "status": job.status,
        },
    )


async def build_initial_state(job: Job, document: Document) -> dict[str, Any]:
    """Build the LangGraph initial state dict from DB rows."""
    file_path = None
    # Prefer path stashed on extracted_structure during upload
    structure = document.extracted_structure or {}
    if isinstance(structure, dict):
        file_path = structure.get("temp_file_path")

    return {
        "job_id": job.id,
        "document_id": document.id,
        "source_filename": document.original_filename,
        "doc_type_hint": document.doc_type_hint,
        "file_path": file_path,
        "document_structure": None,
        "classification": None,
        "knowledge": None,
        "knowledge_chunk_texts": [],
        "teaching_plan": None,
        "classroom_content": None,
        "activities": None,
        "assessments": None,
        "gap_analysis": None,
        "validation": None,
        "validation_retry_count": 0,
        "max_validation_retries": 2,
        "retry_targets": [],
        "validation_feedback": "",
        "tkp": None,
        "pdf_artifacts": {},
        "current_stage": "pending",
        "progress_pct": 0.0,
        "error": None,
        "stage_meta": {},
        "grounding_scores": {},
    }


async def _persist_pipeline_result(
    session: AsyncSession,
    job: Job,
    document: Document,
    result: dict[str, Any],
) -> None:
    """Persist stage outputs, TKP package, and PDF paths from final state."""
    stage = result.get("current_stage") or "publish"
    progress = float(result.get("progress_pct") or 100.0)
    job.current_stage = stage
    job.progress_pct = progress

    # Snapshot key stage fields into stage_outputs when present
    stage_fields = {
        "document_intelligence": result.get("document_structure"),
        "educational_classification": result.get("classification"),
        "knowledge_extraction": result.get("knowledge"),
        "teaching_planner": result.get("teaching_plan"),
        "classroom_content": result.get("classroom_content"),
        "activity_generation": result.get("activities"),
        "assessment_generation": result.get("assessments"),
        "gap_analysis": result.get("gap_analysis"),
        "validation": result.get("validation"),
    }
    for stage_name, output in stage_fields.items():
        if output is None:
            continue
        dumped = _model_dump_safe(output)
        if not isinstance(dumped, dict):
            dumped = {"value": dumped}
        session.add(
            StageOutput(
                job_id=job.id,
                stage_name=stage_name,
                output=dumped,
                model_used=(result.get("stage_meta") or {}).get(stage_name, {}).get("model"),
                latency_ms=(result.get("stage_meta") or {}).get(stage_name, {}).get("latency_ms"),
                token_usage=(result.get("stage_meta") or {}).get(stage_name, {}).get("token_usage"),
            )
        )

    grounding = result.get("grounding_scores") or {}
    if grounding:
        session.add(
            StageOutput(
                job_id=job.id,
                stage_name="grounding_scores",
                output={"grounding_scores": grounding},
            )
        )

    tkp_raw = result.get("tkp")
    if tkp_raw is not None:
        if isinstance(tkp_raw, TeacherKnowledgePackage):
            tkp = tkp_raw
        else:
            tkp = TeacherKnowledgePackage.model_validate(tkp_raw)
        if tkp.job_id is None:
            tkp = tkp.model_copy(update={"job_id": job.id, "document_id": document.id})
        pdf_paths = result.get("pdf_artifacts") or {}
        if not pdf_paths:
            try:
                pdf_paths = await render_all_pdfs(tkp)
            except Exception as exc:
                logger.warning("pdf_render_failed", job_id=str(job.id), error=str(exc))
                pdf_paths = {}
        tkp_json = tkp.model_dump(mode="json")
        if pdf_paths:
            tkp_json.setdefault("metadata", {})
            for name, path in pdf_paths.items():
                tkp_json["metadata"][f"pdf_{name}"] = path
        existing = await session.execute(select(TKPPackage).where(TKPPackage.job_id == job.id))
        pkg = existing.scalar_one_or_none()
        if pkg is None:
            session.add(TKPPackage(job_id=job.id, tkp_json=tkp_json))
        else:
            pkg.tkp_json = tkp_json

    await session.commit()


async def run_job_pipeline(job_id: uuid.UUID) -> None:
    """Execute the LangGraph pipeline for a job and update DB status.

    1. Mark job running
    2. Build initial state from document + job
    3. ``await run_pipeline(state)``
    4. On success → completed; on error → failed
    5. Persist stage outputs / TKP / progress events
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("pipeline_job_not_found", job_id=str(job_id))
            return

        doc_result = await session.execute(select(Document).where(Document.id == job.document_id))
        document = doc_result.scalar_one_or_none()
        if document is None:
            await _update_job(
                session,
                job,
                status="failed",
                error="Document not found for job",
                current_stage="error",
                progress_pct=0.0,
            )
            close_progress_queue(job_id)
            return

        await _update_job(
            session,
            job,
            status="running",
            current_stage="document_intelligence",
            progress_pct=1.0,
            error=None,
        )

        state = await build_initial_state(job, document)

        async def _on_stage(stage: str, progress_pct: float) -> None:
            await _update_job(
                session,
                job,
                status="running",
                current_stage=stage,
                progress_pct=progress_pct,
            )

        try:
            from backend.app.graph.build_graph import run_pipeline

            final_state = await run_pipeline(state, on_stage=_on_stage)
            if not isinstance(final_state, dict):
                if hasattr(final_state, "model_dump"):
                    final_state = final_state.model_dump()
                else:
                    raise TypeError("run_pipeline must return a dict-like state")

            if final_state.get("error"):
                await _update_job(
                    session,
                    job,
                    status="failed",
                    current_stage=final_state.get("current_stage") or "error",
                    progress_pct=float(final_state.get("progress_pct") or job.progress_pct),
                    error=str(final_state["error"]),
                )
            else:
                await _persist_pipeline_result(session, job, document, final_state)
                await _update_job(
                    session,
                    job,
                    status="completed",
                    current_stage=final_state.get("current_stage") or "publish",
                    progress_pct=float(final_state.get("progress_pct") or 100.0),
                )
        except Exception as exc:
            logger.error(
                "pipeline_failed",
                job_id=str(job_id),
                error=str(exc),
                traceback=traceback.format_exc(),
                stage=job.current_stage,
            )
            # Preserve last known stage (e.g. knowledge_extraction) so the UI
            # does not pin the failure on the pre-run document_intelligence label.
            await _update_job(
                session,
                job,
                status="failed",
                error=str(exc),
            )
        finally:
            # Clean temp upload if present
            structure = document.extracted_structure or {}
            temp_path = structure.get("temp_file_path") if isinstance(structure, dict) else None
            if temp_path:
                with contextlib.suppress(OSError):
                    Path(temp_path).unlink(missing_ok=True)
            close_progress_queue(job_id)
