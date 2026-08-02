"""Knowledge extraction schemas with source refs for grounding."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Pointer back into the source document — anchors hallucination checks."""

    section: str | None = None
    paragraph: int | None = None
    page: int | None = None
    quote: str | None = Field(default=None, description="Short supporting excerpt")


class LearningObjective(BaseModel):
    text: str
    bloom_level: str | None = None
    source_ref: SourceRef


class Prerequisite(BaseModel):
    text: str
    source_ref: SourceRef | None = None


class Concept(BaseModel):
    name: str
    explanation: str
    source_ref: SourceRef


class Definition(BaseModel):
    term: str
    definition: str
    source_ref: SourceRef


class Formula(BaseModel):
    name: str
    expression: str
    explanation: str | None = None
    source_ref: SourceRef


class Keyword(BaseModel):
    term: str
    source_ref: SourceRef | None = None


class Example(BaseModel):
    title: str
    description: str
    source_ref: SourceRef


class Application(BaseModel):
    description: str
    source_ref: SourceRef | None = None


class Misconception(BaseModel):
    statement: str
    correction: str
    source_ref: SourceRef | None = None


class ExtractedKnowledge(BaseModel):
    """Stage 3 output — every fact-bearing item carries a source_ref."""

    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    formulae: list[Formula] = Field(default_factory=list)
    keywords: list[Keyword] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    common_misconceptions: list[Misconception] = Field(default_factory=list)
