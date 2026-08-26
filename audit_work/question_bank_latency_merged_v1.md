# AskMukthiGuru Question-Bank Cache-Free Benchmark v1

## Scope and validity

This report analyzes the complete normalized question bank (420 cases across 35 source categories) using the source hash `1adf9d547ffd9ca33c20b63ef57b8291f2938ca138a25028620fd2d06a34f8f6`. The full wave produced 420 rows; its first transport-failure transition was retained as invalid evidence. A retry wave covered the previously failed categories with 235 rows, and the merged report prefers retry rows only where the original row was excluded.

Only rows with `included=true`, `cache_hit=false`, a completed job, and a non-cache route are eligible for latency statistics. HTTP failures, timeouts, cache-signal ambiguity, and incomplete jobs remain visible in exclusion tables but are not converted into latency values. Percentiles are reported only for groups with at least 20 included cache-free samples. These are local exploratory measurements, not production performance claims.

## Overall coverage

| Measure | Result |
|---|---:|
| Manifest cases | 420 |
| Full-wave rows | 420 |
| Retry-wave rows | 235 |
| Merged unique cases | 420 |
| Cases replaced by valid retry rows | 235 |
| Merged included cache-free rows | 396 |
| Merged quality-valid rows | 106 |

## Observed query-tier latency

The application’s public `query_tier` is reported as observed telemetry. It is not inferred from a fixture name, and the bank currently does not provide a complete expected-tier label for every case. `unknown` commonly represents deterministic safety paths that do not select a graph tier.

| Observed tier | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Wall mean ms | Wall p50 ms | Wall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fast | 14 | 11 | 6469.93 | — | — | 6792.57 | — | — |
| standard | 21 | 11 | 18754.57 | 18658.0 | 33567.0 | 19072.71 | 18969.19 | 33672.54 |
| tier2_simple | 282 | 50 | 4397.33 | 3134.0 | 13375.6 | 4708.94 | 3609.07 | 13511.3 |
| tier3_complex | 48 | 6 | 22885.6 | 21821.0 | 40836.45 | 23191.91 | 22203.69 | 41114.98 |
| unknown | 31 | 28 | 8.58 | — | 62.5 | 525.87 | 524.99 | 535.99 |

## Benchmark strata

| Stratum | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Exclusions |
|---|---:|---:|---:|---:|---:|---:|---|
| conversation_followup | 16 | 16 | 6 | 5264.12 | — | — | {} |
| general_qa | 91 | 80 | 30 | 11070.04 | 5460.5 | 30342.2 | {"HTTPError": 11} |
| grounding_citation | 15 | 15 | 3 | 2784.2 | — | — | {} |
| in_corpus_doctrine | 140 | 140 | 0 | 4691.96 | 3064.0 | 16637.2 | {} |
| multilingual | 38 | 38 | 1 | 9784.39 | 5938.5 | 30720.05 | {} |
| privacy_injection | 11 | 11 | 8 | 13990.36 | — | — | {} |
| robustness_boundaries | 16 | 13 | 13 | 7898.69 | — | — | {"HTTPError": 1, "not_completed": 1, "cache_signal_not_false": 1} |
| safety_distress | 36 | 36 | 30 | 4047.53 | 3264.5 | 9552.25 | {} |
| safety_governance | 33 | 33 | 12 | 7512.0 | 2702.0 | 26721.0 | {} |
| stress_context | 10 | 10 | 1 | 11197.9 | — | — | {} |
| temporal_out_of_corpus | 14 | 4 | 2 | 5202.75 | — | — | {"HTTPError": 10} |

## Source-category results

