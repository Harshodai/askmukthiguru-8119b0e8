# AskMukthiGuru Free-to-User Product Audit — Baseline Register

**Date:** 26 August 2026  
**Audit posture:** Read-only/reconnaissance-first; no commit, push, deploy, reset, rebase, corpus mutation, credential rotation, or global Redis flush authorized by this brief.  
**End-user economics constraint:** Users are not expected to pay for using the product. Any recommendation must therefore prioritize low marginal operating cost, abuse resistance, graceful free-tier limits, and high value per unit of compute without degrading safety or groundedness.

## Repository identity

| Field | Observed value |
|---|---|
| Attached checkout | `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8` |
| Branch | `main` |
| Local HEAD | `771b507dd106efffcaeee45575cd00c7f7e5d33a` |
| `origin/main` | `8d57890f852923b3bff2a1bc320265c2c951b60e` |
| Synchronization state | Local HEAD differs from `origin/main`; do not pull/reset/rebase without explicit authorization |
| Working-tree status | 129 status entries; 30 tracked files with unstaged diffs; many audit artifacts are untracked |
| Audit artifacts before this audit | 102 files in `audit_work/` |

## Binding evidence controls

Every significant finding will be classified as **VERIFIED IN REPOSITORY**, **VERIFIED AT RUNTIME**, **MEASURED**, **WEB RESEARCH**, **COMPETITOR EVIDENCE**, **INFERRED**, or **UNKNOWN**. Documentation is a claim to test through the chain **documentation → implementation → runtime → actual user journey**.

The current latency rule is strict: report performance only from application-cache-disabled, completed, non-cache rows with `cache_hit=false`. Warm-cache and mixed-cache results remain diagnostic only. Percentiles require at least 20 included samples per comparison stratum. Transport errors, rate limits, incomplete jobs, ambiguous cache signals, and provider failures remain exclusions rather than latency values.

The current repository safety boundaries include signed anonymous-session credentials, separate direct versus queued SSE contracts, explicit public provenance allowlists, grounded partial evidence distinct from verified teaching, fail-closed distress handling, tenant-isolated memory and cache namespaces, pinned model revisions, and the prohibition on fabricating absent `okf_compiled`/curated artifacts. These constraints are release gates, not optimization targets.

## Free-to-user operating principles

1. Prefer deterministic or local mechanisms when they provide the same safe user outcome; reserve paid provider calls for cases where they add measurable user value.
2. Enforce bounded anonymous quotas, request budgets, concurrency, context size, attachment limits, and abuse controls at admission rather than relying only on downstream provider failure.
3. Measure provider, token, embedding, reranker, storage, bandwidth, observability, and background-job cost separately. Local Docker memory is not a hosting bill.
4. Do not introduce a subscription wall for core chat, safety, citations, or basic practice guidance. Optional advanced features must be evaluated for both user value and cost-to-serve.
5. Never reduce cost by weakening citations, abstention, crisis handling, privacy, tenant isolation, or deletion semantics.

## Current local runtime note

A connected local process is serving Uvicorn on port 8001. Docker and application readiness are environment-specific and must be recorded separately. The absent `okf_compiled` artifact must not be manufactured to make readiness green. Any runtime result will state its environment, provider/model configuration, cache mode, fixture/source, sample size, and excluded rows.

## Immediate audit sequence

The next phase inventories product surfaces and dependency/data flows. Later phases separately verify runtime journeys, security/privacy/content rights, AI/RAG/corpus quality, latency/reliability/scalability, cost-to-serve, and competitive value. Parallel research lanes may be used conceptually, but evidence is reconciled centrally and no state-changing action is taken without explicit approval.


## Read-only runtime verification (26 August 2026)

| Probe | Result | Evidence class | Interpretation |
|---|---|---|---|
| `GET /api/health` on local Uvicorn port 8001 | HTTP response returned `ready=false`, `status=unhealthy`; Qdrant, Redis, Neo4j, LLM, guardrails, exact/semantic cache, fast/standard/deep graph, queue, and OCR were reported with per-service signals | VERIFIED AT RUNTIME | Runtime is serving but not release-ready; embedding and LightRAG were reported unavailable/critical in this process |
| `GET /api/healthz` | `{"ok":true,"status":"alive"}` | VERIFIED AT RUNTIME | Liveness is not readiness; do not treat it as feature availability |
| `GET /api/capabilities` | HTTP 404 on port 8001 | VERIFIED AT RUNTIME | The process OpenAPI document also contains zero `/api/capabilities` paths, while the attached source mounts `capabilities_router`; this is a source-versus-running-process mismatch and must be resolved before capability claims |
| Local process | Long-running Uvicorn process on port 8001 | VERIFIED AT RUNTIME | Its age/launch context predates the current source audit; do not assume it represents current checkout behavior |

No state-changing anonymous-session, chat, upload, authenticated, or admin requests were sent during this read-only runtime phase because the attached audit brief prohibits product/database/external-state mutation without separate approval. Runtime workflow proof remains open.
