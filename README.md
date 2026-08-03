# Gyansetu TKP — Teacher Knowledge Package

> **Note:** Built for the GyanSetu / IIT Mandi AI Engineer Internship technical
> assessment. See [LICENSE](./LICENSE) — usage beyond evaluating this application
> requires the author's permission.

Turns educational documents (**PDF / DOCX / PPTX**) into a structured
`TeacherKnowledgePackage.json` plus exportable PDFs (lesson plan, teacher guide,
assessment book) through a **10-stage LangGraph** pipeline.

| Surface | URL (local) | Stack |
|---|---|---|
| API | http://127.0.0.1:8000 | FastAPI + LangGraph + Postgres/pgvector |
| UI | http://localhost:8501 | Streamlit (upload → live progress → review) |
| Docs | http://127.0.0.1:8000/docs | OpenAPI |

---

## Architecture

```mermaid
flowchart TB
    subgraph Client
        UI[Streamlit UI<br/>upload / SSE progress / review]
    end

    subgraph API["FastAPI :8000"]
        DOC[Documents + Jobs routes]
        SSE[SSE job stream]
        BG[Background pipeline runner]
        DOC --> BG
        SSE --> BG
    end

    subgraph Pipeline["LangGraph TKP pipeline"]
        G[10-stage graph<br/>TKPState]
    end

    subgraph LLM["LLM + embeddings"]
        R[LLMRouter]
        LITE[Gemini Flash-Lite]
        GROQ[Groq Llama]
        FLASH[Gemini Flash<br/>last resort]
        MINI[Local MiniLM<br/>all-MiniLM-L6-v2 · 384-d]
        R --> LITE
        LITE -.->|429 / fail| GROQ
        GROQ -.->|fail| FLASH
        R --> MINI
    end

    subgraph Data["Postgres :5433 · pgvector"]
        DB[(documents · jobs · stage_outputs<br/>tkp_packages · knowledge_chunks<br/>llm_cache)]
    end

    UI -->|X-API-Key| DOC
    UI -->|X-API-Key| SSE
    BG --> G
    G --> R
    G --> DB
    R --> DB
```

**Why these pieces**

- **Postgres + pgvector** — single store for jobs, TKP JSON, LLM cache, and chunk embeddings (no separate vector DB).
- **Local MiniLM** — embeddings never call Gemini/Groq (avoids embed quota burn).
- **Flash-Lite primary** — generation stays under free-tier Flash RPD; Groq absorbs overflow; full Flash only as last resort.
- **No Celery/Redis in v1** — FastAPI `BackgroundTasks` + asyncio are enough for a single-reviewer demo.

---

## Pipeline (10 stages)

```mermaid
flowchart TD
    START([Upload document]) --> N1

    N1[1 · Document Intelligence<br/>parse PDF/DOCX/PPTX · multimodal if needed]
    N2[2 · Educational Classification<br/>subject · grade · topic · category]
    N3[3 · Knowledge Extraction<br/>concepts · definitions · chunk + embed]
    N4[4 · Teaching Planner<br/>flexible period count]
    PAR[5–8 · Parallel generation]
    N5[5 · Classroom content]
    N6[6 · Activities]
    N7[7 · Assessments]
    N8[8 · Learning gap analysis]
    N9[9 · Validation<br/>schema · groundedness · consistency]
    N10[10 · Publish<br/>TKP JSON + PDF exports]
    FAIL([Failed · max retries])

    N1 --> N2 --> N3 --> N4 --> PAR
    PAR --> N5 & N6 & N7 & N8
    N5 & N6 & N7 & N8 --> N9
    N9 -->|pass| N10
    N9 -->|fail · retries left| N4
    N9 -->|fail · exhausted| FAIL
    N10 --> END([Completed])
```

| Stage | Role |
|---|---|
| 1 Document Intelligence | Route text vs multimodal parse; extract structure |
| 2 Classification | Subject, grade, topic, STEM/humanities category |
| 3 Knowledge extraction | Concepts/definitions; chunk text; **local** embeddings → pgvector |
| 4 Teaching planner | Period plan sized to content (not a fixed 5×40) |
| 5–7 Generation | Classroom scripts, activities, assessments (per period) |
| 8 Gap analysis | Prerequisite / misconception gaps (depends on Stage 3 only) |
| 9 Validation | Schema + consistency + groundedness (cosine, then LLM judge if below threshold) |
| 10 Publish | Persist `TeacherKnowledgePackage` + render three PDFs |

