"""Prompt loader for graph node templates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

GROUNDING_RULE = (
    "Grounding rule (mandatory): Only use the provided source material for facts, "
    "definitions, formulae, and examples. You may draw on general pedagogy "
    "(analogies, activity ideas, teaching strategies) that does not introduce new "
    "factual claims about the subject matter. Never invent facts not supported by "
    "the source."
)


@lru_cache
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    text = path.read_text(encoding="utf-8")
    return text.replace("{{GROUNDING_RULE}}", GROUNDING_RULE)
