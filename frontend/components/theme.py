"""Stripe-inspired visual system for the GyanSetu TKP Streamlit app."""

from __future__ import annotations

import streamlit as st


# The visual language is intentionally kept in one injected stylesheet because
# Streamlit renders the page from Python and does not expose a global CSS file.
def inject_theme() -> None:
    """Inject shared tokens, layout primitives, states, and motion."""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

:root {
  --gs-primary: #533afd;
  --gs-primary-deep: #4434d4;
  --gs-primary-press: #2e2b8c;
  --gs-primary-soft: #665efd;
  --gs-primary-mist: #b9b9f9;
  --gs-navy: #1c1e54;
  --gs-ink: #0d253d;
  --gs-ink-secondary: #273951;
  --gs-ink-muted: #64718d;
  --gs-ink-faint: #8a98aa;
  --gs-canvas: #ffffff;
  --gs-canvas-soft: #f6f9fc;
  --gs-canvas-cream: #f5e9d4;
  --gs-hairline: #e3e8ee;
  --gs-input-border: #a8c3de;
  --gs-ruby: #ea2261;
  --gs-font-ui: 'Inter', 'SF Pro Display', system-ui, -apple-system, sans-serif;
  --gs-radius-xs: 4px;
  --gs-radius-sm: 6px;
  --gs-radius-md: 8px;
  --gs-radius-lg: 12px;
  --gs-radius-xl: 16px;
  --gs-radius-pill: 9999px;
  --gs-shadow-soft: 0 1px 3px rgba(0, 55, 112, 0.08);
  --gs-shadow-float: 0 8px 24px rgba(0, 55, 112, 0.08), 0 2px 6px rgba(0, 55, 112, 0.04);
  --gs-shadow-deep: 0 16px 48px rgba(0, 55, 112, 0.12), 0 4px 12px rgba(0, 55, 112, 0.06);
  --gs-ease: cubic-bezier(.2, 0, 0, 1);
}

