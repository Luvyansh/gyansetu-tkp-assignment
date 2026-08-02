"""Unit tests for pipeline_runner and SSE progress helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.api import deps as deps_mod
from backend.app.api.pipeline_runner import (
    _model_dump_safe,
    _persist_pipeline_result,
    _update_job,
    build_initial_state,
    run_job_pipeline,
)
from backend.tests.factories import make_tkp


def test_model_dump_safe() -> None:
    assert _model_dump_safe(None) is None
    assert _model_dump_safe({"a": 1}) == {"a": 1}
    tkp = make_tkp()
    dumped = _model_dump_safe(tkp)
    assert isinstance(dumped, dict)
    assert dumped["classification"]["subject"] == "Physics"


@pytest.mark.asyncio
async def test_build_initial_state() -> None:
    job = MagicMock()
    job.id = uuid4()
    document = MagicMock()
    document.id = uuid4()
    document.original_filename = "stem.pdf"
    document.doc_type_hint = "mostly_text"
    document.extracted_structure = {"temp_file_path": "/tmp/x.pdf"}

    state = await build_initial_state(job, document)
    assert state["job_id"] == job.id
    assert state["document_id"] == document.id
    assert state["file_path"] == "/tmp/x.pdf"
    assert state["source_filename"] == "stem.pdf"


@pytest.mark.asyncio
async def test_update_job_publishes_progress() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    job = MagicMock()
    job.id = uuid4()
    job.current_stage = "pending"
    job.progress_pct = 0.0
    job.status = "pending"
    job.error = None

    with patch("backend.app.api.pipeline_runner.publish_progress", new_callable=AsyncMock) as pub:
        await _update_job(
            session,
            job,
            status="running",
            current_stage="document_intelligence",
            progress_pct=5.0,
        )
    assert job.status == "running"
    pub.assert_awaited()


@pytest.mark.asyncio
async def test_persist_pipeline_result_creates_tkp() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    existing = MagicMock()
    existing.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=existing)

    job = MagicMock()
    job.id = uuid4()
    document = MagicMock()
    document.id = uuid4()
    tkp = make_tkp(job_id=job.id, document_id=document.id)

    result = {
        "current_stage": "publish",
        "progress_pct": 100.0,
        "classification": tkp.classification.model_dump(mode="json"),
        "knowledge": tkp.knowledge.model_dump(mode="json"),
        "tkp": tkp.model_dump(mode="json"),
        "pdf_artifacts": {"lesson-plan": "/tmp/lp.pdf"},
        "grounding_scores": {"period_1": 0.9},
        "stage_meta": {},
    }
    await _persist_pipeline_result(session, job, document, result)
    assert session.add.call_count >= 2  # stage outputs + TKP
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_job_pipeline_job_missing(mock_session_factory: MagicMock) -> None:
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=empty)

    with patch("backend.app.api.pipeline_runner.AsyncSessionLocal", mock_session_factory):
        await run_job_pipeline(uuid4())


@pytest.mark.asyncio
async def test_run_job_pipeline_success(
    mock_session_factory: MagicMock, sample_tkp, tmp_path: Path
) -> None:
    job_id = sample_tkp.job_id
    doc_id = sample_tkp.document_id
    temp = tmp_path / "upload.pdf"
    temp.write_bytes(b"%PDF-1.4")

    job = MagicMock()
    job.id = job_id
    job.document_id = doc_id
    job.status = "pending"
    job.current_stage = "pending"
    job.progress_pct = 0.0
    job.error = None

    document = MagicMock()
    document.id = doc_id
    document.original_filename = "stem.pdf"
    document.doc_type_hint = "mostly_text"
    document.extracted_structure = {"temp_file_path": str(temp)}

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = document
    empty_pkg = MagicMock()
    empty_pkg.scalar_one_or_none.return_value = None

    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(side_effect=[job_result, doc_result, empty_pkg, empty_pkg])
    session.commit = AsyncMock()
    session.add = MagicMock()

    final_state = {
        "current_stage": "publish",
        "progress_pct": 100.0,
        "error": None,
        "tkp": sample_tkp.model_dump(mode="json"),
        "pdf_artifacts": {"lesson-plan": "/tmp/lp.pdf"},
        "classification": sample_tkp.classification.model_dump(mode="json"),
        "grounding_scores": {},
        "stage_meta": {},
    }

    with (
        patch("backend.app.api.pipeline_runner.AsyncSessionLocal", mock_session_factory),
        patch("backend.app.api.pipeline_runner.publish_progress", new_callable=AsyncMock),
        patch(
            "backend.app.graph.build_graph.run_pipeline",
            new_callable=AsyncMock,
            return_value=final_state,
        ),
        patch("backend.app.api.pipeline_runner.close_progress_queue"),
    ):
        await run_job_pipeline(job_id)

    assert job.status == "completed"
    assert not temp.exists()


@pytest.mark.asyncio
async def test_run_job_pipeline_document_missing(mock_session_factory: MagicMock) -> None:
    job = MagicMock()
    job.id = uuid4()
    job.document_id = uuid4()
    job.status = "pending"
    job.current_stage = "pending"
    job.progress_pct = 0.0
    job.error = None

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = None

    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(side_effect=[job_result, doc_result])
    session.commit = AsyncMock()

    with (
        patch("backend.app.api.pipeline_runner.AsyncSessionLocal", mock_session_factory),
        patch("backend.app.api.pipeline_runner.publish_progress", new_callable=AsyncMock),
        patch("backend.app.api.pipeline_runner.close_progress_queue") as close,
    ):
        await run_job_pipeline(job.id)
    assert job.status == "failed"
    close.assert_called()


@pytest.mark.asyncio
async def test_run_job_pipeline_graph_error(
    mock_session_factory: MagicMock, tmp_path: Path
) -> None:
    job = MagicMock()
    job.id = uuid4()
    job.document_id = uuid4()
    job.status = "pending"
    job.current_stage = "pending"
    job.progress_pct = 0.0
    job.error = None

    document = MagicMock()
    document.id = job.document_id
    document.original_filename = "x.pdf"
    document.doc_type_hint = None
    document.extracted_structure = {}

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = document

    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(side_effect=[job_result, doc_result])
    session.commit = AsyncMock()

    with (
        patch("backend.app.api.pipeline_runner.AsyncSessionLocal", mock_session_factory),
        patch("backend.app.api.pipeline_runner.publish_progress", new_callable=AsyncMock),
        patch(
            "backend.app.graph.build_graph.run_pipeline",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch("backend.app.api.pipeline_runner.close_progress_queue"),
    ):
        await run_job_pipeline(job.id)
    assert job.status == "failed"
    assert "boom" in job.error


@pytest.mark.asyncio
async def test_progress_queue_publish_and_close() -> None:
    job_id = uuid4()
    # Clear any prior state
    deps_mod._progress_queues.clear()
    q = deps_mod.get_progress_queue(job_id)
    await deps_mod.publish_progress(job_id, {"stage": "n1", "progress": 10.0, "status": "running"})
    event = await q.get()
    assert event["stage"] == "n1"
    deps_mod.close_progress_queue(job_id)
    sentinel = await q.get()
    assert sentinel is None
    assert str(job_id) not in deps_mod._progress_queues


@pytest.mark.asyncio
async def test_stream_completed_job(client, auth_headers: dict) -> None:
    job = MagicMock()
    job.id = uuid4()
    job.status = "completed"
    job.current_stage = "publish"
    job.progress_pct = 100.0
    job.error = None

    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    client.mock_db.execute = AsyncMock(return_value=result)

    resp = await client.get(f"/api/v1/jobs/{job.id}/stream", headers=auth_headers)
    assert resp.status_code == 200
    # SSE body should mention completed / publish
    text = resp.text
    assert "completed" in text or "publish" in text


@pytest.mark.asyncio
async def test_stream_job_not_found(client, auth_headers: dict) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    client.mock_db.execute = AsyncMock(return_value=result)
    resp = await client.get(f"/api/v1/jobs/{uuid4()}/stream", headers=auth_headers)
    assert resp.status_code == 404
