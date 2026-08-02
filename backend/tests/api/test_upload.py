"""Document upload validation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _mock_document_job() -> tuple[MagicMock, MagicMock]:
    doc_id = uuid4()
    job_id = uuid4()
    document = MagicMock()
    document.id = doc_id
    document.original_filename = "stem.pdf"
    document.doc_type_hint = None
    document.created_at = datetime.now(UTC)
    document.extracted_structure = {}

    job = MagicMock()
    job.id = job_id
    job.document_id = doc_id
    job.status = "pending"
    return document, job


@pytest.mark.asyncio
async def test_reject_bad_extension(client: AsyncClient, auth_headers: dict) -> None:
    files = {"file": ("notes.txt", BytesIO(b"hello"), "text/plain")}
    resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files)
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reject_bad_magic_bytes(client: AsyncClient, auth_headers: dict) -> None:
    files = {"file": ("fake.pdf", BytesIO(b"NOTAPDF!!!!"), "application/pdf")}
    resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files)
    assert resp.status_code == 400
    assert "magic" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reject_oversized(client: AsyncClient, auth_headers: dict, settings) -> None:
    # Header looks like PDF but body exceeds limit via patched setting
    with patch("backend.app.api.routes_documents.get_settings") as gs:
        mock_settings = MagicMock()
        mock_settings.max_upload_bytes = 10
        gs.return_value = mock_settings
        files = {"file": ("tiny.pdf", BytesIO(b"%PDF-1.4 too-big"), "application/pdf")}
        resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files)
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_reject_empty_file(client: AsyncClient, auth_headers: dict) -> None:
    files = {"file": ("empty.pdf", BytesIO(b""), "application/pdf")}
    resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_accept_tiny_pdf_mocked_pipeline(
    client: AsyncClient, auth_headers: dict, stem_pdf_path: Path
) -> None:
    document, job = _mock_document_job()

    async def refresh(obj):
        if obj is document or getattr(obj, "id", None) == document.id:
            pass
        return None

    client.mock_db.refresh = AsyncMock(side_effect=lambda obj: None)  # type: ignore[attr-defined]
    # Simulate flush assigning IDs
    def add(obj):
        if obj.__class__.__name__ == "Document" or hasattr(obj, "original_filename"):
            obj.id = document.id
            obj.created_at = document.created_at
        if hasattr(obj, "document_id") and hasattr(obj, "status"):
            obj.id = job.id

    client.mock_db.add = MagicMock(side_effect=add)  # type: ignore[attr-defined]
    client.mock_db.flush = AsyncMock()  # type: ignore[attr-defined]
    client.mock_db.commit = AsyncMock()  # type: ignore[attr-defined]

    # The route constructs real Document/Job ORM objects — mock the model classes
    with (
        patch("backend.app.api.routes_documents.Document") as DocCls,
        patch("backend.app.api.routes_documents.Job") as JobCls,
        patch("backend.app.api.routes_documents.run_job_pipeline") as pipeline,
    ):
        DocCls.side_effect = lambda **kw: document
        JobCls.side_effect = lambda **kw: job
        pipeline.return_value = None

        pdf_bytes = stem_pdf_path.read_bytes()
        files = {"file": ("stem_excerpt.pdf", BytesIO(pdf_bytes), "application/pdf")}
        data = {"auto_start": "false", "doc_type_hint": "mostly_text"}
        resp = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files=files,
            data=data,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "document_id" in body
    assert "job_id" in body
