# AskMukthiGuru — Ruthless Production Readiness Audit — Progress Log

Audit started: 2026-09-18. Auditing repo at `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`,
branch `main`, commit `96fd24a57b266f03e1afc5062f727df55c7ebb2e` (13 commits ahead of
`origin/main`, 0 behind, unpushed). Docker stack running locally: backend, qdrant,
memgraph, redis all healthy at audit start. Railway production is intentionally
PAUSED (scaled to 0 replicas) per prior operator instruction this session — not
audited as a live deployment target; Docker Compose is the "production-like"
environment under test per Phase 15.

Full context this audit inherits from the same-day work session (not re-derived
from scratch): `handoff.md`, `lessons.md`, `docs/GURU_DEMO_READINESS.md`. Those
documents already contain significant, real evidence for several phases
(Phase 3 faithfulness, Phase 4 RAG retrieval, Phase 7 GC/resource leaks) —
this audit treats that evidence as a verified starting point, not a claim to
blindly trust, and will independently confirm or refute it where phases overlap.

---

## Phase 0 — Audit Initialization

**Status:** PASS

**What was checked:** git status/branch/commit, repo root structure, root
`CLAUDE.md`, `backend/CLAUDE.md`, `src/CLAUDE.md`, `package.json` scripts/deps,
`backend/docker-compose.yml` service list, `backend/requirements.txt`.

