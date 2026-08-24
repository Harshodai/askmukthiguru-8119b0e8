# Scalability

These are local bounded probes, not production capacity claims. A ten-user health wave produced HTTP 200 responses with p50 87.5 ms and maximum 181.6 ms, but 0/10 were ready. A synthetic chat wave was limited by HTTP 429 quota/admission responses. The first visible bottleneck was readiness and admission state, not CPU saturation.

| Required future measure | Current status |
|---|---|
| p50/p95/p99 health, chat, queue completion, retrieval, provider latency | Only health p50/max observed. |
| Queue depth, worker concurrency, pool utilization | Health exposes queue size; no sustained saturation run. |
| CPU, memory, tokens, embeddings, cache hit ratio | Not measured in a clean release-like topology. |
| 10x/100x modeled load | Not defensibly measured. |

A valid capacity run needs unique synthetic identities, clean quota namespaces, provisioned workers and providers, queue completion polling, resource telemetry, and cost accounting.
