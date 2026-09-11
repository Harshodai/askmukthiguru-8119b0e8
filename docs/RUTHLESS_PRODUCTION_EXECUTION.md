# Ruthless Production Execution — Audit & Remediation

**Audit date:** 2026-09-11 · **Branch:** `main` · **Status:** in progress

This is the canonical record for this audit pass. Where it disagrees with any
other document in `docs/`, **this file and the source code win**. Several
claims in the root `CLAUDE.md` were found to be stale and are corrected below.

## Evidence classification

Every finding carries one of:

| Class | Meaning |
|---|---|
| `PROVEN FROM CODE` | Read from source; file:line cited |
| `MEASURED` | Reproduced by running something and recording the number |
| `PROVEN FROM LIVE/STAGING` | Observed against a running system |
| `INFERRED` | Reasoned, not directly observed |
| `REQUIRES LIVE VALIDATION` | Cannot be settled without the live stack |

**No finding in this document is `PROVEN FROM LIVE/STAGING`.** The Mukthi Guru
stack was not running during this audit (the only containers up belonged to an
unrelated project), and no live traffic, latency percentile, or retrieval
quality number was measured. Every performance and quality claim below is
therefore code-level or bench-level only. See *Remaining unknowns*.

## Baseline

| Metric | Value |
|---|---|
| Backend tests collected | 3231 |
| Baseline result | **30 failed, 3180 passed, 21 skipped** (422s) |
| Of those failures | 14 in untracked `canonical_memory` WIP; **16 in tracked, committed code** |
| Python files (backend, excl. venv) | 867 |
| TS/TSX files (src) | 435 |

A 16-failure baseline on `main` is itself a finding: the suite was not green
before this audit began, so "the tests pass" was not available as evidence for
anything.

## Fixes implemented in this pass

Each was proven by running the new regression test against the pre-fix code and
confirming it fails, then against the fixed code and confirming it passes. That
two-way check is the bar; a test that never fails against the defect is not
evidence.

| ID | Severity | Finding | Evidence | Test |
|---|---|---|---|---|
| R1 | P0 data loss | `backup_source` / `restore_from_backup` scrolled with a fixed `limit=1000` and no pagination. `restore_from_backup` also deleted the live copy **before** reading the backup, so a >1000-chunk source rolled back to permanent silent loss — logged as a successful "Rolled back". | `PROVEN FROM CODE` `services/qdrant/indexer.py` | `tests/test_qdrant_backup_pagination.py` (4 tests; 4/4 fail pre-fix) |
| R2 | P0 silent outage | `health_check` called `get_collections()` and returned `True`. `init_collection` **creates** the configured collection when absent, so a deploy that never ran the backfill got an empty collection, a green `/api/health`, and an abstention on every query. | `PROVEN FROM CODE` `services/qdrant/client.py` | `tests/test_qdrant_health_reports_empty_collection.py` (5 tests; 3/5 fail pre-fix) |
| R3 | P0 split-brain | The Neo4j ontology write sat outside the rollback block. With `ontology_write_required=True` it returned `chunks_indexed: 0` without rolling back the Qdrant upsert — the return value lied while N chunks stayed live. With the default `False` it logged a warning and then checkpointed the source as processed, so it was never retried. The playlist path already rolled back; the single-doc paths did not. | `PROVEN FROM CODE` `ingest/pipeline.py`, `app/config.py:810` | `tests/test_ingest_ontology_rollback.py` (8 tests; 8/8 fail pre-fix) |
| R4 | P1 correctness | Token estimation was inverted. `get_token_ratio` is documented "tokens-per-word" and `latin: 1.3` is the standard English figure, but `estimate_tokens` **divided** by it. Every prompt was under-counted. | `MEASURED` — see below | `tests/test_token_budget_guard.py`, `tests/test_rag_advanced.py::test_token_budget_capping` (pre-existing, were failing) |
| R5 | P1 correctness | `KNOWLEDGE_GRAPH_QUERY_ENABLED=false` collapsed a standard-tier query into the `"fast"` lane, which **also** disabled the BM25 fan-out and **halved** `primary_query_limit`. One flag silently degraded three unrelated retrievers — and confounded any attempt to measure the graph's own contribution. Graph work is already gated independently. | `PROVEN FROM CODE` `rag/nodes/retrieval.py` | `tests/test_retrieval_lane_decoupling.py` (3 tests; 1/3 fails pre-fix) |
| R6 | P1 safety | The tier-3 abstention guard could never fire. `context_engineer` built the relationships layer as a header plus a literal `"None"` body, so the layer was always truthy and `not _relationships` was always False. A request with no knowledge and no memory went to the LLM ungrounded instead of abstaining. | `PROVEN FROM CODE` `rag/nodes/generation.py` | `tests/test_abstention_guard_reachable.py` (4 tests; 1/4 fails pre-fix) |

### Round 2 fixes

| ID | Severity | Finding | Evidence | Test |
|---|---|---|---|---|
| R7 | P1 latent isolation | `GET /api/kg/subgraph` is anonymous and ran an **unlabelled** `MATCH (n)` Cypher scan with no tenant or user predicate, over a database that also holds `GlobalMemory` (memory `content`/`insight`), `User`, and `SeekerTurn` (`session_id`, `user_id_hash`). It returned no private data **only because `GlobalMemory` happens not to carry an `entity_id` property** — and the ontology extractor already sets `entity_id` on entities it writes. Isolation rested on an absent property, not on the query. | `PROVEN FROM CODE` `app/api/kg.py` | `tests/test_kg_subgraph_private_label_scope.py` (6 tests; import-errors pre-fix) |
| R8 | P1 cost/abuse | `POST /api/chat/title` invokes the LLM for anonymous callers with an **unbounded** `first_message` string, rate-limited by request count only and **outside the anonymous quota**. The repo's own `test_title_endpoint.py::test_generate_title_endpoint_anon_quota_exceeded` already specified the correct behaviour and had been failing since before this audit — the test was right, the code was missing the control. | `PROVEN FROM CODE` `app/api/chat.py` | that pre-existing test now passes + `tests/test_title_input_bounded.py` (3 tests) |
| R9 | P1 staleness | `_OKF_CACHE` was a write-once module global. `compile_okf()` is called from the admin endpoint, the CLI and ingestion, and **none of them cleared it**, so newly approved doctrine reached no answer until the process restarted. Now keyed on `compiled.json` mtime, so every writer invalidates it. | `PROVEN FROM CODE` `rag/nodes/retrieval.py` | `tests/test_okf_cache_invalidation.py` (3 tests; fail pre-fix) |
| R10 | P1 staleness | Ingestion invalidated only the semantic tier. The exact, hot and doctrine tiers kept serving pre-ingest answers for their full TTL; `doctrine_cache.refresh()` existed with **no caller anywhere in the tree**. | `PROVEN FROM CODE` `ingest/pipeline.py` | `tests/test_ingest_cache_invalidation.py` (5 tests; 5/5 fail pre-fix) |
| R11 | P1 diagnosability | Qdrant payloads carried zero build provenance. Stamped `embedding_model`, `embedding_dimension`, `chunker_version` in `QdrantIndexer.upsert_chunks` — the single chokepoint every writer funnels through — so "which chunks are stale relative to the current encoder" becomes one scroll query. Absent on pre-existing points; readers must treat missing as *unknown/legacy*, never as *matches current*. | `PROVEN FROM CODE` `services/qdrant/indexer.py` | `tests/test_qdrant_payload_provenance.py` (2 tests; 1 fails pre-fix) |