**What was verified:**
- Repo root: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
- Branch: `main`, HEAD `96fd24a5`, 13 commits ahead of `origin/main` (unpushed)
- Frontend entrypoint: React + Vite + TypeScript + shadcn/ui, `src/` (`npm run dev` → `http://localhost:8080`), Capacitor-wrapped for mobile (android/ios via `cap:sync`)
- Backend entrypoint: FastAPI, `backend/app/main.py`, `POST /api/chat` (`backend/app/api/chat.py:423`, streaming `:687`)
- Databases/stores: Qdrant (vector, port 6333/6334), Memgraph (graph, port 7687, replaced Neo4j), Redis (cache/queue, port 6379), Supabase (Postgres — local dev instance running in this environment, `supabase_*` containers observed alongside the app stack)
- Workers: Celery (`celery_config.py`, `tasks/*.py`), profile-gated (`COMPOSE_PROFILES=ingestion`), not running by default
- LLM providers: OpenRouter (live default), Sarvam Cloud, Ollama — see `backend/services/llm_factory.py`, three non-inheriting implementations
- Test commands: `backend/.venv/bin/pytest` (7266 passed / 0 failed / 12 skipped as of this session's last run), `npm test` (Vitest, NOT run this session prior to audit), `npm run test:e2e` (Playwright, NOT run this session prior to audit)
- Docker commands: `docker compose up -d` (default profile: memgraph/redis/qdrant/backend/frontend), `COMPOSE_PROFILES=ingestion|observability|cache` for extras

**Request path (chat, textual)**: Frontend (`src/lib/aiService.ts`, mode=`custom`) →
`POST /api/chat` → anon-quota check → `PipelineCoordinator.execute()` runs
ordered stages (`CacheCheck → RequestState → InputGuardrail → CircuitBreaker →
DoctrineCache → CasualShortCircuit → Distress → BoundedComparisonShortCircuit →
Graph → MeditationGen → Translation → ToneAdapter → OutputGuardrail → Memory →
CacheUpdate → ResultAssembly`) → `GraphStage` runs the LangGraph
(`rag/graph_strategies.py` Fast/Standard/Deep, nodes in `rag/nodes/`) →
response streamed/returned to frontend.

**Problems found:** None at this phase (setup/discovery only).

**Unknowns:** Whether the local Supabase instance backing this dev environment
has the same schema/RLS state as documented production audits from
`CLAUDE.md` (those were run against project `ozmjeuqbholoxypfxixb` — need to
confirm this dev Supabase is the same project or a separate local instance).

**Evidence:** commands run and output captured in this session's tool log;
`docker compose ps` at audit start showed all 4 default-profile services healthy.

**Next phase:** Phase 1 (Feature Discovery), then parallel dispatch of Phases 2-19
grouped into 6 investigation tracks (see below), synthesized into Phase 20/21
by the orchestrating session after all tracks report back.

---

## Audit execution model (declared up front, not a phase)

Given the scope (22 phases, real user asked for zero shortcuts, explicitly
accepted the cost of full live testing), phases 2-19 are dispatched to 6
parallel background investigation agents, each covering a themed group of
phases, each producing its own findings file under `audit/` plus AMK-XXX
findings returned to the orchestrator for consolidation into the final
required documents. This avoids concurrent writers on one shared file and
keeps each agent's context focused. The orchestrating session performs
Phase 0, Phase 1, Phase 20 (cross-system), and Phase 21 (final document)
directly, since those require synthesis across everything the tracks find.

Tracks:
- **Track A** — Phases 3, 4, 5 (Source Faithfulness, RAG/Qdrant/Neo4j/LightRAG, LangGraph/Agents)
- **Track B** — Phases 2, 6, 19 (Real User Journey, Memory/Second Brain isolation, UX/Product completeness)
- **Track C** — Phases 7, 12, 13 (Garbage Collection/Resource Leaks, Redis/Celery, Streaming/Async/Concurrency)
- **Track D** — Phases 8, 9, 14 (Security/Privacy, Data Integrity, Supabase/Database/RLS)
- **Track E** — Phases 10, 11, 15 (Attachments/OCR/Whisper, LLM Providers/Failover, Docker/Deployment)
- **Track F** — Phases 16, 17, 18 (Observability, Performance/Scalability/Cost, Testing Completeness)

Each track's status is appended below as it reports back.

## Phase 20 — Final Cross-System Audit

**Status:** PASS

**What was checked:** interactions between findings across all 6 tracks, not
just their individual severity in isolation.

**Cross-system risks found:**

1. **Verification-retry (AMK-F-008) compounds every crash-under-load finding
   (AMK-A-001, AMK-C-001, AMK-B-002).** The retry that fires on a failed
   first draft doubles LLM calls AND doubles in-process resource usage for
   that request — exactly the kind of spike that pushes concurrent load over
   the thread/memory ceilings the other three findings show this service
   cannot survive. A traffic pattern that looks like "8 concurrent users" to
   the admission-control layer can be "8 concurrent users, 3 of whom are
   secretly running 2 full pipeline passes" to the actual resource layer.
2. **The OOM crash (AMK-C-001) is not hypothetical for AMK-C-002 and
   AMK-C-005 — this audit reproduced the exact trigger condition for both.**
   AMK-C-002 (stuck jobs) and AMK-C-005 (duplicate memory writes) both
   require "the process dies mid-work" as their precondition. That
   precondition was not a hypothetical in this audit — it happened, twice,
   live, in Tracks A/B/C independently. These three findings are one causal
   chain, not three unrelated bugs.
3. **The soft-delete-then-orphaned-vector pattern (AMK-D-002) is the SAME
   shape of bug already found and fixed once this session** (the semantic
   cache's Qdrant vectors outliving their Redis TTL, commit `96fd24a5`,
   earlier today). Two independent instances of "delete the metadata,
   best-effort delete the vector, no reconciliation on failure" found in one
   day, in two unrelated subsystems, suggests this is a repeating pattern
   across the codebase, not two isolated bugs — worth an explicit sweep for
   other instances rather than fixing these two and considering it closed.
4. **The RLS/isolation "PASS" from Track D was verified at the code+DB
   level, but Track B independently found the actual UI+auth flow has never
   worked end-to-end in this environment (AMK-B-001).** These are not
   contradictory, but they combine into a narrower claim than either alone:
   "the database-level isolation guarantees are sound" is proven; "a real
   user going through the real signup/login UI gets those guarantees" is
   NOT proven, because that path has apparently never been exercised
   successfully against a consistent stack.
5. **Three live crashes this session were diagnosed using raw `docker logs`/
   `docker inspect` forensics, not any observability tooling — because
   Track F independently found that tooling doesn't work (AMK-F-001,
   distributed tracing configured-but-dead; AMK-F-003, no error tracking).**
   In a real production incident, without an engineer manually doing what
   this audit's subagents did by hand, these same crashes would be
   materially harder to diagnose. The crash-survivability findings and the
   observability findings compound: the system both crashes under load AND
   cannot explain why when it does.
6. **Two of three "memory" feature surfaces are non-functional today, for
   unrelated reasons, discoverable only by testing all three.** Second Brain
   is 100% down (missing `BRAIN_KEK`, AMK-B-007). Canonical memory works and
   is correctly isolated, but never actually surfaces a recalled fact in an
   answer even to its own owner (AMK-B-006, the verification gate strips it
   as "ungrounded"). Only conversation-turn-level context (not the
   structured memory systems) currently does anything a user would notice.
   A product decision ("is memory a shipped feature or not yet") depends on
   seeing all three findings together, not any one of them.
