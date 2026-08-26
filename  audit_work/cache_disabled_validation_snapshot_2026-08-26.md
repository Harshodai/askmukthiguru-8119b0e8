

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
