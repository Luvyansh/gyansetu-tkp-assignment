"""API tests for jobs, TKP retrieval, PDF export, and eval report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _job_row(**overrides):
    job = MagicMock()
    job.id = overrides.get("id", uuid4())
    job.document_id = overrides.get("document_id", uuid4())
    job.status = overrides.get("status", "completed")
    job.current_stage = overrides.get("current_stage", "publish")
    job.progress_pct = overrides.get("progress_pct", 100.0)
    job.error = overrides.get("error")
    job.created_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    return job


@pytest.mark.asyncio
async def test_get_job_ok(client: AsyncClient, auth_headers: dict) -> None:
    job = _job_row(status="running", current_stage="teaching_planner", progress_pct=40.0)
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["progress_pct"] == 40.0


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient, auth_headers: dict) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/jobs/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_job_schedules_pipeline(client: AsyncClient, auth_headers: dict) -> None:
    job = _job_row(status="pending", current_stage="pending", progress_pct=0.0)
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]
    client.mock_db.commit = AsyncMock()  # type: ignore[attr-defined]
    client.mock_db.refresh = AsyncMock()  # type: ignore[attr-defined]

    with patch("backend.app.api.routes_jobs.run_job_pipeline"):
        resp = await client.post(f"/api/v1/jobs/{job.id}/start", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_start_job_conflict_when_running(client: AsyncClient, auth_headers: dict) -> None:
    job = _job_row(status="running")
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]

    resp = await client.post(f"/api/v1/jobs/{job.id}/start", headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_job_tkp(client: AsyncClient, auth_headers: dict, sample_tkp) -> None:
    job = _job_row(id=sample_tkp.job_id, document_id=sample_tkp.document_id)
    pkg = MagicMock()
    pkg.tkp_json = sample_tkp.model_dump(mode="json")

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    pkg_result = MagicMock()
    pkg_result.scalar_one_or_none.return_value = pkg

    client.mock_db.execute = AsyncMock(side_effect=[job_result, pkg_result])  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/jobs/{job.id}/tkp", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["classification"]["subject"] == "Physics"


@pytest.mark.asyncio
async def test_get_job_tkp_missing(client: AsyncClient, auth_headers: dict) -> None:
    job = _job_row()
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    pkg_result = MagicMock()
    pkg_result.scalar_one_or_none.return_value = None
    client.mock_db.execute = AsyncMock(side_effect=[job_result, pkg_result])  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/jobs/{job.id}/tkp", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_unknown_artifact(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.get(
        f"/api/v1/jobs/{uuid4()}/export/not-a-doc",
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_artifact_regenerates(
    client: AsyncClient, auth_headers: dict, sample_tkp, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "lesson-plan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content for export test")

    pkg = MagicMock()
    pkg.tkp_json = sample_tkp.model_dump(mode="json")
    pkg_result = MagicMock()
    pkg_result.scalar_one_or_none.return_value = pkg
    client.mock_db.execute = AsyncMock(return_value=pkg_result)  # type: ignore[attr-defined]
    client.mock_db.commit = AsyncMock()  # type: ignore[attr-defined]

    with patch(
        "backend.app.api.routes_jobs.render_all_pdfs",
        new_callable=AsyncMock,
        return_value={
            "lesson-plan": str(pdf_path),
            "teacher-guide": str(pdf_path),
            "assessment-book": str(pdf_path),
        },
    ):
        resp = await client.get(
            f"/api/v1/jobs/{sample_tkp.job_id}/export/lesson-plan",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")


@pytest.mark.asyncio
async def test_eval_report(client: AsyncClient, auth_headers: dict) -> None:
    job = _job_row()
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job

    stage_row = MagicMock()
    stage_row.stage_name = "grounding_scores"
    stage_row.output = {"grounding_scores": {"period_1": 0.91, "period_2": 0.88}}
    val_row = MagicMock()
    val_row.stage_name = "validation"
    val_row.output = {"groundedness_check": {"score": 0.9}, "overall_passed": True}

    outputs = MagicMock()
    outputs.scalars.return_value.all.return_value = [stage_row, val_row]

    client.mock_db.execute = AsyncMock(side_effect=[job_result, outputs])  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/jobs/{job.id}/eval-report", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["faithfulness"] == 0.9
    assert body["grounding_scores"]["period_1"] == 0.91


@pytest.mark.asyncio
async def test_get_document_detail(client: AsyncClient, auth_headers: dict) -> None:
    doc = MagicMock()
    doc.id = uuid4()
    doc.original_filename = "chapter.pdf"
    doc.doc_type_hint = "mostly_text"
    doc.created_at = datetime.now(UTC)
    doc.extracted_structure = {"page_count": 3, "parser_route": "pymupdf_text"}

    result = MagicMock()
    result.scalar_one_or_none.return_value = doc
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]

    resp = await client.get(f"/api/v1/documents/{doc.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["page_count"] == 3
    assert resp.json()["parser_route"] == "pymupdf_text"


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient, auth_headers: dict) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    client.mock_db.execute = AsyncMock(return_value=result)  # type: ignore[attr-defined]
    resp = await client.get(f"/api/v1/documents/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
