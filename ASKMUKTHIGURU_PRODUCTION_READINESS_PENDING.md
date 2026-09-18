# AskMukthiGuru — Production Readiness: Pending Work

Audit date: 2026-09-18. Repo `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`,
branch `main`, commit `96fd24a5` (13 commits ahead of `origin/main`, unpushed at
audit time). Methodology and per-phase checkpoint status:
`ASKMUKTHIGURU_AUDIT_PROGRESS.md`. Full evidence per track: `audit/track_{A-F}_findings.md`.

> ## Status update — 2026-09-18 (later session)
>
> Five more findings closed. **Two root causes in this document are wrong** and
> are corrected in place in `audit/track_{B,C}_findings.md`; read those before
> acting on anything below about crashes or concurrency.
>
> | Finding | Status | Note |
> | :--- | :--- | :--- |
> | AMK-B-002 | **Fixed** | Root cause was NOT memory. Segfault from concurrent `forward()` on one shared torch module (`LettuceDetect._shared_detector`), at 4.11 GiB of 6 GiB with `OOMKilled: false`. Fixed with an exclusive lock; verified surviving the same burst. |
> | AMK-C-001 | **Fixed** (same defect) | Overcommit arithmetic is correct but was not the killer. Ceiling now measured: ~324 MB per concurrent chat, ~73 concurrent on 32 GB. `max_concurrent_chat` stays at 8 — the binding limits are the OpenRouter rate limiter and the serialized verification pass, not memory. |
> | AMK-C-005 | **Fixed** | `memory_outbox.completed_steps` makes a reclaimed row resume, not restart. Narrows but does not close the at-least-once window — see the finding. |
> | AMK-B-006 | **Fixed**, verified live | Canonical memory now reaches answers as its own evidence class. Doctrine threshold untouched; memory is never citable. Cross-user leak re-tested after the fix. |
> | AMK-F-001 | **Partly fixed** | The silent no-op is now loud: startup warns when `OTEL_ENABLED` is on and no collector is listening. Whether to run Jaeger by default remains an operator decision. |
>
> Everything else in this document stands. Sizing, measurements and the
> re-derivation procedure: `docs/engineering-notes/concurrency-ceiling-2026-09-18.md`.

This document is a synthesis of 6 parallel live-testing investigation tracks
(A-F, covering Phases 2-19) plus direct orchestrator work (Phases 0, 1, 20).
Every finding below traces to a specific track file with exact evidence —
nothing here is asserted without a citation to where it was verified.

---

## Executive Summary

AskMukthiGuru's **core safety mechanism works**: across 30 independently
tested questions today (18 faithfulness-focused, 12 from a repeated
demo-safe benchmark), the top-severity guarantee — never putting invented
words in a living teacher's mouth — held at 0% real misattribution, with
every flagged detector alert individually ground-truthed against the actual
corpus rather than trusted at face value. Cross-user data isolation, tested
directly by creating two real accounts and probing for leakage, also held.

**The product cannot currently survive realistic concurrent traffic.**
Three independent live-reproduced crashes, from three different root
causes, all inside a single ~2-hour testing window, at load levels the
service's own admission control considers safe:
- Thread-pool exhaustion (`RuntimeError: can't start new thread`) at ~5-7
  concurrent requests, crashing the whole backend process for ~1 minute.
- Host/VM memory overcommit killing the backend (`Exited 137`) at 6
  concurrent requests, ~100s downtime, external watchdog recovery only.
- ONNX/torch native memory pressure (`std::bad_alloc`) crashing the backend
  twice in 15 minutes under moderate concurrent traffic, once requiring a
  **manual** restart because neither Docker's restart policy nor the
  `autoheal` sidecar caught the failure mode.

None of these are edge cases requiring adversarial load generation — each
was hit organically while testing other, unrelated things. Separately: the
dev environment's frontend authenticates against **production** Supabase
while the backend runs against **local** Supabase, meaning no authenticated
UI flow (Second Brain, Profile, canonical memory management) has ever been
genuinely exercised end-to-end this session. Second Brain is additionally
100% down on a missing environment variable. Jobs claimed by a worker that
crashes are never reclaimed — directly caused by, and reproduced by, the
crashes above. Frontend typecheck fails with 14 real errors including a
genuine runtime bug. Distributed tracing and error tracking are both
configured but non-functional, meaning production incidents matching the
ones reproduced today would be diagnosed by manual `docker logs`
archaeology, not tooling.

**This is not production-ready.** The blockers are concentrated (crash
survivability, auth environment config, one broken feature) rather than
diffuse — this is a tractable list, not a rewrite.

---

## Architecture Verified

Confirmed in Phase 0/1 and re-confirmed live throughout the audit:

- **Frontend**: React + Vite + TypeScript + shadcn/ui (`src/`), 18 pages,
  Capacitor-wrapped for mobile.
- **Backend**: FastAPI (`backend/app/main.py`), 25 API router modules (~100+
  endpoints), request path: `POST /api/chat` → anon-quota check →
  `PipelineCoordinator` (13 ordered stages) → `GraphStage` (LangGraph,
  Fast/Standard/Deep strategies) → response.
- **Stores**: Qdrant (vector), Memgraph (graph, replaced Neo4j), Redis
  (cache/queue), Supabase/Postgres (relational + auth).
- **Workers**: Celery, profile-gated, not running by default.
- **LLM providers**: OpenRouter (live default), Sarvam Cloud, Ollama —
  independent, non-inheriting implementations.
- **This audit's environment**: local Docker Compose stack (backend, qdrant,
  memgraph, redis all healthy at audit start; local Supabase running
  alongside, confirmed a genuinely separate instance from production,
  Track D). Railway production is intentionally paused (scaled to 0
  replicas) — not exercised live by this audit.

---

## Feature Inventory

Full detail: `ASKMUKTHIGURU_AUDIT_PROGRESS.md` Phase 1. Summary: this
product is substantially larger than its RAG-chat core — Second Brain,
Canonical Memory, Knowledge Graph views, Study Notebook/SRS, Practices,
Auth/MFA, Profile, a 28K-line cancel/win-back flow, EU AI Act compliance
status, push notifications, Speech (OCR/Whisper/TTS), and a 77K-line admin
surface. Most of these were **not covered by any prior session's work**
(which was RAG-pipeline-focused throughout) and several were audited today
for the first time.