Stages **5–8 run concurrently** after the teaching plan. Stage **9** may loop back to Stage **4** up to `MAX_VALIDATION_RETRIES` (default 2).

---

## LLM routing

```mermaid
flowchart LR
    subgraph Generate
        S[Stage generate / multimodal] --> L[gemini-3.5-flash-lite]
        L -->|rate limit / error| G[Groq · text stages]
        G -->|fail or unset| F[gemini-3.5-flash]
        L -->|multimodal · no Groq vision| F
    end

    subgraph Embed
        E[router.embed] --> M[sentence-transformers<br/>all-MiniLM-L6-v2]
        M --> C[(embed cache in Postgres)]
    end
```

- **Generate:** Flash-Lite → Groq (eligible text stages) → full Flash last.
- **Embed:** always local MiniLM (384-d); Gemini `embed_content` is never used.
- Model lazy-loads on first embed (`device="cpu"`); not at API startup (Render 512MB).

---

## User flow (Streamlit)

```mermaid
flowchart LR
    U[1 · Upload<br/>PDF/DOCX/PPTX + hint] --> P[2 · Progress<br/>SSE stage stepper]
    P -->|completed| R[3 · Review<br/>TKP tabs · JSON · PDFs]
    P -->|failed| R
```

1. **Upload** — `frontend/pages/1_upload.py` → `POST /api/v1/documents/upload`
2. **Progress** — SSE `GET /api/v1/jobs/{id}/stream` drives the 10-stage stepper
3. **Review** — TKP viewer, JSON download, PDF exports via `/api/v1/jobs/{id}/export/{artifact}`

Auth: same `BACKEND_API_KEY` as the API (`X-API-Key`). Streamlit loads `.env` automatically.

---

## Setup

