"""Groundedness / faithfulness checks against knowledge chunk embeddings."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.db.vector_store import cosine_similarity, fetch_chunks_for_document
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


def _as_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _resolve_chunk_embeddings(
    state: dict[str, Any], chunks: list[str]
) -> list[list[float]] | None:
    """Reuse Stage 3 embeddings from state or ``knowledge_chunks`` — never re-embed chunks."""
    cached = state.get("knowledge_chunk_embeddings")
    if (
        isinstance(cached, list)
        and len(cached) == len(chunks)
        and chunks
        and all(isinstance(v, list) and v for v in cached)
    ):
        return [[float(x) for x in v] for v in cached]

    document_id = _as_uuid(state.get("document_id"))
    if document_id is None or not chunks:
        return None

    async with AsyncSessionLocal() as session:
        rows = await fetch_chunks_for_document(session, document_id)

    by_text: dict[str, list[float]] = {}
    for row in rows:
        if row.embedding is None:
            continue
        by_text[row.chunk_text] = [float(x) for x in row.embedding]

    if all(text in by_text for text in chunks):
        return [by_text[text] for text in chunks]
    return None


async def score_text_against_chunks(
    text: str,
    chunks: list[str],
    *,
    chunk_embeddings: list[list[float]] | None = None,
) -> float:
    """Average max cosine similarity of ``text`` embedding vs each chunk embedding.

    When ``chunk_embeddings`` is provided (preferred — from Stage 3 / DB), only the
    query text is embedded. Otherwise falls back to embedding query + chunks once.
    """
    cleaned = (text or "").strip()
    usable_chunks = [c.strip() for c in chunks if c and c.strip()]
    if not cleaned or not usable_chunks:
        return 0.0

    router = get_llm_router()
    if chunk_embeddings is not None and len(chunk_embeddings) == len(usable_chunks):
        query_vecs = await router.embed([cleaned], stage="groundedness_query")
        if not query_vecs:
            return 0.0
        query_vec = query_vecs[0]
        chunk_vecs = chunk_embeddings
    else:
        vectors = await router.embed([cleaned, *usable_chunks], stage="groundedness_fallback")
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

    Chunk vectors are loaded once from Stage 3 state / pgvector and reused —
    generated query texts are the only new embeds.
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

    chunk_embeddings = await _resolve_chunk_embeddings(state, chunks)
    router = get_llm_router()

    # Prefer one query-batch embed + reused chunk vectors (no chunk re-embed).
    nonempty = [(label, text) for label, text in texts_to_score if text.strip()]
    empty_labels = [label for label, text in texts_to_score if not text.strip()]
    for label in empty_labels:
        grounding_scores[label] = 0.0

    if chunk_embeddings is not None and len(chunk_embeddings) == len(chunks) and nonempty:
        query_vecs = await router.embed(
            [text for _, text in nonempty],
            stage="groundedness_queries",
        )
        logger.info(
            "groundedness_scoring",
            queries=len(nonempty),
            chunks=len(chunks),
            chunk_embeds_reused=len(chunk_embeddings),
            query_api_embeds=len(query_vecs),
        )
        for (label, _text), query_vec in zip(nonempty, query_vecs, strict=True):
            sims = [cosine_similarity(query_vec, cv) for cv in chunk_embeddings]
            grounding_scores[label] = float(max(sims)) if sims else 0.0
    else:
        logger.warning(
            "groundedness_chunk_embed_fallback",
            reason="missing Stage-3/DB embeddings — embedding chunks once for this check",
            chunks=len(chunks),
        )
        # Embed chunks once (not per query), then each query.
        chunk_vecs = await router.embed(chunks, stage="groundedness_chunk_fallback")
        state["knowledge_chunk_embeddings"] = chunk_vecs
        for label, text in nonempty:
            grounding_scores[label] = await score_text_against_chunks(
                text, chunks, chunk_embeddings=chunk_vecs
            )

    # Persist onto period models in state when possible
    if classroom is not None:
        updated_periods: list[PeriodContent] = []
        for period in classroom.periods:
            score = grounding_scores.get(f"period_{period.period_number}")
            updated_periods.append(period.model_copy(update={"grounding_score": score}))
        state["classroom_content"] = ClassroomContentBundle(periods=updated_periods).model_dump()

    avg_score = sum(grounding_scores.values()) / len(grounding_scores) if grounding_scores else 0.0
    details = f"avg={avg_score:.3f}; " + ", ".join(
        f"{k}={v:.3f}" for k, v in sorted(grounding_scores.items())
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
