"""Landing + upload view for GyanSetu TKP."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st
from frontend.api_client import get_client

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_ALLOWED_EXT = {".pdf", ".docx", ".pptx"}
_MAX_BYTES = 25 * 1024 * 1024

DOC_TYPE_HINTS = {
    "Mostly text": "mostly_text",
    "Text with tables": "text_with_tables",
    "Text with diagrams": "text_with_diagrams",
    "Text with equations": "text_with_equations",
    "Scanned / image-heavy": "scanned",
    "Not sure": "unsure",
}


def _load_illustration() -> str:
    path = _ASSETS / "landing_illustration.svg"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def render(*, show_hero: bool = True) -> None:
    """Hero + upload dropzone → create job and switch to progress."""
    from frontend.components.theme import inject_theme

    inject_theme()

    if show_hero:
        svg = _load_illustration()
        st.markdown(
            f"""
<div class="gs-hero">
  <div>
    <p class="gs-brand">GyanSetu <span>TKP</span></p>
    <p class="gs-pitch">
      Turn a chapter into a classroom-ready Teacher Knowledge Package —
      teaching plan, activities, assessments, and gap analysis in one pass.
    </p>
    <p class="gs-hero-cta">Upload a chapter to begin →</p>
  </div>
  <div class="gs-hero-art">{svg}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown(
            '<p class="gs-panel-title">Upload your source chapter</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="gs-dropzone-hint">PDF, DOCX, or PPTX · max 25 MB</p>',
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Chapter file",
            type=["pdf", "docx", "pptx"],
            label_visibility="collapsed",
            key="gs_uploader",
        )

        hint_label = st.radio(
            "Document type hint",
            options=list(DOC_TYPE_HINTS.keys()),
            index=len(DOC_TYPE_HINTS) - 1,
            horizontal=True,
            help="Helps the parser choose the best extraction route.",
        )
        hint = DOC_TYPE_HINTS[hint_label]

        validation_msg = ""
        file_bytes: bytes | None = None
        filename = ""

        if uploaded is not None:
            filename = uploaded.name or "upload.bin"
            ext = Path(filename).suffix.lower()
            file_bytes = uploaded.getvalue()
            if ext not in _ALLOWED_EXT:
                validation_msg = f"Unsupported type `{ext}`. Use PDF, DOCX, or PPTX."
            elif len(file_bytes) == 0:
                validation_msg = "The file is empty."
            elif len(file_bytes) > _MAX_BYTES:
                validation_msg = "File exceeds the 25 MB upload limit."
            else:
                st.success(f"Ready: **{filename}** ({len(file_bytes) / 1024:.1f} KB)")

        if validation_msg:
            st.error(validation_msg)

        with st.container(horizontal=True, gap="small"):
            generate = st.button(
                "Generate TKP",
                type="primary",
                icon=":material/play_arrow:",
                width="content",
                disabled=file_bytes is None or bool(validation_msg),
            )
            if st.session_state.get("job_id"):
                if st.button(
                    "Resume last job",
                    icon=":material/history:",
                    width="content",
                ):
                    st.session_state.view = "progress"
                    st.rerun()

        if generate and file_bytes is not None and not validation_msg:
            client = get_client()
            with st.spinner("Uploading and starting the pipeline…"):
                try:
                    result = client.upload_document(file_bytes, filename, hint=hint)
                except httpx.HTTPStatusError as exc:
                    detail = ""
                    try:
                        detail = exc.response.json().get("detail", "")
                    except Exception:
                        detail = exc.response.text[:300]
                    st.error(f"Upload failed ({exc.response.status_code}): {detail}")
                    return
                except httpx.HTTPError as exc:
                    st.error(f"Cannot reach the API: {exc}")
                    return

            st.session_state.document_id = str(result.get("document_id", ""))
            st.session_state.job_id = str(result.get("job_id", ""))
            st.session_state.tkp = None
            st.session_state.progress_pct = 0.0
            st.session_state.current_stage = "pending"
            st.session_state.job_status = "pending"
            st.session_state.job_error = None
            st.session_state.upload_filename = filename
            st.session_state.view = "progress"
            st.rerun()

    st.markdown(
        '<p class="gs-footer-note">GyanSetu TKP · classroom packages from source chapters</p>',
        unsafe_allow_html=True,
    )


if not globals().get("_IMPORTED_BY_APP"):
    render()
