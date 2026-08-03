"""CSS-only loading states for the TKP pipeline."""

from __future__ import annotations

import streamlit as st


def show_loading(key: str = "gs_loader", height: int = 0) -> None:
    """Render a reliable branded loader without requiring a browser animation package."""
    del height  # Kept for backwards compatibility with the previous Lottie API.
    safe_key = "".join(character for character in key if character.isalnum() or character in "-_")
    st.markdown(
        f"""
<div class="gs-loader-wrap" data-loader-key="{safe_key}" role="status" aria-live="polite">
  <span class="gs-loader" aria-hidden="true"></span>
  <div>
    <p class="gs-loader-title">Preparing your Teacher Knowledge Package</p>
    <p class="gs-loader-copy">Tracing each output back to the source chapter.</p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


# Back-compat alias used by earlier drafts.
show_loader = show_loading
