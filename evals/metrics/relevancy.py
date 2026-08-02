"""Relevancy metric — concept overlap vs golden labels + optional ragas."""

from __future__ import annotations

from typing import Any


def concept_overlap_score(
    extracted_concept_names: list[str],
    expected_concepts: list[str],
) -> dict[str, Any]:
    """Jaccard-like recall of expected concepts found in extracted names."""
    extracted_l = {c.strip().lower() for c in extracted_concept_names if c.strip()}
    expected_l = [c.strip().lower() for c in expected_concepts if c.strip()]
    if not expected_l:
        return {"score": 0.0, "matched": [], "missing": [], "method": "concept_overlap"}

    matched: list[str] = []
    missing: list[str] = []
    for exp in expected_l:
        hit = any(exp in name or name in exp for name in extracted_l)
        if hit:
            matched.append(exp)
        else:
            missing.append(exp)
    score = len(matched) / len(expected_l)
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "method": "concept_overlap",
    }


async def score_relevancy(
    *,
    extracted_concept_names: list[str],
    expected_concepts: list[str],
    generated_summary: str = "",
    source_text: str = "",
    use_ragas: bool = False,
) -> dict[str, Any]:
    base = concept_overlap_score(extracted_concept_names, expected_concepts)
    if not use_ragas:
        return base

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy

        ds = Dataset.from_dict(
            {
                "question": ["Summarize the key teaching concepts"],
                "answer": [generated_summary or ", ".join(extracted_concept_names)],
                "contexts": [[source_text[:4000]]],
            }
        )
        result = evaluate(ds, metrics=[answer_relevancy])
        ragas_score = float(result["answer_relevancy"])
        return {
            **base,
            "ragas_relevancy": ragas_score,
            "score": (base["score"] + ragas_score) / 2,
            "method": "concept_overlap+ragas",
        }
    except Exception as exc:  # noqa: BLE001
        return {**base, "ragas_error": str(exc)}