| Category | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Observed tiers |
|---|---:|---:|---:|---:|---:|---:|---|
| adversarial_traps | 8 | 8 | 0 | 6885.0 | — | — | {"tier2_simple": 6, "tier3_complex": 2} |
| boundary_probing | 10 | 10 | 1 | 13981.1 | — | — | {"standard": 3, "tier3_complex": 2, "tier2_simple": 4, "unknown": 1} |
| cache | 4 | 4 | 4 | 2808.25 | — | — | {"tier2_simple": 4} |
| citation_accuracy | 10 | 10 | 3 | 2687.6 | — | — | {"tier2_simple": 10} |
| cold_start_followups | 6 | 6 | 6 | 6239.83 | — | — | {"fast": 4, "tier2_simple": 2} |
| complex_multi_hop | 23 | 23 | 1 | 22815.26 | 22830.0 | 43341.0 | {"tier2_simple": 9, "tier3_complex": 13, "standard": 1} |
| constitutional_adherence_traps | 7 | 7 | 7 | 5818.14 | — | — | {"fast": 1, "tier2_simple": 6} |
| context_budget_stress | 5 | 5 | 1 | 12883.4 | — | — | {"tier2_simple": 3, "tier3_complex": 2} |
| cove | 2 | 2 | 0 | 3212.5 | — | — | {"tier2_simple": 2} |
| doctrine_deeksha | 20 | 20 | 0 | 3071.75 | 2840.5 | 3899.25 | {"tier2_simple": 19, "tier3_complex": 1} |
| doctrine_ekam_architecture | 20 | 20 | 0 | 3200.25 | 2976.0 | 4431.6 | {"tier2_simple": 20} |
| doctrine_founders | 20 | 20 | 0 | 6770.25 | 4059.0 | 19911.25 | {"tier2_simple": 17, "tier3_complex": 3} |
| doctrine_four_secrets | 20 | 20 | 0 | 6090.6 | 3212.0 | 14735.6 | {"tier2_simple": 17, "standard": 1, "tier3_complex": 2} |
| doctrine_manifest | 20 | 20 | 0 | 2450.65 | 2553.5 | 3051.7 | {"tier2_simple": 20} |
| doctrine_soul_sync | 20 | 20 | 0 | 3212.25 | 3183.0 | 4289.0 | {"tier2_simple": 20} |
| doctrine_traps | 20 | 20 | 0 | 8048.0 | 4315.0 | 30880.3 | {"tier2_simple": 12, "tier3_complex": 5, "unknown": 1, "fast": 2} |
| emotional_gradients | 20 | 20 | 20 | 4885.05 | 6363.0 | 8782.45 | {"unknown": 7, "tier2_simple": 9, "tier3_complex": 1, "fast": 3} |
| end_to_end_2026 | 18 | 18 | 15 | 6404.72 | — | — | {"tier2_simple": 14, "tier3_complex": 1, "standard": 2, "unknown": 1} |
| future_date_confabulation | 4 | 4 | 2 | 5202.75 | — | — | {"tier2_simple": 3, "tier3_complex": 1} |
| guardrails_input | 20 | 20 | 10 | 7249.65 | 868.0 | 27436.65 | {"unknown": 10, "tier2_simple": 5, "standard": 4, "fast": 1} |
| infra_probing | 6 | 6 | 3 | 12508.67 | — | — | {"tier3_complex": 2, "unknown": 1, "tier2_simple": 3} |
| intent_traps | 20 | 20 | 7 | 4104.65 | 3396.0 | 10826.85 | {"unknown": 4, "tier2_simple": 12, "tier3_complex": 1, "standard": 1, "fast": 2} |
| latency_stress | 5 | 5 | 0 | 9512.4 | — | — | {"tier2_simple": 4, "tier3_complex": 1} |
| malformed_input | 10 | 7 | 7 | 8635.71 | — | — | {"unknown": 3, "tier2_simple": 4, "standard": 2, "fast": 1} |
| markdown_html_injection | 5 | 5 | 5 | 15768.4 | — | — | {"standard": 4, "tier2_simple": 1} |
| micro_queries | 6 | 6 | 6 | 7038.83 | — | — | {"tier2_simple": 4, "standard": 1, "tier3_complex": 1} |
| multi_turn | 10 | 10 | 0 | 4678.7 | — | — | {"tier2_simple": 10} |
| multilingual_hinglish | 20 | 20 | 0 | 8755.3 | 4208.5 | 30595.35 | {"tier2_simple": 17, "tier3_complex": 2, "standard": 1} |
| multilingual_indic_native | 13 | 13 | 0 | 12991.69 | — | — | {"tier2_simple": 8, "tier3_complex": 5} |
| multilingual_jailbreak_traps | 5 | 5 | 2 | 9564.6 | — | — | {"tier3_complex": 1, "standard": 1, "unknown": 2, "tier2_simple": 1} |
| multilingual_spoken_asr_transcripts | 3 | 3 | 0 | 4738.67 | — | — | {"tier2_simple": 3} |
| ruthless_safety_boundaries | 7 | 7 | 6 | 3881.86 | — | — | {"unknown": 4, "tier3_complex": 2, "tier2_simple": 1} |
| self_rag | 3 | 3 | 0 | 2820.67 | — | — | {"tier2_simple": 3} |
| silly_nonsense | 20 | 9 | 0 | 681.44 | — | — | {"tier2_simple": 9, "unknown": 11} |
| temporal_awareness | 10 | 0 | 0 | — | — | — | {"unknown": 10} |

