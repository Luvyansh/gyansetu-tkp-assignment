"""Custom GyanSetu TKP theme — soft sage, charcoal, and warm gold."""

from __future__ import annotations

import streamlit as st


def inject_theme() -> None:
    """Inject Google Fonts + CSS variables and chrome overrides."""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,500;7..72,600;7..72,700&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

:root {
  --gs-ink: #1C1917;
  --gs-charcoal: #292524;
  --gs-ink-muted: #57534E;
  --gs-sage: #5B7C6E;
  --gs-sage-deep: #3F5A4E;
  --gs-sage-soft: #8FA99B;
  --gs-sage-mist: rgba(91, 124, 110, 0.14);
  --gs-gold: #C4A020;
  --gs-gold-deep: #9A7B12;
  --gs-gold-soft: #E8D48A;
  --gs-paper: #F3EFE6;
  --gs-paper-deep: #E6E0D4;
  --gs-white: #FCFAF6;
  --gs-border: #D6D0C4;
  --gs-danger: #9B2C2C;
  --gs-radius: 12px;
  --gs-shadow: 0 14px 36px rgba(28, 25, 23, 0.08);
  --font-display: 'Literata', 'Iowan Old Style', Georgia, serif;
  --font-body: 'DM Sans', 'Segoe UI', sans-serif;
}

html, body, [class*="css"] {
  font-family: var(--font-body) !important;
  color: var(--gs-ink);
}

.stApp {
  background:
    radial-gradient(ellipse 90% 55% at 8% -8%, rgba(143, 169, 155, 0.28), transparent 52%),
    radial-gradient(ellipse 70% 45% at 96% 4%, rgba(196, 160, 32, 0.16), transparent 48%),
    radial-gradient(ellipse 50% 35% at 50% 100%, rgba(91, 124, 110, 0.10), transparent 55%),
    linear-gradient(165deg, #F6F2EA 0%, var(--gs-paper) 42%, var(--gs-paper-deep) 100%) !important;
}
.stApp::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.035;
  background-image:
    linear-gradient(rgba(28, 25, 23, 0.55) 1px, transparent 1px),
    linear-gradient(90deg, rgba(28, 25, 23, 0.55) 1px, transparent 1px);
  background-size: 28px 28px;
  z-index: 0;
}

[data-testid="stHeader"] {
  background: transparent !important;
  border-bottom: none !important;
}
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--gs-charcoal) 0%, #1C1917 100%) !important;
}
section[data-testid="stSidebar"] * {
  color: var(--gs-paper) !important;
}

.block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 3rem !important;
  max-width: 1160px !important;
  position: relative;
  z-index: 1;
}

h1, h2, h3, .gs-brand, .gs-display {
  font-family: var(--font-display) !important;
  letter-spacing: -0.02em;
  color: var(--gs-ink) !important;
}

/* —— Full-bleed hero —— */
.gs-hero {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: clamp(1.5rem, 4vw, 3rem);
  align-items: center;
  min-height: min(72vh, 640px);
  margin: -0.5rem -1rem 1.5rem -1rem;
  padding: clamp(1.5rem, 4vw, 3rem) clamp(1rem, 3vw, 2rem);
  position: relative;
  overflow: hidden;
}
.gs-hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(115deg, rgba(63, 90, 78, 0.92) 0%, rgba(41, 37, 36, 0.88) 55%, rgba(28, 25, 23, 0.82) 100%);
  z-index: 0;
}
.gs-hero > * { position: relative; z-index: 1; }

@media (max-width: 900px) {
  .gs-hero {
    grid-template-columns: 1fr;
    min-height: auto;
    gap: 1.25rem;
    margin-left: -0.5rem;
    margin-right: -0.5rem;
  }
  .gs-hero-art { order: -1; max-width: 280px; margin: 0 auto; }
}

.gs-brand {
  font-size: clamp(2.75rem, 6vw, 4.1rem) !important;
  font-weight: 700 !important;
  line-height: 1.02 !important;
  margin: 0 0 0.85rem 0 !important;
  color: #FCFAF6 !important;
}
.gs-brand span {
  color: var(--gs-gold-soft);
}

.gs-pitch {
  font-size: 1.12rem;
  line-height: 1.55;
  color: rgba(252, 250, 246, 0.82);
  max-width: 34rem;
  margin: 0 0 1.25rem 0;
}

.gs-hero-art svg {
  width: 100%;
  height: auto;
  filter: drop-shadow(0 18px 32px rgba(0, 0, 0, 0.28));
}

.gs-hero-cta {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--gs-gold-soft);
  letter-spacing: 0.02em;
}

/* —— Interaction panels (not in hero) —— */
.gs-panel {
  background: var(--gs-white);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius);
  box-shadow: var(--gs-shadow);
  padding: 1.35rem 1.5rem;
  margin-bottom: 1rem;
}

.gs-panel-title {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--gs-ink);
  margin: 0 0 0.85rem 0;
}

.gs-dropzone-hint {
  font-size: 0.9rem;
  color: var(--gs-ink-muted);
  margin: 0 0 0.75rem 0;
}

