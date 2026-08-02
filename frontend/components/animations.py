"""Lottie loaders for waiting states."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "lottie"

# Minimal pulsing ring — used when assets/lottie/loading.json is missing or empty.
_INLINE_LOTTIE: dict[str, Any] = {
    "v": "5.7.4",
    "fr": 30,
    "ip": 0,
    "op": 60,
    "w": 200,
    "h": 200,
    "nm": "gs-sage-spinner",
    "ddd": 0,
    "assets": [],
    "layers": [
        {
            "ddd": 0,
            "ind": 1,
            "ty": 4,
            "nm": "ring",
            "sr": 1,
            "ks": {
                "o": {"a": 0, "k": 100},
                "r": {
                    "a": 1,
                    "k": [
                        {"t": 0, "s": [0], "e": [360]},
                        {"t": 60, "s": [360]},
                    ],
                },
                "p": {"a": 0, "k": [100, 100, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {
                    "a": 1,
                    "k": [
                        {"t": 0, "s": [90, 90, 100], "e": [110, 110, 100]},
                        {"t": 30, "s": [110, 110, 100], "e": [90, 90, 100]},
                        {"t": 60, "s": [90, 90, 100]},
                    ],
                },
            },
            "ao": 0,
            "shapes": [
                {
                    "ty": "gr",
                    "it": [
                        {
                            "ty": "el",
                            "d": 1,
                            "s": {"a": 0, "k": [110, 110]},
                            "p": {"a": 0, "k": [0, 0]},
                        },
                        {
                            "ty": "st",
                            "c": {"a": 0, "k": [0.357, 0.486, 0.431, 1]},
                            "o": {"a": 0, "k": 100},
                            "w": {"a": 0, "k": 10},
                            "lc": 2,
                            "lj": 2,
                            "d": [
                                {"n": "d", "nm": "dash", "v": {"a": 0, "k": [50, 70]}},
                            ],
                        },
                        {
                            "ty": "tr",
                            "p": {"a": 0, "k": [0, 0]},
                            "a": {"a": 0, "k": [0, 0]},
                            "s": {"a": 0, "k": [100, 100]},
                            "r": {"a": 0, "k": 0},
                            "o": {"a": 0, "k": 100},
                        },
                    ],
                },
                {
                    "ty": "gr",
                    "it": [
                        {
                            "ty": "el",
                            "d": 1,
                            "s": {"a": 0, "k": [36, 36]},
                            "p": {"a": 0, "k": [0, 0]},
                        },
                        {
                            "ty": "fl",
                            "c": {"a": 0, "k": [0.769, 0.627, 0.125, 1]},
                            "o": {"a": 0, "k": 100},
                        },
                        {
                            "ty": "tr",
                            "p": {"a": 0, "k": [0, 0]},
                            "a": {"a": 0, "k": [0, 0]},
                            "s": {"a": 0, "k": [100, 100]},
                            "r": {"a": 0, "k": 0},
                            "o": {"a": 0, "k": 100},
                        },
                    ],
                },
            ],
            "ip": 0,
            "op": 60,
            "st": 0,
            "bm": 0,
        }
    ],
}


def load_lottie(name: str = "loading.json") -> dict[str, Any]:
    """Load a lottie JSON from assets, or fall back to the inline spinner."""
    path = _ASSETS / name
    if path.is_file() and path.stat().st_size > 0:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("layers"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return _INLINE_LOTTIE


def show_loading(key: str = "gs_loader", height: int = 180) -> None:
    """Render a streamlit-lottie animation (or a quiet caption fallback)."""
    animation = load_lottie()
    try:
        from streamlit_lottie import st_lottie

        st_lottie(animation, height=height, key=key, speed=1.0, loop=True)
    except Exception:
        st.markdown(
            '<p style="text-align:center;color:#57534E;">'
            "Preparing your Teacher Knowledge Package…</p>",
            unsafe_allow_html=True,
        )


# Back-compat alias used by earlier drafts
show_loader = show_loading
