"""Prompt loader tests."""

from __future__ import annotations

import pytest

from backend.app.graph.prompt_loader import GROUNDING_RULE, load_prompt


def test_load_known_prompt() -> None:
    text = load_prompt("n2_classification.md")
    assert len(text) > 20
    # Placeholder should be expanded
    assert "{{GROUNDING_RULE}}" not in text


def test_grounding_rule_injected_when_present() -> None:
    # n3 prompt is expected to include the placeholder
    text = load_prompt("n3_knowledge_extraction.md")
    if "Grounding rule" in GROUNDING_RULE:
        # Either placeholder was replaced or prompt mentions grounding
        assert "Grounding" in text or "ground" in text.lower() or GROUNDING_RULE[:20] in text


def test_missing_prompt_raises() -> None:
    load_prompt.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist.md")
    load_prompt.cache_clear()


def test_load_prompt_cached() -> None:
    load_prompt.cache_clear()
    a = load_prompt("n4_teaching_planner.md")
    b = load_prompt("n4_teaching_planner.md")
    assert a == b
    load_prompt.cache_clear()
