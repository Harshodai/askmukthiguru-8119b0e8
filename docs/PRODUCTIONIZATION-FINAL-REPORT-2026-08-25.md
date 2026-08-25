# AskMukthiGuru Adversarial Productionization Report

**Date:** 2026-08-25
**Executive verdict:** **NOT PRODUCTION READY**
**Release color:** **RED**

## Executive verdict

This was a closed-loop engineering exercise rather than a static review. The repository was mapped, exercised, red-teamed, changed where concrete defects were proven, regression-tested, re-run through the canonical loop, and documented. The final code-validation loop passed, but the release is not production-ready because critical runtime readiness is false, retrieval quality lacks a valid matching evaluation corpus, browser E2E stalled, integration dependencies remain skipped, and recovery/capacity evidence is incomplete.

> A passing unit/build gate does not override a false readiness contract or missing production evidence.

## Biggest risks

| Rank | Risk | Severity | Evidence |
|---:|---|---|---|
| 1 | Critical `okf_compiled` runtime artifact is absent and `/api/health` reports `ready=false`. | P1 | Local readiness payload reproduced the failure. |
| 2 | Retrieval quality is unproven because the configured contextual Qdrant source identifiers do not match the golden labels. | P1 | Four quality cases skip; strict mode remains required. |
| 3 | Browser E2E did not complete. | P1 | Two bounded 300-second waits produced no output; process stopped. |
| 4 | Restore/RPO/RTO and worker-restart behavior are not proven. | P1 | No completed disposable recovery drill. |
| 5 | 10x/100x capacity, provider cost, and chat completion latency are not measured. | P1 | Local chat probes were limited by 429/readiness state. |
| 6 | Redis, Supabase, Neo4j, optional model, and OKF integration tests are skipped when services/artifacts are unavailable. | P1 | Full suite: 2,390 passed, 30 skipped, 1 warning. |

## What was fixed

The retrieval-evaluation harness now detects empty or label-mismatched collections, skips honestly by default, and fails explicitly when `REQUIRE_QDRANT_EVAL=1`; it no longer writes a false zero baseline. The benchmark no longer uses `shell=True` or global Redis `FLUSHALL`, and regression tests protect the scoped cache behavior. Corpus-audit URL access is restricted to absolute HTTP(S) URLs without credentials, query, or fragment.

The Bandit configuration was corrected to an INI argument file and CI plus the canonical loop now invoke it consistently. Test execution defaults OTEL off to avoid ordinary-suite collector noise while preserving explicit integration opt-in. The load harness distinguishes completed HTTP 200 responses from queued HTTP 202 acknowledgements and records that 202 is not completion.

The frontend gained `/guides` and `/support` compatibility redirects, removing the observed top-level hard 404s. The Second Brain failure state now explains that the encrypted vault is separate from Profile Memory and provides a Profile Memory fallback link. Route, load-contract, URL-validation, cache-safety, and Second Brain regressions were added.

## What was verified

| Surface | Result |
|---|---|
| Canonical loop | `LOOP_RESULT=PASS` at `/tmp/askmukthi_audit/loop-final4-20260825`. |
| Backend full suite | 2,390 passed, 30 skipped, 1 warning. |
| Security/isolation/queue/memory/upload/prompt focus | 62 passed. |
| AI-safety/prompt red-team | 61 passed. |
| Privacy/data-integrity | 41 passed. |
| New backend regressions | 12 passed. |
| Frontend route regressions | 5 passed. |
| Second Brain contract regression | 1 passed. |
| Static/security gates | Frontend lint/typecheck/build/bundle, Ruff, Bandit, regex safety, compile, and npm audit passed. |
| Browser E2E | Unavailable after bounded no-output stall; not marked pass. |

## Scalability findings

A ten-user synthetic health wave returned HTTP 200 with p50 87.5 ms and maximum 181.6 ms, but 0/10 were ready. A two-user synthetic chat wave returned HTTP 429 for both requests. The pre-fix load harness saw four 202 admissions and twenty-two 429 responses but called all of them failures; this measurement defect was fixed. A corrected five-second run still saw twenty 429 responses due to local quota/admission state. No chat throughput, queue-completion p95/p99, 10x, or 100x capacity claim is valid.

The first observed bottleneck was readiness/admission state rather than CPU saturation. The next experiment must use clean quota namespaces, unique synthetic identities, provisioned workers/providers, queue completion polling, and CPU/memory/provider/token/embedding/cache telemetry.

## Observability status

Health exposes per-service status, latency, criticality, queue size, and backpressure state. The local payload correctly identified `runtime_artifacts` as critical and missing `okf_compiled`. Structured telemetry, Sentry hooks, and OTEL support exist, and ordinary tests no longer depend on a live Jaeger collector. Trace continuity, alert routing, redaction under failure, and production SLO enforcement remain unverified.

Recommended SLIs are API availability, accepted-to-completed queue latency, time to first token, completion latency, grounded-answer rate, safe-abstention rate, 429 rate, provider/retrieval failure rate, queue depth, and oldest job age. HTTP 200 must not be used as a readiness proxy.

## Security status

Targeted authz, tenant-context, cache-isolation, job-ownership, upload, prompt-injection, streaming-guardrail, memory, privacy, and data-integrity tests passed. Bandit now uses the intended configuration and reports zero medium/high issues; npm audit reports zero high production dependency vulnerabilities. The gitleaks result covered approximately zero commits/bytes and is not historical proof.