@keyframes gs-mesh-drift {
  0%, 100% { transform: scale(1) translate3d(0, 0, 0); opacity: .8; }
  50% { transform: scale(1.04) translate3d(1.5%, -1%, 0); opacity: 1; }
}
@keyframes gs-fade-up {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes gs-pulse {
  0%, 100% { transform: scale(.82); opacity: .45; box-shadow: 0 0 0 0 rgba(83, 58, 253, .2); }
  50% { transform: scale(1); opacity: 1; box-shadow: 0 0 0 8px rgba(83, 58, 253, 0); }
}
@keyframes gs-shimmer {
  from { transform: translateX(-100%); }
  to { transform: translateX(220%); }
}
@keyframes gs-draw {
  from { stroke-dashoffset: 80; }
  to { stroke-dashoffset: 0; }
}

html, body, [class*="css"] {
  font-family: var(--gs-font-ui) !important;
  font-feature-settings: "ss01";
}
body { color: var(--gs-ink); background: var(--gs-canvas-soft); }
.stApp {
  color-scheme: light !important;
  color: var(--gs-ink) !important;
  background: var(--gs-canvas-soft) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
#MainMenu, footer, [data-testid="stDecoration"] { display: none; }
.block-container {
  width: min(100% - 32px, 1200px) !important;
  max-width: 1200px !important;
  padding: 12px 0 56px !important;
}

/* Shared type and page framing */
.gs-display, .gs-page-title, .gs-panel-title, .gs-section-title {
  color: var(--gs-ink) !important;
  font-weight: 300 !important;
  letter-spacing: -.04em !important;
  line-height: 1.08 !important;
}
.gs-page-title { font-size: clamp(2rem, 4vw, 2.5rem) !important; margin: 0 !important; }
.gs-section-title { font-size: 1.35rem !important; margin: 1.5rem 0 .55rem !important; }
.gs-panel-title { font-size: 1.35rem !important; margin: 0 !important; }
.gs-display { font-size: 2rem; }
.gs-tabular, [data-testid="stMetricValue"], .stProgress p {
  font-feature-settings: "tnum" !important;
  font-variant-numeric: tabular-nums !important;
}
.gs-eyebrow, .gs-kicker {
  color: var(--gs-primary-deep) !important;
  font-size: .68rem !important;
  font-weight: 500 !important;
  letter-spacing: .12em !important;
  line-height: 1.2 !important;
  text-transform: uppercase !important;
}
.gs-muted { color: var(--gs-ink-muted) !important; }
.gs-fade-up { animation: gs-fade-up 520ms var(--gs-ease) both; }

/* Navigation */
.st-key-gs_nav_bar {
  position: sticky;
  top: .65rem;
  z-index: 10;
  margin-bottom: 1.25rem;
  padding: .55rem .7rem;
  min-height: 52px;
  background: rgba(255, 255, 255, .88);
  border: 1px solid rgba(227, 232, 238, .9);
  border-radius: var(--gs-radius-pill);
  box-shadow: var(--gs-shadow-float);
  backdrop-filter: blur(18px);
}
.gs-nav-brand {
  display: inline-flex;
  align-items: center;
  gap: .55rem;
  min-width: max-content;
  color: var(--gs-ink) !important;
  font-size: .94rem;
  font-weight: 500;
  letter-spacing: -.02em;
  white-space: nowrap;
}
.gs-nav-mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  color: var(--gs-canvas);
  background: var(--gs-navy);
  border-radius: var(--gs-radius-sm);
  font-size: .72rem;
  font-weight: 600;
}
.gs-nav-brand span { color: var(--gs-primary-deep); }
.st-key-gs_nav_bar div.stButton > button { min-height: 36px !important; padding: .4rem .85rem !important; }
.st-key-gs_nav_bar div.stButton > button[kind="primary"],
.st-key-gs_nav_bar div.stButton > button[data-testid="baseButton-primary"] {
  background: var(--gs-primary) !important;
  border-color: var(--gs-primary) !important;
}

/* Buttons and focus */
div.stButton > button, div.stDownloadButton > button {
  min-height: 44px !important;
  padding: .62rem 1rem !important;
  border-radius: var(--gs-radius-pill) !important;
  border: 1px solid var(--gs-hairline) !important;
  color: var(--gs-ink-secondary) !important;
  background: var(--gs-canvas) !important;
  font-family: var(--gs-font-ui) !important;
  font-size: .86rem !important;
  font-weight: 500 !important;
  letter-spacing: -.01em;
  white-space: nowrap !important;
  box-shadow: none !important;
  transition: transform 180ms var(--gs-ease), background 180ms var(--gs-ease), border-color 180ms var(--gs-ease), box-shadow 180ms var(--gs-ease), color 180ms var(--gs-ease) !important;
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
  color: var(--gs-primary-deep) !important;
  border-color: var(--gs-primary) !important;
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(83, 58, 253, .12) !important;
}
div.stButton > button:active, div.stDownloadButton > button:active { transform: translateY(1px) scale(.98); }
div.stButton > button:focus-visible, div.stDownloadButton > button:focus-visible,
input:focus-visible, textarea:focus-visible, [role="radio"]:focus-visible {
  outline: 3px solid rgba(83, 58, 253, .25) !important;
  outline-offset: 2px !important;
}
div.stButton > button[kind="primary"], div.stButton > button[data-testid="baseButton-primary"],
div.stDownloadButton > button[kind="primary"], div.stDownloadButton > button[data-testid="baseButton-primary"] {
  color: var(--gs-canvas) !important;
  background: var(--gs-primary) !important;
  border-color: var(--gs-primary) !important;
  box-shadow: 0 8px 18px rgba(83, 58, 253, .2) !important;
}
div.stButton > button[kind="primary"]:hover, div.stButton > button[data-testid="baseButton-primary"]:hover {
  color: var(--gs-canvas) !important;
  background: var(--gs-primary-deep) !important;
  border-color: var(--gs-primary-deep) !important;
}

/* Landing hero */
.gs-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, .95fr) minmax(360px, 1.05fr);
  gap: clamp(1.25rem, 4vw, 4.5rem);
  align-items: center;
  min-height: 430px;
  margin: -12px calc((1200px - 100vw) / 2) 0;
  padding: 72px max(32px, calc((100vw - 1200px) / 2 + 24px)) 88px;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 79% 18%, rgba(234, 34, 97, .22), transparent 32%),
    radial-gradient(ellipse at 61% 4%, rgba(83, 58, 253, .34), transparent 38%),
    radial-gradient(ellipse at 17% 0%, rgba(245, 233, 212, .92), transparent 46%),
    linear-gradient(180deg, #f1efff 0%, var(--gs-canvas) 84%);
}
.gs-hero::before {
  content: "";
  position: absolute;
  inset: -10% -5% 16%;
  background: radial-gradient(ellipse at center, rgba(255,255,255,.44), transparent 62%);
  filter: blur(24px);
  animation: gs-mesh-drift 12s ease-in-out infinite;
  pointer-events: none;
}
.gs-hero > * { position: relative; z-index: 1; }
.gs-hero-copy { max-width: 540px; padding-top: 20px; }
.gs-brand {
  margin: .65rem 0 1.25rem !important;
  color: var(--gs-ink) !important;
  font-size: clamp(2.7rem, 6vw, 4.8rem) !important;
  font-weight: 300 !important;
  letter-spacing: -.075em !important;
  line-height: .98 !important;
}
.gs-brand span { color: var(--gs-primary) !important; }
.gs-pitch {
  max-width: 32rem;
  margin: 0 0 1.35rem !important;
  color: var(--gs-ink-secondary) !important;
  font-size: 1rem;
  line-height: 1.6;
}
.gs-hero-note { color: var(--gs-ink-muted) !important; font-size: .78rem; }
.gs-hero-transform { display: grid; grid-template-columns: 1fr 54px 1fr; gap: .65rem; align-items: center; }
.gs-source-card, .gs-package-card {
  min-height: 188px;
  padding: 1.1rem;
  border-radius: var(--gs-radius-lg);
  box-shadow: var(--gs-shadow-float);
}
.gs-source-card { background: rgba(255,255,255,.82); border: 1px solid rgba(227,232,238,.9); }
.gs-package-card { color: var(--gs-canvas); background: var(--gs-navy); box-shadow: 0 18px 42px rgba(28,30,84,.18); }
.gs-card-label { color: var(--gs-ink-muted); font-size: .62rem; letter-spacing: .14em; text-transform: uppercase; }
.gs-package-card .gs-card-label { color: rgba(255,255,255,.62); }
.gs-card-heading { margin: .5rem 0 1rem; font-size: 1rem; font-weight: 500; letter-spacing: -.03em; }
.gs-doc-preview { width: 74px; height: 96px; margin: 1rem auto .7rem; padding: .7rem .55rem; background: var(--gs-canvas); border: 1px solid var(--gs-hairline); border-radius: var(--gs-radius-sm); box-shadow: var(--gs-shadow-soft); }
.gs-doc-line { height: 5px; margin-bottom: 7px; border-radius: 4px; background: #e8edf5; }
.gs-doc-line:first-child { width: 62%; background: var(--gs-primary-mist); }
.gs-doc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 12px; }
.gs-doc-grid i { display: block; height: 22px; border-radius: 3px; background: #f1f5f9; }
.gs-doc-grid i:last-child { background: var(--gs-canvas-cream); }
.gs-package-rows { display: grid; gap: .45rem; }
.gs-package-row { display: flex; align-items: center; justify-content: space-between; padding: .56rem .65rem; color: rgba(255,255,255,.92); background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); border-radius: var(--gs-radius-sm); font-size: .72rem; }
.gs-package-row::before { content: ""; width: 5px; height: 5px; margin-right: .5rem; background: var(--gs-primary-mist); border-radius: 50%; }
.gs-package-row span { margin-left: auto; color: rgba(255,255,255,.56); font-size: .62rem; }
.gs-transform-link { color: var(--gs-primary-deep); font-size: .62rem; text-align: center; text-transform: uppercase; letter-spacing: .09em; }
.gs-transform-link::before { content: "→"; display: grid; place-items: center; width: 28px; height: 28px; margin: 0 auto .35rem; color: var(--gs-primary); background: rgba(255,255,255,.7); border: 1px solid var(--gs-primary-mist); border-radius: 50%; font-size: 1rem; }

