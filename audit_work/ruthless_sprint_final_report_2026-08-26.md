# AskMukthiGuru Ruthless Latency and Quality Sprint — 2026-08-26

## Release decision

The sprint produced a **validated quality-path correction** and a **guarded latency optimization**, but not defensible proof of a major all-tier latency reduction. The final post-change paired wave was invalidated by runtime connection resets, so no post-change p50/p95 or all-tier delta is claimed. Core chat, safety, basic citations, honest abstention, deletion/privacy, and anonymous access remain free to users.

## Implemented

| Change | Result |
|---|---|
| GraphStage now lets strong query-shape evidence override only coarse factual tier hints | Comparative/deep requests no longer silently use the fast graph |
| Intent router preserves a stronger upstream `standard`/`deep` tier for non-terminal query intents | Deep quality gates are not downgraded by later normalization; distress, meditation, casual, and guardrails retain precedence |
| `deep_gate_skip_on_verified` | Duplicate deep verification is skipped only after `verification.passed=true`, `is_faithful=true`, and the configured faithfulness floor is met; all uncertain/partial/failed states remain fail-closed |

## Cache-disabled evidence

The pre-change exact fixture baseline had 20 included, cache-hit-free rows per label:

| Label | Mean ms | p50 ms | p95 ms |
|---|---:|---:|---:|
| fast factual | 4,542.70 | 3,853.00 | 12,072.45 |
| standard factual | 4,915.45 | 4,025.50 | 10,518.60 |
| deep comparison | 16,703.85 | 16,889.50 | 30,860.65 |
| deep multihop | 14,879.60 | 14,663.00 | 18,501.30 |
| distress | 0.40 | 0.00 | 1.10 |
| Hindi simple | 14,252.50 | 9,837.50 | 27,080.60 |
| Hindi comparison | 18,712.70 | 16,328.50 | 37,292.65 |
| Telugu simple | 21,184.75 | 21,244.00 | 33,710.30 |

The post-change run attempted 160 rows but produced only one eligible row before a `ConnectionResetError` regime. All route percentiles were correctly suppressed because no stratum reached n=20. The one eligible fast-factual row is not used as a route claim. A separate stable comparative canary completed cache-free with final `query_tier=deep`, `grounding_state=abstained`, `verification.passed=false`, and verified citations; it is a canary, not a percentile.

The broad current-state 420-case question-bank audit remains non-paired evidence: 396 eligible cache-free rows, 106 strict quality-valid rows, and 26.77% strict quality-valid. That evaluator result is not manipulated or presented as a pre/post gain.

## Validation

The focused routing/verification/safety suites passed **44 tests**. The full backend suite passed **2,471 tests, 30 skipped, 1 warning** in 239.85 seconds. Python compilation and `git diff --check` passed. Frontend validation was not rerun because no frontend or public response-schema changed.

## Free-user and safety constraints

No paywall was added to the free core. The implementation preserves quotas, concurrency caps, attachment bounds, ephemeral untrusted evidence, admin AAL2/allowlisting, SSE public projections, grounded citations, abstention, and distress handling. The OpenRouter hard budget guard remains a separate P0 because its required Redis fail-closed/concurrency drill was not completed; no unsupported spend or revenue claim is made.

## Required follow-up

Stabilize and source-match the Compose runtime, repeat the identical cache-disabled wave with at least 20 completed cache-hit-free rows in every stratum, and then compare latency and strict quality together. If deep remains slow, experiment behind a rollback switch on reranker/provider tails; do not downgrade the quality graph to manufacture a speed result.
