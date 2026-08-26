# Cache-disabled validation snapshot — 26 August 2026

The attached local backend was recreated with `LATENCY_BENCHMARK_CACHE_DISABLED=true`; the container environment was verified before measurement. This bypassed application cache reads and writes in cache admission, doctrine cache, and cache update. No Redis flush was performed.

| Check | Result |
|---|---|
| Benchmark command | `python3 audit_work/latency_benchmark_repeated.py --runs 3 --cache-mode disabled --labels fast_casual,fast_factual,fast_meditation,standard_factual,standard_reflective,deep_comparison,deep_multihop,distress,temporal,hindi_simple,hindi_comparison,telugu_simple` |
| Total samples | 36 |
| Included samples | 36 |
| Excluded samples | 0 |
| Cache hits | 0 |
| Percentiles | Suppressed; only n=3 per route, minimum is 20 |
| Backend health | Docker health `healthy`; API serving |
| API readiness | `ready=false`, `status=unhealthy` solely because required `okf_compiled` is absent |
| Backend regression | 2,464 passed, 30 skipped, 1 warning in 311.48 s |
| Focused cache-disabled suites | 32 passed |
| Repository publication | No commit or push |

## Exploratory cache-disabled means

| Route | n | Backend mean ms | Wall mean ms |
|---|---:|---:|---:|
| fast_casual | 3 | 2.33 | 316.87 |
| fast_factual | 3 | 4,834.67 | 5,042.53 |
| fast_meditation | 3 | 2,518.33 | 2,594.05 |
| standard_factual | 3 | 4,849.33 | 5,001.07 |
| standard_reflective | 3 | 5,924.33 | 6,072.39 |
| deep_comparison | 3 | 24,741.00 | 24,874.05 |
| deep_multihop | 3 | 16,341.67 | 16,435.82 |
| distress | 3 | 0.33 | 277.44 |
| temporal | 3 | 6,278.67 | 6,414.08 |
| hindi_simple | 3 | 20,675.67 | 20,855.78 |
| hindi_comparison | 3 | 18,772.33 | 18,927.50 |
| telugu_simple | 3 | 33,301.67 | 33,494.43 |

These are exploratory means, not p50/p95. The raw JSONL and summary retain route, cache, quality, and verification metadata for every sample.


## Follow-up latency-lane validation

The optional retrieval-planner soft deadline and queue attribution changes passed the focused retrieval/queue tests. The optional OpenRouter provider-latency policy also passed its policy/accounting tests while remaining disabled by default in the stable runtime.

| Check | Result |
|---|---|
| New focused planner/queue/provider-policy tests | 13 passed |
| Final complete backend suite | 2,468 passed, 30 skipped, 1 warning in 525.53 s |
| Runtime provider-sort trial | Invalid for performance: 3/3 attempts excluded due timeout/disconnect; no included samples |
| Warm-up core benchmark | Invalid for performance: 12/12 attempts excluded due connection/reset/runtime startup failures |
| Stable post-change route samples | n=3 each for fast factual, standard factual, and deep comparison; exploratory only; fixtures resolved to tier2_simple |
| Cache-free mode after final revert | `LATENCY_BENCHMARK_CACHE_DISABLED=true`; provider sort empty/default |

No invalid or warm-up sample is included in any latency claim. The authoritative route-wide cache-free evidence remains the 36-sample matrix above; the new n=3 samples are diagnostic route-validation evidence only and have no p50/p95.


## Question-bank all-tier wave (2026-08-26)

The normalized manifest built from `backend/benchmarks/question_bank.py` contains 420 cases across 35 categories, including multi-turn scenarios. Source SHA-256: `1adf9d547ffd9ca33c20b63ef57b8291f2938ca138a25028620fd2d06a34f8f6`.

The first full wave produced 185 valid cache-disabled rows before a near-immediate HTTP-error regime. A retry wave covered the 235 previously failed cases. The merged set has 420 unique cases, 396 included `cache_hit=false` rows, and 106 quality-valid rows. Exclusions were 22 HTTP errors, including one HTTP 422 and 21 HTTP 429 responses, one incomplete job, and one ambiguous cache signal. No warm-cache values are used.

| Observed tier | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Wall mean ms | Wall p50 ms | Wall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fast | 14 | 11 | 6469.93 | suppressed | suppressed | 6792.57 | suppressed | suppressed |
| tier2_simple | 282 | 50 | 4397.33 | 3134.00 | 13375.60 | 4708.94 | 3609.07 | 13511.30 |
| standard | 21 | 11 | 18754.57 | 18658.00 | 33567.00 | 19072.71 | 18969.19 | 33672.54 |
| tier3_complex | 48 | 6 | 22885.60 | 21821.00 | 40836.45 | 23191.91 | 22203.69 | 41114.98 |

Mixed-workload overall: backend mean 7129.41 ms, wall mean 7457.22 ms, backend p50 3399.50 ms, backend p95 26622.75 ms, wall p50 3645.24 ms, wall p95 26996.39 ms. Overall quality-valid rate among included rows: 26.77%. No included row exposed a banned public field in the recursive scan. Full bounded report: `audit_work/question_bank_latency_merged_v1.md`; chart: `audit_work/question_bank_latency_merged_v1.png`.