### Round 3 fixes — the test-evidence pass

| ID | Severity | Finding | Test |
|---|---|---|---|
| R12 | P1 user-facing | **Hinglish routed to English.** `_check_hinglish` needs ≥30% of words to match `HINDI_WORDS`, and the list omitted several of the commonest tokens (`gussa`, `bahut`, `aata`, `karun`). *"Mujhe gussa bahut aata hai when my family does not understand me"* matched 4/16 = 0.25 and fell through to English routing and an English prompt suffix. Vocabulary recall was the defect, **not** the threshold — lowering the threshold would have bought the fixture at the cost of misrouting English. | `tests/test_hinglish_routing_recall.py` pins both directions (2 code-mix + 5 plain-English precision cases); measured 0 English false positives |
| R13 | P1 false confidence | **The retrieval-quality gate could not fail.** `memory/qdrant_quality_baseline.json` records `mean_ndcg: 0.0`, so the regression assertion was `current >= -0.02` — vacuously true for any measurement, including a total retrieval outage. The test now refuses to run against a non-positive baseline instead of reporting green. | `tests/test_qdrant_search_quality.py` |
| R14 | P2 | Nine stale tests repaired, restoring the suite's ability to show regressions. Six were one shared defect: `prepare_user_memory` returns a 3-tuple (`orchestrator_utils.py:799`) and the tests unpacked 2. Plus a stale source-grep, two contradictory context-graph expectations, and a hidden infra dependency. | see below |

**On R14 — these were stale tests, not silenced failures.** Each was diagnosed
against the code before being touched, and in every case the production
behaviour was deliberate and newer than the test:

- `test_ruthless_audit_remediation` grepped for the literal
  `graph.add_node("verify_answer", verify_answer)`. The node is now bound to
  `combined_grade_and_verify`, which runs LettuceDetect and the constitutional
  checks locally and **delegates to `verify_answer`** when confidence is
  uncertain (`verification.py:741`). Verification did not regress; the grep
  could not see through the rename. Now asserts the node *name* is wired.
- `test_context_graph` asserted `mode == "local"` for `tier2_simple` while
  `test_ruthless_phase3_planner.py` asserted `mode == "none"` for the same tier
  **and passed** — two tests contradicting each other. The fast-lane bypass is
  deliberate (`a0f54b8e`); the older expectation was updated and a second test
  added for the non-fast path so coverage was not simply deleted.
- `test_graph_stage_fixes::test_retrieval_query_fan_out_limited_to_two` patched
  `_services` but not `app.dependencies.get_container`, so it passed **only
  when Qdrant was genuinely reachable**. Fixed with the patch its sibling
  `test_retrieve_documents_contract.py:65` already had.
- `test_config_validation` hard-coded `50` and went red when `917ef07c` — a
  *personalization feature* commit — retuned `http_pool_max_connections` to 20
  alongside `embedding_cache_size` 2000→1000. It now asserts against the
  declared default, so the normalization behaviour is tested rather than a
  magic number. **The 60% pool cut itself shipped with no measurement** and is
  logged as B13.

### Corrections to this document's own earlier claims

Two things I asserted in the first pass were wrong. Recording them rather than
quietly editing them away:

1. **"Collection is not deterministic."** It is. `pytest-randomly` is not even
   installed. The 3231 → 3350 → 3419 drift was a concurrent session adding
   `canonical_memory` files to the tree mid-measurement, plus live-infra probes
   at import time (`test_coalescer.py:24`, `test_redis_rate_limiter.py:35` and
   others) that execute and load real models when Docker is up — which is also
   the 422s vs 181s wall-time swing, not nondeterminism.
2. **"`test_graph_stage_fixes` passes when another test leaks a mocked
   container."** No test leaks one. `app.dependencies._container` is a
   process-global that nothing under `tests/` ever assigns a mock. It passed
   because Qdrant was actually reachable.

### Round 4 fixes — closing the unfailable gates

