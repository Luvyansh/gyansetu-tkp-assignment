"""Topic-scope filtering for Stage 3 knowledge extraction."""

from __future__ import annotations

from backend.app.graph.nodes.scope_filter import filter_knowledge_to_scope
from backend.app.graph.prompt_loader import load_prompt
from backend.app.schemas.knowledge import (
    Concept,
    Definition,
    ExtractedKnowledge,
    Keyword,
    SourceRef,
)


def _stem_fixture_knowledge() -> ExtractedKnowledge:
    """Mirrors stem_sample.pdf: three Newton concepts + grounded Photosynthesis."""
    section = "Newton's Laws of Motion"
    return ExtractedKnowledge(
        concepts=[
            Concept(
                name="Newton's First Law of Motion",
                explanation="An object at rest stays at rest unless acted on by a force.",
                source_ref=SourceRef(
                    section=section,
                    paragraph=1,
                    quote=(
                        "Newton's first law states that an object at rest stays at rest "
                        "and an object in motion stays in motion"
                    ),
                ),
            ),
            Concept(
                name="Newton's Second Law of Motion",
                explanation="Acceleration depends on net force and mass (F = ma).",
                source_ref=SourceRef(
                    section=section,
                    paragraph=2,
                    quote="Force equals mass times acceleration (F = ma).",
                ),
            ),
            Concept(
                name="Newton's Third Law of Motion",
                explanation="For every action there is an equal and opposite reaction.",
                source_ref=SourceRef(
                    section=section,
                    paragraph=3,
                    quote=(
                        "Newton's third law states that for every action, "
                        "there is an equal and opposite reaction."
                    ),
                ),
            ),
            Concept(
                name="Photosynthesis",
                explanation="Green plants convert light energy into chemical energy.",
                source_ref=SourceRef(
                    section=section,
                    paragraph=4,
                    quote=(
                        "Photosynthesis is the process by which green plants convert "
                        "light energy into chemical energy. Chlorophyll absorbs sunlight; "
                        "carbon dioxide and water produce glucose and oxygen."
                    ),
                ),
            ),
        ],
        definitions=[
            Definition(
                term="Law of inertia",
                definition="Another name for Newton's first law.",
                source_ref=SourceRef(
                    section=section,
                    paragraph=1,
                    quote="This is also called the law of inertia.",
                ),
            ),
            Definition(
                term="Photosynthesis",
                definition="Green plants convert light energy into chemical energy.",
                source_ref=SourceRef(
                    section=section,
                    paragraph=4,
                    quote=(
                        "Photosynthesis is the process by which green plants convert "
                        "light energy into chemical energy."
                    ),
                ),
            ),
        ],
        keywords=[
            Keyword(
                term="inertia",
                source_ref=SourceRef(section=section, paragraph=1, quote="law of inertia"),
            ),
            Keyword(
                term="chlorophyll",
                source_ref=SourceRef(
                    section=section,
                    paragraph=4,
                    quote="Chlorophyll absorbs sunlight",
                ),
            ),
        ],
    )


def test_n3_prompt_requires_topic_scope() -> None:
    load_prompt.cache_clear()
    text = load_prompt("n3_knowledge_extraction.md")
    assert "Topic scope" in text
    assert "unrelated" in text.lower()


def test_scope_filter_excludes_off_topic_photosynthesis() -> None:
    classification = {
        "subject": "Physics",
        "grade": "Class 9",
        "topic": "Laws of Motion",
        "chapter": "Force and Laws of Motion",
        "category": "STEM",
        "language": "English",
        "difficulty": "introductory",
        "rationale": "Newton's laws chapter",
    }
    # Fixture text that Stage 3 would see (in-scope + deliberate off-topic sentence)
    fixture_source = (
        "Newton's Laws of Motion\n"
        "Newton's first law states that an object at rest stays at rest and an object "
        "in motion stays in motion with the same speed and in the same direction unless "
        "acted upon by an unbalanced force.\n"
        "Photosynthesis is the process by which green plants convert light energy into "
        "chemical energy.\n"
    )
    assert "photosynthesis" in fixture_source.lower()
    assert "newton" in fixture_source.lower()

    filtered = filter_knowledge_to_scope(_stem_fixture_knowledge(), classification)
    names = {c.name.lower() for c in filtered.concepts}
    assert "photosynthesis" not in names
    assert any("first law" in n for n in names)
    assert any("second law" in n for n in names)
    assert any("third law" in n for n in names)

    def_terms = {d.term.lower() for d in filtered.definitions}
    assert "photosynthesis" not in def_terms
    assert any("inertia" in t for t in def_terms)

    kw = {k.term.lower() for k in filtered.keywords}
    assert "chlorophyll" not in kw
    assert "inertia" in kw
