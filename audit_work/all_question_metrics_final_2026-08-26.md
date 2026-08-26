# AskMukthiGuru all-question metrics and implementation status

**Date:** 26 August 2026
**Rule:** Official latency rows are completed, cache-disabled, `cache_hit=false`, and non-cache-route. Percentiles require n>=20 in the stratum. Errors, 429s, disconnects, timeouts, OOM, incomplete jobs, and cache ambiguity are exclusions.

## Executive result

Latency instrumentation and safety-preserving routing corrections are implemented, but a major all-tier latency gain is **not proven**. The fresh full-bank run was stopped after the backend reported `OOMKilled=true`; its partial log reached at least `complex_multi_hop-0017` and produced no complete output. This is a capacity finding, not a latency result.

## Implementation status

| Area | Status | Evidence or limitation |
|---|---|---|
| Cache-disabled benchmark mode | Implemented | App cache reads/writes bypassed; no global Redis flush |
| Queue/trace/stage correlation | Implemented | Job, trace, pipeline, graph, provider, and queue-wait metadata are bounded/internal |
| Deterministic greeting path | Implemented | Pure greetings bypass provider/cache work; stable canary returned 19 ms backend time, not a percentile |
| Retrieval-expansion soft deadline | Implemented | Optional planner is bounded at 0.35 s |
| Coarse-tier route correction | Implemented | Query-shape evidence can select deep instead of coarse factual fast/tier2 |
| Intent-tier preservation | Implemented | Later factual/query normalization cannot downgrade stronger standard/deep tier; safety paths retain precedence |
| Duplicate deep verification reuse | Implemented behind `deep_gate_skip_on_verified=true` | Only strict faithful passes above the configured floor bypass the duplicate verifier |
| Provider latency sorting | Not enabled | Trial produced invalid timeout/disconnect outcomes |
| OpenRouter hard budget guard | Implemented but disabled | Redis fail-closed/concurrency drill remains incomplete |
| Provider 429 admission/cooldown | Not completed | Full-bank runs exposed reset/429 regimes; no unvalidated scheduler was enabled |
| Strict quality evaluator | Preserved | No weakening of terms, citations, faithfulness, safety, abstention, or public-field checks |
| Free-user core | Preserved | No paywall for chat, safety, citations, deletion/privacy, or anonymous access |

## Authoritative 420-case current-state cache-free metrics

The normalized bank contains **420 cases across 35 categories**. The merged current-state audit has **396 eligible cache-free rows**, **106 strict quality-valid rows**, and a **26.77% strict quality-valid rate**. It is current-state evidence, not a pre/post delta.

### Observed tiers

| Tier | Included | Quality-valid | Mean ms | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| fast | 14 | 11 | 6,469.93 | suppressed (<20) | suppressed (<20) |
| standard | 21 | 11 | 18,754.57 | 18,658.00 | 33,567.00 |
| tier2_simple | 282 | 50 | 4,397.33 | 3,134.00 | 13,375.60 |
| tier3_complex | 48 | 6 | 22,885.60 | 21,821.00 | 40,836.45 |
| unknown/safety short-circuit | 31 | 28 | 8.58 | suppressed (<20) | 62.50 |

### Benchmark strata

| Stratum | Total | Included | Quality-valid | Mean ms | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| conversation_followup | 16 | 16 | 6 | 5,264.12 | suppressed | suppressed |
| general_qa | 91 | 80 | 30 | 11,070.04 | 5,460.50 | 30,342.20 |
| grounding_citation | 15 | 15 | 3 | 2,784.20 | suppressed | suppressed |
| in_corpus_doctrine | 140 | 140 | 0 | 4,691.96 | 3,064.00 | 16,637.20 |
| multilingual | 38 | 38 | 1 | 9,784.39 | 5,938.50 | 30,720.05 |
| privacy_injection | 11 | 11 | 8 | 13,990.36 | suppressed | suppressed |
| robustness_boundaries | 16 | 13 | 13 | 7,898.69 | suppressed | suppressed |
| safety_distress | 36 | 36 | 30 | 4,047.53 | 3,264.50 | 9,552.25 |
| safety_governance | 33 | 33 | 12 | 7,512.00 | 2,702.00 | 26,721.00 |
| stress_context | 10 | 10 | 1 | 11,197.90 | suppressed | suppressed |
| temporal_out_of_corpus | 14 | 4 | 2 | 5,202.75 | suppressed | suppressed |

### Source-category metrics