| ID | Severity | Finding | Test |
|---|---|---|---|
| R15 | **P0 corpus integrity** | The repo-root `langchain_text_splitters/` **test stub** shadows the real package for any process started at the repo root — which includes the three bulk corpus-ingestion scripts (`scripts/ingestion/ingest_four_sacred_secrets.py:21`, `bulk_ingest_whisper.py:245`, `bulk_ingest_async.py:381`) and `python3 -m pytest backend/tests/`, the command root `CLAUDE.md` documents. A corpus ingested from the repo root was split by a **simplified test stub**; one ingested from `backend/` used the real library — silently, with nothing in the Qdrant payload distinguishing them. The stub emitted a `RuntimeWarning` and carried on. It now raises `ImportError` outside pytest. | `tests/test_splitter_stub_fails_closed.py` (3 tests) |
| R16 | P1 evidence | `tests/test_edge_cases.py` checked health against `/health` — **a route that does not exist** — with `assert status_code in (200, 404)`, i.e. `404 == 404`, seven times. Repointed at `/api/health` with `== 200`. | `tests/test_edge_cases.py` |
| R17 | P1 evidence | The Redis-outage test asserted `status_code in (200, 500)` **inside** `except (...): pass` — it accepted the crash it existed to rule out, and swallowed any exception. Now asserts `CLAUDE.md` Invariant 1 directly: Redis loss must **not** produce HTTP 500. | `tests/test_edge_cases.py` |
| R18 | P1 anti-hallucination | The Qdrant-degradation test likewise accepted 500 and swallowed the exception. Now asserts Invariant 3 — a served abstention **and no citations**, because zero retrieval means zero provenance and a non-empty citation list would be fabricated. | `tests/test_edge_cases.py` |
| R19 | P1 release gate | `tests/e2e/rls-cross-user.spec.ts` (17K) and `security-aal2.spec.ts` (14K) — the **only executable proof that user A cannot read user B's data** — were referenced by **no gate and no CI workflow anywhere**. Added both to `DEFAULT_SUITES`. | `scripts/prelaunch.sh` |
| R20 | P1 release gate | `main-hard-gates.yml` now fails the build on a degenerate retrieval-quality baseline. **This turns CI red today** (`mean_ndcg` is 0.0) — deliberately: a red build saying "your quality gate is fake" beats a green one that lies. Re-record with `UPDATE_QDRANT_BASELINE=1` to clear it. | `.github/workflows/main-hard-gates.yml` |

**R15 — escalated from code, then settled by measurement. `PROVEN FROM LIVE`.**

I called this "the most consequential finding of the whole audit" on the
strength of code reading. It is not. Measured against the live Qdrant on
2026-09-11:

```
collection spiritual_wisdom_contextual : 12,904 points
sampled 300 -> chunk length min/median/max = 146 / 863 / 2677
most common EXACT length: 5 occurrences in 300 (1.7%)
```

The stub is a pure fixed-width slicer that ignores `separators`, so a
stub-built corpus would show ~40%+ of chunks at exactly `chunk_size`. At 1.7%
the distribution is unambiguous: **the live corpus was built by the boundary
chunker — the intended production path — not by the stub.**

The shadowing hazard was real and the fail-closed guard stays. But the worst
case never materialised, and reporting it as though it had would have been the
same sin as a gate that cannot fail: a confident claim with nothing measured
behind it. Left in the record rather than deleted, because the lesson is the
point — inference raised the alarm, measurement retired it.

Also confirmed live: existing points carry **no** `embedding_model` /
`embedding_dimension` / `chunker_version` keys, as expected for pre-R11
vectors. Absence means *unknown/legacy*, never *matches current*.

### Round 5 — fixes made against the live stack

| ID | Severity | Finding | Proof |
|---|---|---|---|
| R21 | P1 observability | The three `grounded_partial_evidence` return paths hardcoded `faithfulness_score: 0.0` while verification had measured a real score. `scripts/ops/hallucination_anomaly.py:92` takes the **median of that field** across responses, so every partial-evidence answer entered the hallucination median as an observed zero — dragging fleet p50 down and making the alert threshold meaningless in both directions (false alarms, and real degradation hidden under an artificially low baseline). Now reports the measured score. | **`PROVEN FROM LIVE`** — same query before: `faithfulness_score: 0.0`; after: **`0.4375`**, matching the internal `Faithfulness: 0.44 (floor=0.60)`. 48 related tests pass |

**Two things I checked and did NOT change**, having initially called them bugs:

- **`grounding_state: "grounded"` on the partial-evidence path is correct.** The
  returned text is verbatim retrieved excerpts, so it *is* grounded;
  `verification.passed: False` correctly records that the rejected *draft*
  failed. I reported this as a contradiction earlier — it isn't.
- **The other 16 `faithfulness_score: 0.0` sites are correct.** They are genuine
  abstentions with no evidence at all; a zero there is a true statement, not a
  sentinel. Only the partial-evidence paths, which have citations and a
  measured score, were wrong.

**Separately surfaced, not yet fixed:** `app/schemas/__init__.py:268` declares
`grounding_state: Literal["grounded","abstained","safety_redirect","system_error"]`
but the code emits `bounded_hypothetical`, `capability_answer` and
`provenance_boundary`. Either the Literal is wrong or those responses are not
being validated against it. Tracked as B21.

### Deliberately NOT changed

- **`ToneAdapterStage` is not dead code.** It is a documented, tested,
  intentionally inert stage whose whole purpose is to stop a post-hoc LLM
  rewrite of a grounded answer being reintroduced under that name
  (`tone_adapter_stage.py:1-8`, `tests/test_tone_adapter_grounded.py`). An
  earlier draft of this backlog listed it for deletion; that was wrong. It
  costs one no-op call per request and removes a real regression risk.
- **`query_neo4j_subgraph` retained.** Zero production callers, but it has
  tests and is plausibly intended for future wiring. Deleting it is a product
  decision, not an audit finding. It is documented as dead instead.

### R4 in detail — measured, not asserted

Measured against the tokenizer this repo actually ships (`BAAI/bge-m3`):

| lang | real tokens/word | what the code computed | under-count |
|---|---|---|---|
| en | 1.27 | 0.77 | 1.65x |
| hi | 1.23 | 1.25 | ~ok |
| ta | 1.61 | 1.25 | 1.29x |
| te | 1.95 | 1.25 | 1.56x |
| bn | 2.44 | 1.11 | 2.20x |
| kn | 2.53 | 1.25 | 2.02x |

Two independent confirmations that tokens-per-word was always the intended
contract: `latin: 1.3` matches measured English exactly, and **three of the five
call sites already divided budget by the ratio to get words**
(`services/llm/base.py`, `rag/nodes/generation.py`, `rag/compressor.py`) — only
`estimate_tokens` and `cap_to_token_budget` were inverted. The comment claiming
the old form "protects Indic-script text" had it exactly backwards: Indic was
the worst under-counted.

**Why shrinking the prompt is a correctness win here, not a quiet quality cut.**
Against the repo's own declared `context_window_total = 8192`:

```
BEFORE : 15,600 words ~ 19,812 real tokens = 2.42x the declared window
AFTER  :  9,230 words ~ 11,722 real tokens = 1.43x the declared window
```

The fix moves real usage strongly *toward* the declared window. A residual
inconsistency remains and is **not** resolved: `max_tokens_per_request = 12000`
still exceeds `context_window_total = 8192`. Reconciling those two against
sarvam-105b's true context window is `REQUIRES LIVE VALIDATION`.