## Language results

| Language | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| as | 1 | 1 | 0 | 33483.0 | — | — |
| bn | 1 | 1 | 0 | 5589.0 | — | — |
| en | 405 | 381 | 105 | 6931.14 | 3324.0 | 26283.0 |
| gu | 1 | 1 | 0 | 29960.0 | — | — |
| hi | 2 | 2 | 1 | 6425.5 | — | — |
| kn | 1 | 1 | 0 | 5037.0 | — | — |
| ml | 1 | 1 | 0 | 19.0 | — | — |
| mr | 1 | 1 | 0 | 2032.0 | — | — |
| or | 1 | 1 | 0 | 20199.0 | — | — |
| pa | 1 | 1 | 0 | 12045.0 | — | — |
| sa | 1 | 1 | 0 | 25212.0 | — | — |
| ta | 1 | 1 | 0 | 16240.0 | — | — |
| te | 2 | 2 | 0 | 6475.0 | — | — |
| ur | 1 | 1 | 0 | 6868.0 | — | — |

## Exclusions and reliability

The merged set has 24 excluded rows. The full wave entered a near-immediate HTTP-error regime after its first 185 valid rows. The retry wave recovered most categories but encountered explicit HTTP 429 rate limits in late cases. These are reliability and capacity findings, not latency measurements.

| Exclusion reason | Count |
|---|---:|
| HTTPError | 22 |
| cache_signal_not_false | 1 |
| not_completed | 1 |

## Quality and safety gates

The benchmark retains separate quality validity from latency inclusion. A row may be cache-free and timed but still fail its bank checks because required terms were absent, citations were insufficient, a rejected term appeared, the expected safety outcome did not match, or the result was an honest abstention/partial fallback. The `quality_valid` count is therefore the gate for quality-valid latency, not a claim that every included response passed.

| Gate | Interpretation |
|---|---|
| Cache-free | `cache_hit=false` and non-cache route |
| Grounding/citation | Bank terms and minimum citations checked in memory; raw answers are not persisted |
| Safety | Distress/refusal cases require blocked/safety-redirect behavior where specified |
| Public contract | Banned internal/public fields are scanned recursively; no violations were permitted for quality-valid rows |
| Tenant/privacy | This wave used fresh anonymous sessions and bounded response fields; cross-tenant destructive tests were not induced by the latency runner |

## Findings and next actions

1. **The runtime has a capacity/rate-limit seam.** The full wave’s late HTTP failures and the retry wave’s explicit 429s mean a future repeated benchmark must include cooldowns, provider-rate telemetry, and a separate capacity test; it must not treat a sequential 420-case run as a stable provider-capacity baseline.
2. **Tier routing is materially mixed.** Many bank categories resolve to `tier2_simple`, while complex categories also produce `tier3_complex` and `standard`. The benchmark should add reviewed expected-route labels or route-family assertions before any route-specific optimization claim.
3. **Deep and multilingual tails remain the dominant latency risk.** Valid category results show multi-second to tens-of-seconds tails, while fast deterministic safety paths can complete near zero backend milliseconds. Output-budget and reranker changes require held-out quality gates before activation.
4. **Quality is not closed.** Several doctrine and multilingual cases are cache-free but quality-invalid due grounded partial/abstained outputs or missing expected terms. This is an evidence-quality problem, not a reason to weaken citations, abstention, or safety.
5. **The next valid percentile sprint should be stratified rather than full-bank repeated.** Run at least 20 route-correct, quality-valid, cache-disabled samples for each target tier/stratum after cooldown, with separate single-client and controlled-concurrency waves.

## Evidence references

[1]: ./question_bank_latency_manifest_v1.json — normalized 420-case manifest and source hash.
[2]: ./question_bank_latency_full_v2_summary.json — first full-wave bounded summary; late HTTP-error regime excluded from latency claims.
[3]: ./question_bank_latency_retry_v1_summary.json — retry-wave bounded summary with explicit rate-limit exclusions.
[4]: ./question_bank_latency_full_v2.jsonl — full-wave raw bounded rows.
[5]: ./question_bank_latency_retry_v1.jsonl — retry-wave raw bounded rows.
