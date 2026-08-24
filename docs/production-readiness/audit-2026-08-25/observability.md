# Observability and SLOs

The application provides structured health checks, request telemetry hooks, Sentry capture, OpenTelemetry/Jaeger support, queue metrics, and cache metrics. Ordinary tests now disable OTEL by default; integration tests must opt in to verify exporter behavior.

The local `/api/health` endpoint returned HTTP 200 with `ready=false` and `status=unhealthy`. Qdrant, Redis, Neo4j, LLM, embedding, graph, cache, queue, and guardrail checks were healthy; critical `runtime_artifacts` failed because `okf_compiled` was missing. Release orchestration must gate on the readiness payload, not on HTTP status alone.

Recommended SLIs are API availability, accepted-to-completed queue latency, time to first token, completion latency, grounded-answer rate, safe-abstention rate, 429 rate, provider failure rate, retrieval failure rate, queue depth, and oldest job age. Alerts must include route, status class, provider, tenant/corpus, job/correlation ID, and no secrets or raw sensitive prompts.
