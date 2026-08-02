"""LLM cache key stability tests."""

from __future__ import annotations

from backend.app.llm.cache import cache_key


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