Live disposable RLS/BOLA, session expiry, provider abuse, parser resource exhaustion, rate-limit isolation, log redaction, and historical secret-scan scope remain required. No secret was printed, rotated, or changed.

## Performance: baseline versus improvement

The measured baseline was a health-only local wave at p50 87.5 ms and maximum 181.6 ms, with chat blocked by 429s. The principal performance-related improvement was measurement correctness: the load harness now reports 200 completion and 202 queue acknowledgement separately, preventing false failure counts. No application throughput improvement is claimed, and no before/after provider-cost or chat-latency optimization has been justified.

Frontend bundle output remained within configured limits in the final loop: 135 JavaScript files, largest chunk 390.98 kB, with the bundle gate passing. This is a build-budget result, not a backend capacity result.

## Reliability outcomes

Queue admission, cancellation, owner scoping, streaming completion, cache isolation, tenant context, malformed upload, and safety paths passed focused tests. HTTP 429 backpressure and HTTP 202 queue semantics were observed locally. The remaining reliability gaps are worker restart/duplicate delivery, dependency recovery, partial writes, cross-store purge, backup restoration, and rollback behavior in a disposable release-like topology.

## Scorecard

| Dimension | Score / 5 | Blocking issue |
|---|---:|---|
| Architecture | 4 | Deployment and recovery edges need live proof. |
| Correctness | 4 | One stub warning; external behavior not fully exercised. |
| Testing | 3 | Broad local coverage, material integration/E2E skips. |
| Security | 3 | Strong targeted controls; live RLS and historical scan gaps. |
| Scalability | 1 | Chat capacity and 10x/100x behavior unmeasured. |
| Reliability | 2 | Queue controls pass; restart/restore unproven. |
| Observability | 2 | Health is useful; alerts/trace continuity unverified. |
| Performance | 2 | Frontend budget passes; chat baseline blocked. |
| Cost | 1 | Provider and storage cost not measured. |
| Data integrity | 3 | Privacy/encryption tests pass; restore/cross-store proof absent. |
| Deployment | 2 | Read-only assessment; promotion/rollback not exercised. |
| Recovery | 1 | No measured RPO/RTO. |
| Documentation | 4 | Required pack created; canonical docs now present. |
| Developer experience | 3 | Commands are documented; dependency topology still requires cleanup. |
| Product completeness | 3 | Major surfaces exist; mobile and live journeys remain unverified. |

## Remaining work and explicit blockers

Before production, provision and version `okf_compiled`; require readiness true; provide the rights-approved matching retrieval corpus; pass strict retrieval evaluation; repair and complete browser/mobile E2E; provision disposable Redis/Supabase/Neo4j/provider integrations; execute worker, dependency, malformed-input, and abuse fault tests; complete backup/restore and rollback with RPO/RTO; and run a clean ramp with p95/p99, queue completion, resource, token, embedding, cache, and cost telemetry.

The release must remain **NOT PRODUCTION READY** until those P1 blockers are closed or explicitly accepted by the accountable owner. No deployment, push, Railway mutation, secret operation, or destructive user-data action was performed.

## Since this report: security/correctness fixes (2026-08-25, separate pass)

This report's own blockers (`okf_compiled` missing, retrieval-eval corpus mismatch, browser E2E stall, integration skips, no capacity/restore baseline) are unaffected by this note and remain open — the executive verdict above stands. Separately, a security/correctness audit pass closed 8 items from `docs/production-readiness/OMISSION-HUNT-ADDENDUM-2026-08-24.md`:

- **OH-P0-01** — doctrine-cache citation bypass: entries without structured citations can no longer be served, regardless of loader.
- **OH-P0-02** — account deletion missed Qdrant/Neo4j/Redis and 3 Postgres tables (`guru_core_memory`, `guru_memories`, `guru_session_summaries`); now purged via a new `DELETE /api/account/purge-memory` endpoint. Verified live against local Qdrant + Postgres.
- **OH-P1-01** — Docker build-context leak (`backend/data/` wasn't actually excluded despite looking like it was).
- **OH-P1-02** — push notifications silently reported success with missing FCM/APNs credentials; no unregister endpoint; no stale-token pruning. All three fixed.
- **OH-P1-03** — `/sw.js` and `/push-sw.js` service-worker scope collision.
- **OH-P1-05** — two duplicate cron push senders consolidated to one.
- **OH-P1-06** — push deep-link/URL allowlist (phishing vector) and wildcard CORS on 12 edge functions replaced with an opt-in `ALLOWED_ORIGINS` allowlist.
- **OH-P1-08** — email-domain allowlist was client-only, bypassable via direct API call; now enforced server-side.

Also fixed, not in the addendum's original list: an OCR/media-transcription wall-clock timeout gap (a crafted file could hang a worker indefinitely), and a RAG refusal-gate gap where the CRAG-exhaustion fallback returned a bare refusal even when retrieval had found real candidate documents.

Full evidence and commit references are in the addendum's "Resolution status" section. This is a different gate from the one this report scores — see that document for detail, not a re-litigation of this report's scorecard.

## References

[1]: [`src/App.tsx`](src/App.tsx) — frontend route table and compatibility redirects.
[2]: [`backend/app/api/chat.py`](../backend/app/api/chat.py) — HTTP 202 queue contract.
[3]: [`backend/tests/test_qdrant_search_quality.py`](../backend/tests/test_qdrant_search_quality.py) — strict retrieval preflight.
[4]: [`docs/audit-findings.md`](audit-findings.md) — master findings register.
[5]: [`docs/verification-results.md`](verification-results.md) — command-level verification.
