"""Live Groq fallback exercise — skipped unless real API keys are configured.

Run::

    uv run pytest backend/tests/integration/test_groq_fallback_live.py -m live_llm -s -q --no-cov
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.config import Settings, get_settings
from backend.app.graph.nodes import n9_validation
from backend.app.graph.prompt_loader import load_prompt
from backend.app.llm.gemini_client import GeminiClient
from backend.app.llm.groq_client import DEFAULT_GROQ_MODEL, GroqClient
from backend.app.llm.router import LLMRouter
from backend.app.schemas.assessment import AssessmentBundle
from backend.app.schemas.classification import EducationalClassification
from backend.app.schemas.gap_analysis import GapAnalysis
from backend.app.schemas.lesson import ActivityBundle, ClassroomContentBundle, PeriodContent
from backend.tests.factories import (
    make_classification,
    make_knowledge,
    make_teaching_plan,
)

pytestmark = pytest.mark.live_llm

# Fuller Laws-of-Motion excerpt (matches stem_sample physics paragraphs, no Photosynthesis)
# so Groq pedagogy that mentions inertia stays groundable.
STEM_GROUNDING = (
    "Newton's Laws of Motion. "
    "Newton's first law states that an object at rest stays at rest and an object in "
    "motion stays in motion with the same speed and in the same direction unless acted "
    "upon by an unbalanced force. This is also called the law of inertia. "
    "Newton's second law states that the acceleration of an object is dependent upon two "
    "variables: the net force acting upon the object and the mass of the object. Force "
    "equals mass times acceleration (F = ma). "
    "Newton's third law states that for every action, there is an equal and opposite reaction."
)

_PLACEHOLDER_KEYS = {
    "",
    "test-gemini-key-not-real",
    "test-groq-key-not-real",
    "g-test",
    "groq-test",
    "eval-placeholder-key",
}


def _load_repo_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _live_settings() -> Settings | None:
    _load_repo_env()
    get_settings.cache_clear()
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception:
        return None
    if settings.gemini_api_key in _PLACEHOLDER_KEYS:
        return None
    if not settings.groq_api_key or settings.groq_api_key in _PLACEHOLDER_KEYS:
        return None
    return settings


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    settings = _live_settings()
    if settings is None:
        pytest.skip("Real GEMINI_API_KEY + GROQ_API_KEY required for live Groq fallback test")
    return settings


def _classification_prompts() -> tuple[str, str]:
    system = load_prompt("n2_classification.md")
    user = (
        "Source filename: stem_sample.pdf\n"
        "Document title: Newton's Laws of Motion\n"
        "Doc type hint: unsure\n\n"
        f"Document text:\n{STEM_GROUNDING}"
    )
    return system, user


def _force_gemini_429(gemini: GeminiClient):
    async def boom(**kwargs: Any) -> Any:
        raise Exception(
            "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
            "generate_content_free_tier_requests, limit: 5, model: gemini-3.5-flash-lite"
        )

    return patch.object(gemini, "generate_structured", AsyncMock(side_effect=boom))


@pytest.mark.asyncio
async def test_live_gemini_429_falls_back_to_real_groq(live_settings: Settings) -> None:
    gemini = GeminiClient(live_settings.gemini_api_key)
    groq = GroqClient(live_settings.groq_api_key or "")
    router = LLMRouter(settings=live_settings, gemini=gemini, groq=groq)
    system, user = _classification_prompts()

    with _force_gemini_429(gemini):
        resp = await router.generate(
            stage_name="educational_classification",
            system_prompt=system,
            user_prompt=user,
            response_model=EducationalClassification,
            temperature=0.1,
            input_payload={"live_fallback_probe": str(uuid4())},
        )

    assert resp.model == DEFAULT_GROQ_MODEL
    assert resp.latency_ms > 0
    cls = EducationalClassification.model_validate(resp.content)
    assert cls.subject
    assert cls.topic
    print(
        f"\nFALLBACK ok model={resp.model} latency_ms={resp.latency_ms} "
        f"subject={cls.subject} topic={cls.topic}"
    )


@pytest.mark.asyncio
async def test_live_latency_gemini_vs_groq(live_settings: Settings) -> None:
    gemini = GeminiClient(live_settings.gemini_api_key)
    groq = GroqClient(live_settings.groq_api_key or "")
    system, user = _classification_prompts()

    gemini_resp = await gemini.generate_structured(
        system_prompt=system,
        user_prompt=user,
        response_model=EducationalClassification,
        temperature=0.1,
    )
    groq_resp = await groq.generate_structured(
        system_prompt=system,
        user_prompt=user,
        response_model=EducationalClassification,
        temperature=0.1,
    )
    EducationalClassification.model_validate(gemini_resp.content)
    EducationalClassification.model_validate(groq_resp.content)

    print(
        f"\nLATENCY gemini_ms={gemini_resp.latency_ms} "
        f"groq_ms={groq_resp.latency_ms} "
        f"delta_ms={gemini_resp.latency_ms - groq_resp.latency_ms} "
        f"gemini_model={gemini_resp.model} groq_model={groq_resp.model}"
    )
    assert gemini_resp.latency_ms > 0
    assert groq_resp.latency_ms > 0


@pytest.mark.asyncio
async def test_live_groq_stage_outputs_pass_validation(live_settings: Settings) -> None:
    """Generate GROQ_ELIGIBLE bundles via forced Gemini 429, then run Stage 9."""
    gemini = GeminiClient(live_settings.gemini_api_key)
    groq = GroqClient(live_settings.groq_api_key or "")
    router = LLMRouter(settings=live_settings, gemini=gemini, groq=groq)

    classification = make_classification()
    knowledge = make_knowledge()
    plan = make_teaching_plan(total_periods=1)
    plan.periods = plan.periods[:1]
    grounding = STEM_GROUNDING

    with _force_gemini_429(gemini):
        period_resp = await router.generate(
            stage_name="classroom_content",
            system_prompt=load_prompt("n5_classroom_content.md"),
            user_prompt=(
                f"Classification:\n{classification.model_dump_json()}\n\n"
                f"Extracted knowledge:\n{knowledge.model_dump_json()}\n\n"
                f"Period plan:\n{plan.periods[0].model_dump_json()}\n\n"
                f"Grounding chunks from source:\n{grounding}\n\n"
                "Generate classroom content for period_number=1."
            ),
            response_model=PeriodContent,
            temperature=0.2,
            input_payload={"live_groq_period": str(uuid4())},
        )
        activities_resp = await router.generate(
            stage_name="activity_generation",
            system_prompt=load_prompt("n6_activity_generation.md"),
            user_prompt=(
                f"Classification:\n{classification.model_dump_json()}\n\n"
                f"Knowledge:\n{knowledge.model_dump_json()}\n\n"
                f"Teaching plan:\n{plan.model_dump_json()}\n\n"
                f"Grounding:\n{grounding}"
            ),
            response_model=ActivityBundle,
            temperature=0.2,
            input_payload={"live_groq_acts": str(uuid4())},
        )
        assessments_resp = await router.generate(
            stage_name="assessment_generation",
            system_prompt=load_prompt("n7_assessment_generation.md"),
            user_prompt=(
                f"Classification:\n{classification.model_dump_json()}\n\n"
                f"Knowledge:\n{knowledge.model_dump_json()}\n\n"
                f"Teaching plan:\n{plan.model_dump_json()}\n\n"
                f"Grounding:\n{grounding}"
            ),
            response_model=AssessmentBundle,
            temperature=0.2,
            input_payload={"live_groq_assess": str(uuid4())},
        )
        gaps_resp = await router.generate(
            stage_name="gap_analysis",
            system_prompt=load_prompt("n8_gap_analysis.md"),
            user_prompt=(
                f"Classification:\n{classification.model_dump_json()}\n\n"
                f"Knowledge:\n{knowledge.model_dump_json()}\n\n"
                f"Grounding:\n{grounding}"
            ),
            response_model=GapAnalysis,
            temperature=0.2,
            input_payload={"live_groq_gaps": str(uuid4())},
        )

    assert period_resp.model == DEFAULT_GROQ_MODEL
    assert activities_resp.model == DEFAULT_GROQ_MODEL
    assert assessments_resp.model == DEFAULT_GROQ_MODEL
    assert gaps_resp.model == DEFAULT_GROQ_MODEL

    period = PeriodContent.model_validate(period_resp.content)
    period.period_number = 1
    bundle = ClassroomContentBundle(periods=[period])

    state = {
        "job_id": uuid4(),
        "document_id": uuid4(),
        "classification": classification.model_dump(mode="json"),
        "knowledge": knowledge.model_dump(mode="json"),
        "knowledge_chunk_texts": [STEM_GROUNDING],
        "teaching_plan": plan.model_dump(mode="json"),
        "classroom_content": bundle.model_dump(mode="json"),
        "activities": activities_resp.content,
        "assessments": assessments_resp.content,
        "gap_analysis": gaps_resp.content,
        "validation_retry_count": 0,
        "max_validation_retries": 2,
        "retry_targets": [],
        "validation_feedback": "",
    }

    import backend.app.llm.router as router_mod

    router_mod._router = router
    out = await n9_validation.run(state)
    report = out["validation"]
    print(
        "\nVALIDATION "
        f"overall={report['overall_passed']} "
        f"schema={report['schema_check']['status']} "
        f"groundedness={report['groundedness_check']['status']} "
        f"consistency={report['consistency_check']['status']} "
        f"groundedness_details={str(report['groundedness_check'].get('details', ''))[:300]}"
    )
    assert report["schema_check"]["status"] == "pass"
    assert report["consistency_check"]["status"] in {"pass", "warn"}
    # Groundedness must not hard-fail: Groq is eligible overflow, still bound by Stage 9.
    assert report["groundedness_check"]["status"] in {"pass", "warn"}
    assert report["overall_passed"] is True