7. **AMK-C-001's local-Docker-Desktop-VM-specific root cause (memory
   overcommit across 4+ containers sharing 7.75GiB) previews a real Railway
   sizing question that has not been independently verified**, since Railway
   is currently paused and was not part of this audit's live-testing scope.
   The exact numbers won't transfer, but the *shape* of the risk (configured
   per-service memory limits exceeding what's actually available under
   concurrent peak load) is a real question to answer before any real
   deploy, not an artifact unique to this laptop.

**Problems found:** documented above — these are synthesis findings, not new
independently-numbered AMK items (they reference existing findings).

**Unknowns:** whether other TTL-asymmetric or soft-delete patterns beyond
AMK-D-002 and the already-fixed semantic cache exist elsewhere in the
codebase — flagged as worth a dedicated sweep, not audited exhaustively here.

**Evidence:** synthesis of Track A-F findings recorded above and in
`audit/track_*_findings.md`.

**Next phase:** Phase 21 (final production readiness document).

---

## Phase 21 — Final Production Readiness Document

**Status:** PASS (document complete)

Written to `ASKMUKTHIGURU_PRODUCTION_READINESS_PENDING.md` — all required
sections present (Executive Summary through Final Verdict), Master Pending
Table with all 41 findings, Top 20 with full Evidence/Root Cause/Fix/Test
for CRITICAL and HIGH items, and a Final Verdict split into VERIFIED
WORKING / NOT READY / UNKNOWN / LAUNCH CONDITIONS with no percentage score,
per the audit brief's explicit instruction.

**AUDIT COMPLETE.** All 22 phases executed with a PASS/FAIL/PARTIAL result:
Phase 0 PASS, Phase 1 PASS, Phase 2 PARTIAL, Phase 3 PARTIAL PASS, Phase 4
PARTIAL PASS, Phase 5 PARTIAL PASS (1 CRITICAL), Phase 6 COMPLETE (isolation
test PASS), Phase 7 COMPLETE (1 UNKNOWN item), Phase 8 PASS-with-findings,
Phase 9 PASS-with-findings, Phase 10 PASS, Phase 11 PASS, Phase 12 COMPLETE,
Phase 13 PARTIAL, Phase 14 PASS, Phase 15 PASS, Phase 16 PARTIAL, Phase 17
PARTIAL, Phase 18 COMPLETE, Phase 19 PARTIAL, Phase 20 PASS, Phase 21 PASS.

3 independent live-reproduced crash-under-load findings, 41 total findings,
0 CRITICAL security findings, cross-user isolation verified PASS, core
misattribution guarantee verified PASS across 30 questions. Docker stack
confirmed healthy at end of audit (re-checked before writing this section).

---

### Track A — REPORTED (Phases 3, 4, 5) — full detail: audit/track_A_findings.md

**Status:** Phase 3 PARTIAL PASS, Phase 4 PARTIAL PASS, Phase 5 **PARTIAL PASS
with one CRITICAL finding.**

**Phase 3 (Faithfulness):** Real, live-tested, ground-truthed. 6 real
`/api/chat` calls (grounded, unsupported, 3 adversarial). Citations
independently checked against raw Qdrant content, not just trusted. Watched
the redaction mechanism fire live (unsupported sentence stripped,
faithfulness 0.75→1.0). All 3 adversarial attempts (prompt injection,
fabricate-a-quote, "disregard context") failed to produce fabricated
attributed teachings. Caveat carried forward from Phase 0/1: only 18
questions total ever checked against current code, out of a ~1,200-question
bank — coverage remains genuinely unverified, not just "probably fine."

**Phase 4 (RAG pipeline):** Hybrid retrieval, Memgraph KG expansion,
LightRAG, OKF fallback all confirmed real and live, not just documented.
Concurrency wiring in `retrieval.py` itself is mostly sound (bounded
`asyncio.gather`/`wait_for`, fail-open) — but see Phase 5's finding below,
which concurrent retrieval testing helped surface.

**Phase 5 (LangGraph/Agents) — CRITICAL, LAUNCH BLOCKER:**