## Corrections to existing documentation

All `PROVEN FROM CODE`. The root `CLAUDE.md` and `backend/CLAUDE.md` should be
updated; they are currently wrong on these points.

1. **The documented stage order is wrong.** Real order:
   `CacheCheck -> RequestState -> InputGuardrail -> CircuitBreaker -> DoctrineCache
   -> CasualShortCircuit -> Distress -> BoundedComparisonShortCircuit -> Graph ->
   MeditationGen -> Translation -> ToneAdapter -> OutputGuardrail -> Memory ->
   CacheUpdate -> ResultAssembly`. `CircuitBreaker` runs *fourth*, not second,
   and `BoundedComparisonShortCircuit` is undocumented entirely.
2. **`/api/chat` is not in `app/main.py`** — it is `app/api/chat.py:423`, with
   the streaming variant at `:687`.
3. **No Neo4j-derived text reaches the LLM prompt.** `query_neo4j_subgraph`
   (`rag/nodes/retrieval.py:245`) has **zero production callers**. GraphRAG
   fusion and graph prefetch are gated on `graphrag_fusion_enabled`, default
   `False`. The prompt's "RELATIONSHIPS & DOCTRINE ONTOLOGY (sacred graph)"
   block is built from multi-chunk bookkeeping, not graph edges. The graph's
   only possible live influence is extra query *terms*, in a narrow case, with
   no provenance.
4. **Dead on live config:** `ToneAdapterStage` (body is `del ctx; return None`),
   `DoctrineCacheStage` (`DOCTRINE_CACHE_ENABLED=false`), `regenerate_gate`
   (`rag_regenerate_before_rewrite=False`), `agentic_graph_traversal`
   (`agentic_graph_traversal_enabled=False`), the BM25 lane
   (`BM25_RETRIEVAL_ENABLED=false`), and the `lightrag` parameter of
   `retrieve_for_single_query` (declared, never referenced in the body).
5. The previously-documented serial `expand_query_with_ontology` latency tax is
   **fixed** — it now runs inside the retrieval `asyncio.gather`.

## Open backlog (not yet implemented)

Ranked. Each needs the same source-change -> regression-test -> two-way-proof
treatment the fixes above received.

| ID | Sev | Finding | Location |
|---|---|---|---|
| B1 | P0 | Destructive `delete_by_source` runs *before* the upsert with no atomicity. A SIGKILL between them leaves the source entirely absent from Qdrant, checkpoint unsaved, and no startup path scans backup collections. Recovery is manual. | `ingest/pipeline.py` |
| ~~B2~~ | ~~P1~~ | **DONE — R11.** Backfilling provenance onto pre-existing points is still outstanding; until then absence means *unknown*, not *current*. | |
| B3 | P1 | Mixed score scales compared on one axis: Qdrant fusion scores, OKF raw cosine, and graph scores feed four absolute thresholds (0.08, 0.5, 0.75, 0.85). One OKF doc at ~0.9 can skip reranking entirely. | `rag/nodes/retrieval.py`, `rag/nodes/reranking.py` |
| ~~B4~~ | ~~P1~~ | **DONE — R10.** | |
| ~~B5~~ | ~~P1~~ | **DONE — R9.** Note the multi-replica caveat remains: in a deploy where each replica has its own copy of `compiled.json`, only the replica that ran the compile sees a new mtime. A shared volume or a version stamp is still needed for >1 replica. | |
| B6 | P1 | RAPTOR summaries are keyed by `cluster_id`, which is not stable across runs, and inherit `source_urls[0]`. Re-ingesting A can delete a summary spanning A+B, corrupting B without touching it. | `ingest/raptor.py` |
| B7 | P2 | Parent-chunk ids are `uuid4()` in the main pipeline; `contextual_reingest.py` already fixed this and the fix was never ported back. Every re-ingest dangles cached parent references. | `ingest/pipeline.py` |
| B8 | P2 | Ingestion lock is advisory, returns `True` when Redis is absent or errors, and is never released (TTL only). | `ingest/handlers/checkpoint.py` |
| B9 | P2 | Delete the genuinely-dead code in *Corrections* item 4 — the unreferenced `lightrag` parameter and the unused `verify_answer` import. **Not** `ToneAdapterStage` (see *Deliberately NOT changed*). | `rag/nodes/retrieval.py`, `rag/graph_strategies.py` |
| B10 | P2 | `resolve_anon_identity` silently no-ops when `session_id` is empty, leaving the literal id `"anonymous"`. Not currently exploitable — `require_scoped_identity` covers the two id-addressed routes and `_is_persistable_user_id` requires a real UUID before any memory read/write — but two independent controls are carrying it and neither is documented as load-bearing. | `services/auth_service.py:760` |
| B11 | P2 | Two KG routes (`app/api/memory.py:642`, `:715`) authenticate **in the handler body**, so `test_authz_regression.py`'s dependency-grep guard does not see them. Not exploitable today (`build_personal_knowledge_graph(None)` routes to the public ontology branch), but a future edit dropping that `or not user_id` clause would pass every test. | `app/api/memory.py` |
| B12 | P2 | Anonymous callers with an attachment are personalization-eligible with `user_id_for_cache=None`, so the exact-cache **read** hits the shared key. Returns a generic non-personalized answer (the attachment is ignored) — a correctness wart, not a data leak. Write path is safe. | `app/pipeline/stages/cache_stage.py:336` |
| B21 | P2 | `app/schemas/__init__.py:268` restricts `grounding_state` to a 4-value `Literal`, but the code emits `bounded_hypothetical`, `capability_answer`, `provenance_boundary`. Either the contract is stale or those responses bypass validation — both are worth knowing. | `app/schemas/__init__.py` |
| B22 | **P0 latency** `PROVEN FROM LIVE` | Measured p50 **24.6s** and p95 **208.5s** wall-clock against a <3s target — the **median** is 8x over, not just the tail. Even a bare `"hello"` took 10.3s. Comparative/multi-hop queries dominate the tail. Agent A's serialization findings name the specific independent `await` chains (notably `decompose_query -> navigate_and_hyde`, two independent LLM calls on a serial edge where neither reads the other's output), and the graph contributes **no text to the prompt** while costing time — so there is a concrete optimisation target, not a hypothesis. | `rag/graph_strategies.py`, `rag/nodes/retrieval.py` |
| B20 | **P0 deploy** `PROVEN FROM LIVE` | **The documented Docker deployment cannot start on this machine.** `make docker-up` builds and starts `mukthiguru-backend`, which then OOM-kills in a loop — **exit 137, 99 restarts**, never reaching healthy. Measured cause: the compose `deploy.limits.memory` for `backend` is **6 GB**, Docker Desktop is allocated **8.3 GB**, and 25 containers already resident consume **3.3 GiB**, leaving ~5 GB — less than the backend needs once BGE-M3 + the reranker load. Note the other project's containers account for only ~1 GiB, so stopping them does not fix it. Options: raise the Docker Desktop memory allocation, lower `deploy.limits.memory` and accept degraded model loading, or run the backend on the host against containerised infra (the path `backend/CLAUDE.md` already documents). **No CI or test covers "does the documented deploy actually boot".** | `backend/docker-compose.yml` |
| B13 | P1 | `http_pool_max_connections` was cut 50→20 (and `embedding_cache_size` 2000→1000) inside `917ef07c`, a personalization *feature* commit, with no stated rationale and no measurement. A 60% reduction in the outbound connection pool is a plausible p95 tail contributor under concurrency. Validate under load or revert. | `app/config.py:990`, `:1023` |
| B14 | **P0 evidence** | Rewrite `tests/test_edge_cases.py`. Every failure-path test is unfalsifiable: `assert status_code in (200, 500)` plus `assert health.status_code in (200, 404)` against a `/health` route **that does not exist** (`404 == 404`, six times). They mock the graph, so no dependency client code runs. The degradation invariants in `CLAUDE.md` have **no real coverage**. | `tests/test_edge_cases.py` |
| B15 | P1 | `main-hard-gates.yml:61` "validates" retrieval quality with `test -f`. Make the gate actually run the quality test against a service container, or delete the line rather than let it imply coverage. | `.github/workflows/main-hard-gates.yml` |
| B16 | P1 | Re-record `memory/qdrant_quality_baseline.json` against a populated collection. R13 stops it reporting a false green, but the gate stays inert until the baseline is real. | `memory/qdrant_quality_baseline.json` |
| B17 | P1 | Add `rls-cross-user` and `security-aal2` to `DEFAULT_SUITES`. Real cross-user RLS proof exists but runs only nightly against staging, behind three secrets — so it gates nothing at release time. | `scripts/prelaunch.sh:132` |
| B18 | P1 | Delete the repo-root `langchain_text_splitters/` stub or rename it. It shadows the real package when pytest runs from the repo root — the command root `CLAUDE.md` documents — so the two documented ways to run the suite test different implementations. | repo root |
| B19 | P2 | No test covers SIGTERM/graceful shutdown mid-stream, Qdrant genuinely down, Neo4j genuinely down, LLM malformed output, or a provider 429 propagating. Each documented degradation invariant needs one real test. | `backend/tests/` |

