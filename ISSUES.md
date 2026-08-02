# Issues log

Running engineering log for bugs, failed checks, security findings, and accepted risks.
Newest entries at the top. Append on every real finding — do not wait to be asked.

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

## [2026-08-02] Local smoke: Gemini free-tier 429 on Stage 2 (classification)

**Found:** After a successful upload (`200`) and Stage 1 (`document_intelligence`
completed via PyMuPDF), Stage 2 (`educational_classification`) called Gemini
`gemini-2.0-flash-lite` and failed with `429 RESOURCE_EXHAUSTED` (free-tier
generate_content quotas reported as limit `0` for that model). Job marked failed;
not an auth/upload bug.

**Cause:** Google AI Studio free-tier quota exhausted / unavailable for the configured
Flash-Lite model at smoke-test time.

**Fix:** None in code for this session. Retry later or set `GROQ_API_KEY` for
eligible stages; consider switching classification model if Flash-Lite stays at
limit 0. Monitor via AI Studio rate-limit dashboard.
**Status:** Monitoring

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
