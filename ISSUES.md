# Issues log

Running engineering log for bugs, failed checks, security findings, and accepted risks.
Newest entries at the top. Append on every real finding — do not wait to be asked.

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
