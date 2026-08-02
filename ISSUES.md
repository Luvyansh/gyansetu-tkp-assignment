# Issues log

Running engineering log for bugs, failed checks, security findings, and accepted risks.
Newest entries at the top. Append on every real finding — do not wait to be asked.

---

## [2026-08-02] Wrong Gemini model IDs → free-tier limit:0 (not quota exhaustion)

**Found:** Stage 2 (`educational_classification`) failed with
`429 RESOURCE_EXHAUSTED` against `gemini-2.0-flash-lite`. Full SDK body showed
free-tier quotas with **`limit: 0`** for that model id — not a nonzero daily
allowance that had been consumed:

- metric `generate_content_free_tier_input_token_count` /
  quotaId `GenerateContentInputTokensPerModelPerMinute-FreeTier`
  → model `gemini-2.0-flash-lite`, limit 0
- metric `generate_content_free_tier_requests` /
  quotaIds `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` and
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
  → model `gemini-2.0-flash-lite`, limit 0

`client.models.list()` still lists `models/gemini-2.0-flash(-lite)`, but live
`generate_content` probes showed:

| Model | Result |
| --- | --- |
| `gemini-2.0-flash-lite` / `gemini-2.0-flash` | 429, free-tier **limit: 0** (retired 2026-06-01) |
| `gemini-2.5-flash-lite` / `gemini-2.5-flash` | 404 "no longer available to **new users**" |
| `gemini-3.5-flash-lite` / `gemini-3.5-flash` / `gemini-3.1-flash-lite` | success |
| `text-embedding-004` | 404 not found for this key |
| `gemini-embedding-001` | success (request `output_dimensionality=768`) |

**Cause:** Hardcoded retired Gemini 2.0 model strings in
`backend/app/llm/gemini_client.py`. Google documents retirement of
`gemini-2.0-flash` / `gemini-2.0-flash-lite` on 2026-06-01; free tier exposes
that as quota limit 0 rather than a clean "model retired" error. Prior ISSUES
entry incorrectly filed this as ordinary free-tier exhaustion.

**Fix:** Point defaults at current models available to this API key:
`gemini-3.5-flash-lite`, `gemini-3.5-flash`, and `gemini-embedding-001`
(with `output_dimensionality=768` for the pgvector column).

**Smoke re-check (`stem_sample.pdf`):** Stage 2 completed on
`gemini-3.5-flash-lite` (Physics / Class 9 / Laws of Motion). Stage 3
extracted 4 concepts on `gemini-3.5-flash` (Newton's 1st/2nd/3rd + Photosynthesis
from the golden sample). Job later failed in `parallel_generation` with a
**different** 429: genuine free-tier RPM on `gemini-3.5-flash`
(`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, **limit: 5**,
`quotaValue: 5`) — nonzero limit, real exhaustion, not the limit:0 bug.
**Status:** Fixed (this commit)

---

## [2026-08-02] Local smoke: unify frontend API key with BACKEND_API_KEY

**Found:** Streamlit `api_client` preferred `TKP_API_KEY` from the process env and did
not load repo `.env`, so a working `BACKEND_API_KEY` in `.env` still produced 401s
unless a second env var was exported in the terminal.

**Cause:** Split naming (`TKP_API_KEY` vs `BACKEND_API_KEY`) plus no `load_dotenv` in
the frontend client.

**Fix:** Frontend loads repo-root `.env` and uses `BACKEND_API_KEY` as the canonical
auth secret (same as FastAPI). `.env.example` updated accordingly.
**Status:** Fixed (this commit)

---

## [2026-08-02] Local smoke: Gemini free-tier 429 on Stage 2 (classification) — SUPERSEDED

**Found:** After a successful upload (`200`) and Stage 1 (`document_intelligence`
completed via PyMuPDF), Stage 2 (`educational_classification`) called Gemini
`gemini-2.0-flash-lite` and failed with `429 RESOURCE_EXHAUSTED` (free-tier
generate_content quotas reported as limit `0` for that model). Job marked failed;
not an auth/upload bug.

**Cause (initial, incorrect):** Assumed Google AI Studio free-tier quota exhausted
for Flash-Lite at smoke-test time.

**Superseded by:** Correct diagnosis above — retired/unavailable model id
(`limit: 0`), not genuine usage exhaustion. Do not treat this entry as the live
root cause.
**Status:** Superseded

---

## [2026-08-02] Deployment to-do: replace placeholder BACKEND_API_KEY before HF Spaces

**Found:** Local `.env` uses `BACKEND_API_KEY=local-dev-api-key-change-in-prod`
(placeholder / shared-dev secret).

**Cause:** Convenience default for local bring-up; acceptable only on localhost.

**Fix:** Before Hugging Face Spaces / any public deploy, generate a long random
secret and set it as a platform secret (and match Streamlit Cloud if used). Do not
commit the real value. `.env` itself stays gitignored.
**Status:** Deferred (deployment to-do)

---

## [2026-08-02] pip-audit CVE reachability audit (langchain / langgraph)

**Found:** `uv run pip-audit` reported multiple CVEs including CVE-2026-34070
(`langchain-core` prompt path traversal), CVE-2026-28277 (LangGraph checkpoint
deserialization), and CVE-2025-67644 (`langgraph-checkpoint-sqlite` SQLi). Earlier
README text vaguely deferred "16 CVEs" without exploitability analysis.

**Cause:** Transitive LangChain/LangGraph packages are installed for LangGraph
orchestration and the eval stack; advisory databases flag the packages regardless
of whether application code calls the vulnerable APIs.

**Fix:** Documented per-CVE reachability in `SECURITY.md`. All three focus CVEs are
**not reachable** (custom prompt loader only; no checkpointer; SQLite checkpoint
package not installed). CVE-2025-68664 confirmed already patched at
`langchain-core==0.3.86`. No package upgrades performed (major bumps would be
required for several advisories). README now points at `SECURITY.md`.
**Status:** Deferred (unreachable — see `SECURITY.md`)

---

## [2026-08-02] Silent `except Exception: pass` in consistency validation

**Found:** `backend/app/validation/consistency.py` (activity-bundle scan) swallowed
any exception with no logging. Bandit B110. A broken optional scan could fail forever
without anyone noticing.

**Cause:** Defensive try/except around optional `ActivityBundle` validation used
`pass` instead of structured logging.

**Fix:** Use shared `get_logger` from `logging_config`; log warning with
`exc_info=True` and `planned_concept_count`. Control flow unchanged.
Commit: `ed51786`.
**Status:** Fixed
