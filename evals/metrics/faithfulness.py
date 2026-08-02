"""Faithfulness metric — ragas when available, else custom groundedness."""

from __future__ import annotations

from typing import Any


async def score_faithfulness(
    *,
    generated_texts: list[str],
    source_chunks: list[str],
    use_ragas: bool = True,
) -> dict[str, Any]:
    """Return ``{"score": float, "method": str, "details": ...}``.

    Tries ragas Faithfulness when ``use_ragas`` and ragas is installed; otherwise
    falls back to average max-cosine groundedness via the app validation helper
    (embeddings mocked/real depending on caller wiring).
    """
    if use_ragas:
        try:
            return await _ragas_faithfulness(generated_texts, source_chunks)
        except Exception as exc:  # noqa: BLE001 — eval fallback is intentional
            ragas_error = str(exc)
    else:
        ragas_error = "disabled"

    from backend.app.validation.groundedness import score_text_against_chunks

    scores: list[float] = []
    for text in generated_texts:
        if not text.strip():
            continue
        scores.append(await score_text_against_chunks(text, source_chunks))
    avg = sum(scores) / len(scores) if scores else 0.0
    return {
        "score": avg,
        "method": "custom_groundedness",
        "details": {"per_text": scores, "ragas_error": ragas_error},
    }


async def _ragas_faithfulness(
    generated_texts: list[str], source_chunks: list[str]
) -> dict[str, Any]:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness

    answer = "\n\n".join(generated_texts)
    contexts = source_chunks[:20] or [""]
    ds = Dataset.from_dict(
        {
            "question": ["Is the teacher content faithful to the source?"],
            "answer": [answer[:8000]],
            "contexts": [contexts],
        }
    )
    result = evaluate(ds, metrics=[faithfulness])
    # ragas returns different shapes across versions
    if "faithfulness" in result:
        score = float(result["faithfulness"])
    else:
        score = float(list(result.values())[0])
    return {"score": score, "method": "ragas", "details": dict(result)}
