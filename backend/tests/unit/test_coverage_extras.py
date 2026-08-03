"""Extra coverage: config, logging redaction, pdf export, auth helper, graph fail."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.app.config import Settings, get_settings
from backend.app.graph.build_graph import fail_job
from backend.app.logging_config import _redact_secrets, configure_logging, get_logger
from backend.app.pdf_export.render import render_all_pdfs
from backend.app.security.api_key_auth import verify_api_key


def test_settings_cors_and_groq() -> None:
    s = Settings(
        gemini_api_key="g",
        groq_api_key="",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        backend_api_key="test-backend-api-key-32chars!!",
        cors_origins="http://a.com, http://b.com",
    )
    assert s.groq_enabled is False
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_get_settings_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
    get_settings.cache_clear()


def test_logging_redacts_secrets() -> None:
    event = {
        "api_key": "api_key=supersecretvalue",
        "msg": "Authorization: Bearer abcdef1234567890",
        "nested": {"token": "token: xyz"},
        "google": "AIzaSyDummyKeyForTestingOnly123456",
        "groq": "gsk_abcdefghijklmnopqrstuvwxyz12",
        "ok": "plain",
        "list": ["password=hunter2"],
    }
    out = _redact_secrets(None, "info", event)
    assert "[REDACTED]" in out["api_key"]
    assert "[REDACTED]" in out["msg"]
    assert out["ok"] == "plain"
    assert "[REDACTED]" in out["list"][0]


def test_configure_logging_and_get_logger() -> None:
    configure_logging("WARNING")
    log = get_logger("test.coverage")
    log.warning("hello", note="n")


@pytest.mark.asyncio
async def test_render_all_pdfs(sample_tkp, tmp_path: Path) -> None:
    paths = await render_all_pdfs(sample_tkp, output_dir=tmp_path)
    assert set(paths) == {"lesson-plan", "teacher-guide", "assessment-book"}
    for p in paths.values():
        assert Path(p).is_file()
        assert Path(p).stat().st_size > 100


@pytest.mark.asyncio
async def test_verify_api_key_ok(api_key: str) -> None:
    assert await verify_api_key(x_api_key=api_key) == api_key


@pytest.mark.asyncio
async def test_verify_api_key_missing() -> None:
    with pytest.raises(HTTPException) as ei:
        await verify_api_key(x_api_key=None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_fail_job_node() -> None:
    out = await fail_job(
        {
            "validation_feedback": "bad schema",
            "progress_pct": 90,
            "current_stage": "validation",
            "retry_targets": ["classroom_content"],
        }
    )
    # Must report the real last-active stage — never the "failed" sentinel
    # (UI historically mapped that onto Document Intelligence).
    assert out["current_stage"] == "validation"
    assert "bad schema" in out["error"]


@pytest.mark.asyncio
async def test_fail_job_falls_back_to_retry_target() -> None:
    out = await fail_job(
        {
            "validation_feedback": "ungrounded",
            "progress_pct": 90,
            "current_stage": "failed",
            "retry_targets": ["classroom_content"],
        }
    )
    assert out["current_stage"] == "classroom_content"


@pytest.mark.asyncio
async def test_n10_publish_mocked(sample_tkp, mock_session_factory) -> None:
    from backend.app.graph.nodes import n10_publish

    state = {
        "job_id": sample_tkp.job_id,
        "document_id": sample_tkp.document_id,
        "source_filename": sample_tkp.source_filename,
        "classification": sample_tkp.classification.model_dump(mode="json"),
        "knowledge": sample_tkp.knowledge.model_dump(mode="json"),
        "teaching_plan": sample_tkp.teaching_plan.model_dump(mode="json"),
        "classroom_content": sample_tkp.classroom_content.model_dump(mode="json"),
        "activities": sample_tkp.activities.model_dump(mode="json"),
        "assessments": sample_tkp.assessments.model_dump(mode="json"),
        "gap_analysis": sample_tkp.gap_analysis.model_dump(mode="json"),
        "validation": sample_tkp.validation.model_dump(mode="json")
        if sample_tkp.validation
        else None,
        "document_structure": {"parser_route": "pymupdf_text"},
    }
    with (
        patch("backend.app.graph.nodes.n10_publish.AsyncSessionLocal", mock_session_factory),
        patch(
            "backend.app.graph.nodes.n10_publish.render_all_pdfs",
            new_callable=AsyncMock,
            return_value={"lesson-plan": "/tmp/x.pdf"},
        ),
    ):
        out = await n10_publish.run(state)
    assert out["current_stage"] == "publish"
    assert out["tkp"]["classification"]["subject"] == "Physics"
