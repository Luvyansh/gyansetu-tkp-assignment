"""Pytest fixtures: env settings, mock LLM, async client, sample PDFs."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

# Must set env before any backend.app imports that call get_settings().
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-not-real")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key-not-real")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tkp:tkp@localhost:5433/tkp",
)
os.environ.setdefault("BACKEND_API_KEY", "test-backend-api-key-32chars!!")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from backend.app.config import get_settings  # noqa: E402
from backend.app.llm.base import LLMResponse  # noqa: E402
from backend.tests.factories import (  # noqa: E402
    canned_llm_payloads,
    make_classification,
    make_document_structure,
    make_knowledge,
    make_tkp,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
STEM_PDF = FIXTURES_DIR / "stem_excerpt.pdf"
SAMPLE_TXT = FIXTURES_DIR / "sample_excerpt.txt"

API_KEY = os.environ["BACKEND_API_KEY"]


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def api_key() -> str:
    return API_KEY


@pytest.fixture
def stem_pdf_path() -> Path:
    assert STEM_PDF.is_file(), f"Missing fixture PDF: {STEM_PDF}"
    return STEM_PDF


@pytest.fixture
def sample_excerpt() -> str:
    return SAMPLE_TXT.read_text(encoding="utf-8")


@pytest.fixture
def document_structure():
    return make_document_structure()


@pytest.fixture
def classification():
    return make_classification()


@pytest.fixture
def knowledge():
    return make_knowledge()


@pytest.fixture
def sample_tkp():
    return make_tkp()


@pytest.fixture
def mock_async_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_session_factory(mock_async_session: AsyncMock) -> MagicMock:
    """AsyncSessionLocal-compatible factory returning an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_async_session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)
    return factory


@pytest.fixture
def canned_payloads() -> dict[str, dict[str, Any]]:
    return canned_llm_payloads()


@pytest.fixture
def mock_llm_router(canned_payloads: dict[str, dict[str, Any]]) -> AsyncMock:
    """LLM router that returns canned structured payloads and fake embeddings."""

    router = AsyncMock()

    async def _generate(**kwargs: Any) -> LLMResponse:
        stage = kwargs.get("stage_name") or ""
        response_model = kwargs.get("response_model")
        payload = canned_payloads.get(stage)
        if payload is None and response_model is not None:
            # Period content stage reuses classroom_content key
            if response_model.__name__ == "PeriodContent":
                payload = canned_payloads["classroom_content"]
            else:
                payload = {}
        # Align period_number when generating per-period content
        content = dict(payload or {})
        input_payload = kwargs.get("input_payload") or {}
        if "period_number" in input_payload and "period_number" in content:
            content["period_number"] = input_payload["period_number"]
        return LLMResponse(
            content=content,
            model="mock-gemini",
            latency_ms=1,
            token_usage={"prompt": 10, "completion": 20},
            cached=False,
        )

    async def _embed(texts: list[str], **_kwargs: Any) -> list[list[float]]:
        # Deterministic pseudo-embeddings: bag-of-char hash into 8 dims
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * 8
            for i, ch in enumerate(text.lower()):
                vec[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    async def _multimodal(**kwargs: Any) -> LLMResponse:
        return LLMResponse(
            content={"figures": [], "equations": [], "extra_text": "", "page_summary": "mock"},
            model="mock-gemini-mm",
            latency_ms=1,
        )

    router.generate = AsyncMock(side_effect=_generate)
    router.embed = AsyncMock(side_effect=_embed)
    router.multimodal = AsyncMock(side_effect=_multimodal)
    router.model_for_stage = MagicMock(return_value="mock-gemini")
    return router


@pytest.fixture
def patch_llm_router(mock_llm_router: AsyncMock) -> Iterator[AsyncMock]:
    with (
        patch("backend.app.llm.router.get_llm_router", return_value=mock_llm_router),
        patch(
            "backend.app.graph.nodes.n2_educational_classification.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n3_knowledge_extraction.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n4_teaching_planner.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n5_classroom_content.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n6_activity_generation.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n7_assessment_generation.get_llm_router",
            return_value=mock_llm_router,
        ),
        patch(
            "backend.app.graph.nodes.n8_gap_analysis.get_llm_router", return_value=mock_llm_router
        ),
        patch("backend.app.validation.groundedness.get_llm_router", return_value=mock_llm_router),
    ):
        yield mock_llm_router


@pytest.fixture
def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI test client with DB health and pipeline mocked for isolation."""
    with patch("backend.app.main.check_db_connection", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = True
        # Import after env is set
        from backend.app.main import create_app

        app = create_app()

        # Override get_db with a lightweight mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        async def _override_db():
            yield mock_session

        from backend.app.api.deps import get_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Attach helpers for tests that need the session mock
            ac.app = app  # type: ignore[attr-defined]
            ac.mock_db = mock_session  # type: ignore[attr-defined]
            yield ac

        app.dependency_overrides.clear()


@pytest.fixture
def job_ids() -> dict[str, Any]:
    return {"job_id": uuid4(), "document_id": uuid4()}
