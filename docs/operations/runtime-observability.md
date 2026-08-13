# Runtime observability gate

The backend now emits low-cardinality Prometheus measurements for the launch envelope without recording prompts, answer text, source content, user identifiers, session identifiers, or model reasoning.

| Signal | Metric | Collection boundary | Operational use |
|---|---|---|---|
| End-to-end latency | `guru_request_latency_seconds`, `slo_latency_seconds` | Existing stage and pipeline completion | Track p95 by routing tier. |
| Time to first token | `guru_ttft_seconds` | First safe streamed token | Track streaming responsiveness separately from completion. |
| Per-stage latency | `guru_node_latency_ms`, `rag_latency_seconds` | Existing pipeline nodes | Identify slow retrieval, generation, or verification stages. |
| Actual provider cost | `guru_provider_reported_cost_usd_total` | OpenRouter usage payload | Monitor only provider-reported non-negative cost. |
| Process capacity | `guru_process_rss_bytes`, `guru_process_cpu_seconds`, `guru_request_cpu_seconds` | Completed HTTP requests | Detect sustained memory growth and CPU-heavy requests. |
| Queue pressure | `guru_queue_depth` | Health snapshot | Measure bounded job queue backlog. |
| Cache / coalescing | Existing cache counters, `request_collapsed_total`, `coalescer_wait_seconds` | Cache and shared-work paths | Verify cost-saving be| Cache / coalescing | Existing cache counters, `request_collapsed_total`, `coalescer_wait_seconds` | Cache and shared-work paths | Verify cost-saIt exposes only process aggregates. The health snapshot publishes the bounded local job queue size; a multi-replica capacity decision still requires the staged Redis, Railway, and provider drills already retained in the deployment runbook.

> Do not infer production capacity from these metric definitions alone. Promote cohorts only after the staged 25 → 100 → 250 → 500-session tests record p95 latency, TTFT, queue depth, failure rate, provider actual cost, and resource trend evidence for the deployed commit.
