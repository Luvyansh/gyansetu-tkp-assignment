"""Prove post-fix embed_content call reduction with a counting Gemini client.

No live API calls — ``embed_content`` is mocked but invoked through the real
``GeminiClient.embed`` batching path so call counts and text-unit weights match
production RPM accounting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.config import get_settings
from backend.app.graph.build_graph import run_pipeline
from backend.app.graph.nodes.helpers import chunk_text
from backend.app.llm.base import LLMResponse
from backend.app.llm.gemini_client import DEFAULT_EMBED, GeminiClient
from backend.app.llm.router import LLMRouter
from backend.app.parsing.pdf_text import extract_pdf_text
from backend.app.schemas.validation import CheckStatus, ValidationCheck
from backend.tests.factories import canned_llm_payloads, make_document_structure

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "evals" / "golden_dataset"
STEM_GOLDEN = GOLDEN_DIR / "stem_sample.pdf"
HUMANITIES_GOLDEN = GOLDEN_DIR / "humanities_sample.pdf"

# Observed free-tier daily meter when the incomplete Stage-9 job failed today.
PRE_FIX_LIVE_TEXT_UNITS = 984
# Comfortable free-tier budget for multiple full runs per day.
TARGET_MAX_TEXT_UNITS = 200


@dataclass
class EmbedContentCounter:
    """Counts real ``embed_content`` invocations after the embed cache."""

    calls: int = 0
    text_units: int = 0
    batch_sizes: list[int] = field(default_factory=list)


def _mock_embed_response(n: int) -> MagicMock:
    embeddings = []
    for i in range(n):
        emb = MagicMock()
        emb.values = [float((i + 1) % 7) / 7.0] * 768
        embeddings.append(emb)
    resp = MagicMock()
    resp.embeddings = embeddings
    resp.embedding = None
    resp.values = None
    return resp


def _build_counting_router(
    counter: EmbedContentCounter,
    *,
    embed_store: dict[str, list[float]],
) -> LLMRouter:
    """LLMRouter with canned generate + real embed path over a counting Gemini client."""
    settings = get_settings()
    gemini = GeminiClient.__new__(GeminiClient)
    aio_models = MagicMock()

    async def _embed_content(**kwargs: Any) -> MagicMock:
        contents = kwargs.get("contents")
        if isinstance(contents, list):
            n = len(contents)
        elif contents is None:
            n = 0
        else:
            n = 1
        counter.calls += 1
        counter.text_units += n
        counter.batch_sizes.append(n)
        return _mock_embed_response(n)

    aio_models.embed_content = AsyncMock(side_effect=_embed_content)
    gemini._client = MagicMock()
    gemini._client.aio.models = aio_models

    router = LLMRouter(settings=settings, gemini=gemini, groq=None)
    payloads = canned_llm_payloads()

    async def _generate(**kwargs: Any) -> LLMResponse:
        stage = kwargs.get("stage_name") or ""
        response_model = kwargs.get("response_model")
        payload = payloads.get(stage)
        if payload is None and response_model is not None:
            if getattr(response_model, "__name__", "") == "PeriodContent":
                payload = payloads["classroom_content"]
            else:
                payload = {}
        content = dict(payload or {})
        input_payload = kwargs.get("input_payload") or {}
        if "period_number" in input_payload and "period_number" in content:
            content["period_number"] = input_payload["period_number"]
        return LLMResponse(content=content, model="mock-count", latency_ms=1)

    router.generate = AsyncMock(side_effect=_generate)  # type: ignore[method-assign]

    async def _get_cached(_session: Any, hashes: list[str]) -> dict[str, list[float]]:
        return {h: embed_store[h] for h in hashes if h in embed_store}

    async def _put_cached(_session: Any, items: list[tuple[str, list[float]]]) -> None:
        for content_hash, vector in items:
            embed_store[content_hash] = vector

    router._test_get_cached = _get_cached  # type: ignore[attr-defined]
    router._test_put_cached = _put_cached  # type: ignore[attr-defined]
    return router


def _initial_state(file_path: str, *, max_retries: int = 2) -> dict[str, Any]:
    return {
        "job_id": uuid4(),
        "document_id": uuid4(),
        "source_filename": Path(file_path).name,
        "doc_type_hint": "mostly_text",
        "file_path": file_path,
        "document_structure": None,
        "classification": None,
        "knowledge": None,
        "knowledge_chunk_texts": [],
        "knowledge_chunk_embeddings": [],
        "teaching_plan": None,
        "classroom_content": None,
        "activities": None,
        "assessments": None,
        "gap_analysis": None,
        "validation": None,
        "validation_retry_count": 0,
        "max_validation_retries": max_retries,
        "retry_targets": [],
        "validation_feedback": "",
        "tkp": None,
        "pdf_artifacts": {},
        "current_stage": "pending",
        "progress_pct": 0.0,
        "error": None,
        "stage_meta": {},
        "grounding_scores": {},
    }


def _structure_from_pdf(path: Path) -> Any:
    parsed = extract_pdf_text(path)
    return make_document_structure(
        title=parsed.title or path.stem,
        page_count=parsed.page_count,
        sections=parsed.sections,
        full_text=parsed.full_text,
        parser_route=parsed.parser_route or "pymupdf_text",
    )


def _live_scale_structure(base_path: Path, *, target_chunks: int = 40) -> Any:
    """Repeat golden text until chunking matches live STEM upload scale (~40)."""
    base = extract_pdf_text(base_path)
    text = (base.full_text or "").strip() or "Newton force inertia F=ma. "
    expanded = text
    while len(chunk_text(expanded, size=500, overlap=50)) < target_chunks:
        expanded = f"{expanded}\n\n{text}"
    return make_document_structure(
        title=f"{base_path.stem}-live-scale",
        page_count=max(1, base.page_count),
        full_text=expanded,
        parser_route="pymupdf_text",
    )


def _pre_fix_text_units(*, chunks: int, queries_per_validation: int, validations: int) -> int:
    """Old groundedness: embed [query, *chunks] once per scored text, every validation."""
    return chunks + validations * queries_per_validation * (1 + chunks)


def _session_factory() -> MagicMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


def _rate_limit_cm() -> MagicMock:
    rate_cm = MagicMock()
    rate_cm.__aenter__ = AsyncMock(return_value=None)
    rate_cm.__aexit__ = AsyncMock(return_value=None)
    return rate_cm


NODE_SESSION_TARGETS = [
    "backend.app.graph.nodes.n2_educational_classification.AsyncSessionLocal",
    "backend.app.graph.nodes.n3_knowledge_extraction.AsyncSessionLocal",
    "backend.app.graph.nodes.n4_teaching_planner.AsyncSessionLocal",
    "backend.app.graph.nodes.n5_classroom_content.AsyncSessionLocal",
    "backend.app.graph.nodes.n6_activity_generation.AsyncSessionLocal",
    "backend.app.graph.nodes.n7_assessment_generation.AsyncSessionLocal",
    "backend.app.graph.nodes.n8_gap_analysis.AsyncSessionLocal",
    "backend.app.graph.nodes.n10_publish.AsyncSessionLocal",
    "backend.app.validation.groundedness.AsyncSessionLocal",
]


async def run_counted_pipeline(
    *,
    structure: Any,
    file_path: str,
    force_one_retry: bool = True,
    always_fail: bool = False,
) -> tuple[EmbedContentCounter, dict[str, Any], int, int]:
    """Full graph with counting embed_content. Returns counter, state, chunks, val_rounds."""
    counter = EmbedContentCounter()
    embed_store: dict[str, list[float]] = {}
    router = _build_counting_router(counter, embed_store=embed_store)
    validation_rounds = {"n": 0}

    async def _groundedness_gate(state: dict[str, Any]) -> ValidationCheck:
        from backend.app.validation.groundedness import check_groundedness as real_check

        validation_rounds["n"] += 1
        await real_check(state)  # count embeds even when status is overridden
        if always_fail or (force_one_retry and validation_rounds["n"] == 1):
            return ValidationCheck(
                name="groundedness_check",
                status=CheckStatus.FAIL,
                details="forced fail for embed-count test",
                score=0.4,
                retry_target="classroom_content",
            )
        return ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.PASS,
            details="embed-count test pass after retry",
            score=0.95,
            retry_target=None,
        )

    session_factory = _session_factory()
    rate_cm = _rate_limit_cm()
    targets = list(NODE_SESSION_TARGETS)
    if always_fail:
        targets = [t for t in targets if "n10_publish" not in t]

    patches = [patch(t, session_factory) for t in targets]
    for p in patches:
        p.start()
    try:
        with (
            patch(
                "backend.app.graph.nodes.n1_document_intelligence.parse_document",
                new_callable=AsyncMock,
                return_value=structure,
            ),
            patch(
                "backend.app.graph.nodes.n3_knowledge_extraction.insert_chunks",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.app.graph.nodes.n10_publish.render_all_pdfs",
                new_callable=AsyncMock,
                return_value={"lesson-plan": "/tmp/lp.pdf"},
            ),
            patch("backend.app.llm.gemini_client.rate_limited", return_value=rate_cm),
            patch(
                "backend.app.llm.router.get_cached_embeddings",
                side_effect=router._test_get_cached,  # type: ignore[attr-defined]
            ),
            patch(
                "backend.app.llm.router.put_cached_embeddings",
                side_effect=router._test_put_cached,  # type: ignore[attr-defined]
            ),
            patch("backend.app.llm.router.get_llm_router", return_value=router),
            patch(
                "backend.app.graph.nodes.n2_educational_classification.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n3_knowledge_extraction.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n4_teaching_planner.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n5_classroom_content.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n6_activity_generation.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n7_assessment_generation.get_llm_router",
                return_value=router,
            ),
            patch(
                "backend.app.graph.nodes.n8_gap_analysis.get_llm_router",
                return_value=router,
            ),
            patch("backend.app.validation.groundedness.get_llm_router", return_value=router),
            patch(
                "backend.app.graph.nodes.n9_validation.check_groundedness",
                new=_groundedness_gate,
            ),
            patch(
                "backend.app.graph.nodes.n9_validation.check_schema",
                new_callable=AsyncMock,
                return_value=ValidationCheck(
                    name="schema_check",
                    status=CheckStatus.PASS,
                    details="ok",
                    score=1.0,
                ),
            ),
            patch(
                "backend.app.graph.nodes.n9_validation.check_consistency",
                return_value=ValidationCheck(
                    name="consistency_check",
                    status=CheckStatus.PASS,
                    details="ok",
                    score=1.0,
                ),
            ),
        ):
            final = await run_pipeline(_initial_state(file_path))
    finally:
        for p in patches:
            p.stop()

    chunk_count = len(chunk_text(structure.full_text or "", size=500, overlap=50))
    return counter, final, chunk_count, validation_rounds["n"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pdf_path",
    [
        pytest.param(STEM_GOLDEN, id="stem_sample"),
        pytest.param(HUMANITIES_GOLDEN, id="humanities_sample"),
    ],
)
async def test_embed_content_counts_on_golden_with_one_retry(pdf_path: Path) -> None:
    assert pdf_path.is_file(), f"missing golden PDF: {pdf_path}"
    structure = _structure_from_pdf(pdf_path)
    counter, final, chunks, val_rounds = await run_counted_pipeline(
        structure=structure,
        file_path=str(pdf_path),
        force_one_retry=True,
    )

    assert final.get("current_stage") == "publish"
    assert val_rounds == 2  # fail once → retry → pass
    assert chunks >= 1
    # Teaching plan factory: 2 periods + assessments ⇒ 3 groundedness queries / round
    queries_per_round = 3
    pre_fix = _pre_fix_text_units(
        chunks=chunks, queries_per_validation=queries_per_round, validations=val_rounds
    )

    assert counter.text_units <= chunks + queries_per_round * val_rounds
    assert counter.text_units < pre_fix
    assert counter.calls >= 1
    assert counter.text_units < TARGET_MAX_TEXT_UNITS

    ratio_vs_live = PRE_FIX_LIVE_TEXT_UNITS / max(counter.text_units, 1)
    print(
        f"\n[golden {pdf_path.name}] chunks={chunks} val_rounds={val_rounds} "
        f"embed_content_calls={counter.calls} text_units={counter.text_units} "
        f"batches={counter.batch_sizes} pre_fix_same_doc={pre_fix} "
        f"vs_live_984_ratio={ratio_vs_live:.1f}x model={DEFAULT_EMBED}"
    )


@pytest.mark.asyncio
async def test_embed_content_counts_live_scale_stem_with_one_retry() -> None:
    """Live-scale (~40 chunks) projection — comparable to today's Stage-9 failure size."""
    assert STEM_GOLDEN.is_file()
    structure = _live_scale_structure(STEM_GOLDEN, target_chunks=40)
    counter, final, chunks, val_rounds = await run_counted_pipeline(
        structure=structure,
        file_path=str(STEM_GOLDEN),
        force_one_retry=True,
    )

    assert final.get("current_stage") == "publish"
    assert chunks >= 40
    assert val_rounds == 2
    queries_per_round = 3
    pre_fix = _pre_fix_text_units(
        chunks=chunks, queries_per_validation=queries_per_round, validations=val_rounds
    )

    assert counter.text_units <= chunks + queries_per_round * val_rounds
    assert counter.text_units < pre_fix
    assert counter.text_units <= TARGET_MAX_TEXT_UNITS

    ratio_vs_live = PRE_FIX_LIVE_TEXT_UNITS / max(counter.text_units, 1)
    runs_per_day = math.floor(1000 / max(counter.text_units, 1))
    print(
        f"\n[live-scale stem] chunks={chunks} val_rounds={val_rounds} "
        f"embed_content_calls={counter.calls} text_units={counter.text_units} "
        f"batches={counter.batch_sizes} pre_fix_same_doc={pre_fix} "
        f"reduction_vs_pre_fix={pre_fix / max(counter.text_units, 1):.1f}x "
        f"vs_live_984_ratio={ratio_vs_live:.1f}x projected_runs_per_day~{runs_per_day}"
    )


@pytest.mark.asyncio
async def test_embed_content_counts_live_scale_worst_case_retry_exhaustion() -> None:
    """Worst case: validation fails until MAX_VALIDATION_RETRIES exhausts (2 rounds)."""
    structure = _live_scale_structure(STEM_GOLDEN, target_chunks=40)
    counter, final, chunks, val_rounds = await run_counted_pipeline(
        structure=structure,
        file_path=str(STEM_GOLDEN),
        force_one_retry=False,
        always_fail=True,
    )

    assert final.get("error")
    assert val_rounds == 2
    assert counter.text_units <= TARGET_MAX_TEXT_UNITS
    pre_fix = _pre_fix_text_units(chunks=chunks, queries_per_validation=3, validations=2)
    print(
        f"\n[live-scale worst-case exhaust] chunks={chunks} val_rounds={val_rounds} "
        f"embed_content_calls={counter.calls} text_units={counter.text_units} "
        f"batches={counter.batch_sizes} pre_fix_same_doc={pre_fix} "
        f"vs_live_984_ratio={PRE_FIX_LIVE_TEXT_UNITS / max(counter.text_units, 1):.1f}x"
    )
