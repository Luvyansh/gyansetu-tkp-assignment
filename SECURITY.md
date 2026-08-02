# Security notes — GyanSetu TKP

Last reviewed: 2026-08-02 against `uv.lock` as of commit on `feature/tkp-pipeline`
(`langchain-core==0.3.86`, `langgraph==0.6.11`, `langgraph-checkpoint==3.0.1`).

This document records **reachability** analysis for dependency CVEs flagged by
`uv run pip-audit`. An installed vulnerable package is not an exploitable finding
until application code reaches the vulnerable API with attacker-influenced input.

## Already patched (do not re-flag)

| CVE | Package | Status |
|---|---|---|
| **CVE-2025-68664** (serialization injection in `dumps`/`loads`) | `langchain-core` | **Patched** at ≥ `0.3.81`. We ship **`0.3.86`**. `pip-audit` does not report this CVE against the current lockfile. |

## Focus CVEs — reachability verdicts

### CVE-2026-34070 — `langchain-core` path traversal via legacy prompt loading

**Verdict: (a) not reachable.**

- Vulnerable APIs: `langchain_core.prompts.loading.load_prompt` /
  `load_prompt_from_config` (legacy file-path loading from config dicts).
- **Our code never imports or calls those APIs.** Repo-wide search for
  `langchain_core.prompts`, `from langchain`, and `import langchain` under
  `backend/`, `evals/`, and `frontend/` returns **zero matches**.
- The symbol named `load_prompt` in this project is
  **`backend.app.graph.prompt_loader.load_prompt`**, which reads only
  fixed filenames under `backend/app/graph/prompts/` (no user-controlled path).
  Evidence: `inspect` / module path resolves to `backend.app.graph.prompt_loader`;
  call sites in graph nodes pass hardcoded template names like
  `"n2_classification.md"`.
- `pip-audit` still lists this CVE against `0.3.86` with a suggested fix of
  `langchain-core>=1.2.22` (major line). Upstream's `langchain-core==0.3.86`
  release notes also claim a v0.3 backport of the same path-traversal fix; either
  way, **our app does not exercise the vulnerable API**, so no upgrade is required
  for exploitability. A major bump to `1.x` is flagged for a separate decision
  (eval/transitive stack impact), not done here.

### CVE-2026-28277 — LangGraph unsafe msgpack checkpoint deserialization

**Verdict: (a) not reachable.**

- The bug requires loading a **persistent checkpointer** from a backing store an
  attacker can tamper with (crafted msgpack → unsafe object reconstruction).
- We compile the graph with **`graph.compile()` and no `checkpointer=` argument**
  (`backend/app/graph/build_graph.py`). There are **zero** references to
  `checkpointer`, `SqliteSaver`, `AsyncSqliteSaver`, `MemorySaver`, or
  `PostgresSaver` under `backend/`.
- Pipeline execution is ephemeral `ainvoke(initial_state)` — state lives in
  process memory for that run only; we do not resume from serialized checkpoints.
- Suggested fix versions are `langgraph>=1.0.10` (major from `0.6.x`). **Deferred**
  as unreachable; do not bump unilaterally.

### CVE-2025-67644 — SQL injection in `langgraph-checkpoint-sqlite` metadata filters

**Verdict: (a) not reachable — package not installed.**

- Affects **`langgraph-checkpoint-sqlite`** (`SqliteSaver` metadata filter keys).
- `uv pip show langgraph-checkpoint-sqlite` → package not found.
- `uv.lock` contains **no** `langgraph-checkpoint-sqlite` entry.
- `importlib.util.find_spec("langgraph.checkpoint.sqlite")` → **MISSING**.
- We use **Postgres + SQLAlchemy** for app data, not LangGraph SQLite checkpoints.
  The transitive package that *is* present is `langgraph-checkpoint` (base serde),
  which is a different artifact than the SQLite backend named in this CVE.

## Other `pip-audit` noise (summary)

`pip-audit` currently reports additional findings in transitive / eval / dev
packages (`langchain`, `langchain-openai`, `langchain-text-splitters`,
`langgraph-checkpoint`, `langgraph-sdk`, `ragas`, `diskcache`, `pytest`). None of
these are in our direct production call path for document upload → TKP generation
beyond LangGraph's in-memory graph (already covered above). Re-audit after any
intentional major upgrade of the LangChain/LangGraph stack.

## Application controls (non-CVE)

- Shared-secret `X-API-Key` on non-health endpoints; CORS allowlist; upload size /
  magic-byte checks; `slowapi` rate limits; secret redaction in structlog;
  `bandit` on `backend/app` (B101 assert in LLM router / B105 false-positive on
  validation enum label `pass` are accepted low noise).

## How to re-verify

```bash
uv run pip-audit
# Reachability greps:
#   langchain_core.prompts / from langchain  → expect empty in app code
#   checkpointer / SqliteSaver               → expect empty
#   uv pip show langgraph-checkpoint-sqlite  → expect not installed
```
