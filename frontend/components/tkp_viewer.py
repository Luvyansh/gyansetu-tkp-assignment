"""Tabbed Teacher Knowledge Package viewer with grounded, reviewable surfaces."""

from __future__ import annotations

from typing import Any

import streamlit as st
from backend.app.security.sanitize import sanitize_html


def _safe(text: Any) -> str:
    if text is None:
        return ""
    return sanitize_html(str(text))


def _md_block(title: str, body: str) -> None:
    st.markdown(
        f'<div class="gs-content-block"><h4>{_safe(title)}</h4><p>{_safe(body)}</p></div>',
        unsafe_allow_html=True,
    )


def _chips(items: list[str]) -> None:
    if not items:
        return
    chips = "".join(f'<span class="gs-chip">{_safe(i)}</span>' for i in items)
    st.markdown(f'<div class="gs-chips">{chips}</div>', unsafe_allow_html=True)


def _source_ref(ref: dict[str, Any] | None) -> str:
    if not ref:
        return ""
    parts: list[str] = []
    if ref.get("section"):
        parts.append(f"§ {_safe(ref['section'])}")
    if ref.get("page") is not None:
        parts.append(f"p.{ref['page']}")
    if ref.get("quote"):
        parts.append(f'“{_safe(ref["quote"])}”')
    return " · ".join(parts)


def _render_overview(tkp: dict[str, Any]) -> None:
    classification = tkp.get("classification") or {}
    knowledge = tkp.get("knowledge") or {}
    plan = tkp.get("teaching_plan") or {}
    validation = tkp.get("validation")

    cols = st.columns(4)
    meta = [
        ("Subject", classification.get("subject", "—")),
        ("Grade", classification.get("grade", "—")),
        ("Topic", classification.get("topic", "—")),
        ("Periods", str(plan.get("total_periods", "—"))),
    ]
    for col, (label, value) in zip(cols, meta, strict=True):
        with col, st.container(border=True):
            st.caption(label)
            st.markdown(
                f'<strong class="gs-tabular">{_safe(value)}</strong>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<h2 class="gs-section-title">Classification</h2>',
        unsafe_allow_html=True,
    )
    _md_block(
        f"{classification.get('chapter', 'Chapter')} · {classification.get('category', '')}",
        classification.get("rationale")
        or f"Difficulty: {classification.get('difficulty', '—')} · "
        f"Language: {classification.get('language', '—')}",
    )

    objectives = knowledge.get("learning_objectives") or []
    if objectives:
        st.markdown('<h2 class="gs-section-title">Learning objectives</h2>', unsafe_allow_html=True)
        for obj in objectives:
            bloom = obj.get("bloom_level") or ""
            badge = f' <span class="gs-badge amber">{_safe(bloom)}</span>' if bloom else ""
            st.markdown(
                f'<div class="gs-content-block"><h4>{_safe(obj.get("text", ""))}{badge}</h4>'
                f"<p>{_source_ref(obj.get('source_ref'))}</p></div>",
                unsafe_allow_html=True,
            )

    concepts = knowledge.get("concepts") or []
    if concepts:
        st.markdown('<h2 class="gs-section-title">Key concepts</h2>', unsafe_allow_html=True)
        _chips([c.get("name", "") for c in concepts if c.get("name")])

    if validation:
        passed = validation.get("overall_passed")
        st.markdown('<h2 class="gs-section-title">Validation</h2>', unsafe_allow_html=True)
        st.markdown(
            f'<span class="gs-badge{" amber" if not passed else ""}">'
            f"{'Passed' if passed else 'Needs review'}</span>",
            unsafe_allow_html=True,
        )


def _render_teaching_plan(tkp: dict[str, Any]) -> None:
    plan = tkp.get("teaching_plan") or {}
    if plan.get("overall_rationale"):
        _md_block("Plan rationale", plan["overall_rationale"])

    periods = plan.get("periods") or []
    if periods and any(p.get("concepts_covered") for p in periods):
        try:
            import plotly.express as px

            rows = [
                {
                    "Period": f"P{p.get('period_number', '?')}: {str(p.get('title', ''))[:28]}",
                    "Concepts": len(p.get("concepts_covered") or []),
                }
                for p in periods
            ]
            fig = px.bar(
                rows,
                x="Period",
                y="Concepts",
                title="Concept coverage per period",
                color_discrete_sequence=["#533afd"],
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#f6f9fc",
                font_family="Inter",
                title_font_family="Inter",
                title_font_color="#0d253d",
                margin=dict(t=48, b=40, l=40, r=20),
                height=320,
            )
            st.plotly_chart(fig, width="stretch")
        except Exception:
            pass

    for period in periods:
        with st.expander(
            f"Period {period.get('period_number', '?')}: {period.get('title', 'Untitled')} "
            f"({period.get('duration_minutes', '?')} min)",
            expanded=period.get("period_number") == 1,
        ):
            objectives = period.get("objectives") or []
            if objectives:
                st.markdown("**Objectives**")
                for objective in objectives:
                    st.markdown(f"- {_safe(objective)}")
            concepts = period.get("concepts_covered") or []
            if concepts:
                st.markdown("**Concepts covered**")
                _chips(concepts)
            if period.get("pacing_rationale"):
                _md_block("Pacing", period["pacing_rationale"])


