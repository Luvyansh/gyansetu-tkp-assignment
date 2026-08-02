"""SSE progress streaming for pipeline jobs."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend.app.api.deps import get_db, get_progress_queue, limiter, verify_api_key
from backend.app.db.models import Job
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.tkp import StreamEvent

router = APIRouter(prefix="/jobs", tags=["stream"])


@router.get(
    "/{job_id}/stream",
    summary="SSE progress stream for a job",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def stream_job_progress(
    request: Request,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream ``StreamEvent`` JSON payloads as the job progresses.

    Prefers the in-memory progress queue; falls back to polling the DB every 1s
    when no queue events arrive.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = get_progress_queue(job_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        # Immediate snapshot
        snapshot = StreamEvent(
            stage=job.current_stage or "pending",
            progress=job.progress_pct,
            message=f"Job status: {job.status}",
            status=job.status,
        )
        yield {"event": "progress", "data": snapshot.model_dump_json()}

        if job.status in {"completed", "failed"}:
            yield {
                "event": "done",
                "data": StreamEvent(
                    stage=job.current_stage or job.status,
                    progress=job.progress_pct,
                    message=job.error or "Job finished",
                    status=job.status,
                ).model_dump_json(),
            }
            return

        terminal = {"completed", "failed"}
        while True:
            if await request.is_disconnected():
                break

            event = None
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                # DB poll fallback
                async with AsyncSessionLocal() as session:
                    row = await session.execute(select(Job).where(Job.id == job_id))
                    current = row.scalar_one_or_none()
                if current is None:
                    break
                poll_event = StreamEvent(
                    stage=current.current_stage or "unknown",
                    progress=current.progress_pct,
                    message=current.error or f"Job status: {current.status}",
                    status=current.status,
                )
                yield {"event": "progress", "data": poll_event.model_dump_json()}
                if current.status in terminal:
                    yield {"event": "done", "data": poll_event.model_dump_json()}
                    break
                continue

            if event is None:
                # Sentinel from close_progress_queue — final DB read
                async with AsyncSessionLocal() as session:
                    row = await session.execute(select(Job).where(Job.id == job_id))
                    current = row.scalar_one_or_none()
                if current is not None:
                    done = StreamEvent(
                        stage=current.current_stage or current.status,
                        progress=current.progress_pct,
                        message=current.error or "Job finished",
                        status=current.status,
                    )
                    yield {"event": "done", "data": done.model_dump_json()}
                break

            try:
                stream_event = StreamEvent.model_validate(event)
            except Exception:
                stream_event = StreamEvent(
                    stage=str(event.get("stage", "unknown")),
                    progress=float(event.get("progress", 0.0)),
                    message=str(event.get("message", "")),
                    status=str(event.get("status", "running")),
                )
            yield {"event": "progress", "data": stream_event.model_dump_json()}
            if stream_event.status in terminal:
                yield {"event": "done", "data": stream_event.model_dump_json()}
                break

    return EventSourceResponse(event_generator())
