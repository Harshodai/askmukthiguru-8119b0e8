# Observability and SLOs

The application provides structured health checks, request telemetry hooks, Sentry capture, OpenTelemetry/Jaeger support, queue metrics, and cache metrics. Ordinary tests now disable OTEL by default; integration tests must opt in to verify exporter behavior.

The local `/api/health` endpoint returned HTTP 200 with `ready=false` and `status=unhealthy`. Qdrant, Redis, Neo4j, LLM, embedding, graph, cache, queue, and guardrail checks were healthy; critical `runtime_artifacts` failed because `okf_compiled` was missing. Release orchestration must gate on the readiness payload, not on HTTP status alone.

Recommended SLIs are API availability, accepted-to-completed queue latency, time to first token, completion latency, grounded-answer rate, safe-abstention rate, 429 rate, provider failure rate, retrieval failure rate, queue depth, and oldest job age. Alerts must include route, status class, provider, tenant/corpus, job/correlation ID, and no secrets or raw sensitive prompts.

## Fresh operational evidence — 2026-08-25

The local `/api/health` response was available without authentication and returned HTTP 200, but its payload correctly reported `ready=false` and `status=unhealthy` because `runtime_artifacts.ok=false` with missing `okf_compiled`. The same response exposed healthy local checks for Qdrant, Redis, Neo4j, LLM, embeddings, graph variants, cache, queue, backpressure, and guardrails. This confirms that HTTP availability and deployment readiness are distinct signals.

The local `/api/metrics` and `/metrics` endpoints rejected unauthenticated requests with HTTP 401 and the generic body `Authentication required or session expired`. The response included security headers such as `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a restrictive `frame-ancestors 'none'` CSP directive, and a permissions policy disabling camera, microphone, and geolocation. Authenticated metrics export and trace-correlation behavior remain unverified.

A 20-request, 10-way concurrent health probe returned 20/20 HTTP 200 with p50 115.5 ms, p95 267.7 ms, and maximum 493.9 ms. The result is a local liveness/responsiveness observation only; it cannot be used as an application SLO or chat-capacity claim.