/* —— Stepper —— */
.gs-stepper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0 1.5rem 0;
}
.gs-step {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.7rem 0.9rem;
  border-radius: 10px;
  border: 1px solid var(--gs-border);
  background: var(--gs-white);
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}
.gs-step.is-done {
  border-color: rgba(91, 124, 110, 0.4);
  background: linear-gradient(90deg, var(--gs-sage-mist), var(--gs-white));
}
.gs-step.is-active {
  border-color: var(--gs-gold);
  background: linear-gradient(90deg, rgba(232, 212, 138, 0.4), var(--gs-white));
  transform: translateX(4px);
  box-shadow: 0 6px 18px rgba(196, 160, 32, 0.16);
}
.gs-step.is-pending { opacity: 0.7; }
.gs-step-idx {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-size: 0.8rem; font-weight: 700;
  background: var(--gs-paper-deep);
  color: var(--gs-sage-deep);
}
.gs-step.is-done .gs-step-idx {
  background: var(--gs-sage);
  color: var(--gs-white);
}
.gs-step.is-active .gs-step-idx {
  background: var(--gs-gold);
  color: var(--gs-ink);
}
.gs-step-label {
  font-weight: 600;
  color: var(--gs-ink);
}
.gs-step-meta {
  font-size: 0.78rem;
  color: var(--gs-ink-muted);
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
  color: var(--gs-sage-deep);
}
.gs-badge.amber {
  background: rgba(196, 160, 32, 0.22);
  color: var(--gs-gold-deep);
}

.gs-card-soft {
  background: var(--gs-paper);
  border-left: 3px solid var(--gs-sage);
  border-radius: 0 8px 8px 0;
  padding: 0.85rem 1rem;
  margin: 0.55rem 0;
}
.gs-card-soft h4 {
  margin: 0 0 0.35rem 0;
  font-family: var(--font-display);
  color: var(--gs-ink);
  font-size: 1rem;
}
.gs-card-soft p, .gs-card-soft li {
  color: var(--gs-ink-muted);
  margin: 0.2rem 0;
  font-size: 0.95rem;
}

.gs-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin: 0.5rem 0 1rem 0;
}
.gs-chip {
  background: var(--gs-white);
  border: 1px solid var(--gs-border);
  color: var(--gs-sage-deep);
  border-radius: 6px;
  padding: 0.25rem 0.7rem;
  font-size: 0.82rem;
  font-weight: 600;
}

div.stButton > button {
  background: var(--gs-sage-deep) !important;
  color: var(--gs-white) !important;
  border: none !important;
  border-radius: 8px !important;
  font-family: var(--font-body) !important;
  font-weight: 600 !important;
  padding: 0.55rem 1.35rem !important;
  box-shadow: 0 8px 20px rgba(63, 90, 78, 0.22) !important;
  transition: transform 0.15s ease, background 0.15s ease !important;
}
div.stButton > button:hover {
  background: var(--gs-sage) !important;
  transform: translateY(-1px);
  color: var(--gs-white) !important;
}
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  color: var(--gs-sage-deep) !important;
  border: 1.5px solid var(--gs-sage) !important;
  box-shadow: none !important;
}

div[data-testid="stFileUploader"] {
  background: var(--gs-white);
  border: 2px dashed var(--gs-sage-soft) !important;
  border-radius: var(--gs-radius);
  padding: 0.75rem 0.5rem;
}
div[data-testid="stFileUploader"]:hover {
  border-color: var(--gs-gold) !important;
  background: rgba(252, 250, 246, 0.98);
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
  background: transparent;
  border-bottom: 2px solid var(--gs-border);
}
.stTabs [data-baseweb="tab"] {
  font-family: var(--font-body);
  font-weight: 600;
  color: var(--gs-ink-muted);
  border-radius: 8px 8px 0 0;
  padding: 0.55rem 0.9rem;
}
.stTabs [aria-selected="true"] {
  color: var(--gs-sage-deep) !important;
  background: var(--gs-sage-mist);
}

.stProgress > div > div > div > div {
  background: linear-gradient(90deg, var(--gs-sage), var(--gs-gold)) !important;
}

div[data-testid="stAlert"] {
  border-radius: 10px;
}

.gs-footer-note {
  margin-top: 2rem;
  font-size: 0.85rem;
  color: var(--gs-ink-muted);
  text-align: center;
}

.gs-nav-row {
  margin-bottom: 0.5rem;
}

@keyframes gs-fade-up {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes gs-soft-pulse {
  0%, 100% { opacity: 0.85; }
  50% { opacity: 1; }
}
.gs-hero {
  animation: gs-fade-up 0.6s ease both;
}
.gs-panel, .gs-stepper {
  animation: gs-fade-up 0.5s ease both;
}
.gs-hero-art {
  animation: gs-soft-pulse 4.5s ease-in-out infinite;
}
.gs-step:nth-child(odd) { animation: gs-fade-up 0.45s ease both; }
</style>
        """,
        unsafe_allow_html=True,
    )