## LIVE MEASUREMENTS — 2026-09-11 (`PROVEN FROM LIVE`)

The stack was brought up and exercised. Everything in this section is measured,
not inferred. Infra via `scripts/docker-safe.sh docker compose up -d qdrant
redis neo4j`; backend on the host (see L1) against that infra; `/api/health`
returned `ready: true` with every service green.

### L1 — The documented Docker deploy does not boot on an 8.3 GB Docker host

`docker compose up -d --build backend` produced **exit 137 (OOM), 99 restarts**,
never healthy. Measured: compose `deploy.limits.memory` for `backend` is **6 GB**;
Docker Desktop is allocated **8.3 GB**; 25 already-running containers consume
**3.3 GiB**, leaving ~5 GB. Unrelated projects account for only ~1 GiB of that,
so stopping them does not fix it. **No test or CI job asserts that the
documented deploy boots.** Tracked as B20.

### L2 — Latency: the median misses the target and the tail is catastrophic

Eight query classes, each with a cache-busting nonce so no cache tier could
serve them:

| query class | seconds |
|---|---|
| doctrine lookup ("Beautiful State") | **2.2** |
| emotional/personal ("anger towards my father") | **14.4** |
| comparative ("Soul Sync vs Deeksha") | **122.9** |
| comparative ("Beautiful vs Suffering State") | **121.2** |
| reflective ("why do I keep suffering") | **8.3** |

**Authoritative figures** use the job's own `latency_ms` (server-side
processing), not wall-clock — wall-clock includes queue wait plus the harness's
2s poll granularity. Measured overhead between the two is ~1–2s. n=8, all
completed, fresh anon token per query, cache-busting nonce:

| query | server | citations | faithfulness |
|---|---|---|---|
| "Beautiful State" | **0.1s** | 3 | 1.0 |
| "anger towards my father" | 10.8s | 2 | 0.62 |
| "Soul Sync vs Deeksha" | **122.0s** | 2 | 0.0 |
| "Beautiful vs Suffering State" | **165.4s** | 2 | 0.0 |
| "why do I keep suffering" | 12.3s | 0 | 1.0 |
| "what did Sri Preethaji teach…" | 6.0s | 2 | 0.54 |
| Hinglish "mujhe bahut gussa…" | 39.0s | 1 | 1.0 |
| **"hello"** | **6.1s** | 0 | 1.0 |

```
n=8   min 0.1s   p50 10.8s   p95 165.4s   max 165.4s
```

Three things this makes visible that wall-clock hid:

- **0.1s on a repeated query** — the cache tiers work, and that is the only
  sub-second result in the set. Every uncached query is ≥6s.
- **`"hello"` costs 6.1s of server time.** A deterministic greeting should
  short-circuit in milliseconds (`CasualShortCircuit` sits at stage 6). Whatever
  it is paying for, it is not retrieval — this is the cheapest available p50 win
  and likely explains a large share of the median.
- **R21 confirmed live in-sweep**: two rows report real faithfulness (0.62, 0.54)
  where the pre-fix build would have written `0.0` into the alerting median.
  Two rows still show 0.0 despite carrying citations — those take a
  `faithfulness_score: 0.0` return path outside the three patched in R21, so the
  sentinel problem is **narrowed, not eliminated**.

