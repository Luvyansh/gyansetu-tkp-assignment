# Gyansetu TKP — Teacher Knowledge Package

AI pipeline that turns educational documents (PDF/DOCX/PPTX) into a structured
`TeacherKnowledgePackage.json` plus exportable PDFs via a 10-stage LangGraph workflow.

> Full setup, architecture, and decision log are in this README (see sections below).
> Deployment notes live in `deployment.md` (gitignored; filled during the deploy phase).

## Pipeline

```mermaid
flowchart LR
    A[Upload] --> B[Stage 1: Document Intelligence]
    B --> C[Stage 2: Educational Classification]
    C --> D[Stage 3: Knowledge Extraction]
    D --> E[Stage 4: Teaching Planner]
    E --> F[Stage 5: Classroom Content Gen]
    E --> G[Stage 6: Activity Gen]
    E --> H[Stage 7: Assessment Gen]
    D --> I[Stage 8: Learning Gap Analysis]
    F & G & H & I --> J[Stage 9: Validation]
    J -->|fail| E
    J -->|pass| K[Stage 10: Publish TKP.json]
```

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # then fill GEMINI_API_KEY, BACKEND_API_KEY, etc.
docker compose -f docker-compose.dev.yml up -d
uv run alembic upgrade head
# optional: uv run pre-commit install
```

### Makefile shortcuts

```bash
make sync          # uv sync --extra dev
make backend       # uvicorn on :8000
make frontend      # Streamlit
make test          # full pytest + coverage (≥80%)
make test-unit     # unit tests only (pre-commit speed)
make lint          # ruff
make typecheck     # mypy
make eval          # mocked golden-dataset evals → evals/reports/latest_*
make docker-build  # multi-stage backend image
```

On Windows without `make`, run the underlying `uv run …` commands from the Makefile.

### Run backend

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
```

### Run frontend

```bash
uv run streamlit run frontend/streamlit_app.py
```

### Tests & evals

```bash
uv run pytest
uv run python evals/run_ragas_eval.py --mock   # CI-safe; no live LLM keys required
```

Faithfulness threshold: **≥ 0.85** (`FAITHFULNESS_THRESHOLD` / `settings.faithfulness_threshold`).
Reports: `evals/reports/latest_report.json`, `evals/reports/latest_summary.md`.

## Orchestration

LangGraph carries a single `TKPState` through 10 typed nodes. Stage 9 validation can
route back to generation nodes with a bounded retry count. Stages 5–7 fan out per period;
Stage 8 runs in parallel with them (depends only on Stage 3).

## Design decisions

- **Decision:** pgvector on Postgres / **Because:** one free resource instead of a separate vector DB.
- **Decision:** Gemini primary, Groq fallback / **Because:** Gemini's context + multimodal for chapters; Groq for speed/overflow on high-volume generation.
- **Decision:** no Celery/Redis in v1 / **Because:** single-reviewer demo; asyncio + FastAPI background tasks suffice.
- **Decision:** hallucination check via embedding similarity + LLM judge / **Because:** FAQ grounding rule — facts from source only; pedagogy may be general.
- **Decision:** flexible period count / **Because:** FAQ Q3 — driven by content volume/complexity, not hardcoded 5×40.

## Eval thresholds

Minimum acceptable: faithfulness ≥ 0.85 (see `FAITHFULNESS_THRESHOLD`).

### Security audit notes

`uv run bandit -r backend/app` reports no medium/high issues. `uv run pip-audit` may flag
transitive CVEs in `langgraph` / `langchain-*` / `ragas` / `pytest` (dev) pulled by the eval
stack; fixes require major-version bumps not yet compatible with `pytest-asyncio` on Python 3.12.
Re-run after upstream releases; production attack surface is the FastAPI upload path, not eval CLI.

## Deployment

See `deployment.md` (not committed). Filled in during the deployment phase.
