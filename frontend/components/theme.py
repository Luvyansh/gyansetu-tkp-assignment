"""Custom GyanSetu TKP theme — readable light UI with sage accents."""

from __future__ import annotations

import streamlit as st


def inject_theme() -> None:
    """Inject layout CSS. Colors primarily come from `.streamlit/config.toml`."""
    st.markdown(
        """
<style>
:root {
  --gs-ink: #1C1917;
  --gs-ink-muted: #57534E;
  --gs-sage: #5B7C6E;
  --gs-sage-deep: #3F5A4E;
  --gs-sage-soft: #8FA99B;
  --gs-sage-mist: rgba(91, 124, 110, 0.14);
  --gs-gold: #C4A020;
  --gs-gold-deep: #9A7B12;
  --gs-gold-soft: #E8D48A;
  --gs-paper: #F7F5F0;
  --gs-white: #FFFdf9;
  --gs-border: #D0CBC2;
  --gs-radius: 12px;
  --gs-shadow: 0 10px 28px rgba(28, 25, 23, 0.07);
  --font-display: 'Literata', Georgia, serif;
  --font-body: 'DM Sans', 'Segoe UI', sans-serif;
}

.stApp {
  color-scheme: light !important;
  background: linear-gradient(180deg, #FAF8F4 0%, var(--gs-paper) 100%) !important;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
#MainMenu, footer, [data-testid="stDecoration"] { display: none; }

.block-container {
  padding-top: 1rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1100px !important;
}

/* —— Nav bar —— */
.st-key-gs_nav_bar {
  margin-bottom: 0.75rem;
  padding: 0.65rem 0.85rem;
  background: var(--gs-white);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius);
  box-shadow: var(--gs-shadow);
}
.st-key-gs_nav_bar [data-testid="stMarkdownContainer"] p {
  margin: 0 !important;
  font-family: var(--font-display);
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--gs-ink) !important;
  white-space: nowrap;
}

/* Buttons: never wrap labels mid-word */
div.stButton > button,
div.stDownloadButton > button {
  white-space: nowrap !important;
  min-height: 2.5rem !important;
  padding: 0.45rem 1.1rem !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  box-shadow: none !important;
}
div.stButton > button p,
div.stDownloadButton > button p,
div.stButton > button span,
div.stDownloadButton > button span {
  white-space: nowrap !important;
}

/* Primary / secondary already themed via config; keep secondary readable */
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"] {
  background: var(--gs-white) !important;
  color: var(--gs-sage-deep) !important;
  border: 1.5px solid var(--gs-border) !important;
}
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
  background: var(--gs-sage-deep) !important;
  color: #FCFAF6 !important;
  border: 1.5px solid var(--gs-sage-deep) !important;
}

/* —— Hero —— */
.gs-hero {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: clamp(1.25rem, 3vw, 2.5rem);
  align-items: center;
  margin: 0 0 1.25rem 0;
  padding: clamp(1.25rem, 3vw, 2rem);
  border-radius: var(--gs-radius);
  position: relative;
  overflow: hidden;
  background: linear-gradient(120deg, #3F5A4E 0%, #292524 70%, #1C1917 100%);
  box-shadow: var(--gs-shadow);
}
.gs-hero > * { position: relative; z-index: 1; }

@media (max-width: 900px) {
  .gs-hero {
    grid-template-columns: 1fr;
  }
  .gs-hero-art { order: -1; max-width: 220px; margin: 0 auto; }
}

.gs-brand {
  font-family: var(--font-display) !important;
  font-size: clamp(2.2rem, 4.5vw, 3.25rem) !important;
  font-weight: 700 !important;
  line-height: 1.05 !important;
  margin: 0 0 0.75rem 0 !important;
  color: #FCFAF6 !important;
}
.gs-brand span { color: var(--gs-gold-soft) !important; }

.gs-pitch {
  font-size: 1.05rem;
  line-height: 1.55;
  color: rgba(252, 250, 246, 0.88) !important;
  max-width: 34rem;
  margin: 0 0 0.85rem 0;
}
.gs-hero-cta {
  margin: 0;
  font-weight: 600;
  color: var(--gs-gold-soft) !important;
}
.gs-hero-art svg {
  width: 100%;
  height: auto;
  filter: drop-shadow(0 12px 24px rgba(0, 0, 0, 0.25));
}

.gs-panel-title {
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--gs-ink) !important;
  margin: 0 0 0.25rem 0;
}
.gs-dropzone-hint {
  font-size: 0.92rem;
  color: var(--gs-ink-muted) !important;
  margin: 0 0 0.85rem 0;
}
.gs-display {
  font-family: var(--font-display) !important;
  font-weight: 700;
  color: var(--gs-ink) !important;
}
.gs-footer-note {
  margin-top: 1.75rem;
  font-size: 0.85rem;
  color: var(--gs-ink-muted) !important;
  text-align: center;
}

/* —— Stepper —— */
.gs-stepper {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin: 0.75rem 0 1.25rem 0;
}
.gs-step {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--gs-border);
  background: var(--gs-white);
}
.gs-step.is-done {
  border-color: rgba(91, 124, 110, 0.45);
  background: linear-gradient(90deg, var(--gs-sage-mist), var(--gs-white));
}
.gs-step.is-active {
  border-color: var(--gs-gold);
  background: linear-gradient(90deg, rgba(232, 212, 138, 0.35), var(--gs-white));
  box-shadow: 0 4px 14px rgba(196, 160, 32, 0.12);
}
.gs-step.is-pending { opacity: 0.72; }
.gs-step-idx {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-size: 0.8rem; font-weight: 700;
  background: #EEEAE2;
  color: var(--gs-sage-deep) !important;
}
.gs-step.is-done .gs-step-idx {
  background: var(--gs-sage);
  color: #FCFAF6 !important;
}
.gs-step.is-active .gs-step-idx {
  background: var(--gs-gold);
  color: var(--gs-ink) !important;
}
.gs-step-label { font-weight: 600; color: var(--gs-ink) !important; }
.gs-step-meta {
  font-size: 0.75rem;
  color: var(--gs-ink-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.gs-badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--gs-sage-mist);
  color: var(--gs-sage-deep) !important;
}
.gs-badge.amber {
  background: rgba(196, 160, 32, 0.22);
  color: var(--gs-gold-deep) !important;
}

.gs-card-soft {
  background: #F3F0EA;
  border-left: 3px solid var(--gs-sage);
  border-radius: 0 8px 8px 0;
  padding: 0.85rem 1rem;
  margin: 0.55rem 0;
}
.gs-card-soft h4 {
  margin: 0 0 0.35rem 0;
  font-family: var(--font-display);
  color: var(--gs-ink) !important;
  font-size: 1rem;
}
.gs-card-soft p, .gs-card-soft li {
  color: var(--gs-ink-muted) !important;
  margin: 0.2rem 0;
  font-size: 0.95rem;
}

.gs-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0.5rem 0 1rem 0;
}
.gs-chip {
  background: var(--gs-white);
  border: 1px solid var(--gs-border);
  color: var(--gs-sage-deep) !important;
  border-radius: 6px;
  padding: 0.25rem 0.65rem;
  font-size: 0.82rem;
  font-weight: 600;
}

div[data-testid="stFileUploader"] {
  border: 2px dashed var(--gs-sage-soft) !important;
  border-radius: var(--gs-radius);
  background: var(--gs-white);
  padding: 0.5rem;
}
div[data-testid="stFileUploader"]:hover {
  border-color: var(--gs-gold) !important;
}

.stProgress > div > div > div > div {
  background: linear-gradient(90deg, var(--gs-sage), var(--gs-gold)) !important;
}

[data-testid="stExpander"] {
  border-radius: 10px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
