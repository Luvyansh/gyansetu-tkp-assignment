"""Measure embed + generate API cost against the real NCERT chapter PDF.

Uses ``test_assets/sample_ncert.pdf`` (Shaping of the Earth's Surface) — the same
document that exhausted today's daily embed quota. Clients are mocked; counters
sit on the real GeminiClient batching / router stage→model mapping.
"""

from __future__ import annotations

import math
from collections import Counter
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
from backend.app.llm.gemini_client import (
    DEFAULT_FLASH,
    DEFAULT_FLASH_LITE,
    GeminiClient,
)
from backend.app.llm.router import STAGE_MODELS, LLMRouter
from backend.app.parsing.multimodal_fallback import MultimodalPageResult
from backend.app.parsing.pdf_text import extract_pdf_text, pdf_heuristics
from backend.app.parsing.router import _resolve_route
from backend.app.schemas.document import DocTypeHint
from backend.app.schemas.lesson import PeriodPlan
from backend.app.schemas.validation import CheckStatus, ValidationCheck
from backend.tests.factories import (
    canned_llm_payloads,
    make_document_structure,
    make_period_content,
    make_teaching_plan,
)

NCERT_PDF = Path(__file__).resolve().parents[3] / "test_assets" / "sample_ncert.pdf"
PRE_FIX_LIVE_TEXT_UNITS = 984
TARGET_MAX_EMBED_TEXT_UNITS = 200
FLASH_RPD = 20
FLASH_LITE_RPD = 500

# Live Stage-9 failure for this chapter used a 4-period teaching plan.
LIVE_PERIODS = 4


@dataclass
class EmbedCounter:
    calls: int = 0
    text_units: int = 0
    batch_sizes: list[int] = field(default_factory=list)


@dataclass
class GenerateCounter:
    by_stage: Counter[str] = field(default_factory=Counter)
    by_model: Counter[str] = field(default_factory=Counter)
    multimodal_pages: int = 0
    multimodal_calls: int = 0

    def record(self, stage: str, *, model: str | None = None, pages: int = 0) -> None:
        resolved = model or STAGE_MODELS.get(stage, DEFAULT_FLASH)
        self.by_stage[stage] += 1
        self.by_model[resolved] += 1
        if stage == "multimodal_fallback":
            self.multimodal_calls += 1
            self.multimodal_pages += pages


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


def _ncert_payloads(*, periods: int) -> dict[str, dict[str, Any]]:
    payloads = canned_llm_payloads()
    plan = make_teaching_plan(
        total_periods=periods,
        periods=[
            PeriodPlan(
                period_number=i,
                title=f"Earth surface period {i}",
                duration_minutes=40,
                objectives=[f"Objective {i}"],
                concepts_covered=["weathering", "erosion"],
                pacing_rationale="NCERT chapter coverage",
            )
            for i in range(1, periods + 1)
        ],
    )
    payloads["teaching_planner"] = plan.model_dump(mode="json")
    payloads["classroom_content"] = make_period_content().model_dump(mode="json")
    return payloads


def _build_counting_router(
    embed: EmbedCounter,
    generate: GenerateCounter,
    *,
    embed_store: dict[str, list[float]],
    periods: int,
) -> LLMRouter:
    settings = get_settings()
    gemini = GeminiClient.__new__(GeminiClient)
    aio_models = MagicMock()

    async def _embed_content(**kwargs: Any) -> MagicMock:
        contents = kwargs.get("contents")
        n = len(contents) if isinstance(contents, list) else (0 if contents is None else 1)
        embed.calls += 1
        embed.text_units += n
        embed.batch_sizes.append(n)
        return _mock_embed_response(n)

    async def _generate_content(**kwargs: Any) -> MagicMock:
        # Multimodal / structured generate both land here when using the real client.
        model = kwargs.get("model") or DEFAULT_FLASH
        generate.by_model[str(model)] += 1
        generate.by_stage["_raw_generate_content"] += 1
        mock_resp = MagicMock()
        mock_resp.text = "{}"
        mock_resp.usage_metadata = None
        return mock_resp

    aio_models.embed_content = AsyncMock(side_effect=_embed_content)
    aio_models.generate_content = AsyncMock(side_effect=_generate_content)
    gemini._client = MagicMock()
    gemini._client.aio.models = aio_models

    router = LLMRouter(settings=settings, gemini=gemini, groq=None)
    payloads = _ncert_payloads(periods=periods)

    async def _generate(**kwargs: Any) -> LLMResponse:
        stage = str(kwargs.get("stage_name") or "")
        model = router.model_for_stage(stage)
        generate.record(stage, model=model)
        response_model = kwargs.get("response_model")
        payload = payloads.get(stage)
        if payload is None and response_model is not None:
            if getattr(response_model, "__name__", "") == "PeriodContent":
                payload = payloads["classroom_content"]
            else:
                payload = {}
        content = dict(payload or {})
        input_payload = kwargs.get("input_payload") or {}
        if "period_number" in input_payload:
            content["period_number"] = input_payload["period_number"]
        return LLMResponse(content=content, model=model, latency_ms=1)

    async def _multimodal(**kwargs: Any) -> LLMResponse:
        images = kwargs.get("image_bytes_list") or []
        generate.record("multimodal_fallback", model=DEFAULT_FLASH, pages=len(images))
        return LLMResponse(
            content=MultimodalPageResult(
                page_summary="mock ncert pages",
                figures=[],
                equations=[],
                extra_text="[multimodal mock enrichment]",
            ).model_dump(mode="json"),
            model=DEFAULT_FLASH,
            latency_ms=1,
        )

    router.generate = AsyncMock(side_effect=_generate)  # type: ignore[method-assign]
    router.multimodal = AsyncMock(side_effect=_multimodal)  # type: ignore[method-assign]

    async def _get_cached(_session: Any, hashes: list[str]) -> dict[str, list[float]]:
        return {h: embed_store[h] for h in hashes if h in embed_store}

    async def _put_cached(_session: Any, items: list[tuple[str, list[float]]]) -> None:
        for content_hash, vector in items:
            embed_store[content_hash] = vector

    router._test_get_cached = _get_cached  # type: ignore[attr-defined]
    router._test_put_cached = _put_cached  # type: ignore[attr-defined]
    return router


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


