"""LLM-as-judge pedagogical quality rubric (scores 1–5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PedagogicalQualityScore(BaseModel):
    """Rubric: clarity / grade_level / feasibility (and related) on 1–5."""

    clarity: int = Field(..., ge=1, le=5)
    grade_level: int = Field(..., ge=1, le=5, description="Age / grade appropriateness")
    feasibility: int = Field(..., ge=1, le=5, description="Classroom feasibility of activities")
    activity_quality: int = Field(..., ge=1, le=5)
    assessment_alignment: int = Field(..., ge=1, le=5)
    overall: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


_RUBRIC_SYSTEM = (
    "You are an education specialist judging a Teacher Knowledge Package. "
    "Score clarity, grade_level, feasibility, activity_quality, and "
    "assessment_alignment each from 1 (poor) to 5 (excellent). "
    "Also provide overall in [0,1] as the mean of the five scores divided by 5. "
    "Respond with JSON matching the schema."
)


def _heuristic_score(tkp_summary: str) -> PedagogicalQualityScore:
    length = len(tkp_summary)
    base = 4 if length > 200 else 3
    overall = base / 5.0
    return PedagogicalQualityScore(
        clarity=base,
        grade_level=base,
        feasibility=base,
        activity_quality=base,
        assessment_alignment=base,
        overall=overall,
        rationale="Heuristic fallback (no LLM judge configured)",
    )


async def score_pedagogical_quality(
    *,
    tkp_summary: str,
    llm_generate: Any | None = None,
    mock_score: PedagogicalQualityScore | None = None,
) -> PedagogicalQualityScore:
    """Score pedagogical quality via LLM judge, or return ``mock_score`` in CI."""
    if mock_score is not None:
        return mock_score

    if llm_generate is None:
        return _heuristic_score(tkp_summary)

    from backend.app.llm.base import LLMResponse

    resp: LLMResponse = await llm_generate(
        stage_name="validation_judge",
        system_prompt=_RUBRIC_SYSTEM,
        user_prompt=f"TKP summary:\n{tkp_summary[:6000]}",
        response_model=PedagogicalQualityScore,
        temperature=0.0,
    )
    return PedagogicalQualityScore.model_validate(resp.content)
