"""GyanSetu TKP — Streamlit entrypoint with session-state view routing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import streamlit as st

# Ensure repo root is on sys.path so `frontend.*` and `backend.*` resolve.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from frontend.components.theme import inject_theme

st.set_page_config(
    page_title="GyanSetu TKP",
    page_icon="📗",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _load_page(filename: str) -> ModuleType:
    """Load a numbered page module via importlib (names start with digits)."""
    path = Path(__file__).resolve().parent / "pages" / filename
    mod_name = f"frontend_pages_{path.stem}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load page module: {path}")
    module = importlib.util.module_from_spec(spec)
    module._IMPORTED_BY_APP = True  # type: ignore[attr-defined]
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _init_state() -> None:
    defaults = {
        "view": "upload",
        "job_id": None,
        "document_id": None,
        "tkp": None,
        "progress_pct": 0.0,
        "current_stage": None,
        "job_status": None,
        "job_error": None,
        "upload_filename": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def main() -> None:
    inject_theme()
    _init_state()

    nav = st.session_state.view
    cols = st.columns([1, 1, 1, 6])
    labels = [("upload", "Upload"), ("progress", "Progress"), ("review", "Review")]
    for col, (key, label) in zip(cols[:3], labels, strict=True):
        with col:
            disabled = False
            if key in {"progress", "review"} and not st.session_state.get("job_id"):
                disabled = True
            if st.button(
                label,
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if nav == key else "secondary",
                disabled=disabled,
            ):
                st.session_state.view = key
                st.rerun()

    view = st.session_state.view
    if view == "progress":
        _load_page("2_progress.py").render()
    elif view == "review":
        _load_page("3_review.py").render()
    else:
        _load_page("1_upload.py").render(show_hero=True)


main()
