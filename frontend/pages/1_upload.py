"""Curriculum Canvas upload landing view for GyanSetu TKP."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st
from frontend.api_client import get_client
from frontend.components.animations import show_loading

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


def render(*, show_hero: bool = True) -> None:
    """Render the document-to-classroom landing flow and start a TKP job."""
    from frontend.components.theme import inject_theme

    inject_theme()

    if show_hero:
        st.markdown(
            """
<section class="gs-hero gs-fade-up" aria-labelledby="gs-hero-title">
  <div class="gs-hero-copy">
    <p class="gs-eyebrow">Teacher Knowledge Package</p>
    <p id="gs-hero-title" class="gs-brand">Make every chapter <span>teachable.</span></p>
    <p class="gs-pitch">Turn a source chapter into a grounded teaching plan, classroom content,
    assessments, and learning-gap insights — ready for your next lesson.</p>
    <p class="gs-hero-note">One source. Ten grounded stages. Classroom-ready output.</p>
  </div>
  <div class="gs-hero-transform" aria-label="A source chapter becomes a classroom package">
    <div class="gs-source-card">
      <div class="gs-card-label">Input</div>
      <div class="gs-card-heading">Source chapter <span class="gs-badge">PDF</span></div>
      <div class="gs-doc-preview" aria-hidden="true">
        <div class="gs-doc-line"></div>
        <div class="gs-doc-line"></div>
        <div class="gs-doc-line"></div>
        <div class="gs-doc-grid"><i></i><i></i></div>
      </div>
      <div class="gs-card-label">physics · motion and force</div>
    </div>
    <div class="gs-transform-link">10-stage workflow</div>
    <div class="gs-package-card">
      <div class="gs-card-label">Output</div>
      <div class="gs-card-heading">Classroom package</div>
      <div class="gs-package-rows">
        <div class="gs-package-row">Teaching plan <span>ready</span></div>
        <div class="gs-package-row">Classroom content <span>ready</span></div>
        <div class="gs-package-row">Assessments <span>grounded</span></div>
        <div class="gs-package-row">Gap analysis <span>ready</span></div>
      </div>
    </div>
  </div>
</section>
            """,
            unsafe_allow_html=True,
        )

    with st.container(border=True, key="gs_upload_card"):
        st.markdown(
            """
<div class="gs-upload-header">
  <div>
    <p class="gs-eyebrow">Start with a chapter</p>
    <h2>Upload your source chapter</h2>
    <p>PDF, DOCX, or PPTX · maximum 25 MB</p>
  </div>
  <span class="gs-step-tag">Step 01 / 03</span>
</div>
            """,
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

        with st.container(horizontal=True, gap="small", key="gs_upload_actions"):
            generate = st.button(
                "Generate classroom package",
                type="primary",
                icon=":material/auto_awesome:",
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
            loading_slot = st.empty()
            with loading_slot.container():
                show_loading(key="upload_loader")
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
            finally:
                loading_slot.empty()

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
        """
<section class="gs-pipeline" aria-labelledby="gs-pipeline-title">
  <div class="gs-pipeline-head">
    <div>
      <p class="gs-eyebrow">Pipeline preview</p>
      <h2 id="gs-pipeline-title">A clear path through ten stages</h2>
    </div>
    <span class="gs-tabular">0 / 10 complete</span>
  </div>
  <div class="gs-pipeline-track">
    <div class="gs-pipeline-stage is-current">
      <strong>Parse</strong><small>Document intelligence</small>
    </div>
    <div class="gs-pipeline-stage">
      <strong>Classify</strong><small>Subject + grade</small>
    </div>
    <div class="gs-pipeline-stage">
      <strong>Extract</strong><small>Concepts + sources</small>
    </div>
    <div class="gs-pipeline-stage">
      <strong>Plan</strong><small>Teaching flow</small>
    </div>
    <div class="gs-pipeline-stage">
      <strong>Publish</strong><small>TKP + exports</small>
    </div>
  </div>
</section>
<section class="gs-cream-band" aria-labelledby="gs-output-title">
  <div>
    <p class="gs-eyebrow">What you receive</p>
    <h3 id="gs-output-title">Everything needed for the next lesson.</h3>
  </div>
  <div class="gs-stat-row">
    <div class="gs-stat"><strong class="gs-tabular">01</strong><span>lesson plan</span></div>
    <div class="gs-stat"><strong class="gs-tabular">10</strong><span>pipeline stages</span></div>
    <div class="gs-stat"><strong class="gs-tabular">03</strong><span>export PDFs</span></div>
  </div>
</section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="gs-footer-note">GyanSetu TKP · classroom packages from source chapters</p>',
        unsafe_allow_html=True,
    )


if not globals().get("_IMPORTED_BY_APP"):
    render()
