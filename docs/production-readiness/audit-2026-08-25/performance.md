# Performance

The final canonical loop passed frontend tests, lint, typecheck, build, bundle budget, focused backend tests, Ruff, Bandit, regex safety, compilation, and the full backend suite. The frontend output was 135 JavaScript files; the largest chunk was 390.98 kB in the final loop and all configured budgets passed.

Local health p50 was 87.5 ms and maximum 181.6 ms across ten synthetic requests. Chat was 429-limited, so no chat p95/p99 or throughput claim is made. The corrected benchmark reports queue acknowledgement separately from completion. A clean performance baseline must include p50/p95/p99, queue completion, provider calls, tokens, embeddings, cache hit ratio, pools, CPU, memory, and cost.
