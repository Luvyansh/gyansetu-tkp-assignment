"""Live Period 3 hallucination must still fail under MiniLM + FAITHFULNESS_THRESHOLD.

Fixture is the real classroom_content (cache hash 473f49e1…) and Stage-3
knowledge chunks from job ``99dcc2bc-694c-4b8e-9ed9-d058fe5bb291``, which
failed live with Gemini embeddings at avg=0.772 / period_3=0.770 because the
LLM judge caught ungrounded weathering definitions and ``agents of gradation``.

Under MiniLM the same Period 3 text scores ~0.80 max-cosine vs all chunks —
high enough that threshold 0.50 would auto-PASS without calling the judge.
Threshold must stay above that score (we keep 0.85).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.config import Settings
from backend.app.llm.local_embeddings import embed_texts, load_embedding_model
from backend.app.llm.router import LLMRouter
from backend.app.schemas.lesson import ClassroomContentBundle, PeriodContent
from backend.app.schemas.validation import CheckStatus
from backend.app.validation.groundedness import (
    _JudgeVerdict,
    _period_text,
    check_groundedness,
    cosine_similarity,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "period3_hallucination_live.json"

# Measured on this fixture with all-MiniLM-L6-v2 (see ISSUES.md).
EXPECTED_MINILM_PERIOD3_MIN = 0.75
EXPECTED_MINILM_PERIOD3_MAX = 0.85  # exclusive upper: must stay below 0.85 gate


def _settings(**overrides: Any) -> Settings:
    data = {
        "gemini_api_key": "g-test",
        "groq_api_key": None,
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "backend_api_key": "test-backend-api-key-32chars!!",
        "faithfulness_threshold": 0.85,
        "embedding_dim": 384,
    }
    data.update(overrides)
    return Settings(**data)


def _load_fixture() -> tuple[PeriodContent, list[str], dict[str, Any]]:
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    p3 = raw["period_3"]
    period = PeriodContent.model_validate(
        {
            "period_number": p3["period_number"],
            "entry_ticket": p3.get("entry_ticket") or "",
            "teacher_script": p3.get("teacher_script") or "",
            "blackboard_notes": p3.get("blackboard_notes") or "",
            "exit_ticket": p3.get("exit_ticket") or "",
            "homework": p3.get("homework") or "",
            "mentor_moment": p3.get("mentor_moment") or "",
            "checkpoint_questions": p3.get("checkpoint_questions") or [],
            "classroom_activities": p3.get("classroom_activities") or [],
        }
    )
    chunks = list(raw["source_chunks_all"])
    assert "agents of gradation" in (period.teacher_script + period.blackboard_notes).lower()
    assert any("weathering" in c.lower() and "erosion" in c.lower() for c in chunks)
    return period, chunks, raw


@pytest.fixture(scope="module")
def period3_fixture() -> tuple[PeriodContent, list[str], dict[str, Any]]:
    assert FIX.is_file(), f"missing fixture {FIX}"
    load_embedding_model()
    return _load_fixture()


@pytest.mark.asyncio
async def test_live_period3_minilm_score_above_050_below_085(
    period3_fixture: tuple[PeriodContent, list[str], dict[str, Any]],
) -> None:
    """Real hallucination is topical enough that MiniLM max-sim >> 0.50."""
    period, chunks, _meta = period3_fixture
    text = _period_text(period)
    vectors = await embed_texts([text, *chunks])
    query, chunk_vecs = vectors[0], vectors[1:]
    score = max(cosine_similarity(query, cv) for cv in chunk_vecs)

    print(
        f"\n[live period3 MiniLM] score={score:.4f} "
        f"threshold_050_would_pass={score >= 0.50} "
        f"threshold_085_would_embed_fail={score < 0.85}"
    )
    assert EXPECTED_MINILM_PERIOD3_MIN <= score < EXPECTED_MINILM_PERIOD3_MAX, (
        f"Unexpected MiniLM score {score:.4f}; recalibrate FAITHFULNESS_THRESHOLD "
        f"if this drifts (must stay < configured gate so the judge still runs)."
    )
    # The bug we are guarding: 0.50 is too low for this real case.
    assert score >= 0.50


@pytest.mark.asyncio
async def test_live_period3_fails_groundedness_at_085(
    period3_fixture: tuple[PeriodContent, list[str], dict[str, Any]],
) -> None:
    """At 0.85 the embedding gate fails open to the judge; judge rejects as live did."""
    period, chunks, _meta = period3_fixture
    settings = _settings(faithfulness_threshold=0.85)
    chunk_vecs = await embed_texts(chunks)
    router = LLMRouter(settings=settings, gemini=MagicMock(), groq=None)

    async def _embed(texts: list[str], **_k: object) -> list[list[float]]:
        return await embed_texts(list(texts))

    router.embed = AsyncMock(side_effect=_embed)  # type: ignore[method-assign]

    async def _judge_like_live(*_a: object, **_k: object) -> _JudgeVerdict:
        return _JudgeVerdict(
            passed=False,
            score=0.35,
            rationale=(
                "Period 3 introduces detailed definitions of weathering and erosion "
                "and the concept of agents of gradation, none of which are present "
                "in the source chunks."
            ),
        )

    state: dict[str, Any] = {
        "knowledge_chunk_texts": chunks,
        "knowledge_chunk_embeddings": chunk_vecs,
        "classroom_content": ClassroomContentBundle(periods=[period]).model_dump(mode="json"),
        "assessments": None,
    }

    with (
        patch("backend.app.validation.groundedness.get_llm_router", return_value=router),
        patch("backend.app.validation.groundedness.get_settings", return_value=settings),
        patch("backend.app.validation.groundedness._llm_judge", side_effect=_judge_like_live),
    ):
        check = await check_groundedness(state)

    period_score = float(state["grounding_scores"]["period_3"])
    print(
        f"\n[live period3 groundedness@0.85] status={check.status.value} "
        f"period_3={period_score:.4f} score={check.score} details={check.details[:180]}"
    )
    assert period_score < settings.faithfulness_threshold
    assert check.status == CheckStatus.FAIL
    assert check.retry_target == "classroom_content"


@pytest.mark.asyncio
async def test_live_period3_incorrectly_passes_at_050(
    period3_fixture: tuple[PeriodContent, list[str], dict[str, Any]],
) -> None:
    """Regression witness: threshold 0.50 auto-passes this hallucination (no judge)."""
    period, chunks, _meta = period3_fixture
    settings = _settings(faithfulness_threshold=0.50)
    chunk_vecs = await embed_texts(chunks)
    router = LLMRouter(settings=settings, gemini=MagicMock(), groq=None)

    async def _embed(texts: list[str], **_k: object) -> list[list[float]]:
        return await embed_texts(list(texts))

    router.embed = AsyncMock(side_effect=_embed)  # type: ignore[method-assign]
    judge = AsyncMock(side_effect=AssertionError("judge must not run when embed score >= 0.50"))

    state: dict[str, Any] = {
        "knowledge_chunk_texts": chunks,
        "knowledge_chunk_embeddings": chunk_vecs,
        "classroom_content": ClassroomContentBundle(periods=[period]).model_dump(mode="json"),
        "assessments": None,
    }

    with (
        patch("backend.app.validation.groundedness.get_llm_router", return_value=router),
        patch("backend.app.validation.groundedness.get_settings", return_value=settings),
        patch("backend.app.validation.groundedness._llm_judge", judge),
    ):
        check = await check_groundedness(state)

    print(
        f"\n[live period3 groundedness@0.50] status={check.status.value} "
        f"score={check.score:.4f} (UNSAFE auto-pass)"
    )
    assert check.status == CheckStatus.PASS
    judge.assert_not_called()