| Category | Total | Included | Quality-valid | Mean ms | p50/p95 ms |
|---|---:|---:|---:|---:|---:|
| adversarial_traps | 8 | 8 | 0 | 6,885.00 | suppressed |
| boundary_probing | 10 | 10 | 1 | 13,981.10 | suppressed |
| cache | 4 | 4 | 4 | 2,808.25 | suppressed |
| citation_accuracy | 10 | 10 | 3 | 2,687.60 | suppressed |
| cold_start_followups | 6 | 6 | 6 | 6,239.83 | suppressed |
| complex_multi_hop | 23 | 23 | 1 | 22,815.26 | 22,830.00 / 43,341.00 |
| constitutional_adherence_traps | 7 | 7 | 7 | 5,818.14 | suppressed |
| context_budget_stress | 5 | 5 | 1 | 12,883.40 | suppressed |
| cove | 2 | 2 | 0 | 3,212.50 | suppressed |
| doctrine_deeksha | 20 | 20 | 0 | 3,071.75 | 2,840.50 / 3,899.25 |
| doctrine_ekam_architecture | 20 | 20 | 0 | 3,200.25 | 2,976.00 / 4,431.60 |
| doctrine_founders | 20 | 20 | 0 | 6,770.25 | 4,059.00 / 19,911.25 |
| doctrine_four_secrets | 20 | 20 | 0 | 6,090.60 | 3,212.00 / 14,735.60 |
| doctrine_manifest | 20 | 20 | 0 | 2,450.65 | 2,553.50 / 3,051.70 |
| doctrine_soul_sync | 20 | 20 | 0 | 3,212.25 | 3,183.00 / 4,289.00 |
| doctrine_traps | 20 | 20 | 0 | 8,048.00 | 4,315.00 / 30,880.30 |
| emotional_gradients | 20 | 20 | 20 | 4,885.05 | 6,363.00 / 8,782.45 |
| end_to_end_2026 | 18 | 18 | 15 | 6,404.72 | suppressed |
| future_date_confabulation | 4 | 4 | 2 | 5,202.75 | suppressed |
| guardrails_input | 20 | 20 | 10 | 7,249.65 | 868.00 / 27,436.65 |
| infra_probing | 6 | 6 | 3 | 12,508.67 | suppressed |
| intent_traps | 20 | 20 | 7 | 4,104.65 | 3,396.00 / 10,826.85 |
| latency_stress | 5 | 5 | 0 | 9,512.40 | suppressed |
| malformed_input | 10 | 7 | 7 | 8,635.71 | suppressed |
| markdown_html_injection | 5 | 5 | 5 | 15,768.40 | suppressed |
| micro_queries | 6 | 6 | 6 | 7,038.83 | suppressed |
| multi_turn | 10 | 10 | 0 | 4,678.70 | suppressed |
| multilingual_hinglish | 20 | 20 | 0 | 8,755.30 | 4,208.50 / 30,595.35 |
| multilingual_indic_native | 13 | 13 | 0 | 12,991.69 | suppressed |
| multilingual_jailbreak_traps | 5 | 5 | 2 | 9,564.60 | suppressed |
| multilingual_spoken_asr_transcripts | 3 | 3 | 0 | 4,738.67 | suppressed |
| ruthless_safety_boundaries | 7 | 7 | 6 | 3,881.86 | suppressed |
| self_rag | 3 | 3 | 0 | 2,820.67 | suppressed |
| silly_nonsense | 20 | 9 | 0 | 681.44 | suppressed |
| temporal_awareness | 10 | 0 | 0 | no eligible rows | suppressed |

### Language metrics

| Language | Total | Included | Quality-valid | Mean ms | p50/p95 |
|---|---:|---:|---:|---:|---:|
| English | 405 | 381 | 105 | 6,931.14 | 3,324.00 / 26,283.00 |
| Hindi | 2 | 2 | 1 | 6,425.50 | suppressed |
| Telugu | 2 | 2 | 0 | 6,475.00 | suppressed |
| Other Indic (as, bn, gu, kn, ml, mr, or, pa, sa, ta, ur) | 11 | 11 | 0 | mixed; n<20 each | suppressed |

## Gain analysis

The clean earlier matched exploratory deep comparison reported **24,741.00 ms to 22,281.33 ms (-9.94%)**, n=3, and wall **24,874.05 ms to 22,429.12 ms (-9.83%)**, n=3. This was exploratory only and not a major all-tier result.

The route correction makes a direct comparison to old deep-comparison rows invalid because those rows often executed as `tier2_simple`. The corrected stable canary completed cache-free at **31,742 ms backend / 40,806 ms wall**, with `query_tier=deep`, `grounding_state=abstained`, `verification.passed=false`, and verified citations. It proves route correctness and honest quality gating, not a latency gain.

## Final conclusion

The free core is protected and the routing/verification fixes are implemented. The main unresolved issues are low strict quality validity, deep/multilingual tails, provider capacity, and local container memory. A future benchmark must use bounded category batches, cooldowns, cgroup memory capture, and separate 429/reset accounting before any major latency claim or further concurrency change.
