"""Unit tests for local MiniLM embeddings (no network beyond first model cache)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.llm import local_embeddings as le


@pytest.fixture(autouse=True)
def _reset_model() -> None:
    le.reset_embedding_model_for_tests()
    yield
    le.reset_embedding_model_for_tests()


def test_embed_texts_sync_empty() -> None:
    assert le.embed_texts_sync([]) == []


def test_embed_texts_sync_pads_and_truncates() -> None:
    class _Row:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return list(self._values)

    fake_model = MagicMock()
    fake_model.encode.return_value = [
        _Row([0.1, 0.2]),
        _Row([0.1] * (le.LOCAL_EMBED_DIM + 5)),
    ]
    with patch.object(le, "load_embedding_model", return_value=fake_model):
        out = le.embed_texts_sync(["a", "b"])
    assert len(out) == 2
    assert len(out[0]) == le.LOCAL_EMBED_DIM
    assert out[0][0] == pytest.approx(0.1)
    assert out[0][-1] == 0.0
    assert len(out[1]) == le.LOCAL_EMBED_DIM


@pytest.mark.asyncio
async def test_embed_texts_async_empty() -> None:
    assert await le.embed_texts([]) == []


@pytest.mark.asyncio
async def test_ensure_embedding_model_loaded_idempotent() -> None:
    stub = MagicMock()

    def _load() -> MagicMock:
        le._model = stub
        return stub

    with patch.object(le, "load_embedding_model", side_effect=_load) as load:
        await le.ensure_embedding_model_loaded()
        assert le._model is stub
        load.reset_mock()
        await le.ensure_embedding_model_loaded()
        load.assert_not_called()


def test_load_embedding_model_singleton() -> None:
    stub = MagicMock()
    with patch("sentence_transformers.SentenceTransformer", return_value=stub) as ctor:
        a = le.load_embedding_model()
        b = le.load_embedding_model()
    assert a is stub and b is stub
    ctor.assert_called_once()
