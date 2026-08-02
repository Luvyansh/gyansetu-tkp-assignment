"""Groundedness / faithfulness checks against knowledge chunk embeddings."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.db.vector_store import cosine_similarity
from backend.app.llm.router import get_llm_router
from backend.app.logging_config import get_logger
from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.lesson import ClassroomContentBundle, PeriodContent
from backend.app.schemas.validation import CheckStatus, ValidationCheck

logger = get_logger(__name__)


class _JudgeVerdict(BaseModel):
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


_INLINE_JUDGE_SYSTEM = (
    "You are a faithfulness judge for educational content. "
    "Given source knowledge chunks and generated classroom/assessment text, "
    "decide whether the generated content is grounded in the source "
    "(pedagogy and analogies are allowed; invented facts are not). "
    "Respond with JSON matching {passed: bool, score: float, rationale: str} "
    "where score is in [0, 1]."
)


def _period_text(period: PeriodContent) -> str:
    parts = [
        period.entry_ticket,
        period.teacher_script,
        period.blackboard_notes,
        period.exit_ticket,
        period.homework,
        period.mentor_moment,
        " ".join(period.checkpoint_questions),
    ]
    for activity in period.classroom_activities:
        parts.append(activity.name)
        parts.append(activity.instructions)
    return "\n".join(p for p in parts if p).strip()


def _assessment_text(assessments: AssessmentBundle) -> str:
    lines: list[str] = []
    for q in [*assessments.formative, *assessments.summative]:
        lines.append(q.prompt)
        lines.append(q.answer_key)
        if q.options:
            lines.extend(q.options)
    return "\n".join(lines).strip()


def _coerce_classroom(raw: Any) -> ClassroomContentBundle | None:
    if raw is None:
        return None
    if isinstance(raw, ClassroomContentBundle):
        return raw
    return ClassroomContentBundle.model_validate(raw)


def _coerce_assessments(raw: Any) -> AssessmentBundle | None:
    if raw is None:
        return None
    if isinstance(raw, AssessmentBundle):
        return raw
    return AssessmentBundle.model_validate(raw)


async def score_text_against_chunks(text: str, chunks: list[str]) -> float:
    """Average max cosine similarity of ``text`` embedding vs each chunk embedding.

    Returns the mean of per-chunk best-match scores for the query embedding
    against all chunk embeddings (max similarity across chunks).
    """
    cleaned = (text or "").strip()
    usable_chunks = [c.strip() for c in chunks if c and c.strip()]
    if not cleaned or not usable_chunks:
        return 0.0

    router = get_llm_router()
    # Embed query + chunks in one batch when possible
    vectors = await router.embed([cleaned, *usable_chunks])
    if len(vectors) < 2:
        return 0.0

    query_vec = vectors[0]
    chunk_vecs = vectors[1:]
    sims = [cosine_similarity(query_vec, cv) for cv in chunk_vecs]
    return float(max(sims)) if sims else 0.0


async def _llm_judge(text: str, chunks: list[str]) -> _JudgeVerdict:
    router = get_llm_router()
    chunk_preview = "\n---\n".join(chunks[:12])
    user_prompt = (
        f"SOURCE CHUNKS:\n{chunk_preview}\n\n"
        f"GENERATED CONTENT:\n{text[:8000]}\n\n"
        "Judge faithfulness and return structured JSON."
    )

    system_prompt = _INLINE_JUDGE_SYSTEM
    try:
        from backend.app.graph.prompt_loader import load_prompt

        system_prompt = load_prompt("n9_validation_judge.md")
    except (FileNotFoundError, ImportError, OSError):
        logger.info("validation_judge_prompt_fallback", reason="prompt unavailable")

    response = await router.generate(
        stage_name="validation_judge",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=_JudgeVerdict,
        temperature=0.0,
    )
    content = response.content
    if isinstance(content, dict):
        return _JudgeVerdict.model_validate(content)
    return _JudgeVerdict.model_validate(json.loads(str(content)))


async def check_groundedness(state: dict[str, Any]) -> ValidationCheck:
    """Score classroom content / assessments against knowledge_chunk_texts.

    Uses embedding cosine similarity first; if the average is below
    ``settings.faithfulness_threshold``, runs an LLM-as-judge second pass.
    Per-period scores are written into ``state['grounding_scores']`` and
    summarized in ``details``.
    """
    settings = get_settings()
    chunks: list[str] = list(state.get("knowledge_chunk_texts") or [])
    classroom = _coerce_classroom(state.get("classroom_content"))
    assessments = _coerce_assessments(state.get("assessments"))

    grounding_scores: dict[str, float] = {}
    texts_to_score: list[tuple[str, str]] = []

    if classroom is not None:
        for period in classroom.periods:
            label = f"period_{period.period_number}"
            texts_to_score.append((label, _period_text(period)))

    if assessments is not None:
        a_text = _assessment_text(assessments)
        if a_text:
            texts_to_score.append(("assessments", a_text))

    if not texts_to_score:
        check = ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.FAIL,
            details="No classroom content or assessments text to ground",
            score=0.0,
            retry_target="classroom_content",
        )
        state["grounding_scores"] = grounding_scores
        return check

    if not chunks:
        check = ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.FAIL,
            details="No knowledge_chunk_texts available for grounding",
            score=0.0,
            retry_target="classroom_content",
        )
        state["grounding_scores"] = grounding_scores
        return check

    for label, text in texts_to_score:
        if not text.strip():
            grounding_scores[label] = 0.0
            continue
        grounding_scores[label] = await score_text_against_chunks(text, chunks)

    # Persist onto period models in state when possible
    if classroom is not None:
        updated_periods: list[PeriodContent] = []
        for period in classroom.periods:
            score = grounding_scores.get(f"period_{period.period_number}")
            updated_periods.append(period.model_copy(update={"grounding_score": score}))
        state["classroom_content"] = ClassroomContentBundle(periods=updated_periods).model_dump()

    avg_score = (
        sum(grounding_scores.values()) / len(grounding_scores) if grounding_scores else 0.0
    )
    details = (
        f"avg={avg_score:.3f}; "
        + ", ".join(f"{k}={v:.3f}" for k, v in sorted(grounding_scores.items()))
    )
    state["grounding_scores"] = grounding_scores

    if avg_score >= settings.faithfulness_threshold:
        return ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.PASS,
            details=details,
            score=avg_score,
            retry_target=None,
        )

    # Second pass: LLM-as-judge on concatenated generated text
    combined = "\n\n".join(t for _, t in texts_to_score if t.strip())
    try:
        verdict = await _llm_judge(combined, chunks)
        judge_score = float(verdict.score)
        details = f"{details}; judge_passed={verdict.passed}; judge={verdict.rationale}"
        if verdict.passed and judge_score >= settings.faithfulness_threshold * 0.9:
            return ValidationCheck(
                name="groundedness_check",
                status=CheckStatus.PASS,
                details=details,
                score=judge_score,
                retry_target=None,
            )
        return ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.FAIL,
            details=details,
            score=min(avg_score, judge_score),
            retry_target="classroom_content",
        )
    except Exception as exc:
        logger.warning("groundedness_judge_failed", error=str(exc))
        return ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.FAIL,
            details=f"{details}; judge_error={exc}",
            score=avg_score,
            retry_target="classroom_content",
        )