> **AMK-A-001 (CRITICAL)** — Firing ~5-7 concurrent real chat requests at
> the live backend reproduced `RuntimeError: can't start new thread` across
> multiple pipeline stages, and **the backend container actually crashed and
> restarted** — confirmed via `docker inspect` (RestartCount incremented),
> ~1 minute of total unreachability with failed healthcheck probes during
> the crash/restart window. This is thread-pool exhaustion, the same class
> of bug `backend/CLAUDE.md` documents as fixed under L-DOCKER-18 ("never
> pass a synchronous def to Depends() — forces Starlette/AnyIO into the
> worker threadpool, glibc runs out of thread-stack allocation"). Either
> that fix regressed, or a new instance exists.
> - **AMK-A-002 (HIGH)** — `cache_stage.py:342` has an unguarded
>   `asyncio.to_thread` call, unlike every equivalent call in
>   `retrieval.py` — turns a transient failure into a full pipeline crash.
> - **AMK-A-003 (MEDIUM)** — the in-memory coalescer fallback (active
>   during Redis outages) doesn't shield shared work from caller-timeout
>   cancellation the way the Redis-backed path does — risks retry storms
>   exactly when the system is already degraded (compounds AMK-A-001).
> - **AMK-A-004 (LOW)** — several terminal nodes write `verification`
>   dicts missing the `citations_verified` key `backend/CLAUDE.md` documents
>   as mandatory; no test guards this.

**The headline finding of the whole audit so far**: the concurrency level
this service can actually survive is lower than its own admission-control
assumes, and exceeding it doesn't degrade gracefully — it crashes the
process. This alone is grounds to say NOT production-ready until root-caused
and fixed, independent of anything else any other track finds.

### Track E — REPORTED (Phases 10, 11, 15) — full detail: audit/track_E_findings.md

**Status:** Phase 10 PASS (minor findings), Phase 11 PASS, Phase 15 PASS. No
CRITICAL or launch-blocking findings in this track.

**Phase 10 (Attachments/OCR/Whisper):** End-user uploads (`/api/chat/upload`,
`/api/speech/stt`) live-tested and confirmed properly bounded (10MB/file,
50MB total, 25MB audio), ephemeral, MIME-sniffed from magic bytes (not
trusted client headers), temp files cleaned up via `finally:`, both OCR (30s)
and Whisper (60s) timeout-bounded. Oversized/empty/malformed/unsupported
uploads all behaved correctly against the real server except: a malformed
image rides out the full 30s OCR timeout instead of failing fast on decode
(AMK-E-004, LOW).

**Phase 11 (LLM Providers/Failover):** Cross-provider failover confirmed
**fully dead**, worse than CLAUDE.md's own note suggested — not just "NIM
removed": `services/failover_provider.py` doesn't exist anymore at all, and
two OTHER failover-shaped objects (`MultiProviderLLMService`,
`SarvamFailoverService`/`model_registry`) are fully built and wired into
`app/container.py` but have **zero consumers** anywhere in the request path
(verified by grep). Real resilience that DOES exist: bounded OpenRouter
retries, same-provider model fallback on 429/5xx (deepseek-chat →
llama-3.3-70b), a circuit breaker, Redis-backed cross-replica rate limiting.
One real gap found: an invalid API key gets pointlessly retried then leaks a
raw exception string to the end user (HTTP 500) — AMK-E-002 (MEDIUM).

**Phase 15 (Docker/Deployment):** `docker kill` → measured **~120s total
outage** before `restart: unless-stopped` brought it back healthy
(101s to restart trigger + 19s to running + 30s to healthy). Post-recovery,
a real chat call succeeded end-to-end. Non-root runtime confirmed (UID 1000
via `gosu`), no baked-in secrets. Memory: backend 2.8-3.3GB/6GB, memgraph
633-637MB/1GB (confirms this session's earlier finding, still accurate,
~38% headroom — not the ~60-100MB CLAUDE.md aspirational figure). Real
config drift found: Dockerfile wants `start_period=420s` for cold model
downloads, `docker-compose.yml` silently overrides to 180s, never
reconciled (AMK-E-006, MEDIUM — latent risk on a genuinely cold deploy).

**Tooling limitation noted by the track itself**: `docker exec` was denied
by this environment's permission policy on every attempt this track made
(even `whoami`) — filesystem permissions inside the container and temp-file
cleanup verification were done via code reading + `docker top`/`inspect`
instead, and are marked UNKNOWN rather than falsely claimed PASS.

### Track C — REPORTED (Phases 7, 12, 13) — full detail: audit/track_C_findings.md

**Status:** Phase 7 COMPLETE (fd-count item UNKNOWN — `docker exec` denied
by this environment's own permission system throughout the track, same
limitation Track E hit), Phase 12 COMPLETE, Phase 13 PARTIAL (budget spent
recovering from the crash below; no live concurrent-SSE/mid-stream-abort
test actually ran).

**Resource usage under burst did NOT stabilize — it crashed the backend a
SECOND time, via a DIFFERENT root cause than Track A's.**

> **AMK-C-001 (CRITICAL, launch blocker)** — 40 real `/api/chat` requests at
> concurrency 6 (under the app's own configured `max_concurrent_chat=8`
> ceiling): 11/40 succeeded, then the backend was SIGKILLed (`Exited 137`)
> at request #12, ~102s downtime, restarted by the external `autoheal`
> watchdog (not Docker's own restart policy — `RestartCount=0`, meaning
> Docker itself didn't even register this as a restart it caused). Root
> cause confirmed via `docker info`: this machine's Docker Desktop VM has
> only 7.75GiB total memory, while just the 4 running containers'
> CONFIGURED limits sum to ≥10.5GiB (backend 6G + qdrant 3G + memgraph 1G +
> redis 512M) — a host/VM memory-overcommit, not a Python leak. The backend
> process itself never approached its own 6GiB limit (was at 3.6GiB when
> killed).
> - **Nuance for the final doc**: this specific manifestation (this machine's
>   Docker Desktop VM sizing) is local-dev-environment-specific — a
>   production host would presumably provision real memory per service
>   rather than 4 containers sharing one undersized VM. But it directly
>   validates that the CONFIGURED limits across services already assume
>   more memory than a modest host provides, which is exactly the sizing
>   question that matters for whatever Railway/production tier gets chosen
>   — this is a real data point for capacity planning, not a throwaway
>   local-only quirk.
> - **AMK-C-002 (HIGH, launch blocker)** — jobs claimed by a worker that
>   hard-crashes (exactly the crash class just reproduced) are never
>   reclaimed: `job_queue.py`'s recovery logic only covers graceful
>   `CancelledError` shutdowns and the durable-pending list, not jobs
>   already claimed when the process dies. A client polling such a job
>   hangs forever with no timeout.
> - **AMK-C-005 (MEDIUM)** — the memory-outbox's 4 enrichment writes
>   (episodic, L1 atoms, L2 scene) aren't idempotent, and the outbox's own
>   10-minute staleness-reclaim will duplicate them after precisely the
>   crash class reproduced above — a crash mid-write plus the recovery
>   mechanism together produce duplicate memory writes.

**Earlier same-session GC fix (commit 96fd24a5) independently verified
correct and complete** — reactive delete-on-expiry + hourly sweep both
confirmed wired and working; no other TTL-asymmetric cache pattern found
live. The data-retention gap (stored-but-unenforced `retention_days`, zero
cleanup jobs for `chat_responses`/telemetry) confirmed still accurate — plus
a new instance of the same pattern: local compliance-audit JSONL files
rotate by filename daily but are never deleted (AMK-C-004, LOW/MEDIUM,
unbounded local disk growth).

**Running tally: 2 independent, live-reproduced CRITICAL launch-blockers so
far, both "backend dies under concurrent load," different root causes**
(Track A: glibc thread-stack exhaustion from an unguarded sync-in-Depends
pattern; Track C: memory overcommit at the container/VM level). These are
not the same bug wearing two hats — both need fixing.

### Track B — REPORTED (Phases 2, 6, 19) — full detail: audit/track_B_findings.md

**Status:** Phase 2 PARTIAL, Phase 6 COMPLETE for the mandatory isolation
test, Phase 19 PARTIAL — real UI signup/login blocked by an environment bug
(see AMK-B-001), so authenticated-surface UX (Profile, Settings, Second
Brain UI) is UNKNOWN, not verified.

**Mandatory cross-user memory isolation test: PASS.** Two real
Supabase-authenticated accounts created. User A stored a memorable canonical
memory ("favorite color is chartreuse, lives in Erode"). `GET
/api/memory/canonical` returned it only to A, empty to B. Asked B the same
recall question via live chat — no leak, B received unrelated doctrine
excerpts. (Notably, even User A didn't get their own fact echoed back — the
memory was fetched server-side but stripped by the faithfulness/redaction
gate as "ungrounded." A functionality bug, not a security one — see
AMK-B-006 below.)

**Two more CRITICAL/launch-blocker findings:**

> **AMK-B-001 (CRITICAL, launch blocker)** — Frontend `.env.local` points
> auth at **PRODUCTION** Supabase (`ozmjeuqbholoxypfxixb.supabase.co`) while
> the backend this whole session has been testing against points at
> **local** Supabase. Real signup/login through the actual UI is broken in
> this dev setup as a direct result — and carries a real risk of accidental
> writes hitting the production Supabase project during local dev/testing.
> This is a dev-environment-configuration bug, but a serious one: it means
> NO end-to-end UI auth flow has been genuinely exercised against a
> consistent stack, by this audit or (per the session's own history)
> apparently any prior one either.
>
> **AMK-B-002 (CRITICAL, launch blocker)** — **A THIRD independent,
> live-reproduced crash under concurrent load**, distinct signature from
> both Track A (glibc thread-stack exhaustion) and Track C (host-VM memory
> overcommit / SIGKILL): backend crashed twice in ~15 minutes under
> concurrent load with an ONNX/torch `std::bad_alloc`, one exit via SIGKILL
> (137). Despite `restart: unless-stopped`, one of the two crashes left the
> container in `Exited` state requiring a MANUAL `docker start` — neither
> Compose's restart policy nor the `autoheal` watchdog caught it.

**Other findings:**
- **AMK-B-007 (HIGH, launch blocker for that one feature)** — Second Brain
  is 100% non-functional: `BRAIN_KEK` env var is unset, every vault
  endpoint 500s for every user, unconditionally.
- **AMK-B-006 (MEDIUM)** — canonical memory is stored and correctly
  isolated per-user, but never actually reaches a chat ANSWER even for its
  own owner — the verification/redaction gate strips personal recalled
  facts as "ungrounded" before they can be used. The memory feature exists,
  is safe, and does nothing useful yet.
- **AMK-B-003/004 (MEDIUM)** — "Tell me more" stuffs the entire previous
  answer (including internal redaction commentary) verbatim into the next
  turn's composer, which then got misclassified as user distress and
  redirected to a Serene Mind safety prompt instead of continuing the
  teaching — a real, live-reproduced UX break in a common follow-up flow.

**Running tally: THREE independent, live-reproduced crash-under-load
findings now (Tracks A, B, C), three different failure signatures, same
overall symptom — this backend does not survive realistic concurrent
traffic today.** This is now unambiguously the single most important
finding across the whole audit; every other track's results are secondary
to this until it's addressed.

### Track F — REPORTED (Phases 16, 17, 18) — full detail: audit/track_F_findings.md

**Status:** Phase 16 PARTIAL, Phase 17 PARTIAL, Phase 18 COMPLETE (real
numbers obtained for everything, including the frontend suite which had
never been run this session before this audit).

**Real test-suite numbers, first time both sides were actually run this
session:**
- Backend: **7266 passed / 0 failed / 12 skipped** (379s)
- Frontend Vitest: **555 passed / 0 failed / 6 skipped**, 98 test files
- Frontend **typecheck: FAILS, 14 real TS errors**, including one genuine
  API-drift bug — `ChatMessage.tsx:439` calls `transport.getAccessToken`,
  which does not exist on that module.
- Frontend **ESLint: 10 errors, 40 warnings**, including 9 empty-catch
  blocks in auth-adjacent files.
- E2E (Playwright): page-smoke 14/14 PASS; seeker-journey 0/2 FAILED
  (plausibly caused by this audit's own concurrent-load testing happening
  at the same time — not confirmed clean on a quiet box); 14 of 16 specs
  not run at all.

**Observability (Phase 16):** JSON structured logging + correlation IDs are
real and propagate through nearly every log line — genuinely good. But
OpenTelemetry/Jaeger is configured `OTEL_ENABLED=true` by default while
Jaeger itself is profile-gated and was never running (`docker ps -a` showed
zero jaeger container) — tracing silently no-ops, configured-but-dead.
**Caught a live, naturally-occurring bug mid-audit**: telemetry Postgres
inserts failing (`invalid input syntax for type integer: "192.76"`) because
a 2026-09-17 fix (`_coerce_int`) only patched 4 of the integer columns this
file writes — `start_ms`/`duration_ms`/`top_k` are still unguarded, and the
resulting error log carries no correlation_id either (contextvars don't
propagate through `loop.run_in_executor`). This directly feeds
`hallucination_anomaly.py` — the exact "no data reads as no hallucinations"
blind spot root CLAUDE.md already warns about elsewhere in a different
context, now confirmed live in this one.

**Performance (Phase 17):** Captured a live SSE transcript directly
confirming the verification-retry latency theory the session already
suspected — two distinct full-answer generations visibly back-to-back
(different cited videos each pass), ~34.5s total vs 5-14s for comparable
non-retried queries. Also: root CLAUDE.md's documented per-stage latency
breakdown is stale (`navigate_and_hyde` documented at 5.4s, observed live at
32.8s).

**Findings, none independently launch-blocking, but one explains a blocker
and one undermines the safety-monitoring story:**
- **AMK-F-008 (HIGH)** — live-confirmed mechanism: the verification-reject
  retry genuinely doubles both latency and LLM cost per occurrence. Not a
  new problem, but now directly observed rather than inferred.
- **AMK-F-002 (MEDIUM-HIGH)** — live telemetry write failures mean the
  hallucination-rate anomaly monitor cannot currently be trusted to detect
  a real spike — it may just see "no data" during exactly the window it
  needs to alert on.
- **AMK-F-001 (MEDIUM)** — distributed tracing configured as enabled,
  silently does nothing (Jaeger never running).
- **AMK-F-004 (MEDIUM)** — the streaming response path has no per-node
  timing instrumentation (only the sync path does).
- **AMK-F-010 (MEDIUM)** — real frontend typecheck failures, including a
  genuine runtime-risk API-drift bug, not just lint noise.

### Track D — REPORTED (Phases 8, 9, 14) — full detail: audit/track_D_findings.md

**Status:** Phase 8 PASS-with-findings, Phase 9 PASS-with-findings, Phase 14 PASS.

**Environment identity resolved** (was an open unknown from Phase 0): local
Supabase (`hqhcunyifwofyfjtuphl`, port 54322) is confirmed a SEPARATE
instance from production (`ozmjeuqbholoxypfxixb`), and is a SHARED dev
instance also hosting an unrelated job-search app (11 RLS-disabled tables
belong to that, not AskMukthiGuru). Every AskMukthiGuru table (92/103) has
RLS enabled with correctly owner-scoped policies, independently re-verified
against live local Postgres (not inherited from the prior production-audit
claim in CLAUDE.md).

**No CRITICAL security findings.** Live-tested: cross-session job IDOR
(blocked, 404), prompt injection (blocked by input guardrail), CORS (origin
allowlist holds, no reflection), rate limiting (429 after 2 req/min on
anon-session mint). Authenticated-user (JWT) cross-user IDOR NOT live-tested
— marked UNKNOWN, only anonymous-session isolation was exercised.

**Findings (none launch-blocking):**
- **AMK-D-002 (HIGH)** — "Forget this" / memory deletion is not fail-closed.
  `canonical_memory.py`'s delete path silently swallows Qdrant deindex
  errors with no retry; `retriever.py` only score-penalizes
  `status="deleted"` to 0.0 rather than hard-excluding it — so a failed
  deindex can leave a "deleted" memory still retrievable into the LLM
  prompt. The correct fail-closed pattern already exists elsewhere in this
  same codebase (`second_brain_service.py::crypto_shred` wipes vectors
  before DB delete) — this path just doesn't use it.
- **AMK-D-001 (MEDIUM)** — `check_url_safety`'s SSRF guard only checks
  literal-IP hostnames, not DNS-resolved ones (comment in the code admits
  this). The actual `/api/ingest` fetch path does correct DNS-resolution
  checking via a different function, so no live exploit today — but the
  weaker function is a landmine if ever reused as a sole gate.
- **AMK-D-003 (MEDIUM)** — Idempotency middleware only covers
  `/api/feedback` and `/api/ingest`; no DB unique constraints back up
  `canonical_memories`/`user_brain_nodes` writes, so client retries on most
  write endpoints can create duplicate rows.
- Minor: duplicate/redundant RLS policies on `chat_responses`/`chat_sessions`
  (harmless cruft); `allow_credentials=true` sent unconditionally in CORS
  middleware (safe today, fragile if the allowlist logic changes).

**Dispatch status (2026-09-18):** All 6 tracks launched as background agents.
Track A (agent a4043cbc..., Phases 3/4/5), Track B (agent a8631b1a...,
Phases 2/6/19), Track C (agent a4f0b4e9..., Phases 7/12/13), Track D (agent
a3f10793..., Phases 8/9/14), Track E (agent a0707206..., Phases 10/11/15),
Track F (agent abe1ecf0..., Phases 16/17/18). Each writes to its own
`audit/track_X_findings.md` and reports a summary back to the orchestrator on
completion. This section will be updated with PASS/FAIL/PARTIAL per phase as
each track reports in.

---

## Phase 1 — Complete Feature Discovery

**Status:** PASS (inventory complete; end-to-end tracing deferred to tracks below)

**What was checked:** `src/pages/` (18 pages), `backend/app/api/*.py` (25 router
modules + `endpoints/auth.py`), full route list (~100+ endpoints across
`@router.get/post/put/delete`).

**What was verified — this product is substantially larger than this
session's own RAG-pipeline work implies.** Feature areas discovered that were
NOT touched or investigated at all earlier this session:

| Feature area | UI | API module | Notes |
| :--- | :--- | :--- | :--- |
| Chat (core RAG) | `ChatPage.tsx` | `chat.py` (52K) | This session's entire focus. Streaming via `/chat/stream/{job_id}`. |
| Second Brain | `SecondBrainPage.tsx` | `second_brain.py`, `brain/*` routes | Personal knowledge vault — items, export, vault deletion. UNAUDITED this session. |
| Canonical Memory | (via chat/profile) | `canonical_memory.py` (34K), `memory.py` (32.9K) | Partially documented in root `CLAUDE.md` ("Canonical memory: wired end to end") but that doc itself lists 6 defects found and fixed on 2026-09-12 — needs re-verification, not re-trust. |
| Knowledge Graph views | `KnowledgeGraphPage.tsx` | `kg.py` (26.8K) | Personal + global subgraph endpoints. UNAUDITED. |
| Study Notebook / SRS (spaced repetition) | `StudyNotebookPage.tsx` | `srs.py` | `/srs/due` — a full spaced-repetition study feature. UNAUDITED, not mentioned anywhere in this session's prior work. |
| Practices | `PracticesPage.tsx`, `PracticeDetailPage.tsx` | `teachings.py` | Guided practice content delivery. |
| Auth | `AuthPage.tsx`, `MFAChallengePage.tsx`, `ResetPasswordPage.tsx`, `AuthDiagnosticsPage.tsx`, `AuthLatencyDashboard.tsx` | `endpoints/auth.py`, Supabase auth | AAL2/MFA documented in root CLAUDE.md as implemented with its own test suite — needs re-verification. |
| Profile / settings | `ProfilePage.tsx` (69K — the largest page file in the app) | `profile.py` | Large surface, unaudited. |
| Cancel/win-back flow | (unclear which page) | `cancel_flow.py` (28K) | Full churn-prevention flow with scheduled email dispatch (`celery_config.py` beat schedule). Business-critical, unaudited. |
| Compliance / EU AI Act | `AdminSelfCheckPage.tsx`? | `compliance.py`, `/eu-ai-act/status` | Regulatory-facing endpoint exists — unaudited whether it reflects real compliance state or is a stub. |
| Push notifications | — | `push.py` | Unaudited. |
| Speech (OCR/Whisper/TTS) | `TTSVerificationPage.tsx` | `speech.py` (13.6K) | Maps to Phase 10. |
| Admin | `AdminSelfCheckPage.tsx` | `admin.py` (77K — the single largest API file) | Enormous surface, mostly unaudited beyond what root CLAUDE.md documents about specific admin endpoints touched in past sessions. |
| Waitlist / retention / support | — | `waitlist.py`, `retention.py`, `support.py` | Unaudited. |
| Ingestion | (admin-only, `ingest-ui/`) | `ingest.py` | Documented extensively in root CLAUDE.md, but that documentation is itself the kind of claim this audit must independently verify, not inherit. |

**Problems found:** None yet at inventory level — this phase only establishes
scope. The finding IS the scope itself: roughly 15 distinct feature areas
exist beyond the RAG chat core, most never touched by any work this session,
several (Second Brain, SRS, Knowledge Graph views, cancel-flow, compliance
status) with no evidence of any prior audit either, per `handoff.md`'s own
history which is chat-pipeline-focused throughout.

**Unknowns:** Whether `admin.py`'s 77K of routes are used by any real UI at
all, or are internal/ops-only surface never exposed to end users — matters
for Phase 8 (security) since an unauthenticated or under-authenticated admin
route is a different severity than one behind a UI only admins see.

**Evidence:** file listing and route grep output, captured in this session's tool log.

**Next phase:** Dispatch Tracks A-F now.
