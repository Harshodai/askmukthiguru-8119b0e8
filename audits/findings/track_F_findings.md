# Track F — Observability, Performance/Scalability/Cost, Testing Completeness

Audit date: 2026-09-18. Repo: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`.
Docker stack at audit time: `mukthiguru-backend` (healthy), `mukthiguru-qdrant`,
`mukthiguru-memgraph`, `mukthiguru-redis` — all healthy. `mukthiguru-jaeger` was
**not running** (not even a stopped container exists — `docker ps -a` shows no
jaeger container at all). This box was under heavy **concurrent** load for the
duration of this track's work: 5 other audit tracks were simultaneously issuing
real Docker/OpenRouter-backed requests against the same backend container, which
is noted wherever it affects interpretation of a measurement.

This track inherited already-measured latency/faithfulness numbers from
`docs/GURU_DEMO_READINESS.md` §4E (produced earlier today via
`backend/evaluation/bench.py`) per the task brief, and did not re-run that
benchmark from scratch. New evidence gathered directly by this track (log
inspection, live requests, `docker stats`, `pytest`, `npm test`, `tsc`,
`eslint`, `playwright`) is cited with exact commands/log lines throughout.

---

## Phase 16 — Observability

**Status: PARTIAL** — structured logging, correlation IDs, and most business
metrics are real and load-bearing. Distributed tracing is configured but
provably non-functional in the default deployment. Error tracking is absent
server-side. Telemetry-sink write failures are live, under-logged, and
correlation-blind — a genuine, currently-occurring defect.

### What was checked / verified

- **Structured logging**: `backend/app/main.py:133-155` (`JSONFormatter`) —
  confirmed JSON, not plain text. Every log line observed in this session was
  valid JSON with `timestamp`/`level`/`logger`/`message`. A `PIIScrubber`
  logging filter (`main.py:158-183`) redacts PII before any handler formats
  it — confirmed live: a captured log line contained `[REDACTED_PHONE]` in
  place of what was originally a `trace_id` UUID fragment that apparently
  matched a phone-number-shaped pattern (a false-positive redaction, noted
  but not scored as a defect since PII-safety erring toward over-redaction is
  the correct default).
- **Request IDs / correlation IDs**: `app/context.py` (`correlation_id_var`,
  `set_request_id`), wired in `main.py:892-893,905` (gated by
  `settings.enable_correlation_ids`). Confirmed live: every request in this
  session's `docker logs` carried a `correlation_id` field end-to-end
  (validation errors, pipeline stage timings, LLM call timings, final
  `CHAT_STAGE_TIMING` line) — **except** telemetry-sink background writes
  (see AMK-F-002).
- **Metrics** (`backend/app/metrics.py`, 642 lines): real Prometheus
  `Counter`/`Gauge`/`Histogram` registry, exposed at `GET /metrics`
  (`app/api/health.py:647-650`, admin-only via `require_aal2`). Spot-checked
  which declared metrics actually have a `.observe()`/`.inc()`/`.set()` call
  site outside `metrics.py`:
  - **Wired and real**: `LLM_TOKENS` (`services/openrouter_service.py:325`),
    `PIPELINE_STAGE_LATENCY` (`rag/nodes/utils.py:1399,1483`),
    `TTFT_SECONDS` (`app/chat_engine.py:380,393`, `app/stream_orchestrator.py:203`),
    `RETRIEVAL_RELEVANCE_RATIO` (`rag/nodes/reranking.py:430`).
  - **Declared but dead** (zero call sites outside `metrics.py`):
    `RETRIEVAL_LATENCY`, `LLM_LATENCY`, `TPOT_SECONDS`. See AMK-F-005.
  - **Celery/queue metrics**: zero. `grep -n "Counter|Gauge|Histogram"
    celery_config.py tasks/*.py` → no hits; no `task_prerun`/`task_postrun`/
    `task_failure` signal wiring. The in-process `job_queue.py` used by the
    *default* (non-Celery) chat path also has no depth/utilization gauge.
    Celery itself is profile-gated (`COMPOSE_PROFILES=ingestion`) and was
    confirmed not running (`docker ps` at audit start showed no celery
    worker container) — consistent with backend/CLAUDE.md.
  - **Memory metrics**: `MEMORY_LRU_EVICTIONS` counter exists for
    `MemoryServiceV2`'s in-memory LRU fallback; a resident-memory gauge is
    declared (`metrics.py:567`) — not independently verified as wired.
- **Tracing**: `backend/app/observability.py` — OpenTelemetry init is real
  code (FastAPI + LangChain instrumentation, OTLP gRPC exporter), gated by
  `OTEL_ENABLED` (default `true` — **not set** in `backend/.env`, confirmed
  via `grep -i OTEL backend/.env` returning nothing, so the default applies).
  Exporter endpoint defaults to `http://jaeger:4317`
  (`observability.py:65`). `docker-compose.yml:133-136` gates the `jaeger`
  service behind `profiles: [observability]` — **not part of the default
  `docker compose up -d` stack**, and confirmed via `docker ps -a` to have
  zero jaeger container (running or stopped) on this box. Net effect:
  tracing initializes "successfully" (FastAPI/LangChain get instrumented,
  `_INITIALIZED = True`), spans are generated, and the `BatchSpanProcessor`
  silently fails to export them to a host that doesn't exist. This is
  **configured but unused** — see AMK-F-001.
- **Error reporting**: `grep -rln "sentry" backend/app/ backend/services/` →
  zero hits. No error-tracking/alerting SDK wired server-side (frontend has
  `src/lib/sentry.ts`, 100% test-covered per the Vitest coverage report, but
  nothing analogous on the backend). The global exception handler
  (`main.py:1158-1172`) logs a full traceback (`exc_info=True`) with a
  generated `error_id` and returns that id to the client — but its only
  sink is stdout → Docker logs. See AMK-F-003.
- **LLM telemetry / CHAT_COST**: confirmed real and current. Live log line
  captured this session: `CHAT_COST endpoint=/api/chat tenant_id=oneness
  user_id=anonymous model=deepseek/deepseek-chat tokens_in=8516
  tokens_out=780 cost_usd=0.001804` — matches root CLAUDE.md's documented
  `$0.00046-$0.00179` per-query cost range closely (this one ran slightly
  above the documented upper bound, consistent with the heavier tier3_complex
  query it came from). Two `CHAT_COST` emission sites exist
  (`app/api/chat.py:429`, `app/services/job_queue.py:525`) for sync vs.
  queued paths.
- **RAG telemetry**: `app/telemetry_sink.py` (699 lines) and
  `app/telemetry_db.py` (2097 lines) are real, substantial, and actively
  writing to Supabase tables (`chat_queries`, `chat_responses`,
  `retrieval_events`, `trace_spans`, `trigger_events`, `safety_events`,
  `chat_sessions`) — confirmed via live `TELEMETRY_SINK_WRITES` counter
  usage and the live error below. Per-stage node timings
  (`navigate_and_hyde`, `retrieve_documents`, `generate_answer`,
  `verify_answer`, etc.) are logged in full on the **synchronous** `/api/chat`
  path via `CHAT_STAGE_TIMING`. **Not** emitted on the streaming/job-queue
  path — see AMK-F-004.
- **A FAILED request end-to-end (live-triggered this session)**: two
  synthetic malformed requests (missing required fields, invalid JSON) both
  produced clean `422` responses with a `correlation_id`-tagged WARNING log
  naming the exact Pydantic validation errors — an operator CAN fully answer
  WHO/WHAT/WHEN/WHERE/WHY for this class of failure from logs alone (WHO is
  weak — anonymous requests carry no user identity until a session is
  established). Separately, this session caught a **live, naturally-occurring**
  backend-side failure (not synthetically triggered) that is a better test of
  the WHO/WHAT/WHEN/WHERE/WHY/DEPENDENCY/COST/RECOVERY framework — see
  AMK-F-002 for the full breakdown. Short version: WHEN and WHY are
  answerable from that log line alone; WHO, WHAT, WHERE (which of 7 tables),
  and COST are not; RECOVERY is "the user's chat response already succeeded
  regardless" (fire-and-forget telemetry) but the lost audit row itself has
  no retry/recovery.

### Problems found

See AMK-F-001 through AMK-F-006 below.

### Unknowns

- Whether `RESIDENT_MEMORY` gauge (`metrics.py:567`) and the Redis-degraded
  `_track_degraded` counters are genuinely wired at their call sites — not
  independently verified line-by-line (time-boxed).
- Whether Railway (the actual production target) has `OTEL_ENABLED` set
  differently than local `.env` — not checked (Railway is documented paused
  this session).
- Whether the PII-scrubber false-positive (a trace-id fragment redacted as a
  phone number) causes any operationally-relevant loss of debug information
  at scale — only one instance observed.

### Evidence

Exact log lines, file:line references, and grep commands are inline above
and in the AMK findings below.

---

## Phase 17 — Performance / Scalability / Cost

**Status: PARTIAL** — the already-measured numbers in
`docs/GURU_DEMO_READINESS.md` §4E are treated as authoritative per the task
brief and are NOT re-litigated here. This track's original contribution:
(1) a live time-to-first-token measurement via real SSE streaming, (2)
direct evidence that root CLAUDE.md's "Multi-Stage RAG Latency Profile" is
stale, (3) live confirmation — via a captured raw SSE transcript with two
distinct cited videos — that a verification-retry pays a real duplicate-
generation tax, corroborating the `grounded_partial_fallback` suspicion named
in the task brief, and (4) `docker stats` RAM/CPU snapshot.

### Numbers carried forward from docs/GURU_DEMO_READINESS.md §4E (not re-measured)

Three independent 12-question runs today (§4E.2.1, §4E.2.4, §4E.2.5):

| Run | misattribution_rate | must_mention_coverage | latency_p95_s |
| :-- | ---: | ---: | ---: |
| 1 | 0.0 (PASS) | 0.4545 (FAIL) | 70.67 (PASS) |
| 2 (stability check) | not re-measured | 0.6 (PASS) | 148.78 (FAIL) |
| 3 (post-code-review) | 0.0 (PASS) | 0.4 (FAIL) | 106.9 (FAIL) |

**Verdict from that document (carried forward, not re-derived): NOT
demo-safe** — must_mention coverage and latency p95 stability are open,
unresolved blockers; misattribution is the one gate with genuine
cross-run confidence (0% three times).

### New measurements this track took directly

- **Time-to-first-token, live, real query** (`"What is the Beautiful State
  according to the teachings?"`, tier `standard`/full pipeline, via
  `POST /api/chat/stream` → SSE job relay): first `event: token` arrived at
  **+4.85s** from request submission; full streamed response (through
  `event: done`) completed at **+34.5s**. This is a single data point taken
  on a box under heavy concurrent load from 5 other audit tracks — not a
  clean baseline, but directionally consistent with the box being loaded
  (TTFT would be expected lower on a quiet box, matching the ~1-5s range
  implied by root CLAUDE.md's stage breakdown for `navigate_and_hyde`).
- **Duplicate generation, live-confirmed**: the same captured SSE transcript
  shows two distinct, non-simulated token streams of near-identical answer
  text back-to-back — first pass (+4.85s to +17.7s) ends citing
  `youtube.com/watch?v=x-mTRlE0TC4`; a `status: Finalizing your
  response...` / `stage: format_final_answer` event fires at +17.8-18.0s;
  then a **second** pass (+18.0s to +33.9s) restarts from "The Beautiful
  State is a profound..." and ends citing a **different** video
  (`Gt3o8lcbcII`). Two different cited videos is strong evidence these are
  two independent LLM completions, not a client-side replay artifact or the
  code's known "simulate streaming on cache hit" fallback
  (`stream_orchestrator.py:360-366`, which chunks in fixed 20-char/10ms
  steps — the observed timing was irregular, consistent with real
  generation). This directly corroborates the task brief's suspicion that
  `generation.py`'s `grounded_partial_fallback` retry path costs ~2x
  latency, and is independently corroborated by
  `docs/GURU_DEMO_READINESS.md` §4E.2.4's own finding that one
  `grounded_partial_fallback` hit inflated p95 from 70.67s to 148.78s. See
  AMK-F-008. The synchronous-path `CHAT_STAGE_TIMING` node-by-node
  breakdown that would let an operator directly *count* generation calls per
  request is **not** emitted on this streaming path — see AMK-F-004 (this
  finding had to be inferred from the SSE transcript, not read cleanly from
  logs).
- **"Multi-Stage RAG Latency Profile" staleness**: root CLAUDE.md states
  `navigate_and_hyde 5.4s, generate_answer 12.5s, reflect_on_answer 2.4s`.
  Live `docker logs` captured during this audit (2026-09-18T09:26:39Z,
  `trace_id=09b94a1e...`, `query_tier=tier3_complex`) show:
  `navigate_and_hyde: 32767.8ms` (32.8s — 6x the documented figure),
  `generate_answer: 19818.7ms` (19.8s), `verify_answer: 9006.4ms` +
  `combined_grade_and_verify: 10083.7ms` (19.1s combined). Total for that
  one query: 73.96s. This single data point was captured under heavy
  concurrent load (not a clean baseline) but is directionally consistent
  with this session's independently-documented latency instability. See
  AMK-F-007.
- **RAM/CPU** (`docker stats --no-stream`, single snapshot,
  moderate/idle-ish moment): `mukthiguru-backend` 2.385GiB/6GiB (39.8%);
  `mukthiguru-qdrant` 272MiB/3GiB (8.9%); `mukthiguru-memgraph`
  **645MiB/1GiB (63.0%)**; `mukthiguru-redis` 16.3MiB/512MiB (3.2%). The
  memgraph figure is notably higher than root CLAUDE.md's claim of
  "~60MB-100MB" idle RAM for Memgraph — worth a follow-up re-measurement on
  a quiet box before trusting that figure; this track's snapshot may itself
  reflect the concurrent audit load (memgraph gets queried by
  `KNOWLEDGE_GRAPH_QUERY_ENABLED` per-request expansion). Backend's
  2.385GiB is roughly consistent with root CLAUDE.md's documented "2.57GiB
  steady."
- **Sequential vs. parallel operations**: per root CLAUDE.md (not
  independently re-derived by this track — Track A's territory covers
  `rag/nodes/retrieval.py`/`rag/graph_strategies.py` directly), several
  historical serial bottlenecks are already documented as fixed:
  `navigate_and_hyde` merges `decompose_query`/`navigate_knowledge_tree`/
  `generate_hyde` into one `asyncio.gather` (R22, measured 165.4s→113.0s
  p95); KG expansion runs concurrently with the primary retrieval
  fan-out for the `relational` lane. This track's own live latency capture
  above (`navigate_and_hyde: 32767.8ms`) shows this stage is still, despite
  the R22 parallelization, by far the single largest contributor to total
  latency in a loaded scenario — whether that reflects genuine per-call LLM
  latency (HyDE + decompose + navigate each hitting OpenRouter) rather than
  serialization was not re-derived here; flagged for Track A/owner
  follow-up rather than duplicated as a new finding.
- **Retry-storm claim verification**: "does a single failed verification
  really cost 2x latency" — **CONFIRMED**, both by this track's own live SSE
  capture (above) and by `docs/GURU_DEMO_READINESS.md` §4E.2.4's controlled
  re-measurement. Not disputed.

### Workflow-level summary (Current behavior → Bottleneck → Scaling risk → Cost impact)

| Workflow | Current behavior | Bottleneck | Breaks at 10x/100x concurrent | Cost impact |
| :-- | :-- | :-- | :-- | :-- |
| Standard doctrine query (streamed) | 4.85s TTFT, 17-34s+ total, sometimes doubles to 70-149s p95 on verification retry | `navigate_and_hyde` (32.8s observed loaded) + duplicate-generation retry tax | In-process `job_queue.py` has no depth gauge (AMK-F-006) — no leading indicator before requests start queuing/timing out; `AnonQuotaMemoryAdapter` fallback (Redis-down) is process-local, so quota enforcement diverges across replicas at 10x+ horizontal scale (documented existing risk, backend/CLAUDE.md) | 2 full `deepseek-chat` completions instead of 1 on retry (~2x OpenRouter spend for that query); CHAT_COST=$0.0018/query observed live |
| Distress-routed query | Full pipeline runs (not short-circuited per design — root CLAUDE.md explicitly states distress does NOT bypass RAG) | Same as standard query, plus `handle_distress`'s own free-generation path (per docs/GURU_DEMO_READINESS.md §4E.2.1, this path historically bypassed the quote-unquote guard — now fixed) | Same queue-visibility gap as above; a safety-critical path with the same latency profile as a normal query means a distressed user waits just as long for a response | Same order of magnitude as a standard query |
| Casual greeting | Instant short-circuit, `latency_ms: 3` observed live, no LLM call | None — this path is fast and cheap by design | Scales trivially; no LLM cost | Effectively $0 |
| Telemetry write (fire-and-forget, all workflows) | Runs post-response in a thread-pool executor | Un-coerced integer columns (`start_ms`/`duration_ms`/`top_k`) cause live insert failures (AMK-F-002); rate-limited logging hides most of them | At higher request volume, MORE rows hit the un-fixed float→int columns, silently degrading the `hallucination_anomaly.py` safety net exactly when volume (and risk) is highest | Small direct cost (executor thread + failed Supabase call), but the indirect cost is a blind safety monitor |

---

## Phase 18 — Testing Completeness

**Status: PASS (backend), PASS (frontend unit), PARTIAL (frontend
typecheck/lint), PARTIAL (E2E)** — real numbers below, not vibes.

### Backend: `.venv/bin/pytest -q` (run to completion this session)

```
7266 passed, 12 skipped, 3 warnings in 379.41s (0:06:19)
```

0 failed. This matches the same-day figure already recorded in
`ASKMUKTHIGURU_AUDIT_PROGRESS.md` from an earlier run today (7266
passed / 0 failed / 12 skipped) — independently re-confirmed by this track,
not just trusted. 453 test files under `backend/tests/`.

3 warnings, all the same class: `RuntimeWarning: coroutine
'AsyncMockMixin._execute_mock_call' was never awaited`, in
`tests/test_cove_enable.py::test_cove_disabled_via_settings` and two tests
in `tests/test_nli_claim_verification.py`. This means an `AsyncMock` is
being called but not awaited in those three tests — the mock call may not
be asserting what the test author intended (the assertion could pass even
if the mocked code path is never actually exercised the way the test
believes). Low-severity test-hygiene issue, not a production defect — see
AMK-F-013.

### Frontend unit tests: `npm test -- --run` (Vitest, run to completion this session — confirmed NOT run earlier in this session per the task brief, genuinely executed here)

```
Test Files  98 passed | 1 skipped (99)
     Tests  555 passed | 6 skipped (561)
```

0 failed. Coverage summary: Statements 54.54%, Branches 44.45%, Functions
44.76%, Lines 57.11% — moderate, uneven (e.g. `src/lib/memoryApi.ts` at
4.28% statement coverage, `src/hooks/useNotes.ts` at 0%). Console noise
during the run (`Error: Uncaught [Error: overview chunk failed to load]`)
is consistent with an intentional test of `src/lib/lazyWithRetry.ts`'s
retry-on-chunk-failure behavior, not a real failure (0 tests failed).

### Frontend typecheck: `npm run typecheck` (`tsc -b --pretty false`)

**14 real TypeScript errors**, across exactly 2 files:
- `src/admin/lib/mockData.ts` — 12 errors, all `{}`/`unknown`-typed values
  (TS2339/TS18046/TS2345/TS2365/TS2769) consistent with an under-typed
  mock/demo-data generator for the admin dashboard.
- `src/components/chat/ChatMessage.tsx:439` — `TS2339: Property
  'getAccessToken' does not exist on type ... "src/lib/chat/transport"` —
  a genuine API-drift bug, not a typing nicety: the component calls a
  function that does not exist on the actual `transport.ts` module. See
  AMK-F-010.

### Frontend lint: `npm run lint` (ESLint)

**10 errors, 40 warnings, in 33 files.** Top rule violations:
`react-refresh/only-export-components` (34x, cosmetic/dev-only, Fast
Refresh hygiene), `no-empty` (9x — empty blocks, files include
`src/components/chat/ChatInterface.tsx`, `src/components/common/
SessionExpiredHandler.tsx`, `src/lib/meditationStorage.ts`,
`src/pages/AuthPage.tsx`), `react-hooks/exhaustive-deps` (6x, potential
stale-closure bugs, e.g. 4 in `src/admin/pages/RoutingPage.tsx`),
`prefer-const` (1x). See AMK-F-011.

### E2E (Playwright): partial run, real results

Full 16-spec suite was **not** run to completion (time/cost-boxed this
session — each spec that hits live chat can take 30-90s+ per test under the
concurrent load on this box). Two specs run to completion:

- `tests/e2e/page-smoke.spec.ts --project=chromium`: **14 passed, 0
  failed** (25.3s).
- `tests/e2e/seeker-journey.spec.ts --project=chromium`: **0 passed, 2
  failed** (40.3s) — "landing page to anonymous chat flow" hit Playwright's
  30000ms hard test timeout; "complete chat session with STT..." failed a
  `not.toBeVisible()` assertion on the `receive-wisdom-button` after a 5000ms
  wait. Both failures are consistent with box-wide contention from this
  audit's own concurrent load (6 tracks issuing real OpenRouter calls
  simultaneously) rather than a confirmed frontend/backend defect — **not
  re-verified on a quiet box due to time constraints**. See AMK-F-012
  (marked UNKNOWN root cause pending a quiet re-run).
- The other 14 specs (`full-regression`, `rls-cross-user`,
  `google-auth-flow`, `admin-journey`, `chat-scrolling-and-tts`,
  `security-aal2`, `admin-drilldown`, `progressive-anonymous`,
  `i18n-coverage`, `a11y-smoke`, `prelaunch-sweep`,
  `ui-regression-screenshots`, `landing-accessibility`, `session-auth`)
  were **not run this session** — genuinely UNKNOWN pass/fail, do not
  assume they pass.

### Skip/xfail inventory

- `@pytest.mark.skip`/`pytest.skip(...)`: 49 occurrences across the backend
  suite. Spot-checked a representative sample — the overwhelming majority
  are environment-conditional (`pytest.skip(f"Neo4j not reachable: {exc}")`,
  `"Embedding model unavailable"`, `"Reranker not available"`,
  `"TurboQuantization not supported by installed qdrant-client"`), not
  permanently-disabled tests. A smaller number are content-state-conditional
  (`"OKF bundle intentionally empty — cleared for rebuild from green
  corpus"`, `"compiled.json absent"`) — **potentially stale**: git log shows
  a same-session commit `3339b670 data(okf): sync doctrine bundle — 715
  live entries, staging review gate intact`, which post-dates the skip
  message's premise. Not independently re-verified whether these specific
  tests now execute for real (i.e., whether `compiled.json`/`memory/okf/`
  is populated in the test environment) — flagged as UNKNOWN, worth a
  follow-up: if these OKF tests are still silently skipping despite the
  bundle now having 715 entries, that's a coverage gap on exactly the
  doctrine-integrity invariants this repo cares most about.
- `xfail`: 0 occurrences (`grep -rn xfail tests/` → 0 hits).
- `skipif`: 13 occurrences (not individually inspected beyond the sample
  above).
- Frontend: 1 skipped test file, 6 skipped tests (Vitest) — not
  individually inspected for staleness (time-boxed).

### Mocked vs. real-service testing

Not exhaustively quantified (would require per-file inspection of 453
backend test files), but qualitatively: `backend/tests/conftest.py`
contains explicit `pytest.skip(...)` fallbacks for real-service
unavailability (Supabase client init failure, line ~268), indicating a
deliberate pattern of "try real service, skip if unavailable" rather than
universal mocking for integration-shaped tests (`test_chat_endpoint.py`,
`test_qdrant_search_quality.py`, `test_neo4j_gds.py`,
`test_lightrag_concurrency.py`). Pure logic/contract tests
(`test_token_budget_guard.py`, `test_abstractions.py`) are presumably
fully mocked/unit-level by design — not individually verified.

### Dedicated security / isolation / concurrency / memory-leak tests

- **Security**: `tests/test_security_redteam.py` (10.0K), `tests/security/`
  directory, `tests/test_ingestion_security.py` (13.4K),
  `tests/test_ingest_upload_security.py` (8.6K), `tests/test_ocr_ssrf.py`
  (5.4K, SSRF guard).
- **Isolation** (cross-tenant/cross-user leak probes — directly relevant to
  what Track D audits): `tests/test_cross_tenant_leak_probe.py` (12.1K, "36
  cross-user probes, 0 failures" per root CLAUDE.md — re-confirmed passing
  in this session's full pytest run since it's part of the 7266), `tests/
  test_cache_tenant_isolation.py` (6.4K), `tests/
  test_cache_personalization_leak.py` (3.4K, guards the exact `(language,
  message)`-keyed cache-personalization-leak invariant documented in root
  CLAUDE.md), `tests/test_incognito_isolation.py` (1.5K).
- **Concurrency** (directly relevant to what Track C audits):
  `tests/test_adaptive_concurrency_throttle.py`,
  `tests/test_bulk_ingest_lock_release.py`,
  `tests/test_concurrent_retriever.py`, `tests/test_lightrag_concurrency.py`,
  `tests/test_youtube_loader_concurrent.py`, `tests/
  test_healthz_grace_masking.py`. These exist and pass (part of the 7266) —
  so the concurrency behavior Track C investigated was NOT genuinely
  untested before this audit at the unit level, though that says nothing
  about whether it holds under the kind of real multi-track concurrent load
  this session incidentally generated (see AMK-F-012).
- **Memory/leak tests**: no dedicated memory-profiling/leak test found
  under this name pattern in `backend/tests/` (the two "leak" hits are
  data-isolation leaks, not memory leaks — see Isolation above). Track C's
  territory (Phase 7, GC/Resource Leaks) is better positioned to say
  whether a leak-specific harness exists elsewhere (e.g. a script under
  `scripts/`) — not found under `backend/tests/`.

### Workflow coverage table (Phase 18 deliverable)

| Critical Workflow | Unit | Integration | E2E | Failure Test | Security Test | Load/Memory Test |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Chat/RAG answer generation | Yes — `test_nodes.py`, `test_rag_advanced.py`, many `rag/nodes/*` node-level tests | Yes — `test_chat_endpoint.py`, `test_retrieve_documents_contract.py`, `test_tiered_router.py` | Partial — `page-smoke.spec.ts` 14/14 PASS; `seeker-journey.spec.ts` 0/2 this run (load-contended, root cause UNKNOWN, not re-verified quiet) | Yes — `test_token_budget_guard.py`, timeout-path tests, `test_llm_system_design_invariants.py` | Partial — `test_security_redteam.py`, `test_srs_injection_blocked.py`; no test found specifically asserting a prompt-injection-via-retrieved-doctrine-chunk is neutralized | `scripts/load_test.py` exists (not run this session); no dedicated RAG-path memory-leak test found |
| Memory write/read (canonical memory) | Extensive — 16 dedicated `test_canonical_memory_*.py` files, ~2,700 lines total | Yes — `test_memory_context.py`, `test_memory_api.py`, `test_memory_outbox_worker.py` | Not found — no e2e spec dedicated to memory read/write | Yes — `test_canonical_memory_consent_gate.py`, `test_memory_safety.py` | Yes — `test_cross_tenant_leak_probe.py`, `test_cache_tenant_isolation.py`, `test_incognito_isolation.py`, `test_memory_pii_scrub.py` | No dedicated leak/perf test found |
| Auth (anonymous session + Supabase) | Yes — `test_auth_email_allowlist.py`, `test_authz_regression.py` (14.2K) | Yes — `test_test_auth_strategy.py` (13.9K), `test_testauth_not_registered_in_prod.py` | Yes (specs exist: `session-auth.spec.ts`, `google-auth-flow.spec.ts`, `security-aal2.spec.ts`) — **not run this session, pass/fail UNKNOWN** | Yes — `test_edge_cases.py::test_jwt_expiration` (confirmed present, line 334) | Yes — `test_verify_rls_policies.py`, nightly CI `.github/workflows/nightly-rls.yml` | Not found |
| File upload (chat attachments / ingestion) | Yes — `test_chat_uploads.py`, `test_attachment_retrieval_guards.py`, `test_support_attachment_freeze.py` | Yes — `test_ingest_upload_security.py` (8.6K) | Not found — no e2e spec dedicated to upload | Partial — `test_ocr_ssrf.py` covers the SSRF failure mode specifically | Yes — `test_ocr_ssrf.py`, `test_ingest_upload_security.py` | Not found |
| Distress detection / Serene Mind (safety-critical) | Yes — `test_serene_mind.py` (8.4K) | Yes — pipeline-stage-level coverage implied by the 7266-pass full suite (distress stage is in the default pipeline chain) | Not found — no e2e spec dedicated to distress/Serene Mind flow | Yes — bounded-fallback behavior covered per `docs/GURU_DEMO_READINESS.md` §4E.2.1 (`handle_distress` quote-guard regression test `test_distress_quote_guard.py`) | `test_srs_injection_blocked.py` (name suggests Serene-mind/safety-redirect injection guard — not opened in full) | Not found |

---

## Findings

### AMK-F-001 — Distributed tracing is configured but provably non-functional in the default deployment
**Severity:** MEDIUM
**Launch Blocker:** NO
**Evidence:** `backend/app/observability.py:65` defaults
`OTEL_EXPORTER_OTLP_ENDPOINT` to `http://jaeger:4317`; `OTEL_ENABLED`
(`observability.py:21-27`) defaults to `true` and is unset in
`backend/.env` (`grep -i OTEL backend/.env` → no output), so the default
applies. `docker-compose.yml:133-136` gates the `jaeger` service behind
`profiles: [observability]`. `docker ps -a` at audit time shows **zero**
jaeger container, running or stopped — it has never been started on this
box this session. `init_observability()` (`observability.py:31-87`)
catches only `ImportError` and a broad `except Exception` around the whole
setup, both of which succeed here (the packages ARE installed, and
`FastAPIInstrumentor.instrument_app`/`LangChainInstrumentor().instrument()`
both complete without raising) — so `_INITIALIZED = True` and the code logs
`"OpenTelemetry tracing initialized: ..."` as an **INFO**, not a warning,
even though the configured export target does not exist.
**Root Cause:** The `jaeger` service and `OTEL_ENABLED` are not
co-configured — tracing is silently a no-op (spans generated, buffered,
export attempted, dropped) whenever the `observability` compose profile
isn't active, and nothing surfaces that condition at more than debug/info
log severity.
**User Impact:** None directly. Operationally: anyone relying on
distributed tracing for latency root-causing (e.g., to see whether
`navigate_and_hyde`'s live-observed 32.8s is one slow OpenRouter call or
three sequential ones) has zero trace data and must fall back entirely to
the custom `node_timings` log line, which is itself missing on the
streaming path (AMK-F-004).
**Required Fix:** Either add `jaeger` (or a lightweight OTLP collector) to
the default compose profile for any environment that documents tracing as
available, or set `OTEL_ENABLED=false` in the default `.env` and document
tracing as an explicit opt-in via `COMPOSE_PROFILES=observability`, with a
startup-time WARNING (not INFO) if `OTEL_ENABLED=true` but the exporter
endpoint is unreachable.
**Regression Test:** A startup check (or a Docker healthcheck-style probe)
that fails loudly if `OTEL_ENABLED=true` and a TCP connect to the exporter
endpoint fails, rather than silently logging INFO and continuing.
**Verification:** `docker compose --profile observability up -d`, run a
chat query, confirm the trace appears in the Jaeger UI at
`http://localhost:16686`.

### AMK-F-002 — Telemetry sink write failures are correlation-blind, under-logged, and still hitting an unguarded integer column live
**Severity:** MEDIUM-HIGH
**Launch Blocker:** NO (no direct user impact — but it silently defeats an
existing safety monitor)
**Evidence:** Live-observed during this audit, unprompted (not synthetically
triggered): `{"timestamp": "2026-09-18T09:25:02+0000", "level": "ERROR",
"logger": "app.telemetry_sink", "message": "Telemetry Sink insert failed (1
consecutive): {'message': 'invalid input syntax for type integer:
\"192.76\"', 'code': '22P02', ...} — downstream hallucination alerting
reads these rows and will read empty while this persists"}` — this log line
carries **no** `correlation_id`, `query_id`, `session_id`, or table name.
`backend/app/telemetry_sink.py:141-160` (`_coerce_int`) was added
specifically after a near-identical 2026-09-17 incident (the function's own
docstring cites `invalid input syntax for type integer: "108.43"` killing a
`chat_responses` insert) and is applied to exactly 4 fields:
`latency_ms`, `ttft_ms`, `prompt_tokens`, `completion_tokens`
(`telemetry_sink.py:185,204,206-207,341,357,359-360`). It is **not** applied
to `start_ms`/`duration_ms` in the `trace_spans` payload
(`telemetry_sink.py:436-437`) or `top_k` in the `retrieval_events` payload
(`telemetry_sink.py:422`) — all three are float-shaped in practice (this
session's own `CHAT_STAGE_TIMING` node_timings log values, e.g.
`navigate_and_hyde: 32767.8`, `verify_answer: 9006.4`, are exactly the shape
of value that would hit these unguarded columns). Separately,
`telemetry_sink.py:573-582` only logs this error at consecutive-failure
counts 1, 10, 100, then every 500, and `_consecutive_write_failures` resets
to 0 on the next successful write (`telemetry_sink.py:566`) — so an
intermittent failure pattern (fail → succeed → fail → succeed) is logged
**once** and then never again, regardless of how many times it recurs.
Root cause of the missing `correlation_id`: the whole batch insert
(`do_inserts()`) runs via `loop.run_in_executor(None, do_inserts)`
(`telemetry_sink.py:585-586`) — Python's `contextvars` (which carry
`correlation_id_var`, the source of every other log line's `correlation_id`
field per `JSONFormatter`) are not propagated into `run_in_executor`
callables the way they are into `asyncio.create_task`.
**Root Cause:** (1) the 2026-09-17 fix patched 4 of N integer-typed columns
in this file, not all of them; (2) rate-limited error logging silently
hides all but the 1st/10th/100th/500th-multiple occurrence of an
intermittent (non-consecutive) failure; (3) `run_in_executor` does not
propagate `contextvars`, so this file's logs are structurally unable to
carry the request correlation id the rest of the app relies on.
**User Impact:** None in the moment — this write happens after the chat
response has already been returned to the user (fire-and-forget). The real
impact is downstream: `scripts/ops/hallucination_anomaly.py` (named
directly in the sink's own error message) reads the `chat_responses` table
for its daily anomaly-rate gate; a silently-dropped row reads as "no
hallucinations" rather than "no data" — the exact blind spot root
CLAUDE.md's Gotchas section already documents for a different table
(`SUPABASE_URL` misconfiguration), now independently confirmed to also
apply here via a different mechanism.
**Required Fix:** Route `start_ms`/`duration_ms`/`top_k` (and any other
integer-column value in this file) through `_coerce_int` or equivalent;
include `query_id` and the target table name in the rate-limited error log
so a failure is at least attributable to a request after the fact; either
copy `correlation_id_var`'s current value into a plain argument passed to
`do_inserts()` for logging, or propagate the context explicitly
(`ctx = contextvars.copy_context(); loop.run_in_executor(None, ctx.run,
do_inserts)`).
**Regression Test:** A unit test asserting a float-valued span duration
(e.g. `192.76`) round-trips into a `trace_spans` insert payload without
raising; a unit test asserting the failure-path log line for a synthetic
insert failure carries the same `query_id` given to `log_query_trace_direct`.
**Verification:** Re-run a live chat query, `docker logs mukthiguru-backend
| grep "Telemetry Sink insert failed"` and confirm it does not recur; when
it does (for an unrelated cause), confirm the log line now carries a
query_id/table name.

### AMK-F-003 — No server-side error-tracking/alerting integration
**Severity:** MEDIUM
**Launch Blocker:** NO
**Evidence:** `grep -rln "sentry" backend/app/ backend/services/` → zero
hits (frontend has `src/lib/sentry.ts`, backend has nothing analogous).
`backend/app/main.py:1158-1172` (`global_exception_handler`) logs
`exc_info=True` with a generated `error_id` (`err_<epoch>_<8hex>`) and
returns that id in the response body — its only sink is stdout.
**Root Cause:** No error-tracking SDK is wired into the backend's global
exception handler or FastAPI middleware.
**User Impact:** None in the moment. Time-to-detect and time-to-diagnose a
production 500 depend entirely on an operator actively tailing logs at the
time it happens, or later grep-ing raw logs for the `error_id` a user
reports back — no automatic alert, dedupe, trend view, or paging.
**Required Fix:** Wire an error-tracking SDK (e.g. `sentry-sdk`, or a
self-hosted OSS-license-compatible alternative such as GlitchTip, given the
repo's Apache-2.0/MIT/Meta-Community dependency constraint) into
`global_exception_handler` and FastAPI middleware, tagged with
`correlation_id`/`error_id`.
**Regression Test:** A test triggering `global_exception_handler` directly
and asserting the tracking SDK's capture function was invoked once with a
matching `error_id`.
**Verification:** Trigger a real 500 in a test/staging environment, confirm
an event appears in the error-tracking dashboard within seconds.

### AMK-F-004 — Streaming (SSE job-queue) chat path emits no per-node latency breakdown, masking a live-observed apparent duplicate generation
**Severity:** MEDIUM
**Launch Blocker:** NO
**Evidence:** Live test this session: `POST /api/chat/stream` for
`"What is the Beautiful State according to the teachings?"`
(`job_b4c96444582e`). `docker logs` for this job show only one coarse
`PIPELINE_STAGE_TIMING ... stage=langgraph status=success
duration_ms=27146.16` line — the synchronous path's `CHAT_STAGE_TIMING ...
node_timings={...}` line (present and populated for other, concurrent,
sync-path requests in the exact same log window, e.g. trace_id
`f0a1092f...` and `12b99c93...`) never appears for this job. The raw SSE
transcript captured client-side, however, shows two distinct passes of
near-identical answer text — see AMK-F-008 for the full evidence — that
could only be confirmed as two separate generations (rather than one
generation re-rendered) by comparing the cited video URL at the end of
each pass, because the node-level log line that would have shown
`generate_answer` (or an equivalent) executing twice, with a timestamp and
duration for each, is simply not emitted on this path.
**Root Cause:** The `CHAT_STAGE_TIMING`/`node_timings` instrumentation
lives in the synchronous orchestrator (`app/orchestrator.py`); the
job-queue/streaming execution path (`app/services/job_queue.py` +
`app/chat_engine.py`) does not appear to emit the equivalent per-node
breakdown, only a single aggregate `stage=langgraph` duration.
**User Impact:** None directly to the user (one final answer is still
delivered). This is an observability blind spot on exactly the workflow
(streaming chat) most real users hit, for exactly the cost/latency question
this audit was asked to verify — it had to be inferred indirectly from
citation differences in the SSE transcript rather than read cleanly from a
log line.
**Required Fix:** Emit the same `node_timings`-style breakdown from the
job-queue/streaming execution path that the synchronous path already
produces.
**Regression Test:** Assert a streamed chat request's logs contain a
node-level timing line enumerating each LangGraph node actually executed,
matching the synchronous path's format.
**Verification:** Re-run a streamed query that is known to trigger
`grounded_partial_fallback`, confirm the node-level log line shows
`generate_answer` (or equivalent) with two distinct duration entries/two
separate invocations.

### AMK-F-005 — Three declared Prometheus metrics are dead code
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** `RETRIEVAL_LATENCY` (`app/metrics.py:158`), `LLM_LATENCY`
(`:193`), and `TPOT_SECONDS` (`:36`) each have zero `.observe()`/`.inc()`
call sites anywhere outside `app/metrics.py`
(`grep -rn "RETRIEVAL_LATENCY\.\|LLM_LATENCY\.\|TPOT_SECONDS\." backend/app
backend/rag backend/services` → no hits). By contrast,
`RETRIEVAL_RELEVANCE_RATIO`, `LLM_TOKENS`, `PIPELINE_STAGE_LATENCY`, and
`TTFT_SECONDS` are genuinely wired and observed at real call sites.
**Root Cause:** Partial instrumentation — these three histograms were
declared but never connected to an actual measurement call site, even
though the underlying duration data is already computed elsewhere for log
lines (e.g. `rag.nodes.utils`'s `PIPELINE_STAGE_LATENCY` call site already
has the retrieval/LLM durations available).
**User Impact:** None directly. An operator building a dashboard against
`retrieval_latency_seconds` or `llm_latency_seconds` would see an empty
series and could wrongly conclude retrieval/LLM calls are instant or the
metrics pipeline itself is broken.
**Required Fix:** Either wire `.observe()` calls at the retrieval and LLM
call sites (the duration data already exists at those log-line sites), or
remove the dead declarations so `/metrics` doesn't advertise data that
never arrives.
**Regression Test:** A static test asserting every `Histogram`/`Counter`/
`Gauge` declared in `app/metrics.py` has at least one call-site match
outside that file (grep-based, matching the pattern the repo already uses
for "dead settings" per root CLAUDE.md).
**Verification:** Hit `/api/metrics` after a live chat query, confirm
`retrieval_latency_seconds_count` and `llm_latency_seconds_count` are
non-zero.

### AMK-F-006 — No queue-depth/Celery metrics
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** `grep -n "Counter|Gauge|Histogram" backend/celery_config.py
backend/tasks/*.py` → zero hits; no `task_prerun`/`task_postrun`/
`task_failure` Celery signal handlers found. The default (non-Celery)
in-process `app/services/job_queue.py` path — confirmed live this session
(`JobQueue: enqueued job_b4c96444582e`, `JobQueue worker 2: completed
job_b4c96444582e`) — has no queue-depth or worker-utilization gauge in
`app/metrics.py` either.
**Root Cause:** Metrics instrumentation was added per-node/per-LLM-call but
never for the queueing layer itself, on either the default job-queue path
or the profile-gated Celery path.
**User Impact:** None directly. An operator cannot see queue backlog
building under the 10x/100x-concurrent-user scaling scenario this track was
asked to consider — there is no leading indicator before requests start
timing out.
**Required Fix:** Add a `Gauge` for in-process job-queue depth / active
worker count in `app/services/job_queue.py`; wire Celery signal handlers to
Prometheus counters if/when Celery is ever promoted out of the `ingestion`
profile.
**Regression Test:** Enqueue N jobs, assert a queue-depth gauge reads N
before they drain.
**Verification:** `/api/metrics` exposes a `job_queue_depth`-style series
that visibly moves under concurrent load.

### AMK-F-007 — Root CLAUDE.md's "Multi-Stage RAG Latency Profile" is stale (navigate_and_hyde now 6x its documented figure in a live sample)
**Severity:** MEDIUM (documentation-accuracy finding; the underlying
instability it obscures is already tracked as a blocker in
`docs/GURU_DEMO_READINESS.md` §4E)
**Launch Blocker:** NO
**Evidence:** Root `CLAUDE.md`'s "Multi-Stage RAG Latency Profile
(L-LATENCY-1)" states `navigate_and_hyde 5.4s, generate_answer 12.5s,
reflect_on_answer 2.4s`. Live `docker logs` captured this session
(2026-09-18T09:26:39Z, `trace_id=09b94a1e...`, `query_tier=tier3_complex`)
show `navigate_and_hyde: 32767.8ms` (32.8s), `generate_answer: 19818.7ms`
(19.8s), and (a differently-named but adjacent verification stage)
`verify_answer: 9006.4ms` + `combined_grade_and_verify: 10083.7ms`
(19.1s combined). Total for that one query: 73.96s.
**Root Cause:** Not investigated in depth by this track (RAG-internals
root-causing is Track A's assigned territory); this single data point was
captured under heavy concurrent load from 5 other simultaneous audit
tracks, so should not be read as a clean single-user baseline — but it is
directionally consistent with this session's independently-documented
p95 instability (§4E.2.4: 70.67s / 148.78s / 106.9s across three separate
runs today).
**User Impact:** None directly. Anyone using the documented profile to
prioritize a latency-optimization effort would target the wrong stage
(the documented `generate_answer`'s 12.5s vs. the observed
`navigate_and_hyde`'s 32.8s).
**Required Fix:** Re-measure the per-node latency profile on a quiet box
(same discipline already used for the §4E benchmark runs — zero concurrent
traffic, verified `RestartCount=0`) and update root CLAUDE.md's L-LATENCY-1
section, or explicitly date-stamp it as historical/superseded.
**Regression Test:** N/A (documentation).
**Verification:** Re-run with confirmed zero concurrent traffic, capture
`node_timings`, compare to the committed figures, update the doc.

### AMK-F-008 — Verification-retry pays a full duplicate-generation tax, live-confirmed via distinct citations in a captured SSE transcript
**Severity:** HIGH
**Launch Blocker:** Contributes materially to an already-tracked blocker
(latency_p95 failing 2 of the last 3 measured runs per §4E) rather than
being a new standalone blocker; directly answers this track's assigned
question ("does a single failed verification really cost 2x latency?") —
**YES, confirmed**.
**Evidence:** This session's own live SSE capture
(`POST /api/chat/stream`, `job_b4c96444582e`, `"What is the Beautiful
State according to the teachings?"`) streamed two distinct, non-simulated
full-answer passes back-to-back: pass 1 (+4.85s to +17.7s from request
submission) ends citing `youtube.com/watch?v=x-mTRlE0TC4`; a `status:
Finalizing your response...` / `stage: format_final_answer` SSE event fires
at +17.8-18.0s; pass 2 (+18.0s to +33.9s) restarts from "The Beautiful
State is a profound..." and ends citing a **different** video,
`Gt3o8lcbcII`. Two different cited source videos for what reads as the
same answer is strong evidence of two independent LLM completions, not a
client-rendering artifact — the code's only known "re-emit text" path
(`stream_orchestrator.py:360-366`, the cache-hit "simulate streaming"
fallback) chunks in fixed 20-char/10ms steps, and the observed second-pass
timing was irregular (consistent with real token-by-token generation, not
that fallback). Independently corroborated by
`docs/GURU_DEMO_READINESS.md` §4E.2.4's controlled finding that a single
`grounded_partial_fallback` hit alone moved measured p95 latency from
70.67s to 148.78s.
**Root Cause:** Per root CLAUDE.md's documented graph flow,
`generate_answer` → `reflect_on_answer`/`verify_answer` → on failure,
regeneration via the rewrite/retry loop — the retry appears to re-run
generation in full (not a targeted patch of only the unsupported spans),
and (per this session's evidence) each pass is independently streamed to
the client rather than only the final validated pass.
**User Impact:** On the fraction of queries where the first draft fails
verification — not rare, given this session hit it on a plain factual
question about a core doctrine term — the user waits roughly 2x as long,
and the backend pays for 2 full LLM completions instead of 1, directly
inflating both the already-failing p95 latency gate and per-query
OpenRouter cost.
**Required Fix:** Per `docs/GURU_DEMO_READINESS.md`'s own stated position,
this is a deliberate safety trade-off, not a bug to silently patch away
("the retry-on-reject gate is not being weakened to buy a stabler number")
— the fix direction should be reducing the FREQUENCY of first-draft
verification failures (better grounding on the first generation pass)
rather than removing the retry. Separately, wire the node-level timing
visibility from AMK-F-004 so this is directly countable from logs rather
than inferred from citation differences.
**Regression Test:** Not found in this track's scope — recommend a test
asserting `generate_answer` (or its LLM-call counter) executes exactly once
per request unless `grounded_partial_fallback`/verification-retry
explicitly fires, with an assertion on the counter for both branches.
**Verification:** Once AMK-F-004 lands, instrument generation-call-count
per request; confirm p95 latency improves as first-draft-failure rate
drops, without the retry safety net being removed.

### AMK-F-009 — Memgraph RAM usage (645MB/1GB, 63%) exceeds root CLAUDE.md's documented idle figure by 6-10x
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** `docker stats --no-stream mukthiguru-memgraph` →
`645MiB / 1GiB` (62.99%). Root CLAUDE.md's Memgraph migration section
claims idle RAM of "~60MB-100MB (capped at 512MB in Docker Compose)" —
both the cap (actual: 1GiB per this stats output) and the usage figure
disagree with the current running container.
**Root Cause:** Not investigated — plausibly reflects genuine per-request
graph query load accumulated during this session's heavy concurrent audit
traffic (6 tracks running simultaneously, several issuing
`KNOWLEDGE_GRAPH_QUERY_ENABLED`-gated per-query expansion), rather than a
true "idle" baseline; not re-measured on a quiet box.
**User Impact:** None directly; a documentation-accuracy issue similar in
kind to AMK-F-007.
**Required Fix:** Re-measure Memgraph RAM on a quiet box immediately after
container start (true idle) and again after a sustained load test; update
root CLAUDE.md if idle RAM is genuinely higher than documented, or note
that the 512MB figure is outdated relative to the current 1GiB compose
limit.
**Regression Test:** N/A (documentation/ops).
**Verification:** `docker stats --no-stream mukthiguru-memgraph`
immediately after `docker compose up -d memgraph` with zero traffic.

### AMK-F-010 — Frontend `tsc -b` fails with 14 real TypeScript errors, including one genuine API-drift bug
**Severity:** MEDIUM
**Launch Blocker:** UNKNOWN — depends on whether `npm run build` type-checks
as part of the Vite build (not verified this session) and whether CI gates
merges on `npm run typecheck`; if either is true, this is currently broken.
**Evidence:** `npm run typecheck` (`tsc -b --pretty false`) → 14
`error TS...` lines, across exactly 2 files. `src/admin/lib/mockData.ts` —
12 errors, all stemming from `{}`/`unknown`-typed values (TS2339, TS18046,
TS2345, TS2365, TS2769), consistent with a loosely-typed admin-dashboard
mock/demo-data generator. `src/components/chat/ChatMessage.tsx:439` —
`TS2339: Property 'getAccessToken' does not exist on type ...
"src/lib/chat/transport"` — the component calls a function that the actual
`transport.ts` module does not currently export.
**Root Cause:** `mockData.ts` — under-typed parsed/generated mock data
(low risk, dev-tooling only). `ChatMessage.tsx:439` — genuine API drift:
either `transport.ts`'s auth-token accessor was renamed/removed without
updating this call site, or this is genuinely dead/unreachable code that
was never exercised by any test (none of the 555 passing Vitest tests or
the E2E specs that were run caught it, though most E2E specs were not run
this session).
**User Impact:** `mockData.ts` — none (admin dev-only). `ChatMessage.tsx`
— if this line is reachable at runtime, it would throw `TypeError:
transport.getAccessToken is not a function` for real users hitting
whatever feature branch guards it; this track did not trace reachability.
**Required Fix:** Fix or properly type `mockData.ts`'s parsed shapes; fix
the stale `getAccessToken` reference in `ChatMessage.tsx:439` (confirm
`transport.ts`'s actual current export name and either rename the call site
or restore the export).
**Regression Test:** `npm run typecheck` gating CI (verify whether already
wired; if not, add it).
**Verification:** `npm run typecheck` exits 0.

### AMK-F-011 — ESLint: 10 errors, 40 warnings; 9 empty-block (`no-empty`) violations including auth-adjacent files
**Severity:** LOW-MEDIUM
**Launch Blocker:** NO
**Evidence:** `npm run lint` → "ESLint: 10 errors, 40 warnings in 33
files." `no-empty` fires 9 times, including in
`src/components/common/SessionExpiredHandler.tsx` (2x) and
`src/pages/AuthPage.tsx` (2x) — both auth-adjacent. `react-hooks/
exhaustive-deps` fires 6 times (potential stale-closure bugs), 4 of them
in `src/admin/pages/RoutingPage.tsx`.
**Root Cause:** `no-empty` typically flags an empty `catch {}` block — the
exact "swallow errors silently" pattern the user's own global CLAUDE.md
explicitly prohibits ("Raise errors explicitly — never swallow them or add
fallbacks I didn't ask for"). Not individually opened/read in this track
(time-boxed) to confirm each is a swallowed-error case vs. an intentionally
empty branch.
**User Impact:** Unknown without per-site review — an empty catch in
`SessionExpiredHandler.tsx` or `AuthPage.tsx` could silently mask a real
auth-flow failure (e.g., a failed token refresh treated as a no-op success).
**Required Fix:** Review and resolve the 9 `no-empty` sites individually —
either handle/log the caught condition or add an explicit
`// intentionally empty: <reason>` comment; review the 6
`exhaustive-deps` warnings case-by-case.
**Regression Test:** `npm run lint -- --max-warnings 0` in CI once cleared
(verify whether already gated).
**Verification:** `npm run lint` exits with 0 errors; the two auth files
specifically reviewed and each empty block justified or fixed.

### AMK-F-012 — E2E chat-flow test times out under this session's concurrent load; root cause UNCONFIRMED (quiet-box re-run needed)
**Severity:** LOW as measured; potentially HIGH if it reproduces quiet —
**UNKNOWN**
**Launch Blocker:** UNKNOWN
**Evidence:** `npx playwright test tests/e2e/seeker-journey.spec.ts
--project=chromium` → 0 passed, 2 failed. "landing page to anonymous chat
flow" hit Playwright's fixed 30000ms test timeout. "complete chat session
with STT, automatic language detection, and native TTS fallback" failed a
`not.toBeVisible()` assertion on `receive-wisdom-button` after a 5000ms
wait (`tests/e2e/seeker-journey.spec.ts:589`). Both runs executed while 5
other audit tracks were simultaneously issuing real OpenRouter-backed chat
requests against the same backend container (confirmed via concurrent
`docker logs` entries with distinct `correlation_id`/`trace_id` values at
matching wall-clock timestamps). `tests/e2e/page-smoke.spec.ts` (14 tests,
no live-chat calls) passed 14/14 in the same contended environment,
suggesting the failure is chat-latency-specific rather than a broad
harness/environment problem.
**Root Cause:** UNKNOWN — not re-tested on a quiet box due to time
constraints. Plausible: the documented p95 latency instability (§4E.2.4,
up to 148.78s for a 12-question batch, and this track's own 34.5s
single-query TTFT-to-done observation) can straightforwardly exceed a
fixed 30s Playwright test timeout or a fixed 5s UI-transition assertion
under load.
**User Impact:** UNKNOWN until re-verified quiet. If it reproduces without
contention, it means real users can hit client-side/UX timeouts tuned
against an assumed latency budget the backend does not reliably meet.
**Required Fix:** Re-run `tests/e2e/seeker-journey.spec.ts` on an otherwise
idle box (zero other traffic, matching the discipline `docs/
GURU_DEMO_READINESS.md` §4E already uses) before drawing any conclusion.
If it still fails, either lengthen the test's timeout budget to match
measured p95, or the backend latency instability (already tracked as a
blocker) needs to come down.
**Regression Test:** This test IS the regression test — make its
pass/fail record reliable by controlling for concurrent load in CI.
**Verification:** Re-run on a quiet box, record pass/fail; if it passes
quiet, downgrade this finding to "load-sensitivity note," not a defect.

### AMK-F-013 — Three backend tests have an un-awaited AsyncMock coroutine (test may not exercise what it asserts)
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** Full `pytest` run (7266 passed, 12 skipped, 0 failed) emitted
3 warnings, all `RuntimeWarning: coroutine
'AsyncMockMixin._execute_mock_call' was never awaited`, attributed to
`tests/test_cove_enable.py::test_cove_disabled_via_settings`,
`tests/test_nli_claim_verification.py::test_unsupported_claims_fail_
verification`, and `tests/test_nli_claim_verification.py::
test_low_faithfulness_fails_even_if_no_explicit_unsupported_sentences`.
**Root Cause:** An `AsyncMock`-backed call in each of these three tests is
invoked without `await`, meaning the coroutine object is created but never
actually runs — the assertion that follows may be checking mock call
metadata that was recorded correctly regardless (in which case this is
cosmetic), or may be missing exercising the actual mocked code path
(in which case the test could pass even if the real logic is broken).
**User Impact:** None directly — this affects confidence in test coverage,
not production behavior. Notably, two of the three affected tests are in
`test_nli_claim_verification.py`, adjacent to the faithfulness-verification
logic this whole audit is centrally concerned with — worth resolving before
trusting those two tests as strong evidence of NLI-verification
correctness.
**Required Fix:** Add the missing `await` (or switch to `Mock` if async
behavior isn't actually needed) in each of the 3 call sites; re-run and
confirm the warning disappears and the test still exercises the intended
path (add an explicit assertion on the mock's call count/args if not
already present).
**Regression Test:** `pytest -W error::RuntimeWarning` (or equivalent
`filterwarnings` config) to fail the build on any future un-awaited
coroutine, rather than letting it pass silently as a warning.
**Verification:** Re-run `pytest -q`, confirm 0 warnings.

### AMK-F-014 — Potentially-stale OKF-related test skips (skip messages predate a same-session doctrine-bundle sync commit)
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** `tests/test_okf_index_available.py:57`,
`tests/test_okf_doctrine_only.py:52,115`, and
`tests/test_okf_pipeline_integrity.py:40` all skip with messages like
`"OKF bundle intentionally empty — cleared for rebuild from green corpus"`
or `"compiled.json absent"`. The repo's own git log (visible in this
session's gitStatus context) shows a same-session commit `3339b670
data(okf): sync doctrine bundle — 715 live entries, staging review gate
intact`, which post-dates the premise those skip messages describe.
**Root Cause:** Unconfirmed — either (a) these skip conditions are
evaluated fresh at test-run time and genuinely still hold in the specific
test environment used for `pytest` (e.g. a test fixture path that doesn't
see the same `memory/okf/compiled.json` the running backend container
uses), in which case this finding is a false alarm, or (b) the skip
condition is stale relative to the now-populated bundle and these tests
have not meaningfully executed in some time.
**User Impact:** If (b), a meaningful coverage gap exists on exactly the
doctrine-integrity invariants (`DOCTRINE_TYPES` gate, `staging/` exclusion,
extractor-copy-identity) the repo's own CLAUDE.md calls out as
load-bearing for preventing non-doctrine content from reaching an answer.
**Required Fix:** Re-run these specific tests
(`.venv/bin/pytest tests/test_okf_index_available.py
tests/test_okf_doctrine_only.py tests/test_okf_pipeline_integrity.py -v`)
and inspect whether they skip or execute; if they skip, trace why
`compiled.json`/the bundle isn't visible to the test environment despite
the live commit.
**Regression Test:** N/A pending the investigation above.
**Verification:** Same command; confirm PASS (not SKIP) once the bundle is
confirmed visible to the test environment.

---

## Summary for orchestrator

- **Phase 16 (Observability): PARTIAL.** Structured logging, correlation
  IDs, and core business metrics (CHAT_COST, node timings on the sync path)
  are real and load-bearing. Tracing is configured but non-functional
  (Jaeger never runs by default — AMK-F-001). No server-side error tracking
  (AMK-F-003). A live, currently-occurring telemetry-sink bug drops rows
  silently and correlation-blind, degrading the hallucination-anomaly safety
  net (AMK-F-002, the strongest single finding from this phase). Streaming
  path has weaker observability than the sync path (AMK-F-004).
- **Phase 17 (Performance/Cost): PARTIAL**, mostly relying on already-
  measured §4E numbers per the task brief (**not demo-safe** per that
  document: must_mention coverage and latency p95 both fail more often than
  they pass). This track's own contribution: live-confirmed that
  verification-retry really does cost ~2x latency via a captured SSE
  transcript with two different cited source videos (AMK-F-008, HIGH), and
  found the documented latency-stage breakdown in root CLAUDE.md is stale
  by up to 6x on a live (loaded) sample (AMK-F-007).
- **Phase 18 (Testing): backend PASS (7266 passed, 0 failed, 12 skipped),
  frontend unit PASS (555 passed, 0 failed, 6 skipped)** — genuinely run
  this session, not assumed. **Frontend typecheck and lint both FAIL**
  (14 TS errors incl. one real API-drift bug; 10 ESLint errors) — this was
  genuinely NOT verified before this session per the task brief, and is now
  a confirmed gap. **E2E partially run**: page-smoke 14/14 PASS,
  seeker-journey 0/2 FAIL (root cause unconfirmed — likely load
  contention from this audit's own 6 parallel tracks, not re-verified
  quiet); the other 14 of 16 specs were not run this session.

**Top severity findings from this track:** AMK-F-008 (HIGH, verification
retry doubles latency+cost, confirmed live), AMK-F-002 (MEDIUM-HIGH,
live telemetry data loss defeating the hallucination safety net),
AMK-F-001/AMK-F-003/AMK-F-004 (MEDIUM, observability gaps), AMK-F-010
(MEDIUM, real frontend typecheck failures including one live API-drift
bug).

**No findings from this track alone are launch blockers** in the strict
sense (nothing here newly blocks launch on its own) — but AMK-F-008
materially explains WHY the latency_p95 gate in `docs/
GURU_DEMO_READINESS.md` §4E (already flagged there as a blocker) fails as
often as it does, and AMK-F-002 means the hallucination-anomaly monitor
that would catch a *production* faithfulness regression cannot currently
be trusted to have complete data.