def _render_content(tkp: dict[str, Any]) -> None:
    bundle = tkp.get("classroom_content") or {}
    periods = bundle.get("periods") or []
    activities = (tkp.get("activities") or {}).get("activities") or []

    for period_content in periods:
        with st.expander(
            f"Period {period_content.get('period_number', '?')} — classroom flow",
            expanded=False,
        ):
            for label, key in [
                ("Entry ticket", "entry_ticket"),
                ("Teacher script", "teacher_script"),
                ("Blackboard notes", "blackboard_notes"),
                ("Exit ticket", "exit_ticket"),
                ("Homework", "homework"),
                ("Mentor moment", "mentor_moment"),
            ]:
                if period_content.get(key):
                    _md_block(label, period_content[key])
            checks = period_content.get("checkpoint_questions") or []
            if checks:
                st.markdown("**Checkpoints**")
                for question in checks:
                    st.markdown(f"- {_safe(question)}")
            for activity in period_content.get("classroom_activities") or []:
                _md_block(
                    f"{activity.get('name', 'Activity')} ({activity.get('activity_type', '')})",
                    activity.get("instructions") or activity.get("success_criteria") or "",
                )

    if activities:
        st.markdown('<h2 class="gs-section-title">Unit activities</h2>', unsafe_allow_html=True)
        for activity in activities:
            materials = ", ".join(activity.get("materials") or []) or "—"
            _md_block(
                f"{activity.get('name', 'Activity')} · {activity.get('duration_minutes', '?')} min",
                f"{activity.get('instructions', '')}\nMaterials: {materials}",
            )


