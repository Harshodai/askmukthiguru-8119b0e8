# Performance

The final canonical loop passed frontend tests, lint, typecheck, build, bundle budget, focused backend tests, Ruff, Bandit, regex safety, compilation, and the full backend suite. The frontend output was 135 JavaScript files; the largest chunk was 390.98 kB in the final loop and all configured budgets passed.

Local health p50 was 87.5 ms and maximum 181.6 ms across ten synthetic requests. Chat was 429-limited, so no chat p95/p99 or throughput claim is made. The corrected benchmark reports queue acknowledgement separately from completion. A clean performance baseline must include p50/p95/p99, queue completion, provider calls, tokens, embeddings, cache hit ratio, pools, CPU, memory, and cost.

## Fresh feature-expansion measurements — 2026-08-25

A bounded local synthetic probe against the existing disposable backend ran **40 chat admission attempts** at concurrency 4 for five seconds with streaming disabled. All 40 returned HTTP 429, so the run establishes an admission/quota boundary only; it does not establish throughput, completion latency, provider capacity, or p95/p99 chat performance. No threshold was lowered and no quota or production data was changed.

The local readiness endpoint was sampled ten times sequentially: all returned HTTP 200 in the range captured by the run, with **p50 50.5 ms** and **maximum 70.3 ms**. A separate 20-request, 10-way concurrent health probe returned **20/20 HTTP 200**, **p50 115.5 ms**, **p95 267.7 ms**, and **maximum 493.9 ms**. These are local host observations, not user-facing SLO evidence; the response payload still reports `ready=false` because the required `okf_compiled` artifact is missing.

The production-like frontend build passed in **5.25 s real time** (`vite` reported **4.88 s**), emitted **188 files**, and occupied approximately **9.2 MB** in `dist`. The largest observed JavaScript assets were `index` 474.7 kB, `ChatPage` 400.4 kB, `generateCategoricalChart` 358.9 kB, and `radix-vendor` 292.3 kB before compression. The configured build budgets passed, but the chunk sizes justify a later route-level bundle split and chart-loading review before claiming mobile performance maturity.

No chat capacity or cost baseline is promoted from these observations. A clean performance gate still requires a matching approved corpus, controlled provider configuration, completion-aware queue measurements, token/embedding/cache metrics, resource saturation telemetry, and repeatable p50/p95/p99 runs.