def _rate_cm() -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _initial_state(file_path: str, *, hint: str | None) -> dict[str, Any]:
    return {
        "job_id": uuid4(),
        "document_id": uuid4(),
        "source_filename": Path(file_path).name,
        "doc_type_hint": hint,
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
        "max_validation_retries": 2,
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


@pytest.fixture(scope="module")
def ncert_path() -> Path:
    assert NCERT_PDF.is_file(), f"Place the NCERT chapter at {NCERT_PDF}"
    return NCERT_PDF


@pytest.fixture(scope="module")
def ncert_parse_stats(ncert_path: Path) -> dict[str, Any]:
    heuristics = pdf_heuristics(ncert_path)
    structure = extract_pdf_text(ncert_path)
    text = structure.full_text or ""
    chunks = chunk_text(text, size=500, overlap=50)
    routes = {
        hint.value: _resolve_route(hint, heuristics)
        for hint in (
            DocTypeHint.UNSURE,
            DocTypeHint.TEXT_WITH_DIAGRAMS,
            DocTypeHint.MOSTLY_TEXT,
        )
    }
    # Current multimodal path always takes the first min(page_count, 5) pages —
    # not image-selective (see parse_document).
    mm_pages = min(int(heuristics.get("page_count", 0)), 5)
    return {
        "heuristics": heuristics,
        "chars": len(text),
        "words": len(text.split()),
        "chunks": len(chunks),
        "pages": structure.page_count,
        "figures": len(structure.figures),
        "sections": len(structure.sections),
        "routes": routes,
        "multimodal_pages_if_triggered": mm_pages,
        "structure": structure,
    }


def test_ncert_stage1_real_chunk_and_multimodal_stats(ncert_parse_stats: dict[str, Any]) -> None:
    """Stage 1 facts from the exact failure document — no estimates."""
    h = ncert_parse_stats["heuristics"]
    assert ncert_parse_stats["pages"] == 26
    assert ncert_parse_stats["chunks"] == 72  # measured, not the old ~40 guess
    assert int(h["image_count"]) >= 100
    assert ncert_parse_stats["routes"]["unsure"] == "multimodal"
    assert ncert_parse_stats["routes"]["text_with_diagrams"] == "multimodal"
    assert ncert_parse_stats["routes"]["mostly_text"] == "text"
    # Multimodal is capped at first 5 pages today (not every diagram page).
    assert ncert_parse_stats["multimodal_pages_if_triggered"] == 5
    print(
        f"\n[ncert parse] pages={ncert_parse_stats['pages']} chars={ncert_parse_stats['chars']} "
        f"words={ncert_parse_stats['words']} chunks={ncert_parse_stats['chunks']} "
        f"figures={ncert_parse_stats['figures']} image_count={h['image_count']} "
        f"chars_per_page={h['chars_per_page']:.1f} routes={ncert_parse_stats['routes']} "
        f"multimodal_pages_if_triggered={ncert_parse_stats['multimodal_pages_if_triggered']}"
    )


@pytest.mark.asyncio
async def test_ncert_full_pipeline_api_costs_with_one_retry(
    ncert_path: Path, ncert_parse_stats: dict[str, Any]
) -> None:
    """Full 10-stage run on the real NCERT PDF with counted embed + generate."""
    embed = EmbedCounter()
    generate = GenerateCounter()
    embed_store: dict[str, list[float]] = {}
    router = _build_counting_router(embed, generate, embed_store=embed_store, periods=LIVE_PERIODS)
    validation_rounds = {"n": 0}
    structure = make_document_structure(
        title=ncert_parse_stats["structure"].title or "Shaping of the Earth's Surface",
        page_count=ncert_parse_stats["pages"],
        sections=ncert_parse_stats["structure"].sections,
        full_text=ncert_parse_stats["structure"].full_text,
        figures=ncert_parse_stats["structure"].figures,
        parser_route="pymupdf+gemini_multimodal",
        metadata={
            **(ncert_parse_stats["structure"].metadata or {}),
            **ncert_parse_stats["heuristics"],
            "page_summary": "mock",
        },
    )

    async def _groundedness_gate(state: dict[str, Any]) -> ValidationCheck:
        from backend.app.validation.groundedness import check_groundedness as real_check

        validation_rounds["n"] += 1
        await real_check(state)
        if validation_rounds["n"] == 1:
            return ValidationCheck(
                name="groundedness_check",
                status=CheckStatus.FAIL,
                details="forced retry for ncert cost test",
                score=0.5,
                retry_target="classroom_content",
            )
        return ValidationCheck(
            name="groundedness_check",
            status=CheckStatus.PASS,
            details="ncert cost test pass after retry",
            score=0.95,
            retry_target=None,
        )

    # (parse_document stubbed below — multimodal counted separately)

    session_factory = _session_factory()
    rate_cm = _rate_cm()
    patches = [patch(t, session_factory) for t in NODE_SESSION_TARGETS]
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
                    name="schema_check", status=CheckStatus.PASS, details="ok", score=1.0
                ),
            ),
            patch(
                "backend.app.graph.nodes.n9_validation.check_consistency",
                return_value=ValidationCheck(
                    name="consistency_check", status=CheckStatus.PASS, details="ok", score=1.0
                ),
            ),
        ):
            # Stage-1 multimodal would fire for UNSURE/diagrams (first 5 pages).
            # Count it explicitly — parse itself is stubbed with the measured structure.
            mm = await router.multimodal(
                stage_name="multimodal_fallback",
                system_prompt="x",
                user_prompt="x",
                image_bytes_list=[b"p"] * ncert_parse_stats["multimodal_pages_if_triggered"],
                response_model=MultimodalPageResult,
            )
            assert mm.model == DEFAULT_FLASH

            final = await run_pipeline(
                _initial_state(str(ncert_path), hint=DocTypeHint.UNSURE.value)
            )
    finally:
        for p in patches:
            p.stop()

    chunks = ncert_parse_stats["chunks"]
    assert final.get("current_stage") == "publish"
    assert validation_rounds["n"] == 2
    assert chunks == 72

    # Queries: 4 periods + assessments = 5 per validation round; 2nd round cache-hit.
    queries_per_round = LIVE_PERIODS + 1
    pre_fix_same = chunks + 2 * queries_per_round * (1 + chunks)
    assert embed.text_units <= chunks + queries_per_round * 2
    assert embed.text_units < pre_fix_same

    flash_calls = generate.by_model[DEFAULT_FLASH]
    lite_calls = generate.by_model[DEFAULT_FLASH_LITE]
    # Expected generate shape (1 retry, 4 periods):
    # Flash: multimodal(1) + knowledge(1) + teaching(2) [+ optional judge 0]
    # Lite: class(1) + classroom(8) + activity(2) + assessment(2) + gap(2) = 15
    assert generate.by_stage["multimodal_fallback"] == 1
    assert generate.multimodal_pages == 5
    assert generate.by_stage["classroom_content"] == LIVE_PERIODS * 2
    assert lite_calls >= 15
    assert flash_calls >= 4  # multimodal + knowledge + 2× teaching

    ratio = PRE_FIX_LIVE_TEXT_UNITS / max(embed.text_units, 1)
    flash_runs = math.floor(FLASH_RPD / max(flash_calls, 1))
    lite_runs = math.floor(FLASH_LITE_RPD / max(lite_calls, 1))
    embed_runs = math.floor(1000 / max(embed.text_units, 1))

    print(
        f"\n[ncert full+retry] chunks={chunks} "
        f"embed_calls={embed.calls} embed_text_units={embed.text_units} "
        f"embed_batches={embed.batch_sizes} pre_fix_same_doc={pre_fix_same} "
        f"vs_live_984={ratio:.1f}x "
        f"generate_by_stage={dict(generate.by_stage)} "
        f"generate_by_model={{flash:{flash_calls}, lite:{lite_calls}}} "
        f"multimodal_pages={generate.multimodal_pages} "
        f"projected_runs/day embed~{embed_runs} flash~{flash_runs} lite~{lite_runs}"
    )

    # Soft comfort-band check — still print metrics above; fail only if we regress
    # past the pre-fix live burn for this same document.
    assert embed.text_units < PRE_FIX_LIVE_TEXT_UNITS
    assert embed.text_units <= TARGET_MAX_EMBED_TEXT_UNITS, (
        f"NCERT embed text-units {embed.text_units} exceed comfort band "
        f"{TARGET_MAX_EMBED_TEXT_UNITS}; see ISSUES.md levers"
    )
