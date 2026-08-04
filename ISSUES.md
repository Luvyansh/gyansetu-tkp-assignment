# Issues log

Running engineering log for bugs, failed checks, security findings, and accepted risks.
Newest entries at the top. Append on every real finding — do not wait to be asked.

---

## [2026-08-04] Render pipeline stall — MiniLM hub download at first embed

**Symptom:** Job `1aa13616-2b9d-469f-9319-b42f24f177dd` — SSE connected, no OOM
(137), no traceback; `/tkp` still 404 minutes later. Pipeline appeared stuck.

**Root cause:** MiniLM weights were **not** in the image. Dockerfile set
`HF_HOME=/tmp/hf_cache` (empty on every boot). First `router.embed` in
`knowledge_extraction` called `SentenceTransformer(...)` which downloads
~80–100MB from Hugging Face hub at runtime. Local runs looked fine because
`~/.cache` was already warm. On Render free tier that cold fetch stalls /
starves the single worker with no clear log trail.

**Local evidence:**
- Pre-bake image + empty `HF_HOME=/tmp/empty_hf`: cold load took **~34s** alone
  under `--memory=512m` (and competes with uvicorn RSS in a real job).
- Post-bake image + `HF_HUB_OFFLINE=1`: load from `/app/hf_cache` in **~7.5s**,
  encode OK; empty cache + offline **fails fast** (`LocalEntryNotFoundError`).

**Fix:**
1. Dockerfile `RUN` downloads MiniLM into `/app/hf_cache` at **build** time;
   `HF_HOME` etc. point there (not `/tmp`); runtime `HF_HUB_OFFLINE=1` /
   `TRANSFORMERS_OFFLINE=1`.
2. `local_embeddings.py`: `local_files_only` when offline; log `hf_home` /
   `offline` on load.
3. `build_graph.py`: `pipeline_stage_enter` / `pipeline_stage_exit` /
   `pipeline_stage_error` wrappers on every node (incl. parallel children);
   `pipeline_runner` logs `pipeline_stage_persisted`.

**Status:** Fixed and verified under local 512MB docker; ready to redeploy.

---

## [2026-08-04] Render free tier OOM (exit 137) — CUDA torch + eager MiniLM

**Symptom:** Render Docker free (512MB) build OK, then container killed immediately
after `app_startup` — `Exited with status 137` (SIGKILL / OOM).

**Local repro:** `docker run --memory=512m --memory-swap=512m … tkp-backend`
→ `OOMKilled=true`, exit 137 during MiniLM load (same timeline as Render).

**Root cause:**
1. `sentence-transformers` pulled default PyPI **CUDA** `torch` on Linux
   (`nvidia-cublas`, `cudnn`, `nccl`, …) — huge RSS vs CPU wheel.
2. Lifespan called `ensure_embedding_model_loaded()` at startup, so peak memory
   hit before the process could stay healthy.

**Fix:**
- Pin CPU-only torch: `[[tool.uv.index]] name=pytorch-cpu` +
  `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]` + direct `torch` dep;
  regenerated `uv.lock` → `torch==2.13.0+cpu`, **zero** `nvidia-*` packages.
- Lazy-load MiniLM on first embed (`main.py` lifespan no longer warms model;
  `SentenceTransformer(..., device="cpu")`).