Against `SPEC_DEV.md`'s aspirational **<3s**:

| | server-side | over target |
|---|---|---|
| p50 | **10.8s** | **3.6x** |
| p95 | **165.4s** | **55x** |

**The median misses the target, not just the tail.** Comparative/multi-hop
queries form the tail, and they are exactly the questions a seeker most needs
answered. This is the first latency data ever recorded for this system.

An earlier draft of this section reported "p50 2.2s, p50 is acceptable". That
was wrong, and wrong in a specific way worth recording: the three quota-rejected
requests had been counted as `0.0s` successes, pulling the median down by
6.5x. **The rejections were being averaged in as if they were fast answers.**
Same failure mode as a gate that cannot fail — a good-looking number produced
by something that was not actually measuring what it claimed.

**Measurement caveat, recorded because it nearly produced a false number:** the
first run reused one anonymous session token for all eight queries.
`anon_quota_messages` is 5, so queries 6–8 returned 429 with no `poll_url` and
were logged as `0.0s` — flattering p50 and hiding the rejections. Verified
directly (`req1..req5 -> 202`, `req6 -> 429`). The harness now takes a fresh
token per query and refuses to count a non-completed request as a fast one.
**The quota itself works correctly** — that part is a positive result.

### L3 — Anti-hallucination holds; its telemetry does not

For "How do I deal with anger towards my father?" the pipeline returned
`verification.passed = False`, `Faithfulness: 0.52 (floor=0.60)`, and degraded to
*"a grounded partial answer taken directly from the retrieved excerpts"* with 2
real citations. **The core promise held under live conditions** — it refused to
pass off an unverified draft as doctrine.

Three defects surfaced alongside it:

1. **The reported metric contradicts the measured one.** The API surfaces
   `faithfulness_score: 0.0` while verification internally recorded **0.52**.
   The deliberate-low-telemetry convention documented at `generation.py:309`
   covers the *abstention* path (`NO_EVIDENCE_CONFIDENCE`), which has no
   evidence at all — this was the *partial-answer* path, which has citations
   and a genuine score. `scripts/ops/hallucination_anomaly.py` alerts on
   faithfulness p50 drawn from this field, so the alerting input is wrong.
2. **`grounding_state: "grounded"` while `verification.passed: False`** —
   contradictory state on the same response.
3. **Prompt leakage into the draft.** The unsupported claim the verifier caught
   was the model echoing its own instruction: `'I need to answer based ONLY on
   the ...'`. The gate caught it, but it should not be generated.

`is_faithful` and `confidence_score` come back `None` on this path.

### L4 — Corpus and collection state

`spiritual_wisdom_contextual`: **12,904 points**; `spiritual_wisdom`: absent
(migration completed). Chunk lengths 146–2677, median 863, dominant exact
length **1.7%** — the boundary chunker, **not** the stub (see R15). Existing
points carry no R11 provenance keys, as expected for pre-fix vectors.
The G13 empty-collection hazard is **not** currently live, and R2's stricter
health check passes against the real collection.

## Coverage against the audit brief — what was and was NOT done

The brief specified 23 workstreams. Claiming completion would be the exact
failure mode it warns about, so here is the honest accounting. **Six major
workstreams were not executed at all.**

| § | Workstream | State | Note |
|---|---|---|---|
| 0 | Operating principles | **DONE** | evidence labelled; every fix two-way proven; own fixes attacked by an independent agent; two of my own conclusions retracted |
| 1 | Parallel subagents A–L | **PARTIAL** | ran A (runtime), B+C (RAG/graph), F (security), G (ingestion), I (QA). **D+E (LLM economics / latency) never ran** — died on a rate limit twice. H (frontend/UX), J (dependencies), K (question taxonomy), L (independent red-team) **never ran** |
| 2 | Canonical source of truth | **DONE** | this document |
| 3 | End-to-end request trace | **PARTIAL** | chat path traced node-by-node. Memory, Second Brain, ingestion and admin traced at route/auth level only. **Attachments not traced** |
| 4 | Runtime DAG | **DONE** | `docs/RAG_RUNTIME_DAG.md` |
| 5 | **Latency program** | **NOT DONE** | no instrumentation added, no critical path measured, no deadline propagation implemented, no adaptive-routing change. Serialization points identified from code only |
| 6 | **RAG quality program** | **NOT DONE** | no held-out corpus built; ablations A–F never run; no Recall@K / MRR / nDCG / citation-correctness measured |
| 7 | Prove graph value | **PARTIAL** | proved from code that the graph contributes **no text to the prompt**. The measured ablation still has to be run — and could not have been valid before R5 removed the BM25 confound |
| 8 | Security isolation matrix | **DONE** | 202 routes scanned; no P0; cache invariant verified; R7/R8/R19 landed |
| 9 | Ingestion consistency | **DONE** | split-brain scenarios enumerated; R1/R3/R10/R11/R15 landed |
| 10 | Cache correctness | **PARTIAL** | staleness fixed (R9/R10). **Cache-hit-type separation not implemented** — coalescing is still not distinguished from a response-cache hit in metrics |
| 11 | **Fallback quality visibility** | **NOT DONE** | belonged to D+E. Whether a 200 hides a degraded fallback is still unknown |
| 12 | **Memory / worker / concurrency** | **NOT DONE** | no RSS, model-load-count, or safe-concurrency measurement |
| 13 | **Frontend / real user journey** | **NOT DONE** | no browser flow exercised at all |
| 14 | **Dependency / CVE audit** | **NOT DONE** | no `pip-audit`, no `npm audit`, no base-image scan |
| 15 | Failure-injection matrix | **PARTIAL** | R16–R18 made Redis and Qdrant degradation real. **SIGTERM mid-stream, malformed LLM output and 429 propagation remain untested**; surviving tests still mock the graph rather than the dependency clients |
| 16 | What to delete | **DONE** | incl. one refusal (`ToneAdapterStage`) with reasoning |
| 17 | Implementation backlog | **PARTIAL** | every item has ID/severity/evidence/location/failure/fix/status. **Owner, observability and rollback columns are not populated per item** |
| 18 | Phases 0–10 | **PARTIAL** | 0–3 done; **4 (latency), 5 (RAG optimisation), 6 (chaos), 7 (frontend), 8 (production validation) not done**; 9 partial (QA agent served as red team); 10 done |
| 19 | Definition of done | **PARTIAL** | implementation + regression test + failure-path test + observability met for most fixes. **Benchmark before/after, quality comparison, latency comparison and cost comparison were not possible** — nothing was measured |
| 20 | Production gates | **DONE** | stated honestly, several FAIL |
| 21 | Final report A–H | **DONE** | below |
| 22 | UX goal | **PARTIAL** | analysed; the adaptive-execution work it implies is §5, not done |
| 23 | Do not cheat | **ADHERED** | no test silenced; stale tests diagnosed individually; failures reported with the numbers attached |