Requires: **Python 3.12+**, [uv](https://github.com/astral-sh/uv), **Docker** (Postgres).

```bash
uv sync --extra dev
cp .env.example .env          # fill GEMINI_API_KEY, BACKEND_API_KEY; GROQ_API_KEY optional
docker compose -f docker-compose.dev.yml up -d
uv run alembic upgrade head   # 0001_initial → 0002_embed_dim_384
```

### Environment (see `.env.example`)

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | yes | Flash-Lite / Flash / multimodal |
| `BACKEND_API_KEY` | yes | API + Streamlit shared secret |
| `DATABASE_URL` | yes | default `postgresql+asyncpg://tkp:tkp@localhost:5433/tkp` |
| `GROQ_API_KEY` | no | enables Groq fallback; Gemini-only if absent |
| `FAITHFULNESS_THRESHOLD` | no | default **0.85** |
| `EMBEDDING_DIM` | no | **384** (must match MiniLM + Alembic `0002`) |
| `CORS_ORIGINS` | no | default includes `http://localhost:8501` |

### Run (three processes)

```bash
# 1) DB (if not already up)
docker compose -f docker-compose.dev.yml up -d

# 2) API
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 3) UI (second terminal)
uv run streamlit run frontend/streamlit_app.py --server.port 8501
```

**Windows (PowerShell)** — same commands; use two terminals for API and UI. Without `make`, run the `uv run …` lines below instead of Makefile targets.

Health: `GET http://127.0.0.1:8000/health` → `database: up`, key presence flags.

### Makefile shortcuts

```bash
make sync          # uv sync --extra dev
make dev-db        # docker compose up -d
make migrate       # alembic upgrade head
make backend       # uvicorn :8000
make frontend      # Streamlit
make test          # pytest + ≥80% coverage
make test-unit     # unit only
make lint          # ruff
make typecheck     # mypy
make eval          # mocked golden evals → evals/reports/latest_*
make docker-build  # backend image
```

---

## Project layout

```
backend/app/
  api/           # documents, jobs, SSE stream, pipeline runner
  graph/         # LangGraph build + n1…n10 nodes
  llm/           # router, Gemini/Groq clients, local MiniLM, rate limit, cache
  parsing/       # PDF/DOCX/PPTX + multimodal fallback
  validation/    # schema, groundedness, consistency
  pdf_export/    # ReportLab lesson-plan / teacher-guide / assessment-book
  db/            # SQLAlchemy models, session, vector helpers
  schemas/       # Pydantic TKP + stage payloads
frontend/        # Streamlit pages + theme + TKP viewer
migrations/      # Alembic (incl. embed dim 384)
evals/           # RAGAS-style golden STEM/humanities suite
samples/         # live-verified TKP JSON + PDF exports
test_assets/     # local-only large PDFs (gitignored *.pdf)
```

---

## API (prefix `/api/v1`)

All mutating/read job routes require header `X-API-Key: <BACKEND_API_KEY>`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + DB + key presence |
| `POST` | `/documents/upload` | Upload file; optional `auto_start` |
| `GET` | `/documents/{id}` | Document metadata |
| `POST` | `/jobs/{id}/start` | Start / restart pipeline |
| `GET` | `/jobs/{id}` | Job status |
| `GET` | `/jobs/{id}/stream` | SSE progress events |
| `GET` | `/jobs/{id}/tkp` | Full `TeacherKnowledgePackage` JSON |
| `GET` | `/jobs/{id}/export/{artifact}` | PDF: `lesson-plan` · `teacher-guide` · `assessment-book` |
| `GET` | `/jobs/{id}/stages` | Persisted stage outputs |

Interactive docs: `/docs`.

---

## Sample artifacts

Live end-to-end runs (Flash-Lite + local MiniLM, threshold 0.85) are checked in under [`samples/`](./samples/):

| File | Content |
|---|---|
| `tkp_sample_geography.json` | Class 9 Geography — *Shaping of the Earth's Surface* |
| `tkp_sample_humanities.json` | Class 9 History — *The French Revolution* |
| `*_lesson-plan.pdf` / `*_teacher-guide.pdf` / `*_assessment-book.pdf` | Matching PDF exports |
| `live_run_summary.json` | Wall-clock + provider usage notes from the live pass |

Place optional large chapter PDFs under `test_assets/` locally (gitignored). NCERT cost tests **skip in CI** when that file is absent.

---

## Validation & evals

**Groundedness:** reuse Stage 3 chunk embeddings; embed only query texts; if average cosine &lt; `FAITHFULNESS_THRESHOLD`, run an LLM faithfulness judge.

**Threshold stays 0.85** after MiniLM migration. A real Period 3 hallucination case scores ~0.80 under MiniLM and would **auto-pass at 0.50** without the judge (see [ISSUES.md](./ISSUES.md)).

```bash
uv run pytest -m "not live_llm"          # CI-equivalent
uv run python evals/run_ragas_eval.py --mock
```

Reports: `evals/reports/latest_report.json`, `evals/reports/latest_summary.md`.

---

## Design decisions

- **Local `all-MiniLM-L6-v2` (384-d) → pgvector** — Gemini Embedding free-tier caps were burning demos; model loads once at startup; Alembic `0002_embed_dim_384`.
- **Flash-Lite → Groq → Flash last-resort** — Flash 20 RPD was the binding quota; Lite (~250K TPM) covers full-doc stages; Groq absorbs overflow.
- **pgvector on Postgres** — one free resource instead of a separate vector DB.
- **No Celery/Redis in v1** — asyncio + FastAPI background tasks suffice for single-reviewer use.
- **Hallucination = embedding gate + LLM judge; threshold 0.85** — FAQ: facts from source only; pedagogy may be general. Synthetic MiniLM bands suggested 0.50; the live “agents of gradation” case does not.
- **Flexible period count** — driven by content volume/complexity (FAQ Q3), not hardcoded 5×40.
- **Topic-scoped knowledge extraction** — Stage 3 prompt + post-filter keep concepts on the classified subject/topic.

---

## Security

See **[SECURITY.md](./SECURITY.md)** for pip-audit CVE reachability (patched vs installed-but-unreachable). App controls: API-key auth, CORS allowlist, upload size/type checks, rate limits, secret redaction, `bandit` on `backend/app`.

Engineering issue log: **[ISSUES.md](./ISSUES.md)**.