def _render_assessments(tkp: dict[str, Any]) -> None:
    assessments = tkp.get("assessments") or {}
    total = assessments.get("total_marks")
    if total is not None:
        st.markdown(
            f'<span class="gs-badge">Total marks: '
            f'<span class="gs-tabular">{_safe(total)}</span></span>',
            unsafe_allow_html=True,
        )

    def _questions(title: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        st.markdown(f'<h2 class="gs-section-title">{_safe(title)}</h2>', unsafe_allow_html=True)
        for index, question in enumerate(items, 1):
            options = question.get("options") or []
            opt_html = ""
            if options:
                opt_html = (
                    "<ul>"
                    + "".join(f"<li>{_safe(option)}</li>" for option in options)
                    + "</ul>"
                )
            concepts = question.get("concepts_tested") or []
            st.markdown(
                f'<div class="gs-content-block"><h4>Q{index}. '
                f'[{_safe(question.get("question_type", ""))}] '
                f"{_safe(question.get('prompt', ''))}</h4>{opt_html}"
                f"<p><strong>Answer:</strong> {_safe(question.get('answer_key', ''))}</p>"
                f"<p>{_safe(question.get('rubric') or '')}</p></div>",
                unsafe_allow_html=True,
            )
            if concepts:
                _chips(concepts)

    _questions("Formative", assessments.get("formative") or [])
    _questions("Summative", assessments.get("summative") or [])


def _render_gap_analysis(tkp: dict[str, Any]) -> None:
    gap = tkp.get("gap_analysis") or {}
    if gap.get("summary"):
        _md_block("Summary", gap["summary"])
    for item in gap.get("gaps") or []:
        severity = (item.get("severity") or "medium").lower()
        st.markdown(
            f'<div class="gs-content-block"><h4>{_safe(item.get("misconception", ""))} '
            f'<span class="gs-badge{" amber" if severity != "low" else ""}">'
            f"{_safe(severity)}</span></h4>"
            f"<p><strong>Diagnostic:</strong> "
            f"{_safe(item.get('diagnostic_question', ''))}</p>"
            f"<ul>"
            + "".join(
                f"<li>{_safe(action)}</li>"
                for action in (item.get("remedial_actions") or [])
            )
            + "</ul></div>",
            unsafe_allow_html=True,
        )
        related = item.get("related_concepts") or []
        if related:
            _chips(related)


def _render_sources(tkp: dict[str, Any]) -> None:
    knowledge = tkp.get("knowledge") or {}
    st.markdown(
        f'<p class="gs-dropzone-hint" style="margin-top:0;">Source anchors from '
        f"<strong>{_safe(tkp.get('source_filename') or 'uploaded document')}</strong>. "
        "Every fact-bearing item should point back into the chapter.</p>",
        unsafe_allow_html=True,
    )

    sections = [
        ("Concepts", knowledge.get("concepts") or [], "name", "explanation"),
        ("Definitions", knowledge.get("definitions") or [], "term", "definition"),
        ("Formulae", knowledge.get("formulae") or [], "name", "expression"),
        ("Examples", knowledge.get("examples") or [], "title", "description"),
    ]
    for title, items, name_key, body_key in sections:
        if not items:
            continue
        st.markdown(f'<h2 class="gs-section-title">{title}</h2>', unsafe_allow_html=True)
        for item in items:
            ref = _source_ref(item.get("source_ref"))
            st.markdown(
                f'<div class="gs-content-block"><h4>{_safe(item.get(name_key, ""))}</h4>'
                f"<p>{_safe(item.get(body_key, ''))}</p>"
                f"<p class=\"gs-muted\">{ref}</p></div>",
                unsafe_allow_html=True,
            )

    keywords = knowledge.get("keywords") or []
    if keywords:
        st.markdown('<h2 class="gs-section-title">Keywords</h2>', unsafe_allow_html=True)
        _chips([keyword.get("term", "") for keyword in keywords if keyword.get("term")])


def render_tkp(tkp: dict[str, Any]) -> None:
    """Render a full TKP with Overview / Plan / Content / Assessments / Gaps / Sources."""
    if not tkp:
        st.markdown(
            '<div class="gs-empty-state"><h2>No classroom package to display</h2>'
            '<p>Return to upload and generate a package from a source chapter.</p></div>',
            unsafe_allow_html=True,
        )
        return

    header = tkp.get("classification") or {}
    plan = tkp.get("teaching_plan") or {}
    knowledge = tkp.get("knowledge") or {}
    assessments = tkp.get("assessments") or {}
    period_count = plan.get("total_periods", "—")
    concept_count = len(knowledge.get("concepts") or [])
    question_count = len(assessments.get("formative") or []) + len(
        assessments.get("summative") or []
    )
    faithfulness = (tkp.get("validation") or {}).get("faithfulness_score", "—")
    st.markdown(
        f'<div class="gs-review-shell"><p class="gs-eyebrow" '
        'style="color:#b9b9f9 !important;">Grounded classroom output</p>'
        f'<h2>{_safe(header.get("topic") or "Teacher Knowledge Package")}</h2>'
        f'<p>{_safe(header.get("subject", ""))} · {_safe(header.get("grade", ""))} · '
        f'{_safe(header.get("chapter", ""))}</p>'
        '<div class="gs-review-preview"><div class="gs-review-card is-light">'
        f'<div class="gs-card-label">Package overview</div><h3>'
        f'{_safe(header.get("topic") or "Ready to teach")}</h3>'
        '<div class="gs-review-metric"><div><strong class="gs-tabular">'
        f'{_safe(period_count)}</strong><span>periods</span></div>'
        '<div><strong class="gs-tabular">'
        f'{concept_count}</strong><span>concepts</span></div>'
        '<div><strong class="gs-tabular">'
        f'{question_count}</strong><span>questions</span></div></div></div>'
        '<div class="gs-review-card"><div class="gs-card-label">Validation</div>'
        '<h3 class="gs-tabular">'
        f'{_safe(faithfulness)}</h3>'
        '<p>Source anchors available for review.</p></div></div></div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "Overview",
            "Teaching plan",
            "Classroom content",
            "Assessments",
            "Gap analysis",
            "Sources",
        ]
    )
    with tabs[0]:
        _render_overview(tkp)
    with tabs[1]:
        _render_teaching_plan(tkp)
    with tabs[2]:
        _render_content(tkp)
    with tabs[3]:
        _render_assessments(tkp)
    with tabs[4]:
        _render_gap_analysis(tkp)
    with tabs[5]:
        _render_sources(tkp)
