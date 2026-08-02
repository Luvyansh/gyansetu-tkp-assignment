"""Educational classification schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EducationalClassification(BaseModel):
    """Stage 2 output."""

    subject: str = Field(..., description="e.g. Physics, History")
    grade: str = Field(..., description="e.g. Class 9, Grade 10")
    difficulty: str = Field(..., description="introductory | intermediate | advanced")
    topic: str
    chapter: str
    category: str = Field(..., description="STEM | humanities | vocational | other")
    language: str = Field(default="English")
    rationale: str = Field(default="", description="Brief classification rationale")