| Feature | UI | Backend | E2E Tested Today | Status |
|---|---|---|---|---|
| Chat / RAG core | ChatPage.tsx | chat.py | Yes, extensively | Working, but crashes under load (see Concurrency) |
| Canonical Memory | via chat/profile | canonical_memory.py | Yes | Works, correctly isolated, but never surfaces in answers (AMK-B-006) |
| Second Brain | SecondBrainPage.tsx | second_brain.py | Yes | **100% down** — missing `BRAIN_KEK` (AMK-B-007) |
| Knowledge Graph views | KnowledgeGraphPage.tsx | kg.py | No | UNKNOWN |
| Study Notebook / SRS | StudyNotebookPage.tsx | srs.py | No | UNKNOWN |
| Auth (signup/login/MFA) | AuthPage.tsx etc. | endpoints/auth.py | Partial | Broken in this dev config (AMK-B-001) |
| Profile / Settings | ProfilePage.tsx (69K, largest page) | profile.py | No (blocked by AMK-B-001) | UNKNOWN |
| Cancel/win-back flow | ? | cancel_flow.py (28K) | No | UNKNOWN |
| Compliance / EU AI Act | AdminSelfCheckPage.tsx? | compliance.py | No | UNKNOWN |
| Attachments/OCR/Whisper | via chat upload | speech.py | Yes | Working, bounded, minor gaps (Track E) |
| Admin | AdminSelfCheckPage.tsx | admin.py (77K) | No | UNKNOWN |

---

## Real User Journey Results

Full detail: `audit/track_B_findings.md` Phase 2. Anonymous journey
(ask/answer/follow-up/persistence) verified working, with two real UX bugs
found (AMK-B-003 "tell me more" prompt-stuffing, AMK-B-004 benign follow-up
misrouted to distress handling). Failure-mode testing (empty/malformed/huge
input, rapid-fire) behaved correctly. **Authenticated journey (signup →
login → use authenticated features → return) could not be completed** —
blocked by AMK-B-001 (frontend/backend Supabase mismatch). Returning-user
persistence verified at the API level (conversation history, canonical
memory) but not through a real UI session for the reason above.

| Journey | Result |
|---|---|
| New anonymous user: ask → answer → follow-up | PASS, with UX bugs (AMK-B-003/004) |
| New user: signup → login → authenticated feature | **BLOCKED** (AMK-B-001) |
| Returning user: persistence (API-level) | PASS |
| Returning user: persistence (real UI session) | UNKNOWN (blocked by above) |
| Failure inputs (empty/malformed/huge/rapid-fire) | PASS |

---

## Source Faithfulness

Full detail: `audit/track_A_findings.md` Phase 3. **PARTIAL PASS — real,
positive evidence, incomplete coverage.** 6 live tests today (1 grounded, 1
unsupported, 3 adversarial) all showed correct behavior: citations
independently ground-truthed against raw Qdrant content (not just trusted),
the redaction mechanism observed live stripping an unsupported claim and
raising faithfulness 0.75→1.0, and all 3 adversarial attempts (prompt
injection, fabricate-a-quote, "disregard context") failed to produce a
fabricated attributed teaching. Combined with this session's earlier
3-run demo-safe benchmark (misattribution 0.0% each time, ground-truthed),
**30 questions total have now been independently confirmed clean.**
**~1,200 questions in the full evaluation bank have never been re-run
against current code** — this is the honest remaining gap, not a doubt
about the mechanism itself.

---

## RAG / Qdrant / Memgraph / LightRAG

Full detail: `audit/track_A_findings.md` Phase 4, full pipeline-stage table
included there. **PARTIAL PASS.** Hybrid retrieval, Memgraph KG expansion
(confirmed concurrent with primary retrieval), LightRAG (confirmed live,
real entity/relation counts from real Memgraph queries), OKF curated-doctrine
fallback (confirmed firing on genuinely empty vector retrieval, never
producing a hallucinated or blank answer instead) — all real, not stubs.
CRAG rewrite loop provably bounded (`rewrite_count >= rag_max_rewrites`).
**New finding**: under concurrent load, multiple retrieval sub-calls failed
with thread exhaustion (`RuntimeError: can't start new thread`), gracefully
degrading retrieval to 0 documents in a way invisible to `/api/health` —
part of the same root cause as AMK-A-001. Ingestion/chunking/embedding
stages were code-verified (live Qdrant payload inspection confirms the
expected chunk/header structure) but not exercised via a live ingestion run
this session.

---

## LangGraph / Agents

Full detail: `audit/track_A_findings.md` Phase 5, full per-node table
included there. **PARTIAL PASS, one CRITICAL.** No infinite-loop risk found
— all rewrite/retry loops are provably capped, `recursion_limit=60` is a
deliberate margin above the actually-reachable worst case. Per-request state
isolation confirmed by design (fresh state per request, correct reducer
semantics for LangGraph's `Send`-based parallel branches, no shared mutable
globals). `GraphRecursionError` degrades gracefully. **AMK-A-001 (CRITICAL,
launch blocker)**: thread-pool exhaustion under modest concurrent load,
live-reproduced, took down the entire container. Full writeup in the Master
Pending Table and Top 20 below.

---

## Memory / Second Brain

Full detail: `audit/track_B_findings.md` Phase 6. **Mandatory cross-user
isolation test: PASS**, tested directly with two real Supabase accounts —
User A's stored fact never leaked to User B via API or chat. But the
feature area as a whole is in poor shape functionally: Second Brain is
100% down (AMK-B-007, missing `BRAIN_KEK`), and canonical memory — though
correctly isolated — never actually surfaces a recalled fact in a chat
answer, even to its own owner, because the faithfulness/redaction gate
strips personal facts as "ungrounded" (AMK-B-006). Separately (Track D,
`audit/track_D_findings.md`): a soft-deleted ("forgotten") memory can still
reach the LLM prompt if the Qdrant deindex step fails at delete time — the
delete path is fire-and-forget with no retry, and the retrieval path only
rank-penalizes deleted status instead of hard-excluding it (AMK-D-002,
HIGH). **Verdict: memory is safe (isolated) but not yet a working product
feature**, and has one real "forget me" trust gap.

