"""Live pipeline progress — SSE + 10-stage stepper."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st
from backend.app.security.sanitize import sanitize_html
from frontend.api_client import get_client
from frontend.components.animations import show_loading

PIPELINE_STAGES: list[tuple[str, str]] = [
    ("document_intelligence", "Document intelligence"),
    ("educational_classification", "Educational classification"),
    ("knowledge_extraction", "Knowledge extraction"),
    ("teaching_planner", "Teaching planner"),
    ("classroom_content", "Classroom content"),
    ("activity_generation", "Activity generation"),
    ("assessment_generation", "Assessment generation"),
    ("gap_analysis", "Gap analysis"),
    ("validation", "Validation"),
    ("publish", "Publish TKP"),
]

_STAGE_ORDER = {key: i for i, (key, _) in enumerate(PIPELINE_STAGES)}


def _stage_index(stage: str | None) -> int:
    if not stage:
        return -1
    key = stage.strip().lower().replace(" ", "_")
    if key in _STAGE_ORDER:
        return _STAGE_ORDER[key]
    for name, idx in _STAGE_ORDER.items():
        if name in key or key in name:
            return idx
    if key in {"pending", "queued"}:
        return -1
    if key in {"completed", "done"}:
        return len(PIPELINE_STAGES)
    return -1


def _stepper_html(active_stage: str | None, status: str) -> str:
    active_idx = _stage_index(active_stage)
    if status == "completed":
        active_idx = len(PIPELINE_STAGES)
    rows: list[str] = []
    for i, (_key, label) in enumerate(PIPELINE_STAGES):
        # Only pin "failed" onto a known stage index — never coerce unknown/error
        # onto Document Intelligence (index 0).
        if status == "failed" and active_idx >= 0 and i == active_idx:
            state = "is-active"
            meta = "failed"
        elif i < active_idx or status == "completed":
            state = "is-done"
            meta = "done"
        elif i == active_idx:
            state = "is-active"
            meta = "running"
        else:
            state = "is-pending"
            meta = "waiting"
        rows.append(
            f'<div class="gs-step {state}">'
            f'<div class="gs-step-idx">{i + 1}</div>'
            f'<div class="gs-step-label">{sanitize_html(label)}</div>'
            f'<div class="gs-step-meta">{meta}</div></div>'
        )
    return '<div class="gs-stepper">' + "".join(rows) + "</div>"


def _apply_event(event: dict) -> None:
    st.session_state.current_stage = event.get("stage") or st.session_state.get("current_stage")
    try:
        st.session_state.progress_pct = float(event.get("progress") or 0.0)
    except (TypeError, ValueError):
        pass
    st.session_state.job_status = event.get("status") or st.session_state.get(
        "job_status", "running"
    )
    msg = event.get("message")
    if msg and st.session_state.job_status == "failed":
        st.session_state.job_error = str(msg)


def render() -> None:
    """Consume SSE (with poll fallback) until the job finishes."""
    from frontend.components.theme import inject_theme

    inject_theme()
    job_id = st.session_state.get("job_id")
    if not job_id:
        st.warning("No active job. Upload a document first.")
        if st.button("Back to upload"):
            st.session_state.view = "upload"
            st.rerun()
        return

    st.markdown(
        '<p class="gs-display" style="font-size:1.75rem;margin:0 0 0.25rem 0;">'
        "Building your package</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Job {sanitize_html(str(job_id)[:8])}… · "
        f"{sanitize_html(st.session_state.get('upload_filename') or 'document')}"
    )

    progress_box = st.empty()
    stepper_box = st.empty()
    message_box = st.empty()
    loader_box = st.empty()

    status = st.session_state.get("job_status") or "running"
    stage = st.session_state.get("current_stage")
    pct = float(st.session_state.get("progress_pct") or 0.0)

    progress_box.progress(min(max(pct / 100.0, 0.0), 1.0), text=f"{pct:.0f}%")
    stepper_box.markdown(_stepper_html(stage, status), unsafe_allow_html=True)

    if status in {"completed", "failed"}:
        if status == "completed":
            st.success("Pipeline complete.")
            if st.button("Open TKP review", type="primary"):
                st.session_state.view = "review"
                st.rerun()
        else:
            st.error(st.session_state.get("job_error") or "Pipeline failed.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Try again", type="primary"):
                    try:
                        get_client().start_job(str(job_id))
                        st.session_state.job_status = "pending"
                        st.session_state.progress_pct = 0.0
                        st.session_state.current_stage = "pending"
                        st.session_state.job_error = None
                        st.rerun()
                    except httpx.HTTPError as exc:
                        st.error(f"Could not restart: {exc}")
            with c2:
                if st.button("New upload"):
                    st.session_state.view = "upload"
                    st.rerun()
        return

    with loader_box:
        show_loading(key="progress_lottie", height=160)

    client = get_client()
    terminal = {"completed", "failed"}

    try:
        for event in client.stream_job_events(str(job_id)):
            _apply_event(event)
            status = st.session_state.job_status
            stage = st.session_state.current_stage
            pct = float(st.session_state.progress_pct or 0.0)
            progress_box.progress(
                min(max(pct / 100.0, 0.0), 1.0),
                text=f"{pct:.0f}% · {stage or 'working'}",
            )
            stepper_box.markdown(_stepper_html(stage, status), unsafe_allow_html=True)
            if event.get("message"):
                message_box.caption(sanitize_html(str(event["message"])))
            if status in terminal or event.get("_event") == "done":
                break
    except httpx.HTTPError:
        message_box.info("Live stream unavailable — polling job status…")
        for _ in range(600):
            try:
                job = client.get_job(str(job_id))
            except httpx.HTTPError as exc:
                st.error(f"Lost connection to API: {exc}")
                break
            _apply_event(
                {
                    "stage": job.get("current_stage"),
                    "progress": job.get("progress_pct", 0),
                    "status": job.get("status"),
                    "message": job.get("error") or f"Status: {job.get('status')}",
                }
            )
            status = st.session_state.job_status
            stage = st.session_state.current_stage
            pct = float(st.session_state.progress_pct or 0.0)
            progress_box.progress(
                min(max(pct / 100.0, 0.0), 1.0),
                text=f"{pct:.0f}% · {stage or 'working'}",
            )
            stepper_box.markdown(_stepper_html(stage, status), unsafe_allow_html=True)
            if status in terminal:
                break
            time.sleep(1.5)

    loader_box.empty()
    status = st.session_state.get("job_status")
    if status == "completed":
        st.session_state.view = "review"
        st.rerun()
    elif status == "failed":
        st.error(st.session_state.get("job_error") or "Pipeline failed.")
        if st.button("Back to upload"):
            st.session_state.view = "upload"
            st.rerun()
    else:
        st.info("Still running — refresh if the view stalls.")
        if st.button("Refresh status"):
            st.rerun()


if not globals().get("_IMPORTED_BY_APP"):
    render()