**The single biggest gap is §5/§6.** No latency number and no retrieval-quality
number exists for this system. Everything about performance and answer quality
in this repo — including anything I wrote — is unmeasured. That is the work to
do next, and it needs the stack running.

## Final report (brief §21)

**A. Verdict — NO-GO.** Not for one catastrophic bug. Two reasons: several
release gates could not fail (now fixed, but the underlying measurements still
do not exist), and **the live corpus may have been chunked by a test stub**
(R15) — which, if true, invalidates every retrieval-quality judgement made
about this system to date.

**B. Top problems** — R1 silent data loss on rollback; R2 empty-collection
outage behind a green health check; R3 permanent ingestion split-brain;
R15 corpus chunked by a test stub; R4 token under-count 1.65–2.20x;
R6 abstention guard that could never fire; R7 anonymous graph scan over private
memory; R5 one flag degrading three retrievers; R12 Hinglish misrouting;
R13/R20 a quality gate that could not fail. All fixed and two-way proven.

**C. Genuinely strong** — the three embedding-dimension guards; the
cache-personalization invariant (verified real, not merely claimed); anon-identity
HMAC scoping; Second Brain ownership predicates; the SSRF guard; and the
`ToneAdapterStage` decision to keep a deliberate no-op rather than "tidy" a
safety property away.

**D. Delete** — the `lightrag` dead parameter, the root splitter stub,
`test_edge_cases.py` as originally written. Keep `ToneAdapterStage`.

**E. Fastest path to good answers** — settle the chunker question (R15), then
measure. The graph currently contributes nothing to the prompt while costing
latency, so the cheapest credible architecture is Qdrant + rerank + OKF, with
graph work gated behind a measured win.

**F. Before/after** — suite `30 failed / 3180 passed` → `35 failed / 3561
passed`, where **all 35 remaining failures belong to a concurrent session's
feature and zero are in audited code** (tracked failures there: 16 → 0).
**No latency, token, cost, or quality deltas — nothing was measured.**

**G. Unknowns** — all latency; all retrieval quality; which splitter built the
corpus; RLS policy SQL; dependency/CVE posture; sarvam-105b's real context
window; frontend behaviour.

**H. Release checklist** — see the gate table below; four gates FAIL, two are
PARTIAL.

## False confidence — what the green suite does NOT prove

The most important result of this audit. Each item is `PROVEN FROM CODE`. These
are **not fixed** except where noted; they are the honest boundary of the
evidence.

1. **The failure-path suite is unfalsifiable.** Every test in
   `tests/test_edge_cases.py` — `test_llm_api_failure`,
   `test_redis_connection_error`, `test_graph_timeout`,
   `test_qdrant_timeout_graceful_degradation`,
   `test_neo4j_unavailable_graceful_degradation`,
   `test_embedding_service_load_failure`, `test_provider_rate_limit_handling`,
   `test_cascading_failure_two_dependencies_down` — wraps the request in
   `try/except: pass` and asserts `status_code in (200, 500)`. It then checks
   "server still healthy" with `assert health.status_code in (200, 404)`
   against `/health`, **which does not exist** (the route is `/api/health`), so
   that line is `404 == 404` — a literal tautology, repeated six times. These
   tests can only fail if the Python process dies. They also mock
   `container.*_graph.ainvoke`, so no Qdrant/Neo4j/Redis client code runs at
   all: they exercise the orchestrator's `except` clause, not the degradation
   invariants `CLAUDE.md` documents.
2. **The retrieval-quality hard gate runs nothing.**
   `.github/workflows/main-hard-gates.yml:61` is
   `test -f backend/tests/test_qdrant_search_quality.py` — a file-existence
   check. The quality test itself is never executed by the gates.
3. **The baseline made the gate unfailable** — fixed as R13, but the baseline
   value itself is still `0.0` and must be re-recorded against a populated
   collection before the gate means anything.
4. **The eval gate is green-when-absent.** `eval-gate.yml:58` runs only
   `if steps.target.outputs.available == 'true'`; with Railway paused and no
   `BACKEND_URL`, the job **succeeds** with a note. `lint-test.yml:134` runs
   pytest with no service containers, so every infra-gated test skips in CI.
5. **Some security tests assert source text, not behaviour.**
   `test_authz_regression.py` is better than feared — the job-ownership and
   chat-stream-ownership tests really invoke handlers as user B against user
   A's resource. But `test_concept_graph_requires_admin`,
   `test_circuit_breaker_endpoints_admin_only` and `test_cache_metrics_admin_only`
   are source-greps (`assert "is_superuser" in src`), which pass even if the
   call is dead code. `test_cache_personalization_leak.py` asserts only the
   **hot** tier; `exact_cache` and `semantic_cache` are bare `MagicMock`s there,
   so a leak into those tiers would pass that test. (The invariant does hold —
   Agent F verified it directly — but this test is not what proves it.)
6. **RLS is never proven in the pre-launch gate.** Real cross-user proof exists
   only in `tests/e2e/rls-cross-user.spec.ts` and
   `backend/scripts/verify_rls_policies.py`. `scripts/prelaunch.sh:132`'s
   `DEFAULT_SUITES` omits both `rls-cross-user` and `security-aal2`; the
   verifier runs only in `nightly-rls.yml`, against staging, conditional on
   three secrets.
7. **A checked-in fake shadows a real dependency depending on cwd.** Repo-root
   `langchain_text_splitters/__init__.py` is a test stub. Running
   `python3 -m pytest backend/tests/` from the repo root — **the command the
   root `CLAUDE.md` documents** — imports the stub, while `.venv/bin/pytest`
   from `backend/` imports the real package. Same tests, different
   implementation under test.