---

## Garbage Collection / Memory Leaks

Full detail: `audit/track_C_findings.md` Phase 7. This session's own earlier
GC fix (semantic-cache Qdrant vectors with no TTL, commit `96fd24a5`)
independently re-verified correct and complete — reactive delete-on-expiry
plus hourly sweep, both confirmed wired and working, no regression. No
*other* live TTL-asymmetric cache pattern found. **Resource usage under a
realistic burst test did NOT stabilize — it crashed the backend**
(AMK-C-001, see Concurrency below) — this is the headline Phase 7 finding,
and it is a host-memory-overcommit issue, not a Python object leak; the
backend process itself never approached its own configured memory limit
when killed. Data-retention gap confirmed still open and unfixed
(`retention_days` stored, never enforced; zero Celery Beat cleanup jobs for
`chat_responses`/telemetry — AMK-C-003) plus a newly-found instance of the
same pattern for local compliance-audit JSONL files (AMK-C-004).

---

## Resource Lifecycle

Covered across Tracks A, C, E. CREATE→OWN→USE→RELEASE was traced for HTTP
clients, DB/Qdrant/Memgraph/Redis clients, temp files (upload path confirmed
cleaned up via `finally:` blocks, Track E), and asyncio tasks/futures
(coalescer's Redis-leader path correctly shields shared work from
cancellation via `asyncio.shield()`; the in-memory fallback path does NOT —
AMK-A-003, MEDIUM). File-descriptor-count verification inside the container
was **UNKNOWN** in both Track A and Track C — `docker exec` was denied by
this session's own permission policy on every attempt across multiple
tracks, a genuine tooling gap in the audit itself, not a claim that fd
leaks don't exist.

---

## Async / Concurrency

The single most important finding of this audit spans this section: **three
independent live-reproduced full-process crashes under concurrent load**,
different root causes:

