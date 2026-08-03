"""Groundedness / cosine similarity scoring tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.db.vector_store import cosine_similarity
from backend.app.schemas.validation import CheckStatus
from backend.app.validation.groundedness import check_groundedness, score_text_against_chunks
from backend.tests.factories import (
    make_assessments,
    make_classroom_content,
    make_document_structure,
)


def test_cosine_identical() -> None:
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_mismatched_length() -> None:
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


@pytest.mark.asyncio
async def test_score_text_against_chunks_with_fake_embeddings() -> None:
    async def fake_embed(texts: list[str], **_kwargs: object) -> list[list[float]]:
        # Same text → same vector → high similarity
        out = []
        for t in texts:
            if "newton" in t.lower() or "force" in t.lower():
                out.append([1.0, 0.0, 0.0])
            else:
                out.append([0.0, 1.0, 0.0])
        return out

    router = AsyncMock()
    router.embed = AsyncMock(side_effect=fake_embed)
    with patch("backend.app.validation.groundedness.get_llm_router", return_value=router):
        score = await score_text_against_chunks(
            "Newton force F=ma",
            ["Newton's second law force", "unrelated history"],
        )
    assert score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_score_reuses_provided_chunk_embeddings() -> None:
    """Only the query should be embedded when chunk vectors are supplied."""
    router = AsyncMock()
    router.embed = AsyncMock(return_value=[[1.0, 0.0, 0.0]])
    chunks = ["Newton force", "other"]
    chunk_embs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    with patch("backend.app.validation.groundedness.get_llm_router", return_value=router):
        score = await score_text_against_chunks(
            "Newton force F=ma",
            chunks,
            chunk_embeddings=chunk_embs,
        )
    assert score == pytest.approx(1.0)
    router.embed.assert_awaited_once()
    assert router.embed.await_args.args[0] == ["Newton force F=ma"]


@pytest.mark.asyncio
async def test_score_empty_returns_zero() -> None:
    assert await score_text_against_chunks("", ["chunk"]) == 0.0
    assert await score_text_against_chunks("text", []) == 0.0


@pytest.mark.asyncio
async def test_check_groundedness_pass(patch_llm_router: AsyncMock) -> None:
    # Force high similarity by making embed return identical vectors
    async def high_sim(texts: list[str], **_kwargs: object) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    patch_llm_router.embed = AsyncMock(side_effect=high_sim)
    state = {
        "knowledge_chunk_texts": [make_document_structure().full_text],
        "classroom_content": make_classroom_content().model_dump(mode="json"),
        "assessments": make_assessments().model_dump(mode="json"),
    }
    check = await check_groundedness(state)
    assert check.name == "groundedness_check"
    assert check.status == CheckStatus.PASS
    assert check.score is not None and check.score >= 0.50
    assert "period_1" in state["grounding_scores"]


@pytest.mark.asyncio
async def test_check_groundedness_does_not_reembed_stage3_chunks(
    patch_llm_router: AsyncMock,
) -> None:
    """With Stage-3 vectors in state, only query texts are sent to embed()."""
    chunk = "Newton's laws of motion F=ma inertia"
    chunk_vec = [1.0, 0.0, 0.0]
    calls: list[list[str]] = []

    async def capture_embed(texts: list[str], **_kwargs: object) -> list[list[float]]:
        calls.append(list(texts))
        return [[1.0, 0.0, 0.0] for _ in texts]

    patch_llm_router.embed = AsyncMock(side_effect=capture_embed)
    state = {
        "knowledge_chunk_texts": [chunk],
        "knowledge_chunk_embeddings": [chunk_vec],
        "classroom_content": make_classroom_content().model_dump(mode="json"),
        "assessments": make_assessments().model_dump(mode="json"),
    }
    check = await check_groundedness(state)
    assert check.status == CheckStatus.PASS
    assert calls, "expected at least one embed call for queries"
    for batch in calls:
        assert chunk not in batch
    # One batched call for all query texts (periods + assessments)
    assert len(calls) == 1
    assert len(calls[0]) >= 2


@pytest.mark.asyncio
async def test_check_groundedness_no_content() -> None:
    check = await check_groundedness({"knowledge_chunk_texts": ["x"]})
    assert check.status == CheckStatus.FAIL
    assert "No classroom" in check.details


@pytest.mark.asyncio
async def test_check_groundedness_no_chunks() -> None:
    state = {
        "knowledge_chunk_texts": [],
        "classroom_content": make_classroom_content().model_dump(mode="json"),
    }
    check = await check_groundedness(state)
    assert check.status == CheckStatus.FAIL
    assert "No knowledge_chunk" in check.details