- Dockerfile: `WEB_CONCURRENCY=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
  `TOKENIZERS_PARALLELISM=false`.

**Measured (512MB cgroup, post-fix):**
- Idle uvicorn `/health` 200: **~77–127 MiB**, `health=healthy`, `oom=false`
- Same-process app + MiniLM load + encode: **peak ~453 MiB** (under limit)

**Status:** Fixed locally under 512MB constraint; ready to redeploy to Render.

---

## [2026-08-03] FAITHFULNESS 0.50 unsafe — live Period 3 hallucination scores 0.795 MiniLM

**Case:** Job `99dcc2bc-694c-4b8e-9ed9-d058fe5bb291` Period 3 classroom content
(cache `473f49e1…`) — invented weathering/erosion definitions + "agents of
gradation". Live Gemini groundedness: period_3=**0.770**, avg=0.772 → below
0.85 → LLM judge correctly FAIL.

**MiniLM (all chunks from that job, n=75):** period_3 max-cosine = **0.795**.
- At threshold **0.50**: embedding gate **auto-PASSes** (judge never runs) — hallucination slips through.
- At threshold **0.85**: 0.795 < 0.85 → judge path → FAIL (matches live).

Synthetic paraphrase bands (identical 1.0 / close 0.63 / unrelated 0.05) were
misleading for topical NCERT chapters where many chunks mention weathering/
erosion without defining "agents of gradation".

**Fix:** Keep `FAITHFULNESS_THRESHOLD=0.85`. Fixture regression
`test_period3_hallucination_threshold.py` +
`fixtures/period3_hallucination_live.json`.

**Alembic:** `uv run alembic upgrade head` applied `0001_initial → 0002_embed_dim_384`
cleanly on local Postgres; `alembic current` = `0002_embed_dim_384 (head)`.

**Status:** Confirmed / threshold restored to 0.85

---

## [2026-08-03] Local MiniLM embeddings + Flash-Lite-primary routing (quota bypass)

**Context:** Gemini 3.5 Flash over daily quota (22/20) and RPM-maxed; Embedding-1
at 660/1000. Needed a path that spends **zero** embed quota and **near-zero**
full Flash.

### 1. Embeddings -> local `all-MiniLM-L6-v2` (384-d)
- `sentence-transformers` dependency; model **lazy-loads** on first embed
  (not at FastAPI startup — eager load + CUDA torch OOMs Render 512MB).
  Singleton reused thereafter; never re-downloaded per-request.

- `LLMRouter.embed` calls local encode only (Postgres content-hash cache kept).
  Gemini/Groq are **out of the embed path** entirely.
- `EMBEDDING_DIM=384`, Alembic `0002_embed_dim_384` (clears old 768-d vectors +
  embed cache rows).

### 2. Generation routing: Flash-Lite -> Groq -> Flash last-resort
- All stages (incl. knowledge_extraction, teaching_planner, validation_judge,
  multimodal) primary on `gemini-3.5-flash-lite`.
- GROQ_ELIGIBLE expanded to those text stages; multimodal has no Groq vision ->
  Lite then Flash only.
- Full `gemini-3.5-flash` only if Lite and Groq both fail (or Lite alone when
  Groq unset).

### 3. Mocked NCERT cost (`sample_ncert.pdf`, 1 forced validation retry)
| API | Count | Notes |
|---|---:|---|
| Gemini `embed_content` | **0** | local MiniLM only |
| local embed text-units | **77** | batches [32,32,8,5] — same shape as before |
| `generate` Flash | **0** | was 4 |
| `generate` Flash-Lite | **19** | was 15 Lite + 4 Flash |
| heavy-stage input tokens est. | **~6.4K** | knowledge + teaching |
| all-stage input tokens est. | **~39.5K** | vs Flash-Lite TPM **250K** — ~16% |

### 4. FAITHFULNESS_THRESHOLD recalibration (MiniLM space)
| Pair | Cosine |
|---|---:|
| identical | 1.00 |
| close paraphrase | 0.63 |
| same-topic loose pedagogy | 0.42 |
| unrelated | 0.05 |

**Synthetic bands suggested 0.50**, but the live Period 3 hallucination scores **0.795** under MiniLM and would auto-pass at 0.50 — see entry above.
**Threshold kept at 0.85.**

**Status:** Implemented; threshold decision superseded by real-case check above. Alembic `0002` applied.

---

## [2026-08-03] Real NCERT chapter API-cost measurement (mocked clients)

**Document:** `test_assets/sample_ncert.pdf` — "Shaping of the Earth's Surface"
(NCERT Geography, **26 pages**, ~21 MB, diagram-heavy). This is the file behind
today's 984/1000 daily embed burn — not the tiny golden samples / guessed
40-chunk proxy.

### Stage 1 (real parse — no estimate)
| Metric | Value |
|---|---|
| pages | **26** |
| chars / words | 32,147 / **4,961** |
| **chunks (500/50)** | **72** (was guessed ~40) |
| image_count (heuristics) | **118** |
| figures extracted | 137 |
| chars_per_page | **1243.7** (text-rich despite diagrams) |
| route `unsure` / `text_with_diagrams` | **multimodal** |
| route `mostly_text` | text |
| multimodal pages if triggered | **5** (code takes `range(min(pages,5))` — first 5 pages, **not** image-selective) |

### Full pipeline + 1 forced validation retry (4 periods, as in live logs)
| API | Count | Notes |
|---|---:|---|
| `embed_content` calls | **4** | batches `[32, 32, 8, 5]` |
| embed **text-units** | **77** | Stage3=72 + groundedness queries=5; retry queries **cache-hit 0** |
| same-doc pre-fix embeds | **802** | `72 + 2×5×73` |
| vs today's live **984** | **12.8× fewer** | 77/984 ≈ **7.8%** of that burn |
| `generate` Flash (`gemini-3.5-flash`) | **4** | multimodal(1)+knowledge(1)+teaching×2 |
| `generate` Flash-Lite | **15** | class(1)+classroom×8+activity×2+assess×2+gap×2 |
| multimodal pages billed | **5** / 1 call | |

Projected free-tier runs/day at these costs: embed ~**12**, Flash-Lite ~**33**,
**Flash ~5** ← binding constraint (20 RPD).

Embeds are now comfortably under the 150–200/run band (**77**). The remaining
risk on this document is **Flash 20/day**, not embeds.

### Concrete levers (priority order)
1. **Flash budget:** move `knowledge_extraction` / `teaching_planner` /
   `multimodal_fallback` toward Flash-Lite where quality allows, or skip
   multimodal when `chars_per_page` is already high (this chapter is 1243 cpp —
   text extract is sufficient; `image_count>=2` alone should not force multimodal).
2. **Selective multimodal pages:** replace blind `range(min(n,5))` with pages
   that are image-heavy / text-sparse; cap pages harder (e.g. 2) for free tier.
3. **Chunk cap / coarser chunking** for large docs (e.g. max 40–48 chunks or
   size 800–1000) — optional further embed headroom; not required at 77/run.
4. **Near-duplicate chunk collapse** before embed (low priority given cache +
   reuse already landed).

**Status:** Measured via `test_ncert_api_costs.py` — no live quota spent.
**Superseded for Flash/embed levers by:** Local MiniLM + Flash-Lite-primary entry above.

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
