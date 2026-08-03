"""TKP review — tabs, downloads, optional eval summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st
from backend.app.security.sanitize import sanitize_html
from frontend.api_client import get_client
from frontend.components.tkp_viewer import render_tkp

_PDF_ARTIFACTS = [
    ("lesson-plan", "Lesson plan PDF"),
    ("teacher-guide", "Teacher guide PDF"),
    ("assessment-book", "Assessment book PDF"),
]


def render() -> None:
    """Load TKP for the current job and present the review UI."""
    from frontend.components.theme import inject_theme

    inject_theme()
    job_id = st.session_state.get("job_id")
    if not job_id:
        st.warning("No job selected. Upload a document to generate a TKP.")
        if st.button("Go to upload"):
            st.session_state.view = "upload"
            st.rerun()
        return

    st.markdown(
        '<p class="gs-display" style="font-size:1.75rem;margin:0 0 0.25rem 0;">Review</p>',
        unsafe_allow_html=True,
    )
    st.caption("Inspect the package, download JSON or PDFs, then iterate.")

    client = get_client()
    tkp = st.session_state.get("tkp")

    if not tkp:
        with st.spinner("Loading Teacher Knowledge Package…"):
            try:
                tkp = client.get_tkp(str(job_id))
                st.session_state.tkp = tkp
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    st.info("TKP is not ready yet. Return to progress and wait for publish.")
                    if st.button("Back to progress"):
                        st.session_state.view = "progress"
                        st.rerun()
                    return
                st.error(f"Failed to load TKP ({exc.response.status_code})")
                return
            except httpx.HTTPError as exc:
                st.error(f"API error: {exc}")
                return

    with st.container(border=True):
        st.markdown(
            '<p class="gs-panel-title">Exports</p>',
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True, gap="small"):
            st.download_button(
                "Download JSON",
                data=json.dumps(tkp, indent=2, default=str),
                file_name=f"tkp-{str(job_id)[:8]}.json",
                mime="application/json",
                icon=":material/data_object:",
                width="content",
            )
            for artifact, label in _PDF_ARTIFACTS:
                try:
                    pdf_bytes = client.download_export(str(job_id), artifact)
                    st.download_button(
                        label,
                        data=pdf_bytes,
                        file_name=f"{artifact}-{str(job_id)[:8]}.pdf",
                        mime="application/pdf",
                        icon=":material/picture_as_pdf:",
                        width="content",
                        key=f"dl_{artifact}",
                    )
                except httpx.HTTPError:
                    st.caption(f"{label} unavailable")

    with st.expander("Evaluation / grounding report", expanded=False):
        try:
            report = client.get_eval_report(str(job_id))
            faith = report.get("faithfulness")
            if faith is not None:
                st.metric("Faithfulness", f"{float(faith):.2f}")
            scores = report.get("grounding_scores") or {}
            if scores:
                st.markdown("**Grounding scores**")
                for k, v in scores.items():
                    st.markdown(f"- `{sanitize_html(str(k))}`: {float(v):.2f}")
            details = report.get("details") or {}
            if details:
                st.json(details)
        except httpx.HTTPError:
            st.caption("Eval report not available for this job.")

    render_tkp(tkp)

    with st.container(horizontal=True, gap="small"):
        if st.button("New upload", icon=":material/upload_file:", width="content"):
            for key in (
                "job_id",
                "document_id",
                "tkp",
                "progress_pct",
                "current_stage",
                "job_status",
                "job_error",
                "upload_filename",
            ):
                st.session_state.pop(key, None)
            st.session_state.view = "upload"
            st.rerun()
        if st.button("View progress", icon=":material/hourglass_top:", width="content"):
            st.session_state.view = "progress"
            st.rerun()


if not globals().get("_IMPORTED_BY_APP"):
    render()
