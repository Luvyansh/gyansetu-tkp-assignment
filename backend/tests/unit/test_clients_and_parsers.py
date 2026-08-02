"""Extra coverage: real docx/pptx parsers, LLM clients, cache I/O, vector helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel, Field

from backend.app.db.vector_store import (
    cosine_similarity,
    fetch_chunks_for_document,
    insert_chunks,
)
from backend.app.llm.base import LLMResponse
from backend.app.llm.cache import cache_key, get_cached, put_cached
from backend.app.llm.gemini_client import GeminiClient
from backend.app.llm.groq_client import GroqClient
from backend.app.parsing.docx_parser import extract_docx
from backend.app.parsing.multimodal_fallback import MultimodalPageResult, enrich_with_multimodal
from backend.app.parsing.pptx_parser import extract_pptx
from backend.app.schemas.validation import CheckStatus
from backend.app.validation.groundedness import check_groundedness
from backend.tests.factories import make_assessments, make_classroom_content


class _Tiny(BaseModel):
    value: str = Field(default="ok")


def test_extract_real_docx(tmp_path: Path) -> None:
    from docx import Document

    path = tmp_path / "lesson.docx"
    doc = Document()
    doc.add_heading("Photosynthesis", level=1)
    doc.add_paragraph("Plants convert light energy into chemical energy.")
    doc.add_heading("Chlorophyll", level=2)
    doc.add_paragraph("Chlorophyll absorbs light in chloroplasts.")
    doc.save(path)

    structure = extract_docx(path)
    assert structure.parser_route == "python_docx"
    assert "Photosynthesis" in (structure.title or "") or "light" in structure.full_text.lower()
    assert structure.page_count == 1
    assert len(structure.sections) >= 1


def test_extract_real_pptx(tmp_path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    path = tmp_path / "slides.pptx"
    prs = Presentation()
    slide_layout = prs.slide_layouts[5]  # blank
    slide = prs.slides.add_slide(slide_layout)
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(2))
    box.text_frame.text = "Inertia keeps objects at rest until a force acts."
    prs.save(path)

    structure = extract_pptx(path)
    assert structure.parser_route == "python_pptx"
    assert structure.page_count == 1
    assert "Inertia" in structure.full_text or "force" in structure.full_text.lower()


@pytest.mark.asyncio
async def test_gemini_generate_structured_mocked() -> None:
    client = GeminiClient.__new__(GeminiClient)
    mock_resp = MagicMock()
    mock_resp.text = '{"value": "hello"}'
    mock_resp.usage_metadata = MagicMock(prompt_token_count=3, candidates_token_count=2)
    aio_models = MagicMock()
    aio_models.generate_content = AsyncMock(return_value=mock_resp)
    client._client = MagicMock()
    client._client.aio.models = aio_models

    with patch("backend.app.llm.gemini_client.types") as types_mod:
        types_mod.GenerateContentConfig = MagicMock(return_value=MagicMock())
        resp = await client.generate_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=_Tiny,
        )
    assert resp.content["value"] == "hello"
    assert resp.latency_ms >= 0


@pytest.mark.asyncio
async def test_gemini_embed_pad_and_empty() -> None:
    client = GeminiClient.__new__(GeminiClient)
    emb = MagicMock()
    emb.values = [0.1, 0.2]
    mock_resp = MagicMock()
    mock_resp.embeddings = [emb]
    mock_resp.embedding = None
    mock_resp.values = None
    aio_models = MagicMock()
    aio_models.embed_content = AsyncMock(return_value=mock_resp)
    client._client = MagicMock()
    client._client.aio.models = aio_models

    assert await client.embed([]) == []
    vectors = await client.embed(["hi"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert vectors[0][0] == pytest.approx(0.1)
    # Single text still sent as a one-element batch (not a per-text loop).
    call_kwargs = aio_models.embed_content.await_args.kwargs
    assert call_kwargs["contents"] == ["hi"]
    assert aio_models.embed_content.await_count == 1


@pytest.mark.asyncio
async def test_gemini_embed_batches_multiple_texts() -> None:
    client = GeminiClient.__new__(GeminiClient)
    emb_a = MagicMock(values=[0.1])
    emb_b = MagicMock(values=[0.2])
    emb_c = MagicMock(values=[0.3])
    mock_resp = MagicMock()
    mock_resp.embeddings = [emb_a, emb_b, emb_c]
    aio_models = MagicMock()
    aio_models.embed_content = AsyncMock(return_value=mock_resp)
    client._client = MagicMock()
    client._client.aio.models = aio_models

    vectors = await client.embed(["a", "b", "c"])
    assert len(vectors) == 3
    assert aio_models.embed_content.await_count == 1
    assert aio_models.embed_content.await_args.kwargs["contents"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_gemini_multimodal_mocked() -> None:
    client = GeminiClient.__new__(GeminiClient)
    mock_resp = MagicMock()
    mock_resp.text = '{"value": "mm"}'
    aio_models = MagicMock()
    aio_models.generate_content = AsyncMock(return_value=mock_resp)
    client._client = MagicMock()
    client._client.aio.models = aio_models

    with patch("backend.app.llm.gemini_client.types") as types_mod:
        types_mod.GenerateContentConfig = MagicMock(return_value=MagicMock())
        types_mod.Part.from_bytes = MagicMock(return_value=MagicMock())
        resp = await client.generate_multimodal(
            system_prompt="sys",
            user_prompt="user",
            image_bytes_list=[b"png"],
            response_model=_Tiny,
        )
    assert resp.content["value"] == "mm"


@pytest.mark.asyncio
async def test_groq_generate_structured_mocked() -> None:
    client = GroqClient.__new__(GroqClient)
    choice = MagicMock()
    choice.message.content = '{"value": "from-groq"}'
    mock_resp = MagicMock()
    mock_resp.choices = [choice]
    mock_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=2)
    client._client = MagicMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

    resp = await client.generate_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=_Tiny,
    )
    assert resp.content["value"] == "from-groq"


@pytest.mark.asyncio
async def test_groq_embed_and_multimodal_unsupported() -> None:
    client = GroqClient.__new__(GroqClient)
    client._client = MagicMock()
    with pytest.raises(NotImplementedError):
        await client.embed(["x"])
    with pytest.raises(NotImplementedError):
        await client.generate_multimodal(
            system_prompt="s",
            user_prompt="u",
            image_bytes_list=[b"x"],
            response_model=_Tiny,
        )


@pytest.mark.asyncio
async def test_get_and_put_cached() -> None:
    session = AsyncMock()
    # miss
    miss = MagicMock()
    miss.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=miss)
    assert await get_cached(session, "deadbeef") is None

    # hit
    row = MagicMock()
    row.response = {"content": {"value": "cached"}, "model": "m"}
    hit = MagicMock()
    hit.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=hit)
    session.commit = AsyncMock()
    cached = await get_cached(session, "abc")
    assert cached["content"]["value"] == "cached"

    # put new
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()
    key = cache_key("stage", {"a": 1}, "model")
    await put_cached(session, key, "stage", {"content": {"ok": True}})
    session.add.assert_called_once()

    # put existing skips
    session.get = AsyncMock(return_value=MagicMock())
    session.add.reset_mock()
    await put_cached(session, key, "stage", {"content": {"ok": True}})
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_insert_and_fetch_chunks_mocked() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    doc_id = uuid4()
    rows = await insert_chunks(
        session,
        doc_id,
        [("chunk one", "Intro", [0.1, 0.2]), ("chunk two", None, None)],
    )
    assert len(rows) == 2
    session.flush.assert_awaited()

    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    fetched = await fetch_chunks_for_document(session, doc_id)
    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_enrich_multimodal_mocked(stem_pdf_path: Path) -> None:
    router = AsyncMock()
    router.multimodal = AsyncMock(
        return_value=LLMResponse(
            content={
                "page_summary": "stem page",
                "figures": [],
                "equations": [{"latex_or_text": "F=ma", "page": 1}],
                "extra_text": "extra",
            },
            model="mock",
            latency_ms=1,
        )
    )
    with patch(
        "backend.app.parsing.multimodal_fallback.render_page_png",
        return_value=b"fakepng",
    ):
        result = await enrich_with_multimodal(stem_pdf_path, router, page_indices=[0])
    assert isinstance(result, MultimodalPageResult)
    assert result.extra_text == "extra"
    assert result.equations[0].latex_or_text == "F=ma"


@pytest.mark.asyncio
async def test_check_groundedness_llm_judge_pass(patch_llm_router: AsyncMock) -> None:
    async def low_sim(texts: list[str]) -> list[list[float]]:
        # Orthogonal-ish vectors → low cosine
        out = []
        for i, _ in enumerate(texts):
            v = [0.0] * 4
            v[i % 4] = 1.0
            out.append(v)
        return out

    patch_llm_router.embed = AsyncMock(side_effect=low_sim)
    patch_llm_router.generate = AsyncMock(
        return_value=LLMResponse(
            content={"passed": True, "score": 0.92, "rationale": "grounded enough"},
            model="mock",
            latency_ms=1,
        )
    )
    state = {
        "knowledge_chunk_texts": ["Newton force inertia"],
        "classroom_content": make_classroom_content().model_dump(mode="json"),
        "assessments": make_assessments().model_dump(mode="json"),
    }
    with patch("backend.app.config.get_settings") as gs:
        settings = MagicMock()
        settings.faithfulness_threshold = 0.99  # force judge path
        gs.return_value = settings
        check = await check_groundedness(state)
    assert check.status == CheckStatus.PASS
    assert check.score is not None and check.score >= 0.9


def test_cosine_similarity_basic() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
