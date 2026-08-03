# Issues log

Running engineering log for bugs, failed checks, security findings, and accepted risks.
Newest entries at the top. Append on every real finding — do not wait to be asked.

---

## [2026-08-03] Embed-count proof (mocked embed_content counter — no live quota)

**Method:** Integration test
`backend/tests/integration/test_embed_call_counts.py` runs the full LangGraph with
a Gemini client whose ``embed_content`` is mocked but still invoked through real
``GeminiClient.embed`` batching. Counts HTTP-equivalent calls + text-units
(weight). Includes one forced validation retry (2 Stage-9 rounds).

| Scenario | chunks | embed_content calls | text-units | batches | same-doc pre-fix | vs live 984 |
|---|---:|---:|---:|---|---:|---:|
| golden `stem_sample.pdf` + 1 retry | 2 | 2 | **5** | [2, 3] | 20 | **196.8×** |
| golden `humanities_sample.pdf` + 1 retry | 2 | 2 | **5** | [2, 3] | 20 | **196.8×** |
| live-scale (~40 chunks) + 1 retry | 40 | 3 | **43** | [32, 8, 3] | 286 | **22.9×** |
| live-scale worst-case retry exhaust | 40 | 3 | **43** | [32, 8, 3] | 286 | **22.9×** |

Breakdown (live-scale): Stage 3 = 40 texts (n3 batches 32+8); Stage 9 queries =
3 texts once (2nd validation round = **cache hits**, 0 API). Chunks never
re-embedded.

**Vs today's incomplete pre-fix run (~984 text-units):** live-scale full run
with retry is **43 / 984 ≈ 4.4%** of that burn (**22.9× fewer**). At 43/run,
free-tier 1000/day allows **~23 full runs/day** — well under the 150–200
comfort band per run.
**Status:** Measured / committed — do not live-confirm until daily quota resets

---

## [2026-08-03] Daily embed quota — Stage 9 re-embedded Stage 3 chunks

**Found:** Job `efcb33eb-fe15-4c15-b617-229d609319c9` hit
`EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier` (limit **1000**/day).
UI/`current_stage` showed **gap_analysis** because `parallel_generation` leaves that
label until Stage 9 finishes; the stack trace is Stage **9** groundedness
(`score_text_against_chunks` → `router.embed([query, *chunks])`).

**Stage 8 (gap_analysis) embed count: 0.** `n8_gap_analysis` only calls
`router.generate` — no `embed` path.

**Structlog evidence (job `efcb33eb`, terminal after n5):**
| Event | Weight (texts) | Meaning |
|---|---|---|
| `gemini_rpm_throttle` @ 20:45:21Z | 40 | Stage 9 groundedness batch |
| `gemini_rpm_throttle` @ 20:45:55Z | 40 | Stage 9 groundedness batch |
| `gemini_rpm_throttle` @ 20:46:03Z | 40 | Stage 9 groundedness batch |
| `pipeline_failed` @ 20:46:59Z | — | daily `PerDay` RESOURCE_EXHAUSTED |

≈ **120 text-units** attempted in Stage 9 alone before the daily cap (weights sum
to 120). Stage 3 `n3_knowledge_extraction_done` for this job scrolled out of the
reload buffer; earlier same-day runs on similar PDFs logged `chunks: 2` on tiny
fixtures, while live STEM uploads produce ~40-chunk batches (weight 40 =
1 query + ~39 chunks per period score).

**Redundancy (confirmed in code, not a guess):**
`score_text_against_chunks` embedded `[cleaned, *usable_chunks]` **once per**
period/assessment. For `T` scored texts and `C` chunks that is **T×(1+C)** API
texts, of which **T×C** are identical chunk strings already embedded in Stage 3
and stored on `knowledge_chunks.embedding`. Stage 3 correctly wrote them once;
Stage 9 ignored them.

**Example:** C=39, T=4 (3 periods + assessments) → Stage 3: **39**; Stage 9 old:
**4×40=160** (39×4=156 duplicate chunk embeds). Matches the weight-40 throttle
pattern on this job.

**Fix:** Persist `knowledge_chunk_embeddings` in graph state; groundedness loads
Stage 3 / DB vectors and embeds **queries only** (one batch). Content-hash
embed cache (same `llm_cache` table, stage=`embedding`) skips identical strings
across retries/smoke runs. Daily `PerDay` EmbedContent errors map to
"Daily free-tier embedding quota reached, resets at midnight Pacific" instead of
raw Google JSON in the UI.
**Status:** Fixed this commit — no live re-run (daily quota still exhausted)