1. Thread-pool exhaustion (Track A, AMK-A-001) at ~5-7 concurrent requests.
2. Host/VM memory overcommit (Track C, AMK-C-001) at 6 concurrent requests
   (below the app's own `max_concurrent_chat=8`).
3. ONNX/torch native `std::bad_alloc` (Track B, AMK-B-002), twice in 15
   minutes under moderate traffic, one requiring manual recovery.

See Phase 20 (cross-system) in the progress log for how these compound with
the verification-retry latency tax (AMK-F-008) and the job-queue crash-
recovery gap (AMK-C-002). Streaming/SSE concurrent-abort testing was only
PARTIAL (Track C ran out of budget recovering from crash #2) — client
mid-stream disconnect cleanup is UNKNOWN, not verified either way.

---

## Security / Privacy

Full detail: `audit/track_D_findings.md` Phase 8. **No CRITICAL security
findings.** Live-tested: cross-session IDOR (blocked, 404), prompt injection
(blocked by input guardrail — also independently confirmed in Track A's
Phase 3 testing), CORS (origin allowlist holds, no reflection), rate
limiting (429 enforced). RLS independently re-verified against live local
Postgres for all 92 AskMukthiGuru-owned tables (owner-scoped policies,
`auth.uid() = user_id` pattern) — NOT inherited from the prior production
audit claim in root CLAUDE.md. Findings: SSRF guard has a weaker duplicate
function with a real gap, though the actual live fetch path is not affected
(AMK-D-001, MEDIUM); most write endpoints lack idempotency protection or DB
unique constraints (AMK-D-003, MEDIUM). **Authenticated (JWT) cross-user
IDOR was NOT live-tested** — only anonymous-session isolation was exercised
— marked UNKNOWN. XSS in frontend markdown rendering also out of this
track's scope, UNKNOWN.

---

## Data Integrity

Full detail: `audit/track_D_findings.md` Phase 9. Live crash-simulation was
judged too risky against shared dev-environment state, so this phase is
code-analysis-based rather than live-reproduced (contrast with Tracks A/B/C,
which reproduced crashes live in the concurrency phases and surfaced real
data-integrity consequences as a side effect — AMK-C-002 stuck jobs,
AMK-C-005 duplicate memory writes). The soft-delete-orphaned-vector pattern
(AMK-D-002) is the clearest concrete data-integrity finding from this
track. No DB unique constraints back up most write paths (AMK-D-003).

---

## Attachments / OCR / Whisper

Full detail: `audit/track_E_findings.md` Phase 10. **PASS, minor findings.**
End-user uploads live-tested directly against the running server: properly
bounded (10MB/file, 50MB total, 25MB audio), ephemeral (not
persisted/indexed), MIME-sniffed from magic bytes not client headers, temp
files cleaned up via `finally:` blocks, both OCR (30s) and Whisper (60s)
timeout-bounded. Oversized/empty/malformed/unsupported uploads all behaved
correctly except: a malformed image rides out the full 30s OCR timeout
instead of failing fast on decode (AMK-E-004, LOW). Admin/ingestion uploads
are a separate risk class, not covered by this track.

---

## LLM Providers / Failover

Full detail: `audit/track_E_findings.md` Phase 11. Cross-provider failover
is **confirmed fully dead** — not just the documented "NIM removed":
`services/failover_provider.py` doesn't exist anymore, and two OTHER
failover-shaped objects (`MultiProviderLLMService`, `SarvamFailoverService`)
are fully wired into the container but have zero consumers anywhere in the
request path (verified by grep, AMK-E-003, LOW — dead code, not a live
risk, but startup cost for no benefit). Real resilience that DOES exist and
was live-tested: bounded OpenRouter retries, same-provider model fallback on
429/5xx, a circuit breaker, Redis-backed cross-replica rate limiting. Real
gap found: an invalid API key gets pointlessly retried then leaks a raw
exception to the end user instead of a friendly message (AMK-E-002,
MEDIUM). **"PRIMARY FAILURE → FALLBACK → VALID RESPONSE" cannot currently
be demonstrated across providers** — only within OpenRouter's own model
fallback.

---

## Redis / Celery

Full detail: `audit/track_C_findings.md` Phase 12. **"What happens if a
worker dies halfway through a task?"** — for the memory outbox: it gets
correctly reclaimed after 10 minutes, but the 4 enrichment side-effect
writes are not idempotent, so reclaim duplicates them (AMK-C-005, MEDIUM,
narrow window but the trigger was live-reproduced this session). For the
job queue (`job_queue.py`): jobs already claimed when the process dies are
**never reclaimed at all** — no staleness sweep exists for the
already-claimed state, only for jobs never claimed or gracefully cancelled
(AMK-C-002, HIGH, launch blocker — directly caused by and will recur with
any future crash). **"Can the same job execute twice safely?"** — UNKNOWN
in general; the memory outbox specifically cannot (AMK-C-005).

---

## Supabase / Database / RLS

Full detail: `audit/track_D_findings.md` Phase 14. Local dev Supabase
confirmed a genuinely separate instance from production (Phase 8/14
combined finding, resolving Phase 0's open unknown), also a *shared* dev
instance hosting an unrelated app's tables. All 92 AskMukthiGuru tables have
RLS enabled with correct owner-scoped policies, independently re-verified
live. But per the cross-system synthesis (Phase 20, item 4): this DB-level
soundness has never been exercised through a real authenticated UI session
in this environment, because of AMK-B-001. Backup/recovery: RPO unbounded
per this session's own earlier finding (backup cron never installed),
confirmed still accurate, not re-litigated by this audit.

---

## Streaming

Covered in Track F (Phase 17) and Track C (Phase 13, partial). A live SSE
capture directly confirmed the verification-retry mechanism streams TWO
distinct full-answer generations back-to-back to the client on a
first-draft failure (AMK-F-008) — the user visibly sees the answer restart
partway through. The streaming path has no per-node timing instrumentation,
unlike the sync path (AMK-F-004, MEDIUM) — this made diagnosing AMK-F-008
harder than it should have been. Concurrent-SSE and mid-stream-disconnect
testing did not complete (Track C ran out of budget after crash recovery) —
UNKNOWN.

---

## Docker / Deployment

Full detail: `audit/track_E_findings.md` Phase 15. `docker kill` →
`restart: unless-stopped` recovery measured at **~120s total** (101s to
restart trigger + 19s running + 30s healthy); a real chat call succeeded
post-recovery. Non-root runtime confirmed (UID 1000 via `gosu`), no baked-in
secrets (BuildKit secret mounts). Memory: backend had real headroom
(2.8-3.3GB/6GB) in Track E's test — but Track C's later, heavier burst test
crashed it anyway via host-level overcommit (AMK-C-001), showing per-
container headroom alone doesn't guarantee survival. Memgraph confirmed at
633-645MB/1GB (62-63%), 6-10x CLAUDE.md's documented idle figure, still real
and unchanged from earlier this session (AMK-F-009, LOW). Config drift
found: Dockerfile wants a 420s health-check `start_period` for cold model
downloads, `docker-compose.yml` silently overrides to 180s (AMK-E-006,
MEDIUM — latent risk on a genuinely cold deploy).

---

## Graceful Shutdown / Recovery

`restart: unless-stopped` recovered correctly from a clean `docker kill` in
Track E's test (~120s). It did **not** reliably recover from the harder
`std::bad_alloc`/SIGKILL crash class Track B hit — one crash left the
container in `Exited` state requiring a manual `docker start`, because
neither Docker's restart policy nor the `autoheal` sidecar (which only
watches HEALTHCHECK "unhealthy" transitions, not full container death) fired
for that specific failure shape (AMK-B-002, part of the same finding). This
means recovery reliability depends on *which* crash mode is hit, which is
itself unpredictable — a real single point of failure on the documented
single-replica Railway deployment.

---

## Observability

Full detail: `audit/track_F_findings.md` Phase 16. Real and good: JSON
structured logging with PII scrubbing, correlation IDs propagating through
nearly every log line, real per-request LLM cost logging. Not real:
distributed tracing (`OTEL_ENABLED=true` by default, Jaeger never actually
running, silent no-op — AMK-F-001), server-side error tracking (stdout logs
only — AMK-F-003). **A live, naturally-occurring bug was caught mid-audit**:
telemetry Postgres inserts still failing on unguarded integer columns
(`start_ms`/`duration_ms`/`top_k`) despite a 2026-09-17 fix that only
patched 4 of the affected columns — and the resulting error log carries no
correlation_id either, because `contextvars` don't propagate through
`loop.run_in_executor` (AMK-F-002, MEDIUM-HIGH). This directly undermines
`hallucination_anomaly.py`'s ability to detect a real spike. For a real
failed request today: WHO/WHAT/WHEN are answerable from logs; WHERE/WHY
partially (per-node timing exists on sync path only); DEPENDENCY/COST are
answerable (CHAT_COST lines); RECOVERY is answerable only by manually
checking `docker inspect`, not any dashboard.

---

## Performance

Full detail: `audit/track_F_findings.md` Phase 17, and this session's own
earlier §4E measurements (`docs/GURU_DEMO_READINESS.md`). Three
demo-safe-benchmark runs today: latency_p95 70.67s (PASS) / 148.78s (FAIL) /
106.9s (FAIL) — fails more often than it passes against the 90s gate.
must_mention coverage similarly unstable: 0.37→0.45→0.53(PASS)→0.60(PASS)→
0.40(FAIL) across 5 runs. Root CLAUDE.md's documented per-stage latency
breakdown confirmed stale (`navigate_and_hyde` documented 5.4s, observed
live 32.8s). The verification-retry double-generation (AMK-F-008) is now
the confirmed, not merely suspected, mechanism behind the latency
instability.

---

## Scalability

At the concurrency levels this audit tested (5-8 simultaneous requests, well
within the app's own configured `max_concurrent_chat=8`), the service
crashes via three independent mechanisms (see Async/Concurrency). This is
not a "what happens at 10x scale" question — it is a "does not survive
1x-of-its-own-configured-ceiling" finding. Root CLAUDE.md's own SPOF policy
table targets 5-15 QPS at the "1k Tier" pilot stage; this audit did not
reach QPS-scale load, only concurrent-request-count, and already found the
ceiling lower than configured.

---

## Cost

Per-query LLM cost is logged (`CHAT_COST`) and was independently confirmed
live. The verification-retry mechanism (AMK-F-008) doubles cost on the
fraction of queries whose first draft fails verification — not a rare case,
per this session's own repeated benchmark runs. No spend cap/circuit breaker
beyond the existing provider-level circuit breaker was found. Unbounded
`chat_responses`/telemetry retention (AMK-C-003) is a slow-growing cost risk
on the Supabase side, compounding indefinitely.

---

## Testing

Full detail: `audit/track_F_findings.md` Phase 18. **Real numbers, both
sides run for the first time this session:**

| Suite | Result |
|---|---|
| Backend pytest | 7266 passed / 0 failed / 12 skipped (379s) |
| Frontend Vitest | 555 passed / 0 failed / 6 skipped, 98 files |
| Frontend `tsc -b` (typecheck) | **FAILS, 14 real errors**, incl. genuine API-drift bug (`ChatMessage.tsx:439`) |
| Frontend ESLint | 10 errors, 40 warnings, incl. 9 empty-catch blocks in auth-adjacent files |
| E2E (Playwright) | page-smoke 14/14 PASS; seeker-journey 0/2 FAILED (plausibly this audit's own concurrent load, not confirmed clean); 14/16 specs not run |

No dedicated concurrency/load test exists in the repo as a CI gate — every
crash this audit found was reproduced ad hoc, not caught by an existing
test. No dedicated cross-user-isolation test exists as an automated
regression either (this audit's Phase 6 isolation test was manual).

| Critical Workflow | Unit | Integration | E2E | Failure Test | Security Test | Load/Memory Test |
|---|---|---|---|---|---|---|
| Chat/RAG answer | Yes | Yes | Partial | Yes | Partial | **No — audit was first** |
| Memory write/read | Yes | Yes | No (blocked) | Partial | Yes (isolation) | No |
| Auth | Partial | Partial | **Blocked (AMK-B-001)** | Unknown | Partial | No |
| File upload | Yes | Yes | Unknown | Yes | Partial | No |
| Second Brain | No (feature down) | No | No | No | No | No |

---

## UX / Product

Full detail: `audit/track_B_findings.md` Phase 19. Anonymous/error/mobile
surfaces verified. Real bugs found: "tell me more" stuffs the entire
previous answer including internal redaction commentary into the next
composer turn (AMK-B-003), which then got misclassified as distress and
redirected to a safety prompt instead of continuing the teaching
(AMK-B-004) — a real, live-reproduced break in a common follow-up flow. A
stale `NET_OFFLINE` banner doesn't clear after a successful retry
(AMK-B-005, LOW). Mobile empty-state for a fresh conversation lacks desktop's
welcome copy (AMK-B-008, LOW). Authenticated-surface UX (Profile, Settings,
Second Brain UI, Knowledge Graph, Study Notebook) is **UNKNOWN** — blocked
by AMK-B-001, not verified either way.

---

## Technical Debt

- Dead failover code fully wired but unreachable (AMK-E-003).
- `llm_cache.py` docstring/log claims Qdrant usage; actual implementation is
  a bounded local map (AMK-C-006) — misleading to a future engineer.
- Three declared Prometheus metrics are dead code (AMK-F-005); no
  queue-depth/Celery metrics exist (AMK-F-006).
- Root CLAUDE.md's documented latency-stage breakdown and Memgraph idle-RAM
  figure are both stale (AMK-F-007, AMK-F-009) — a recurring pattern of
  documentation drift from measured reality this session found repeatedly,
  not a one-off.
- Several terminal LangGraph nodes write `verification` dicts missing a
  documented-mandatory key (AMK-A-004) — no test enforces the documented
  invariant.
- 3 backend tests have an un-awaited `AsyncMock` coroutine (AMK-F-013) —
  may not exercise what they assert.

---

## Unknowns

Explicitly not verified either way by this audit — do not treat silence as
either "safe" or "broken":

- Corpus-wide misattribution rate beyond 30 independently-confirmed
  questions (out of ~1,200+ in the full bank).
- Authenticated (JWT) cross-user IDOR (only anonymous-session isolation was
  live-tested).
- XSS in frontend markdown/LLM-output rendering.
- File-descriptor leak behavior inside the container (`docker exec` denied
  to the audit throughout).
- Whether the thread-exhaustion ceiling (AMK-A-001) is a container ulimit,
  cgroup pids limit, or native-library thread accumulation — only the
  failure symptom was confirmed, not the exact mechanism.
- Concurrent-SSE and mid-stream-disconnect cleanup behavior.
- Knowledge Graph views, Study Notebook/SRS, Profile/Settings, cancel/
  win-back flow, EU AI Act compliance status, most of `admin.py` (77K
  lines) — not reached by any track this audit.
- Whether other soft-delete/TTL-asymmetric patterns exist beyond the two
  found (semantic cache, already fixed; canonical memory, AMK-D-002).
- Whether Railway (currently paused) would reproduce the same
  concurrency-crash findings under its own actual memory allocation, or
  whether the local-Docker-Desktop-VM-specific overcommit (AMK-C-001) is
  purely a local artifact.

---

## Exact Remaining Work

See Master Pending Table and Top 20 below for the itemized list with fixes,
tests, and verification steps. At a category level:

1. Fix the 3 independent crash-under-load root causes (thread exhaustion,
   memory overcommit, ONNX/torch allocation) before any real concurrent
   traffic.
2. Fix the frontend/backend Supabase environment split so authenticated
   flows are testable at all.
3. Configure `BRAIN_KEK` (or explicitly descope Second Brain from launch).
4. Add job-queue crash recovery (stale "processing" sweep).
5. Fix the frontend typecheck failures, especially the genuine API-drift bug.
6. Wire distributed tracing or accept and document that production
   incidents will be diagnosed via manual log archaeology.
7. Fix the telemetry integer-coercion gap so the hallucination-anomaly
   monitor can be trusted.
8. Decide the memory feature's actual launch scope (currently: isolated but
   inert).
9. Add a load/concurrency test to CI so crash findings like today's are
   caught automatically, not discovered by an audit.
10. Push the 13 local commits (including this audit's own fixes and this
    document) to `origin/main` — currently blocked by this session's
    permission layer.

---

## Master Pending Table

41 findings total across 6 tracks. CRITICAL and HIGH shown in full below
this table (Top 20 section); MEDIUM/LOW summarized here with a pointer to
the owning track file for complete Evidence/Root Cause/Fix/Test detail.

| ID | Issue | Category | Severity | Launch Blocker | Track File |
|---|---|---|---|---|---|
| AMK-A-001 | Thread-pool exhaustion crashes backend under modest concurrent load | Concurrency | CRITICAL | YES | track_A |
| AMK-A-002 | `cache_stage.py:342` unguarded `asyncio.to_thread` turns degradation into total failure | Concurrency | HIGH | NO (bundled w/ 001) | track_A |
| AMK-A-003 | In-memory coalescer fallback doesn't shield shared work from cancellation | Concurrency | MEDIUM | NO | track_A |
| AMK-A-004 | Terminal nodes write `verification` dicts missing documented `citations_verified` key | Correctness/Debt | LOW | NO | track_A |
| AMK-B-001 | Frontend auth targets production Supabase, backend targets local — real login broken in dev | Config/Environment | CRITICAL | YES | track_B |
| AMK-B-002 | Backend crashes under moderate concurrent load (ONNX/torch `std::bad_alloc`); auto-restart unreliable | Concurrency | CRITICAL | YES | track_B |
| AMK-B-003 | "Tell me more" injects entire previous answer as literal prompt text | UX/Correctness | MEDIUM | NO | track_B |
| AMK-B-004 | Benign follow-up misclassified as distress, redirected to safety prompt | UX/Correctness | MEDIUM | NO | track_B |
| AMK-B-005 | Stale `NET_OFFLINE` banner doesn't clear after successful retry | UX | LOW | NO | track_B |
| AMK-B-006 | Canonical memory stored/isolated correctly but never surfaces in chat answers | Correctness | MEDIUM | NO | track_B |
| AMK-B-007 | Second Brain 100% non-functional — `BRAIN_KEK` not configured | Config | HIGH | YES (for that feature) | track_B |
| AMK-B-008 | Mobile empty-state lacks desktop welcome copy | UX | LOW | NO | track_B |
| AMK-C-001 | Backend OOM-killed by host-VM memory overcommit under load within its own concurrency ceiling | Concurrency/GC | CRITICAL | YES | track_C |
| AMK-C-002 | Jobs claimed by a crashed worker never reclaimed; client polling hangs forever | Data Integrity/Redis | HIGH | YES | track_C |
| AMK-C-003 | No Supabase data-retention enforcement despite `retention_days` metadata | Data Hygiene | MEDIUM | NO | track_C |
| AMK-C-004 | Local compliance-audit JSONL files never deleted | GC/Disk | LOW/MEDIUM | NO | track_C |
| AMK-C-005 | Memory-outbox enrichment writes not idempotent; crash+reclaim duplicates them | Data Integrity | MEDIUM | NO | track_C |
| AMK-C-006 | `llm_cache.py` docstring/log claims Qdrant usage; actual impl is a local map | Tech Debt | LOW | NO | track_C |
| AMK-D-001 | SSRF pre-check lacks DNS resolution (weaker duplicate of the real guard) | Security | MEDIUM | NO | track_D |
| AMK-D-002 | Soft-deleted memories can still reach the LLM prompt after a Qdrant deindex failure | Data Integrity/Privacy | HIGH | NO | track_D |
| AMK-D-003 | Only 2 of many write endpoints are idempotency-protected | Data Integrity | MEDIUM | NO | track_D |
| AMK-E-002 | Invalid LLM API key wastes retries then leaks raw exception to user | Reliability | MEDIUM | NO | track_E |
| AMK-E-003 | Dead cross-provider failover code wired but unreachable | Tech Debt | LOW | NO | track_E |
| AMK-E-004 | Malformed image upload doesn't fail fast (rides out full OCR timeout) | Reliability | LOW | NO | track_E |
| AMK-E-005 | No server-side visibility into `/tmp` cleanup (tooling gap) | Unknown | LOW | NO | track_E |
| AMK-E-006 | Healthcheck `start_period` drift (180s compose vs 420s Dockerfile intent) | Deployment | MEDIUM | NO | track_E |
| AMK-E-007 | ~2min full outage on hard crash, single replica, no fast-path | Deployment | MEDIUM | NO | track_E |
| AMK-F-001 | Distributed tracing configured but non-functional (Jaeger never running) | Observability | MEDIUM | NO | track_F |
| AMK-F-002 | Telemetry sink write failures, correlation-blind, unguarded integer column still live | Observability | MEDIUM-HIGH | NO | track_F |
| AMK-F-003 | No server-side error-tracking/alerting integration | Observability | MEDIUM | NO | track_F |
| AMK-F-004 | Streaming path has no per-node latency breakdown | Observability | MEDIUM | NO | track_F |
| AMK-F-005 | Three declared Prometheus metrics are dead code | Observability | LOW | NO | track_F |
| AMK-F-006 | No queue-depth/Celery metrics | Observability | LOW | NO | track_F |
| AMK-F-007 | Root CLAUDE.md's documented latency-stage breakdown is stale (6x off) | Tech Debt/Docs | MEDIUM | NO | track_F |
| AMK-F-008 | Verification-retry pays a full duplicate-generation tax, live-confirmed | Performance | HIGH | Contributes to existing blocker | track_F |
| AMK-F-009 | Memgraph RAM 6-10x documented idle figure | Tech Debt/Docs | LOW | NO | track_F |
| AMK-F-010 | Frontend `tsc -b` fails, 14 real errors incl. genuine API-drift bug | Testing/Correctness | MEDIUM | UNKNOWN (depends on build config) | track_F |
| AMK-F-011 | ESLint 10 errors/40 warnings incl. 9 empty-catch in auth-adjacent files | Testing | LOW-MEDIUM | NO | track_F |
| AMK-F-012 | E2E chat-flow test failed under this audit's own concurrent load; root cause unconfirmed | Testing | LOW (potentially HIGH) | NO | track_F |
| AMK-F-013 | 3 backend tests have an un-awaited `AsyncMock` coroutine | Testing | LOW | NO | track_F |
| AMK-F-014 | Potentially-stale OKF test skips (predate a same-session doctrine sync) | Testing | LOW | NO | track_F |

---

## Top 20 — Items Before Real Users

Ranked by actual risk, not implementation convenience. Full Evidence/Root
Cause/Fix/Test/Verification for the CRITICAL and HIGH items below; the
remaining slots point to the Master Pending Table above (all MEDIUM,
genuinely lower-risk than the top 12).

### 1. AMK-A-001 — Thread-pool exhaustion crashes the backend under modest concurrent load
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_A_findings.md`. Reproduced live: ~5-7 concurrent
chat requests → `RuntimeError: can't start new thread` at multiple call
sites → container `RestartCount` incremented, ~1 minute total
unreachability. Fix: guard the unguarded `cache_stage.py:342` call
(immediate), then root-cause and either raise the container's thread
ceiling or move blocking calls to a bounded, capacity-planned executor.
Test: a load test asserting zero `"can't start new thread"` occurrences and
zero error-fallback responses at ≥5 concurrent real requests, added to CI.

### 2. AMK-C-001 — Backend OOM-killed by host/VM memory overcommit under load
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_C_findings.md`. 40 requests at concurrency 6 (below
the app's own `max_concurrent_chat=8`) → 11/40 succeeded, then `Exited
(137)`, ~102s downtime, external watchdog recovery only. Configured
per-container memory limits (≥10.5GiB) exceed actual available VM memory
(7.75GiB). Fix: re-derive a safe concurrency ceiling against actual
available memory (production sizing, not local Docker Desktop), and/or
reduce configured limits to have real headroom. Test: same load pattern
against production-representative memory sizing, asserting the container
stays running with headroom, not just "didn't die this time."

### 3. AMK-B-002 — Backend crashes twice in 15 minutes under moderate load (ONNX/torch `std::bad_alloc`); recovery unreliable
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_B_findings.md`. Reranker/LettuceDetect ONNX+torch
native memory pressure crashes the process; one crash left the container in
`Exited` state that neither `restart: unless-stopped` nor `autoheal` (which
only watches HEALTHCHECK transitions, not full container death) recovered
from automatically — required a manual `docker start`. Fix: cap
reranker/LettuceDetect concurrency independently of the general chat
admission control; extend the watchdog to cover `Exited`/non-running states,
not just "unhealthy". Test: sustained 6-10 concurrent chat load for several
minutes as a pre-release gate, asserting `docker inspect .State.Status`
stays `running` throughout.

### 4. AMK-B-001 — Frontend auth targets production Supabase, backend targets local — real login broken in dev, and a possible accidental-prod-write risk
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_B_findings.md`. `.env.local`'s `VITE_SUPABASE_URL`
points at the production project (`ozmjeuqbholoxypfxixb`); `backend/.env`
points at local Supabase. A user created via one is invisible to, and can't
authenticate against, the other. Fix: align both to local Supabase for dev
(per root CLAUDE.md's own documented intent), or explicitly document and
support a production-frontend/local-backend split if that's ever
intentional. Test: an E2E test that signs up, logs in, and successfully
calls one authenticated backend endpoint, added to the Playwright suite.

### 5. AMK-B-007 — Second Brain is 100% non-functional (`BRAIN_KEK` not configured)
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_B_findings.md`. Every vault endpoint 500s for every
user; root cause is an unset required env var with no startup-time
fail-fast check. Fix: set `BRAIN_KEK` in the target deployment's env, and
add a startup health check that fails loud if it's missing rather than
letting the feature silently 500 per-request. Test: a startup-time
assertion test, plus re-running this session's cross-user isolation
pattern against Second Brain once it works.

### 6. AMK-C-002 — Jobs claimed by a crashed worker are never reclaimed; client polling hangs forever
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_C_findings.md`. Directly caused by and reproduced
alongside findings #1-3 above. `job_queue.py`'s recovery only covers
never-claimed jobs and gracefully-cancelled ones, not jobs whose worker
process disappeared mid-work. Fix: a staleness sweep (mirroring the working
10-minute pattern already used for the memory outbox) that requeues or
fails stuck "processing" jobs. Test: simulate a stuck claimed job, run the
sweep, assert it resolves to a terminal state.

### 7. AMK-D-002 — Soft-deleted memories can still reach the LLM prompt after a Qdrant deindex failure
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_D_findings.md`. Delete path swallows Qdrant errors
silently with no retry; retrieval path only rank-penalizes deleted status
instead of hard-excluding it. Violates the "forget this" promise. Fix:
hard-filter `status != "active"` before ranking in
`CanonicalMemoryRetriever.retrieve()` (the fix pattern already exists
correctly in `second_brain_service.py::crypto_shred` — just port it), and/or
route deindex failures through the existing `memory_outbox` for retry. Test:
seed a `status="deleted"` candidate with a high score, assert it never
appears in retrieval results.

### 8. AMK-F-008 — Verification-retry pays a full duplicate-generation tax, live-confirmed
**Problem → Evidence → Root Cause → User Impact → Fix → Test**: see full
writeup in `audit/track_F_findings.md`. A captured SSE transcript shows two
distinct full-answer generations (different cited videos each pass) for one
user-visible response. This is the confirmed mechanism behind the
already-tracked latency instability. Per this session's own stated position,
the fix direction is reducing first-draft failure frequency (better
grounding), not removing the safety retry. Test: assert `generate_answer`'s
call count per request matches expectation (1, or 2 only when
`grounded_partial_fallback` legitimately fires).

### 9. Frontend typecheck failures (AMK-F-010) — 14 real TS errors, including a genuine runtime bug
`ChatMessage.tsx:439` calls a method (`transport.getAccessToken`) that
doesn't exist on that module — a real, live bug, not lint noise. Fix: fix
the 14 errors, starting with the API-drift one; add `tsc -b` to a required
CI gate if it isn't already. Test: `npm run typecheck` passing is the test.

### 10. AMK-C-005 — Memory-outbox enrichment writes are not idempotent
Reclaim after a crash (the exact crash class reproduced by findings #1-3)
duplicates episodic/L1/L2 memory writes. Fix: key each write by
`outbox_id`, check-before-insert. Test: simulate crash-before-mark-processed,
reclaim, assert writes aren't duplicated.

### 11. AMK-F-002 — Telemetry writes still failing on an unguarded integer column; undermines hallucination monitoring
A 2026-09-17 fix only patched 4 of the affected columns. Fix: extend the
existing `_coerce_int` guard to `start_ms`/`duration_ms`/`top_k`; also fix
correlation-id propagation through `loop.run_in_executor`. Test: insert a
row with a decimal-string value in each currently-unguarded column, assert
no write failure.

### 12. AMK-E-006/E-007 — Healthcheck drift and ~2min recovery window
Fix the `start_period` mismatch (180s vs 420s intended); consider whether a
2-minute single-replica outage window is acceptable for launch or needs a
faster-recovery mechanism. Test: cold-start timing test against the
corrected `start_period`.

### 13-20. See Master Pending Table for: AMK-B-003/004 (follow-up UX bugs),
AMK-D-001 (SSRF guard duplicate weakness), AMK-D-003 (idempotency gaps),
AMK-C-003/004 (data retention), AMK-E-002 (leaked exception on bad API key),
AMK-F-001/003 (dead observability tooling). All MEDIUM, all with fixes and
tests documented in their owning track file.

---

## Final Verdict

### VERIFIED WORKING

- Top-severity misattribution guarantee: 0% across 30 independently
  ground-truthed questions today (6 live adversarial/grounded/unsupported
  tests, plus a repeated 12-question demo-safe benchmark run 3 times),
  including live-observed unsupported-claim redaction firing correctly and
  all adversarial fabrication attempts failing to produce sourced
  invention.
- Cross-user data isolation: tested directly with two real accounts, no
  leakage found via API or chat, at either the code/RLS level (Track D) or
  the functional level (Track B).
- Hybrid RAG retrieval, Memgraph KG expansion, LightRAG, and OKF
  curated-doctrine fallback are all real and live, not stubs or
  aspirational documentation.
- End-user file/audio upload handling is properly bounded, validated, and
  cleaned up.
- Backend and frontend unit/integration test suites both genuinely pass
  (7266/0 and 555/0 respectively) — the first time the frontend suite was
  run at all this session.
- No infinite-loop or unbounded-recursion risk in the LangGraph pipeline;
  all rewrite/retry paths are provably capped.

### NOT READY

- The backend crashes under realistic concurrent load via three
  independent, live-reproduced mechanisms, at load levels its own
  admission control considers safe.
- No authenticated user journey (signup → login → use any authenticated
  feature) currently works end-to-end in this dev environment, due to a
  frontend/backend Supabase configuration mismatch.
- Second Brain is completely non-functional (missing required
  configuration).
- Jobs orphaned by a worker crash — which this audit reproduced live,
  repeatedly — are never recovered; affected users wait forever with no
  error.
- A "forget this" memory deletion can silently fail to actually stop a
  memory from being used.
- Distributed tracing and error tracking are both configured but
  non-functional — production incidents matching the ones found today would
  require manual log archaeology to diagnose.
- Frontend typecheck fails, including a genuine (not cosmetic) API-drift
  bug.
- 13 local commits, including all of this session's fixes and this audit
  itself, are not pushed to `origin/main`.

### UNKNOWN

- Corpus-wide misattribution rate beyond the 30 questions checked today
  (~1,200 remain unverified against current code).
- Authenticated (JWT) cross-user IDOR — only anonymous-session isolation
  was live-tested.
- XSS exposure in frontend markdown/LLM-output rendering.
- File-descriptor leak behavior inside the container (tooling access
  denied to this audit throughout).
- The exact OS-level ceiling behind the thread-exhaustion crash (symptom
  confirmed, mechanism not).
- Whether Railway (currently paused) reproduces the same memory-overcommit
  crash under its own actual allocation, or whether that finding is
  specific to this local machine's Docker Desktop VM sizing.
- Most of Knowledge Graph views, Study Notebook/SRS, Profile/Settings,
  cancel/win-back flow, EU AI Act compliance status, and the 77K-line admin
  surface — not reached by any track.

### LAUNCH CONDITIONS

Before this can safely serve real users:

1. Fix or mitigate all three independent crash-under-load mechanisms
   (AMK-A-001, AMK-B-002, AMK-C-001) and demonstrate survival under
   sustained realistic concurrent traffic on production-representative
   infrastructure sizing (not local Docker Desktop).
2. Fix the frontend/backend Supabase environment mismatch (AMK-B-001) and
   demonstrate one complete real authenticated user journey end-to-end.
3. Either fix Second Brain (AMK-B-007) or explicitly descope it from the
   initial launch surface.
4. Add job-queue crash recovery (AMK-C-002) so a crash (which WILL happen —
   this audit proved it happens under normal load, not just adversarial
   conditions) doesn't leave users waiting forever.
5. Fix the canonical-memory soft-delete gap (AMK-D-002) before making any
   "forget this" promise to users in copy or marketing.
6. Fix the frontend typecheck failures (AMK-F-010), especially the genuine
   API-drift bug.
7. Either make tracing/error-tracking actually work (AMK-F-001, AMK-F-003)
   or have an explicit, accepted operational plan for diagnosing incidents
   without them.
8. Add a load/concurrency test to CI so the launch-blocking findings in
   this document cannot silently regress once fixed.
9. Push everything to `origin/main` and get eyes on this document from
   whoever owns the launch decision — it should not sit as an
   uncommitted/unpushed local artifact.

None of the above requires a rewrite. The core safety mechanism the product
exists to guarantee — not putting invented words in a living teacher's
mouth — is real and holds up under adversarial testing. What's missing is
concentrated in reliability-under-load and a handful of configuration/
completeness gaps, not architecture.