/* Cards, uploader, chips, and status */
.gs-upload-card, .gs-export-card { position: relative; z-index: 2; }
.st-key-gs_upload_card, .st-key-gs_export_card {
  margin: -36px auto 2.5rem;
  padding: 1.7rem !important;
  background: var(--gs-canvas) !important;
  border: 1px solid var(--gs-hairline) !important;
  border-radius: var(--gs-radius-lg) !important;
  box-shadow: var(--gs-shadow-deep) !important;
  animation: gs-fade-up 560ms var(--gs-ease) both;
}
.st-key-gs_export_card { margin: 0 0 1.25rem; padding: 1.1rem 1.25rem !important; }
.gs-upload-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.gs-upload-header h2 { margin: .35rem 0 .3rem; color: var(--gs-ink); font-size: 1.55rem; font-weight: 300; letter-spacing: -.04em; }
.gs-upload-header p { margin: 0; color: var(--gs-ink-muted); font-size: .84rem; }
.gs-step-tag, .gs-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: .25rem .6rem;
  color: var(--gs-primary-deep) !important;
  background: #efefff;
  border-radius: var(--gs-radius-pill);
  font-size: .68rem;
  font-weight: 500;
  letter-spacing: .02em;
}
.gs-dropzone-hint { color: var(--gs-ink-muted) !important; font-size: .85rem; }
div[data-testid="stFileUploader"] { margin: .75rem 0 1.1rem; }
div[data-testid="stFileUploader"] section {
  min-height: 150px;
  padding: 1rem !important;
  background: var(--gs-canvas-soft) !important;
  border: 1px dashed var(--gs-input-border) !important;
  border-radius: var(--gs-radius-md) !important;
  transition: border-color 180ms var(--gs-ease), background 180ms var(--gs-ease), transform 180ms var(--gs-ease);
}
div[data-testid="stFileUploader"] section:hover { background: #f9fbff !important; border-color: var(--gs-primary) !important; transform: translateY(-1px); }
div[data-testid="stFileUploader"] small, div[data-testid="stFileUploader"] label { color: var(--gs-ink-muted) !important; }
[data-testid="stRadio"] > div { gap: .45rem !important; }
[data-testid="stRadio"] label {
  min-height: 44px;
  padding: .45rem .7rem;
  border: 1px solid var(--gs-hairline);
  border-radius: var(--gs-radius-pill);
  background: var(--gs-canvas);
  color: var(--gs-ink-secondary) !important;
  font-size: .74rem !important;
  transition: border-color 180ms var(--gs-ease), background 180ms var(--gs-ease);
}
[data-testid="stRadio"] label:has(input:checked) { border-color: var(--gs-primary) !important; background: #efefff !important; color: var(--gs-primary-deep) !important; }
.gs-action-row { margin-top: .9rem; }
.gs-action-note { align-self: center; color: var(--gs-ink-muted) !important; font-size: .75rem; }

.gs-pipeline {
  margin: 1rem 0 2.25rem;
  padding: 1.25rem;
  background: rgba(255,255,255,.72);
  border: 1px solid var(--gs-hairline);
  border-radius: var(--gs-radius-lg);
  box-shadow: var(--gs-shadow-soft);
}
.gs-pipeline-head { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: .85rem; }
.gs-pipeline-head h2 { margin: .35rem 0 0; color: var(--gs-ink); font-size: 1.35rem; font-weight: 300; letter-spacing: -.04em; }
.gs-pipeline-head span { color: var(--gs-ink-muted); font-size: .72rem; }
.gs-pipeline-track { display: grid; grid-template-columns: repeat(5, 1fr); overflow: hidden; border: 1px solid var(--gs-hairline); border-radius: var(--gs-radius-md); background: var(--gs-canvas); }
.gs-pipeline-stage { position: relative; min-height: 64px; padding: .75rem .7rem .65rem; border-right: 1px solid var(--gs-hairline); }
.gs-pipeline-stage:last-child { border-right: 0; }
.gs-pipeline-stage strong { display: block; color: var(--gs-ink-secondary); font-size: .75rem; font-weight: 500; }
.gs-pipeline-stage small { display: block; margin-top: .3rem; color: var(--gs-ink-muted); font-size: .64rem; }
.gs-pipeline-stage.is-current strong { color: var(--gs-primary-deep); }
.gs-pipeline-stage.is-current::after { content: ""; position: absolute; right: 0; bottom: 0; left: 0; height: 3px; background: var(--gs-primary); }
.gs-pipeline-stage.is-done::before { content: "✓"; display: inline-grid; place-items: center; width: 18px; height: 18px; margin-bottom: .25rem; color: var(--gs-canvas); background: var(--gs-primary); border-radius: 50%; font-size: .64rem; }
.gs-cream-band { display: grid; grid-template-columns: 1fr auto; gap: 2rem; align-items: center; margin: 1.25rem 0 2.25rem; padding: 1.35rem 1.55rem; background: var(--gs-canvas-cream); border-radius: var(--gs-radius-lg); }
.gs-cream-band h3 { margin: .25rem 0 0; color: var(--gs-ink); font-size: 1.3rem; font-weight: 300; letter-spacing: -.04em; }
.gs-stat-row { display: flex; gap: 1.25rem; }
.gs-stat { min-width: 88px; padding-left: 1.1rem; border-left: 1px solid rgba(13,37,61,.18); }
.gs-stat strong { display: block; color: var(--gs-ink); font-size: 1.6rem; font-weight: 300; letter-spacing: -.05em; }
.gs-stat span { color: var(--gs-ink-secondary); font-size: .66rem; }

/* Progress and review surfaces */
.gs-progress-shell { max-width: 720px; margin: 1.5rem auto 0; padding: 1.6rem; background: var(--gs-canvas); border: 1px solid var(--gs-hairline); border-radius: var(--gs-radius-lg); box-shadow: var(--gs-shadow-float); }
.gs-progress-header { margin-bottom: 1.1rem; }
.gs-progress-header h1 { margin: 0 0 .35rem; color: var(--gs-ink); font-size: 2.1rem; font-weight: 300; letter-spacing: -.055em; }
.gs-progress-header p { margin: 0; color: var(--gs-ink-muted); font-size: .84rem; }
.gs-stepper { display: grid; gap: .4rem; margin: 1rem 0 1.25rem; }
.gs-step { display: grid; grid-template-columns: 36px 1fr auto; gap: .75rem; align-items: center; min-height: 48px; padding: .5rem .65rem; border: 1px solid transparent; border-radius: var(--gs-radius-md); background: var(--gs-canvas-soft); transition: background 180ms var(--gs-ease), border-color 180ms var(--gs-ease), transform 180ms var(--gs-ease); }
.gs-step-idx { display: grid; place-items: center; width: 32px; height: 32px; color: var(--gs-ink-muted); background: var(--gs-canvas); border: 1px solid var(--gs-hairline); border-radius: 50%; font-size: .72rem; font-weight: 500; }
.gs-step-label { color: var(--gs-ink-secondary); font-size: .8rem; font-weight: 500; }
.gs-step-meta { color: var(--gs-ink-muted); font-size: .68rem; }
.gs-step.is-done { background: #f8f8ff; border-color: #e6e4ff; }
.gs-step.is-done .gs-step-idx { color: var(--gs-canvas); background: var(--gs-primary); border-color: var(--gs-primary); }
.gs-step.is-active { background: #efefff; border-color: var(--gs-primary-mist); transform: translateX(3px); }
.gs-step.is-active .gs-step-idx { color: var(--gs-canvas); background: var(--gs-primary-deep); border-color: var(--gs-primary-deep); animation: gs-pulse 1.8s ease-in-out infinite; }
.gs-step.is-active .gs-step-label, .gs-step.is-active .gs-step-meta { color: var(--gs-primary-deep); }
.gs-step.is-pending { opacity: .68; }
.gs-progress-message { margin: .8rem 0; color: var(--gs-ink-muted); font-size: .78rem; }
.gs-loader-wrap { display: flex; align-items: center; justify-content: center; gap: .8rem; margin: 1.35rem auto; padding: .9rem 1rem; color: var(--gs-ink-secondary); background: var(--gs-canvas-soft); border-radius: var(--gs-radius-md); }
.gs-loader { display: inline-block; width: 22px; height: 22px; border: 2px solid #dcdcff; border-top-color: var(--gs-primary); border-radius: 50%; animation: gs-pulse 1.2s ease-in-out infinite; }
.gs-loader-title { margin: 0; font-size: .8rem; font-weight: 500; }
.gs-loader-copy { margin: .15rem 0 0; color: var(--gs-ink-muted); font-size: .7rem; }
.gs-review-shell { margin: 1rem 0 1.6rem; padding: 1.4rem; color: var(--gs-canvas); background: var(--gs-navy); border-radius: var(--gs-radius-xl); box-shadow: 0 16px 40px rgba(28,30,84,.18); }
.gs-review-shell h2 { margin: .3rem 0 .25rem; color: var(--gs-canvas); font-size: 1.55rem; font-weight: 300; letter-spacing: -.045em; }
.gs-review-shell p { color: rgba(255,255,255,.68) !important; }
.gs-review-preview { display: grid; grid-template-columns: 1.3fr .7fr; gap: .75rem; margin-top: 1rem; }
.gs-review-card { padding: 1rem; background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.12); border-radius: var(--gs-radius-md); }
.gs-review-card.is-light { color: var(--gs-ink); background: var(--gs-canvas); border: 0; }
.gs-review-card h3 { margin: .25rem 0 .8rem; color: inherit; font-size: 1rem; font-weight: 400; }
.gs-review-metric { display: grid; grid-template-columns: repeat(3, 1fr); gap: .45rem; }
.gs-review-metric div { padding: .65rem; background: var(--gs-canvas-soft); border-radius: var(--gs-radius-sm); }
.gs-review-metric strong { display: block; color: var(--gs-ink); font-size: 1.1rem; font-weight: 300; }
.gs-review-metric span { color: var(--gs-ink-muted); font-size: .62rem; }

/* TKP content primitives */
.gs-content-block { margin: .6rem 0; padding: .95rem 1rem; background: var(--gs-canvas); border: 1px solid var(--gs-hairline); border-radius: var(--gs-radius-md); box-shadow: var(--gs-shadow-soft); }
.gs-content-block h4 { margin: 0 0 .35rem; color: var(--gs-ink); font-size: .94rem; font-weight: 500; letter-spacing: -.02em; }
.gs-content-block p, .gs-content-block li { color: var(--gs-ink-secondary) !important; font-size: .82rem; line-height: 1.55; }
.gs-chips { display: flex; flex-wrap: wrap; gap: .42rem; margin: .55rem 0 1rem; }
.gs-chip { display: inline-flex; align-items: center; min-height: 26px; padding: .28rem .62rem; color: var(--gs-primary-deep) !important; background: #efefff; border: 1px solid #dfddff; border-radius: var(--gs-radius-pill); font-size: .68rem; font-weight: 500; }
.gs-badge.amber { color: #8b5d22 !important; background: var(--gs-canvas-cream); }
.gs-empty-state { padding: 2rem; text-align: center; background: var(--gs-canvas); border: 1px dashed var(--gs-input-border); border-radius: var(--gs-radius-lg); }
.gs-empty-state h2 { margin: 0 0 .4rem; color: var(--gs-ink); font-size: 1.3rem; font-weight: 300; }
.gs-empty-state p { margin: 0 auto 1rem; max-width: 32rem; color: var(--gs-ink-muted) !important; font-size: .85rem; }

/* Streamlit primitives */
[data-testid="stProgress"] > div > div > div > div { background: var(--gs-primary) !important; }
[data-testid="stProgress"] > div { background: #e8e8fb !important; }
[data-testid="stMetric"] { padding: .85rem; background: var(--gs-canvas-soft); border-radius: var(--gs-radius-md); }
[data-testid="stMetricLabel"] { color: var(--gs-ink-muted) !important; font-size: .7rem !important; }
[data-testid="stMetricValue"] { color: var(--gs-ink) !important; font-weight: 300 !important; }
[data-testid="stExpander"] { overflow: hidden; border: 1px solid var(--gs-hairline) !important; border-radius: var(--gs-radius-md) !important; background: var(--gs-canvas) !important; }
[data-testid="stExpander"] summary { color: var(--gs-ink-secondary) !important; }
[data-baseweb="tab-list"] { gap: .35rem; border-bottom: 1px solid var(--gs-hairline); }
button[data-baseweb="tab"] { min-height: 38px !important; padding: .45rem .75rem !important; color: var(--gs-ink-muted) !important; border-radius: var(--gs-radius-pill) var(--gs-radius-pill) 0 0 !important; font-size: .78rem !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: var(--gs-primary-deep) !important; background: #efefff !important; }

.gs-footer-note { margin-top: 2rem; color: var(--gs-ink-muted) !important; text-align: center; font-size: .72rem; }

@media (max-width: 820px) {
  .block-container { width: min(100% - 24px, 720px) !important; }
  .gs-hero { grid-template-columns: 1fr; margin-left: calc((720px - 100vw) / 2); margin-right: calc((720px - 100vw) / 2); padding-top: 54px; }
  .gs-hero-copy { max-width: 680px; }
  .gs-hero-transform { max-width: 640px; }
  .gs-cream-band { grid-template-columns: 1fr; gap: 1rem; }
  .gs-stat-row { justify-content: space-between; }
}
@media (max-width: 620px) {
  .block-container { width: min(100% - 16px, 560px) !important; padding-top: 8px !important; }
  .st-key-gs_nav_bar { top: .35rem; padding: .45rem .55rem; border-radius: var(--gs-radius-lg); }
  .st-key-gs_nav_bar .gs-nav-brand { font-size: .82rem; }
  .st-key-gs_nav_bar div.stButton > button { padding: .35rem .55rem !important; font-size: .72rem !important; }
  .gs-hero { display: block; min-height: auto; margin-left: -8px; margin-right: -8px; padding: 44px 20px 78px; }
  .gs-brand { font-size: clamp(2.5rem, 13vw, 3.5rem) !important; }
  .gs-hero-transform { grid-template-columns: 1fr; gap: .65rem; margin-top: 2rem; }
  .gs-transform-link { display: flex; align-items: center; justify-content: center; gap: .45rem; }
  .gs-transform-link::before { display: inline-grid; margin: 0; transform: rotate(90deg); }
  .gs-source-card, .gs-package-card { min-height: auto; }
  .st-key-gs_upload_card { margin-top: -28px; padding: 1rem !important; }
  .gs-upload-header { display: block; }
  .gs-step-tag { margin-top: .75rem; }
  .gs-pipeline-track { grid-template-columns: 1fr; }
  .gs-pipeline-stage { border-right: 0; border-bottom: 1px solid var(--gs-hairline); }
  .gs-pipeline-stage:last-child { border-bottom: 0; }
  .gs-review-preview { grid-template-columns: 1fr; }
  .gs-review-metric { grid-template-columns: repeat(3, 1fr); }
  [data-baseweb="tab-list"] { overflow-x: auto; padding-bottom: .25rem; }
  button[data-baseweb="tab"] { flex: 0 0 auto; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
</style>
        """,
        unsafe_allow_html=True,
    )