---

## [2026-08-03] Validation-retry exhaust misattributed to Document Intelligence

**Found:** Job `99dcc2bc-694c-4b8e-9ed9-d058fe5bb291` correctly failed groundedness
(Period 3 ungrounded weathering / agents of gradation), retried to
`classroom_content` per `retry_target`, then after retries exhausted the UI
pinned the failure onto **Document Intelligence (stage 1)**.

**Stuck period (not a hang):** After retry #1 (~20:11:43Z), classroom content
mostly cache-hit; the apparent 4–5 min stall (~20:12:02 → 20:16:56Z) was
`gemini_rpm_throttle` waits while Stage 9 re-embedded for groundedness
(`wait_s` up to ~55s, weight 36–40 against embed RPM 80). Then retry #2 failed
and `tkp_pipeline_failed_validation` fired — clean terminal failure, not a
silent exception or infinite loop. `MAX_VALIDATION_RETRIES=2` is enforced
(`retry_count` 1 → retry, 2 → fail).

**Cause:** `d3b8e3f` fixed the *exception* path (preserve `job.current_stage`,
stepper no longer `max(idx, 0)`). The *validation-exhaust* path still set
`current_stage: "failed"` in `fail_job`. That sentinel is not a pipeline stage;
the stepper cannot map it and historically coerced unknown → index 0.

**Fix:** `fail_job` / `_terminal_failure_stage` report the real last-active
stage (`validation`, or first `retry_target` if prior stage was a sentinel).
`pipeline_runner` refuses to persist `"failed"`/`"error"` as the stage.
Stepper treats failed/error/unknown as unmapped (no Document Intelligence pin).
Mocked integration test covers validation → groundedness fail → retries
exhaust → stage=`validation`.
**Status:** Fixed this commit

---

## [2026-08-02] EmbedContent 429 — per-chunk loop outside RPM limiter

**Found:** Live run hit `EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier`
(limit **100**/min) on `gemini-embedding-001` / displayed as `gemini-embedding-1.0`.
This is a real nonzero quota — the app fired >100 embed requests in a minute.

**Cause:** `GeminiClient.embed` looped `embed_content` **once per text** with **no**
`rate_limited(...)` wrapper. Stage 3 (`n3_knowledge_extraction`) correctly batches
chunk texts into groups of 32 and calls `router.embed(batch)`, but the client then
expanded each batch into 32 individual API calls. The RPM limiter added for
generate fan-out (`a91e79f`) only wrapped `generate_content`, so embeddings were
unthrottled. Stage 9 groundedness also embeds `[query, *chunks]` and inherited the
same one-call-per-text behaviour.

**Quota nuance (verified live):** free-tier embed RPM counts **per text**, not per
HTTP request — a single batched `embed_content` with 100 strings still consumes
100 of the 100/min budget. Batching helps latency/overhead but must be paired with
**weighted** RPM accounting (`weight=len(batch)`).

**Stage attribution:** Embedding belongs to **Stage 3 (knowledge extraction)**, not
Document Intelligence. The UI blamed Stage 1 because (a) the job row stayed on the
pre-run `document_intelligence` placeholder until the pipeline finished, and
(b) the progress stepper mapped unknown/error stages to index 0 via
`max(active_idx, 0)`.

**Fix:** Batch `contents=[...]` in a single `embed_content` request (SDK-supported);
wrap each batch in `rate_limited(DEFAULT_EMBED, weight=len(batch))` with an
embed-aware RPM budget (80 texts/min headroom under the 100 free-tier cap) and
max batch 40. Stream mid-pipeline stage updates via
`astream(..., stream_mode="values")` + `on_stage` so failures keep the real stage;
stepper no longer pins unknown failures onto Document Intelligence.
**Status:** Fixed / verified — live embed of 120 texts completed without 429
under weighted throttle (~62s). E2E reached `knowledge_extraction` at 35%
(embeds done); full pipeline then failed on unrelated Flash **daily** generate
quota (limit 20), not EmbedContent RPM.

---

## [2026-08-02] Groq fallback exercised live (routing + Stage 9 + latency)