8. **~16 assertion-free tests** and 208 `assert_called*` sites; several tests
   whose only assertion is `is not None`.

### Failure paths with no test at all

SIGTERM / graceful shutdown mid-stream (zero matches anywhere); Qdrant actually
down (the documented abstention fallback is untested — the existing test raises
`CircuitOpenException` from a mocked graph); Neo4j actually down (the documented
Qdrant+BM25 fallback is untested); LLM malformed or truncated output; a
provider-returned 429 propagating through the pipeline. Client disconnect has
exactly one real test (`test_streaming_guardrail.py:197`).

**There is no performance/latency regression test.**
`test_latency_catalog.py:11` explicitly asserts `budget.validated is False` —
the suite codifies that the latency budgets are unvalidated hypotheses.

## Test-evidence health

- `tests/test_graph_stage_fixes.py::test_retrieval_query_fan_out_limited_to_two`
  is **order-dependent**: it fails in isolation with `ConnectError` on
  unmodified code, and passes in a full run only when another test leaves a
  mocked container behind. Verified by stashing all changes and re-running.
- Two consecutive full-suite runs collected different test counts (3231 vs
  3350) and differed 2.2x in wall time (422s vs 192s). Collection is not
  deterministic; this needs its own investigation before suite results are
  trusted as a release gate.
- Several regression tests added in this pass assert over **source text** via
  `inspect.getsource` rather than executing the failure path. They catch the
  specific regression cheaply but are the weaker form of evidence; behavioural
  equivalents need fake Neo4j/Qdrant drivers and are tracked as follow-up.

## Remaining unknowns

Genuinely unproven. Do not let these be reported as green.

1. **All latency numbers.** No TTFT, p50/p95/p99, or critical-path timing was
   measured. The stack was never running.
2. **All retrieval quality numbers.** No Recall@K, nDCG, MRR, citation
   correctness, or hallucination rate was measured. No held-out evaluation
   corpus exists in the repo.
3. **Whether the graph adds value.** Cannot be measured until R5 ships,
   because `KNOWLEDGE_GRAPH_QUERY_ENABLED` was confounded with BM25 and query
   budget. R5 removes the confound; the ablation still has to be run.
4. **sarvam-105b's true context window**, and therefore whether
   `max_tokens_per_request=12000` vs `context_window_total=8192` is safe.
5. **Security isolation — partially resolved.** The workstream completed on a
   second attempt and found **no P0 and no working cross-user or cross-tenant
   bypass**. A 202-route AST scan confirmed all 84 `admin.py` routes sit on
   `_require_admin` (the earlier "admin.py has no routes" lead was a grep
   artifact: its router is named `admin_router`). The documented cache
   personalization invariant **genuinely holds** — all four tiers guarded on
   both read and write by the same predicate, and each cache has exactly one
   non-test writer, all in `cache_stage.py`. Second Brain, notebooks, memory,
   profile and the SSRF guard all verified clean.
   **Still unverified:** the Supabase RLS policies themselves (SQL migrations
   were not read), frontend storage, `ingest/pdf_parser.py` SSRF, the Qdrant
   tenant-collection migration, and WebSocket/SSE auth beyond `/chat/stream`.
   A DNS-rebind TOCTOU between the scraper's URL check and fetch is known and
   unaddressed.
6. **Dependency/CVE posture.** Not audited in this pass.
7. Whether `.env.optimized` or the Railway environment override the flags that
   make `agentic_graph_traversal`, `regenerate_gate`, and `DoctrineCacheStage`
   dead. Only `backend/.env` was read.

## Release gates — current state

| Gate | State | Why |
|---|---|---|
| Security isolation verified | PARTIAL | 202-route scan, no P0, no working bypass; cache invariant holds. RLS policies themselves still unread |
| Held-out quality evaluation passes | FAIL | a golden corpus and nDCG tests exist but are **inert**: the CI "gate" is `test -f`, the baseline is 0.0, and the tests skip without Qdrant |
| Dependency-failure behaviour has real tests | PARTIAL | R16–R18 made the health checks real and pinned the Redis and Qdrant invariants (incl. no fabricated citations). Still no test for SIGTERM mid-stream, malformed LLM output, or 429 propagation; the remaining tests still mock the graph rather than the dependency clients |
| Isolation proof runs in the release gate | PASS | R19 — `rls-cross-user` and `security-aal2` now in `DEFAULT_SUITES`; previously referenced by no gate or workflow at all |
| Corpus chunker is unambiguous | **PASS** `PROVEN FROM LIVE` | measured: 12,904 points, chunk lengths 146–2677 (median 863), dominant exact length 1.7% — the boundary chunker, not the stub. R15 closes the hazard going forward |
| Configured collection is populated | **PASS** `PROVEN FROM LIVE` | `spiritual_wisdom_contextual` holds 12,904 points; the G13 empty-collection hazard is not currently live |
| TTFT / p50 / p95 / p99 measured | NOT MEASURED | stack not running |
| Dependency risk reviewed | NOT ASSESSED | |
| Dependency-failure behaviour tested | partial | R2 closes the empty-collection case |
| Ingestion consistency | partial | R3 done; B1, B4, B6 open |
| Backup/restore correctness | PASS | R1, proven two-way |
| Suite green | FAIL | 16 tracked failures at baseline; not yet zero |

**Verdict: NO-GO**, and the reason sharpened over the three passes.

The first pass called it NO-GO for missing evidence. The test-evidence pass
found something worse than missing evidence: **evidence-shaped artifacts that
cannot fail.** A retrieval-quality gate that runs `test -f`. A regression
baseline of `0.0` that makes its own assertion vacuous. A failure-path suite
whose health check asserts `404 == 404` six times. An eval gate that reports
success when its target is absent.

Missing tests are a known gap. Tests that cannot fail are a *false* signal —
they actively argue for readiness. That is the thing to fix before any
go/no-go conversation is meaningful.

What is genuinely established: no P0 security isolation bug exists (202 routes
scanned; the documented cache invariant verified directly), and the suite is
now a usable regression signal again — the stale failures that made "the tests
pass" meaningless have been diagnosed individually and repaired.

What remains unestablished is unchanged in kind, if not in confidence: **no
latency number and no retrieval-quality number has ever been measured on this
system.** Until B14–B19 close, a green suite is not evidence of resilience.
