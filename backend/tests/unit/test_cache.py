"""LLM / embedding cache key stability tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.llm.cache import (
    cache_key,
    embed_cache_key,
    get_cached_embeddings,
    put_cached_embeddings,
)
from backend.app.llm.gemini_client import DEFAULT_EMBED


def test_cache_key_stable_for_same_inputs() -> None:
    a = cache_key("teaching_planner", {"x": 1, "y": [2, 3]}, "gemini-3.5-flash")
    b = cache_key("teaching_planner", {"y": [2, 3], "x": 1}, "gemini-3.5-flash")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_cache_key_changes_with_stage() -> None:
    a = cache_key("a", "payload", "model")
    b = cache_key("b", "payload", "model")
    assert a != b


def test_cache_key_changes_with_model() -> None:
    a = cache_key("stage", "payload", "model-a")
    b = cache_key("stage", "payload", "model-b")
    assert a != b


def test_cache_key_changes_with_payload() -> None:
    a = cache_key("stage", {"q": "one"}, "m")
    b = cache_key("stage", {"q": "two"}, "m")
    assert a != b


def test_cache_key_handles_non_json_via_default_str() -> None:
    class Obj:
        def __str__(self) -> str:
            return "obj"

    key = cache_key("stage", {"obj": Obj()}, "m")
    assert isinstance(key, str) and len(key) == 64


def test_embed_cache_key_stable_and_model_scoped() -> None:
    a = embed_cache_key("same text", DEFAULT_EMBED)
    b = embed_cache_key("same text", DEFAULT_EMBED)
    c = embed_cache_key("same text", "other-model")
    d = embed_cache_key("other text", DEFAULT_EMBED)
    assert a == b
    assert a != c
    assert a != d


@pytest.mark.asyncio
async def test_get_and_put_cached_embeddings() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    empty = MagicMock()
    empty.all.return_value = []
    session.execute = AsyncMock(return_value=empty)

    key = embed_cache_key("hello", DEFAULT_EMBED)
    await put_cached_embeddings(session, [(key, [0.1, 0.2, 0.3])])
    session.add.assert_called_once()

    row = MagicMock()
    row.content_hash = key
    row.response = {"embedding": [0.1, 0.2, 0.3]}
    hit = MagicMock()
    hit.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=hit)

    found = await get_cached_embeddings(session, [key])
    assert found[key] == [0.1, 0.2, 0.3]
