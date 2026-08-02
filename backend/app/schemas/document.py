"""Document upload and parsing schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocTypeHint(StrEnum):
    MOSTLY_TEXT = "mostly_text"
    TEXT_WITH_TABLES = "text_with_tables"
    TEXT_WITH_DIAGRAMS = "text_with_diagrams"
    TEXT_WITH_EQUATIONS = "text_with_equations"
    SCANNED = "scanned"
    UNSURE = "unsure"


class FigureInfo(BaseModel):
    caption: str | None = None
    page: int | None = None
    description: str | None = Field(
        default=None, description="Multimodal description when available"
    )


class TableInfo(BaseModel):
    page: int | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str | None = None


class EquationInfo(BaseModel):
    latex_or_text: str
    page: int | None = None
    context: str | None = None


class Section(BaseModel):
    heading: str
    level: int = 1
    text: str = ""
    page_start: int | None = None
    page_end: int | None = None
    subsections: list[Section] = Field(default_factory=list)


class DocumentStructure(BaseModel):
    """Structured extraction result — not a flat text blob."""

    title: str | None = None
    page_count: int = 0
    sections: list[Section] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    figures: list[FigureInfo] = Field(default_factory=list)
    equations: list[EquationInfo] = Field(default_factory=list)
    full_text: str = ""
    parser_route: str = "pymupdf_text"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentMeta(BaseModel):
    id: UUID
    original_filename: str
    doc_type_hint: DocTypeHint | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    job_id: UUID
    message: str = "Upload accepted; job created"


class DocumentDetailResponse(BaseModel):
    id: UUID
    original_filename: str
    doc_type_hint: DocTypeHint | None = None
    created_at: datetime
    page_count: int | None = None
    parser_route: str | None = None

    model_config = {"from_attributes": True}
