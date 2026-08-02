"""Post-filter extracted knowledge to the Stage 2 classification scope."""

from __future__ import annotations

import re
from typing import Any

from backend.app.logging_config import get_logger
from backend.app.schemas.knowledge import ExtractedKnowledge

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "class",
        "grade",
        "unit",
        "chapter",
        "topic",
        "subject",
    }
)


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN_RE.findall(text):
        t = raw.lower()
        if len(t) <= 2 or t in _STOP:
            continue
        out.add(t)
        if t.endswith("s") and len(t) > 4:
            out.add(t[:-1])
    return out


def scope_tokens(classification: dict[str, Any] | None) -> set[str]:
    if not classification:
        return set()
    parts = [
        str(classification.get("subject") or ""),
        str(classification.get("topic") or ""),
        str(classification.get("chapter") or ""),
    ]
    return _tokens(" ".join(parts))


def _item_text(*parts: Any) -> str:
    bits: list[str] = []
    for part in parts:
        if part is None:
            continue
        if hasattr(part, "quote"):
            bits.append(str(getattr(part, "quote", "") or ""))
        else:
            bits.append(str(part))
    return " ".join(bits)


def item_in_scope(text: str, scope: set[str]) -> bool:
    """True when item shares a content token with the active scope vocabulary."""
    if not scope:
        return True
    return bool(scope & _tokens(text))


def filter_knowledge_to_scope(
    knowledge: ExtractedKnowledge,
    classification: dict[str, Any] | None,
) -> ExtractedKnowledge:
    """Drop grounded-but-off-topic items relative to Stage 2 classification.

    Pass 1 keeps concepts that overlap the classified subject/topic/chapter.
    Pass 2 keeps other fields that overlap that classification **or** the
    vocabulary of the kept concepts (so "inertia" survives with Newton's laws,
    while "chlorophyll" tied only to Photosynthesis does not).
    """
    scope = scope_tokens(classification)
    if not scope:
        return knowledge

    before = len(knowledge.concepts)
    kept_concepts = [
        c
        for c in knowledge.concepts
        if item_in_scope(_item_text(c.name, c.explanation, c.source_ref), scope)
    ]
    expanded = set(scope)
    for c in kept_concepts:
        expanded |= _tokens(_item_text(c.name, c.explanation, c.source_ref))

    filtered = knowledge.model_copy(
        update={
            "concepts": kept_concepts,
            "learning_objectives": [
                o
                for o in knowledge.learning_objectives
                if item_in_scope(_item_text(o.text, o.source_ref), expanded)
            ],
            "prerequisites": [
                p
                for p in knowledge.prerequisites
                if item_in_scope(_item_text(p.text, p.source_ref), expanded)
            ],
            "definitions": [
                d
                for d in knowledge.definitions
                if item_in_scope(_item_text(d.term, d.definition, d.source_ref), expanded)
            ],
            "formulae": [
                f
                for f in knowledge.formulae
                if item_in_scope(
                    _item_text(f.name, f.expression, f.explanation, f.source_ref),
                    expanded,
                )
            ],
            "keywords": [
                k
                for k in knowledge.keywords
                if item_in_scope(_item_text(k.term, k.source_ref), expanded)
            ],
            "examples": [
                e
                for e in knowledge.examples
                if item_in_scope(_item_text(e.title, e.description, e.source_ref), expanded)
            ],
            "applications": [
                a
                for a in knowledge.applications
                if item_in_scope(_item_text(a.description, a.source_ref), expanded)
            ],
            "common_misconceptions": [
                m
                for m in knowledge.common_misconceptions
                if item_in_scope(_item_text(m.statement, m.correction, m.source_ref), expanded)
            ],
        }
    )
    dropped = before - len(filtered.concepts)
    if dropped:
        logger.info(
            "knowledge_scope_filter_dropped",
            dropped_concepts=dropped,
            kept_concepts=len(filtered.concepts),
            scope_tokens=sorted(scope),
        )
    return filtered