**Found:** With a real `GROQ_API_KEY`, Gemini→Groq overflow was not truly
fail-fast: eligible stages still entered `_call_gemini`'s tenacity loop
(up to 6 RateLimitError retries / ~minutes) before the outer handler could
call Groq. Also, Stage 9 logging used Unicode `→`, which crashed on Windows
cp1252 when validation failed.

**Live exercise (forced Gemini 429 → real Groq `llama-3.3-70b-versatile`):**
- Classification fallback succeeded (Physics / Newton's Laws, Groq
  `latency_ms=876`).
- Same prompt latency: **Gemini `gemini-3.5-flash` 2785 ms** vs **Groq 419 ms**
  (Δ ≈ 2366 ms; Groq ~6.6× faster on this call).
- Stage 9 on Groq-produced classroom/activity/assessment/gap bundles:
  schema **pass**, consistency **pass**. Groundedness **failed** when
  grounding chunks were the short factory excerpt (Groq elaborated inertia /
  full first-law wording beyond the chunk); **passed** with fuller
  Laws-of-Motion grounding (`avg≈0.76`, judge_passed=True, overall_passed).

**Cause:** Retry-before-fallback ordering defeated the "fast overflow" design;
Groq is more expansive than Gemini on thin grounding, so Stage 9 still matters.

**Fix:** Eligible+Groq-available stages call Gemini once then fall back
immediately; non-eligible stages keep retries. Stage 9 feedback uses ASCII
`->`. Live tests under `backend/tests/integration/test_groq_fallback_live.py`
(`-m live_llm`).
**Status:** Fixed / verified (this commit)

---

## [2026-08-02] Parallel generation 429 on gemini-3.5-flash (RPM limit 5)

**Found:** After model-ID fix, Stages 1–4 succeeded but `parallel_generation`
failed with genuine free-tier RPM exhaustion on `gemini-3.5-flash`
(`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, **limit: 5**,
`quotaValue: 5`). Stage 5 fan-out used unthrottled `asyncio.gather` over all
periods while Stages 5–8 also ran concurrently — no semaphore/rate gate.

**Cause:** Build plan called for concurrency control on Stage 5–7 fan-out; it was
never wired. `GROQ_API_KEY` is empty locally, so Groq overflow fallback cannot
absorb Flash RPM pressure.

**Fix:** Per-model `ModelRateLimiter` (semaphore + sliding-window RPM) wraps
Gemini `generate_content`; classroom/assessment fan-out routed to
`gemini-3.5-flash-lite` (separate quota); RateLimitError retries lengthened.
**Status:** Fixed (this commit)

---

## [2026-08-02] Stage 3 extracted off-topic grounded concepts (topic-scope gap)

**Found:** Knowledge extraction returned "Photosynthesis" alongside Newton's Laws
concepts for a Physics / Laws of Motion chapter. Not a hallucination — see the
golden-sample entry below — but Stage 3 treated any grounded passage as in-scope
teaching knowledge.

**Cause:** `n3_knowledge_extraction.md` required `source_ref` grounding but never
constrained extraction to Stage 2's classified subject/topic/chapter. The node
passed classification only as soft context.

**Fix:** Prompt now mandates topic-scope exclusion for unrelated source text;
`filter_knowledge_to_scope` post-filters ExtractedKnowledge against classification
(+ kept-concept vocabulary). Unit test covers the stem_sample fixture pattern.
Smoke: Stage 3 returns only the three Newton's Laws concepts.
**Status:** Fixed (this commit)

---

## [2026-08-02] Golden `stem_sample.pdf` intentionally contains Photosynthesis text

**Found:** Raw PyMuPDF text of `evals/golden_dataset/stem_sample.pdf` includes a
verbatim Photosynthesis / chlorophyll paragraph after Newton's third law
(case-insensitive grep hit_count=1). Stage 3's earlier Photosynthesis concept
had a faithful `source_ref.quote` — not a fabricated citation.

**Cause:** Golden STEM fixture mixes on-topic Laws of Motion content with an
off-topic but real sentence (useful for scope / groundedness tests).

**Fix:** None to the PDF. Documented so future 429/hallucination triage does not
misread this as LLM invention. Scope filtering is handled in the Stage 3 entry
above.
**Status:** Accepted (fixture data quality — intentional)

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
