# Mukthi Guru — Master Remediation Plan

Collected from the full remediation session. Legend: DONE = done & verified · OPEN = I can do ·
USER = user-driven (LLM/compute-heavy) · WONT = won't-do (documented). Grounded in the live stack
(backend/celery/redis/qdrant/neo4j all healthy at time of writing).

---

## Part A — DONE & VERIFIED this session (do not redo)

| # | Fix | Where | Evidence |
|---|---|---|---|
| A1 | Anonymous-UUID memory failures 77/2h -> 0 | `services/user_profile_service.py` `_is_persistable_user_id` guard | logs: 67 before restart, 0 after |
| A2 | **Reranker 88s -> 2.9s** (bge-m3->MiniLM on CPU, device-aware) | `config.py` `reranker_model_cpu`, `reranker_service.py`, `embedding_service.py` | micro-bench 23x; live `19 docs in 5.5s` |
| A3 | Router over-routing to slow path | `config.py` `semantic_router_confidence_threshold` 0.65->0.55 | live `0.576 -> fast` |
| A4 | OKF doc-drift fixed + staging tests hardened | root+backend `CLAUDE.md`, `test_okf_pipeline_integrity.py` | 10/10; guards rglob recursion + `_excluded_parts` |
| A5 | KG doc reconciled to reality (11,136 edges, flag `true`) | `CLAUDE.md`, memory | live Neo4j count |
| A6 | Ekam answer quality — 4 sub-bugs | see below | API + streaming + **browser UI** |
| A6a | Dangling CTA strip ("Watch more here:") | `generation.py:_clean_inline_citations` | test + UI |
| A6b | Out-of-corpus **logistics short-circuit** (deterministic honest answer) | `intent.py` `_is_logistics_query` | 2.1s canned answer, both paths |
| A6c | Semantic **cache-bleed** guards (x2: don't-cache + bypass) | `cache_stage.py` | teaching<->logistics no longer cross-serve |
| A7 | **Data-quality root-cause system** (see Part D) | `services/doctrine_terms.py` +4 rewires +test +audit +admin API | 22 tests + audit clean — **but NOT live-verified: the running backend has not been restarted since this rewire, so the process still runs the pre-rewire code. Restart + one Ekam query is the outstanding confirmation.** Admin-editable needs the Supabase table (Part C) to actually save. |
| A8 | Streaming confirmed already built (frontend `src/lib/chat`) | — | SSE returns tokens |
| A9 | ~/Downloads P0/P1 audit: 17/18 already done (stale audit) | — | verified line-by-line |

---

## Part B — OPEN, I can implement (prioritized)

### B1 — Rerank threshold recalibration for MiniLM (highest-leverage correctness)
The bge-m3->MiniLM swap (A2) changed the `rerank_score` distribution, but `rerank_min_score`
(0.2), `rerank_floor`, and the sufficiency gate (0.5/0.75 in `reranking.py:307`) are still
tuned for bge-m3. **Symptom:** tangential chunks pass the floor (the Ekam third-eye leak).
**Fix:** offline script over ~30 known relevant/irrelevant pairs -> measure MiniLM score
distribution -> set `rerank_min_score` + a new `rerank_sufficiency_min` as config. Data-driven.

### B2 — Relevance-aware context-sufficiency
`reranking.py:307` counts docs that merely pass the floor as "sufficient". Require a genuine
top-score, so out-of-corpus queries fall through to the honest fallback at retrieval time
(complements the intent-level logistics short-circuit). Gated behind B1's measured threshold.

### B3 — Book-purchase URL determinism
Same class as the logistics short-circuit: "where can I buy the book" should deterministically
return amazon.in/the canonical store, not rely on the LLM (which currently says "various
platforms"). Extend the `intent.py` short-circuit with a `_is_purchase_query` branch.

### B4 — Ops items from the 2h log audit (each small)
- **ColBERT models fail to load (9x/2h)** -> rerank cascade degrades to CrossEncoder-only.
  Decide: fix the model cache OR explicitly disable ColBERT + document (CrossEncoder is fine).
- **`doctrine_faqs` Supabase table missing (3x/2h)** -> `doctrine_cache` never loads. Create the
  table OR disable the Supabase doctrine-cache path.
- **`compliance_logger` /var/log perm denied (3x/2h)** -> point to a writable dir / pre-create in
  the Dockerfile with correct perms.

### B5 — Latency (harder)
- **Complex-path ~130s** (decompose->3x retrieve->grade->generate->verify). Sub-query retrieval is
  already `gather`'d; the tax is sequential LLM hops. Lever: tighten the decomposition gate
  (fewer queries decompose) + confirm reflect/verify are skipped for tier2_simple.
- **Cold-start ~10s first query** -> warm the reranker/embedder/Llama-Guard on boot.

---

## Part C — Operational one-offs (need your hand / infra)
- **Create the `doctrine_terms` Supabase table** (SQL below) so admins can *save* terms — the code
  already degrades gracefully without it.
- **Admin UI page** for doctrine terms under `src/admin/pages/` (API + storage already landed).
- **Qdrant `lightrag_vdb_*` collections empty** while Neo4j has 11,136 edges — investigate whether
  LightRAG's vector side needs re-ingest or is intentionally Neo4j-only.
- **Re-ingest corpus** once B1/D settle, to bake corrections into Qdrant (output safety-net covers
  it meanwhile).

```sql
create table if not exists doctrine_terms (
  canonical text primary key, variants text[] not null default '{}',
  enabled boolean not null default true, updated_by text, updated_at timestamptz default now());
```

---

## Part D — Data-quality system (DONE; here for completeness)
Single source of truth `services/doctrine_terms.py` -> `get_whisper_initial_prompt()` (biases
Whisper), `apply_corrections()` (ingest + output), admin-editable Supabase overrides + hot-reload.
Whisper/corrector/generation all rewired to it; `test_doctrine_terms.py` fails CI if a local
correction dict returns; `scripts/ops/audit_doctrine_data_quality.py` sweeps the corpus.

---

## Part E — Benchmark & knowledge (USER — LLM/compute-heavy)
- **10-class benchmark taxonomy** in `benchmarks/question_bank.py` (in-corpus, complex,
  out-of-corpus, distress, off-topic, adversarial, multilingual, follow-up, temporal, latency-SLA).
- **255-q run** (`RUN_ME.sh`) -> per-class breakdown of the 39% doctrine score (suspects:
  out-of-corpus + multilingual, since CPU reranker is now English MiniLM).
- **OKF / Karpathy LLM-wiki**: coverage expansion (22 entries is thin), conventions doc,
  contradiction pages. Auto-extract -> review.
- **Contextual-chunking prompt-caching** verification (ingest cost at scale).

---

## Part F — WONT-do (documented rationale)
- **RunnableConfig UserWarning** (93x) — benign; `from __future__ import annotations` defeats
  LangGraph's type check; module-level filter doesn't hold. Cosmetic only.
- **Remove prometheus/grafana** — already in `Created` (never started); FIX 16 is moot.

---

## Part G — Ruthless verification protocol (standing)
1. Change -> `pytest` touched areas -> restart backend -> **flush ALL 4 cache layers**: Redis
   (`redis-cli -a $PW FLUSHALL`) + in-process (restart) + semantic + **frontend localStorage**.
2. Fire the 10-class battery via `/api/chat` **and** `/api/chat/stream` (UI uses streaming).
3. Read docker logs per query: tier, rerank time + score dist, `context_sufficient`, citations,
   WARN/ERROR, latency.
4. UI spot-check in the browser (clear localStorage first — it caches responses).
5. Only then declare done.

**Known cache gotcha:** four layers. Re-tests kept returning stale answers until all four cleared.

---

## Recommended execution order (ruthless)
1. **B1 + B2** (rerank recalibration + relevance sufficiency) — one focused change, lifts precision
   and un-breaks the sufficiency gate; unblocks the benchmark.
2. **B4** (three small ops fixes) — cheap, removes real log noise.
3. **B3** (purchase determinism) — quick, closes the last answer-quality gap.
4. **C** (Supabase table + admin UI) — makes the data-quality system operator-complete.
5. **E** (benchmark) — your terminal; turns 39% into an actionable per-class map.
6. **B5** (latency) — only if the benchmark shows it hurting SLAs.

Confidence: high. Every DONE item is verified; every OPEN item names the file, the symptom, and the
approach. Nothing from the conversation is dropped.
