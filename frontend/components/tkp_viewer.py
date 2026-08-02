"""Tabbed Teacher Knowledge Package viewer."""

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
        f'<div class="gs-card-soft"><h4>{_safe(title)}</h4>'
        f"<p>{_safe(body)}</p></div>",
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
        parts.append(f"“{_safe(ref['quote'])}”")
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
        with col:
            st.markdown(
                f'<div class="gs-panel"><div class="gs-badge">{_safe(label)}</div>'
                f'<p class="gs-display" style="font-size:1.25rem;margin:0.4rem 0 0 0;">'
                f"{_safe(value)}</p></div>",
                unsafe_allow_html=True,
            )

    st.markdown("#### Classification")
    _md_block(
        f"{classification.get('chapter', 'Chapter')} · {classification.get('category', '')}",
        classification.get("rationale")
        or f"Difficulty: {classification.get('difficulty', '—')} · "
        f"Language: {classification.get('language', '—')}",
    )

    objectives = knowledge.get("learning_objectives") or []
    if objectives:
        st.markdown("#### Learning objectives")
        for obj in objectives:
            bloom = obj.get("bloom_level") or ""
            badge = f' <span class="gs-badge amber">{_safe(bloom)}</span>' if bloom else ""
            st.markdown(
                f'<div class="gs-card-soft"><h4>{_safe(obj.get("text", ""))}{badge}</h4>'
                f"<p>{_source_ref(obj.get('source_ref'))}</p></div>",
                unsafe_allow_html=True,
            )

    concepts = knowledge.get("concepts") or []
    if concepts:
        st.markdown("#### Key concepts")
        _chips([c.get("name", "") for c in concepts if c.get("name")])

    if validation:
        passed = validation.get("overall_passed")
        st.markdown("#### Validation")
        st.markdown(
            f'<span class="gs-badge{" amber" if not passed else ""}">'
            f'{"Passed" if passed else "Needs review"}</span>',
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
                color_discrete_sequence=["#5B7C6E"],
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(243,239,230,0.65)",
                font_family="DM Sans",
                title_font_family="Literata",
                title_font_color="#1C1917",
                margin=dict(t=48, b=40, l=40, r=20),
                height=320,
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

    for p in periods:
        with st.expander(
            f"Period {p.get('period_number', '?')}: {p.get('title', 'Untitled')} "
            f"({p.get('duration_minutes', '?')} min)",
            expanded=p.get("period_number") == 1,
        ):
            objs = p.get("objectives") or []
            if objs:
                st.markdown("**Objectives**")
                for o in objs:
                    st.markdown(f"- {_safe(o)}")
            concepts = p.get("concepts_covered") or []
            if concepts:
                st.markdown("**Concepts covered**")
                _chips(concepts)
            if p.get("pacing_rationale"):
                _md_block("Pacing", p["pacing_rationale"])


def _render_content(tkp: dict[str, Any]) -> None:
    bundle = tkp.get("classroom_content") or {}
    periods = bundle.get("periods") or []
    activities = (tkp.get("activities") or {}).get("activities") or []

    for pc in periods:
        with st.expander(
            f"Period {pc.get('period_number', '?')} — classroom flow",
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
                if pc.get(key):
                    _md_block(label, pc[key])
            checks = pc.get("checkpoint_questions") or []
            if checks:
                st.markdown("**Checkpoints**")
                for q in checks:
                    st.markdown(f"- {_safe(q)}")
            for act in pc.get("classroom_activities") or []:
                _md_block(
                    f"{act.get('name', 'Activity')} ({act.get('activity_type', '')})",
                    act.get("instructions") or act.get("success_criteria") or "",
                )

    if activities:
        st.markdown("#### Unit activities")
        for act in activities:
            materials = ", ".join(act.get("materials") or []) or "—"
            _md_block(
                f"{act.get('name', 'Activity')} · {act.get('duration_minutes', '?')} min",
                f"{act.get('instructions', '')}\nMaterials: {materials}",
            )


def _render_assessments(tkp: dict[str, Any]) -> None:
    assessments = tkp.get("assessments") or {}
    total = assessments.get("total_marks")
    if total is not None:
        st.markdown(
            f'<span class="gs-badge">Total marks: {_safe(total)}</span>',
            unsafe_allow_html=True,
        )

    def _questions(title: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        st.markdown(f"#### {title}")
        for i, q in enumerate(items, 1):
            opts = q.get("options") or []
            opt_html = ""
            if opts:
                opt_html = "<ul>" + "".join(f"<li>{_safe(o)}</li>" for o in opts) + "</ul>"
            concepts = q.get("concepts_tested") or []
            st.markdown(
                f'<div class="gs-card-soft"><h4>Q{i}. [{_safe(q.get("question_type", ""))}] '
                f'{_safe(q.get("prompt", ""))}</h4>{opt_html}'
                f'<p><strong>Answer:</strong> {_safe(q.get("answer_key", ""))}</p>'
                f"<p>{_safe(q.get('rubric') or '')}</p></div>",
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
    for g in gap.get("gaps") or []:
        severity = (g.get("severity") or "medium").lower()
        st.markdown(
            f'<div class="gs-card-soft"><h4>{_safe(g.get("misconception", ""))} '
            f'<span class="gs-badge{" amber" if severity != "low" else ""}">'
            f"{_safe(severity)}</span></h4>"
            f'<p><strong>Diagnostic:</strong> {_safe(g.get("diagnostic_question", ""))}</p>'
            f"<ul>"
            + "".join(f"<li>{_safe(a)}</li>" for a in (g.get("remedial_actions") or []))
            + "</ul></div>",
            unsafe_allow_html=True,
        )
        related = g.get("related_concepts") or []
        if related:
            _chips(related)


def _render_sources(tkp: dict[str, Any]) -> None:
    knowledge = tkp.get("knowledge") or {}
    st.markdown(
        f'<p style="color:#57534E;margin-top:0;">Source anchors from '
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
        st.markdown(f"#### {title}")
        for item in items:
            ref = _source_ref(item.get("source_ref"))
            st.markdown(
                f'<div class="gs-card-soft"><h4>{_safe(item.get(name_key, ""))}</h4>'
                f"<p>{_safe(item.get(body_key, ''))}</p>"
                f"<p>{ref}</p></div>",
                unsafe_allow_html=True,
            )

    keywords = knowledge.get("keywords") or []
    if keywords:
        st.markdown("#### Keywords")
        _chips([k.get("term", "") for k in keywords if k.get("term")])


def render_tkp(tkp: dict[str, Any]) -> None:
    """Render a full TKP with Overview / Plan / Content / Assessments / Gaps / Sources."""
    if not tkp:
        st.warning("No Teacher Knowledge Package to display.")
        return

    header = tkp.get("classification") or {}
    st.markdown(
        f'<p class="gs-display" style="font-size:1.85rem;margin-bottom:0.25rem;'
        f'font-family:Literata,Georgia,serif;color:#1C1917;font-weight:700;">'
        f'{_safe(header.get("topic") or "Teacher Knowledge Package")}</p>'
        f'<p style="color:#57534E;margin-bottom:1rem;">'
        f'{_safe(header.get("subject", ""))} · {_safe(header.get("grade", ""))} · '
        f'{_safe(header.get("chapter", ""))}</p>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "Overview",
            "Teaching Plan",
            "Content",
            "Assessments",
            "Gap Analysis",
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
