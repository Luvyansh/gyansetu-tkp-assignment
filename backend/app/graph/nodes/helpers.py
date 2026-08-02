"""Shared helpers for graph nodes."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel


def as_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def coerce_model[T: BaseModel](model_type: type[T], value: Any) -> T:
    if isinstance(value, model_type):
        return value
    return model_type.model_validate(value)


def dump_model(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json")


def full_document_text(state: dict[str, Any]) -> str:
    structure = state.get("document_structure")
    if structure is None:
        return ""
    if isinstance(structure, dict):
        return str(structure.get("full_text") or "")
    return str(getattr(structure, "full_text", "") or "")


def truncate(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...truncated...]"


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into ~size character chunks with overlap."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if size <= 0:
        return [cleaned]
    overlap = max(0, min(overlap, size - 1))
    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + size, length)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = end - overlap
    return chunks


def dumps_compact(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, default=str)
