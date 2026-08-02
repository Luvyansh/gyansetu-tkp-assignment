"""Job status, TKP retrieval, PDF export, and eval report routes."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, limiter, verify_api_key
from backend.app.api.pipeline_runner import run_job_pipeline
from backend.app.db.models import Job, StageOutput, TKPPackage
from backend.app.pdf_export.render import render_all_pdfs
from backend.app.schemas.tkp import EvalReportSummary, JobStatus, TeacherKnowledgePackage

router = APIRouter(prefix="/jobs", tags=["jobs"])

_ARTIFACTS = {"lesson-plan", "teacher-guide", "assessment-book"}


def _job_to_status(job: Job) -> JobStatus:
    return JobStatus(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        current_stage=job.current_stage,
        progress_pct=job.progress_pct,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post(
    "/{job_id}/start",
    response_model=JobStatus,
    summary="Start or restart a pipeline job",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def start_job(
    request: Request,
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> JobStatus:
    """Schedule the LangGraph pipeline as a background task for ``job_id``."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Job is already running")

    job.status = "pending"
    job.error = None
    job.progress_pct = 0.0
    job.current_stage = "pending"
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(run_job_pipeline, job.id)
    return _job_to_status(job)


@router.get(
    "/{job_id}",
    response_model=JobStatus,
    summary="Get job status",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def get_job(
    request: Request,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobStatus:
    """Return current status, stage, and progress for a job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_status(job)


@router.get(
    "/{job_id}/tkp",
    response_model=TeacherKnowledgePackage,
    summary="Get Teacher Knowledge Package JSON",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def get_job_tkp(
    request: Request,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TeacherKnowledgePackage:
    """Return the published ``TeacherKnowledgePackage`` for a completed job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    pkg_result = await db.execute(select(TKPPackage).where(TKPPackage.job_id == job_id))
    pkg = pkg_result.scalar_one_or_none()
    if pkg is None:
        raise HTTPException(
            status_code=404,
            detail="TKP not available yet (job may still be running or failed)",
        )
    return TeacherKnowledgePackage.model_validate(pkg.tkp_json)


@router.get(
    "/{job_id}/export/{artifact}",
    summary="Download a PDF artifact",
    dependencies=[Depends(verify_api_key)],
    responses={200: {"content": {"application/pdf": {}}}},
)
@limiter.limit("10/minute")
async def export_artifact(
    request: Request,
    job_id: uuid.UUID,
    artifact: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve ``lesson-plan``, ``teacher-guide``, or ``assessment-book`` PDF.

    Regenerates PDFs on demand if metadata paths are missing.
    """
    if artifact not in _ARTIFACTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown artifact '{artifact}'. Expected one of: {sorted(_ARTIFACTS)}",
        )

    pkg_result = await db.execute(select(TKPPackage).where(TKPPackage.job_id == job_id))
    pkg = pkg_result.scalar_one_or_none()
    if pkg is None:
        raise HTTPException(status_code=404, detail="TKP not available for export")

    tkp = TeacherKnowledgePackage.model_validate(pkg.tkp_json)
    meta = tkp.metadata or {}
    path_str = meta.get(f"pdf_{artifact}")
    path = Path(path_str) if path_str else None

    if path is None or not path.is_file():
        paths = await render_all_pdfs(tkp)
        path_str = paths.get(artifact)
        path = Path(path_str) if path_str else None
        if path is not None:
            meta = dict(meta)
            for name, p in paths.items():
                meta[f"pdf_{name}"] = p
            pkg.tkp_json = {**pkg.tkp_json, "metadata": meta}
            await db.commit()

    if path is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to locate or generate PDF artifact",
        )

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{artifact}-{job_id}.pdf",
    )


@router.get(
    "/{job_id}/eval-report",
    response_model=EvalReportSummary,
    summary="Get evaluation / grounding report",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def get_eval_report(
    request: Request,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EvalReportSummary:
    """Build an ``EvalReportSummary`` from stored grounding scores and validation output."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    outputs = await db.execute(
        select(StageOutput).where(StageOutput.job_id == job_id)
    )
    rows = list(outputs.scalars().all())

    grounding_scores: dict[str, float] = {}
    faithfulness: float | None = None
    details: dict[str, object] = {}

    for row in rows:
        if row.stage_name == "grounding_scores":
            raw = row.output.get("grounding_scores") or {}
            if isinstance(raw, dict):
                grounding_scores = {
                    str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))
                }
        if row.stage_name == "validation":
            details["validation"] = row.output
            gcheck = row.output.get("groundedness_check") or {}
            if isinstance(gcheck, dict) and gcheck.get("score") is not None:
                faithfulness = float(gcheck["score"])

    if faithfulness is None and grounding_scores:
        faithfulness = sum(grounding_scores.values()) / len(grounding_scores)

    return EvalReportSummary(
        job_id=job_id,
        faithfulness=faithfulness,
        relevancy=None,
        grounding_scores=grounding_scores,
        details=details,
    )
