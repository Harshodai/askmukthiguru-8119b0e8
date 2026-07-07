# Deployment Gap Analysis — Mukthi Guru

Task E7 (Enhancement doc Task Group 6): deployment hardening verification.
Generated against live Docker stack (backend, frontend, qdrant, neo4j, redis, gptcache, prometheus, grafana, jaeger all `Up`).

## E7.1 — `docker-compose.prod.yml` vs Manus stack table

`docker-compose.prod.yml` exists (150 lines). It defines a self-hosted Docker deployment on a single host, pulling pre-built images from GHCR. Comparison against the Manus reference stack:

| Component | Manus target | Current in prod compose | Gap | Action |
|-----------|-------------|------------------------|-----|--------|
| Frontend | Vercel | Nginx container on host (ports 80/443) | No edge CDN/TLS automation | Deploy to Vercel OR add Cloudflare + cert-manager in front of Nginx |
| Backend | Railway | FastAPI container, 2 workers, GHCR image | Self-hosted, no managed PaaS | Acceptable for single-host; Railway/Vercel for auto-scale if needed |
| Vector DB | Qdrant Cloud | Qdrant v1.17.1 container + local volume | No managed Qdrant; no HA/backup | Migrate to Qdrant Cloud for prod, or add S3 snapshot cron |
| Graph DB | Neo4j AuraDB | **Missing from prod compose** | Neo4j not in `docker-compose.prod.yml` (present in dev compose) | Add neo4j service to prod compose or use AuraDB Free/Pro |
| Cache | Upstash Redis | Redis 7-alpine with password + LRU | Self-hosted, no replication | Use Upstash for serverless, or add Redis Sentinel |
| Object storage | AWS S3 | Not referenced | No S3 integration | Add for PDF/doc ingestion storage + backups |
| LLM | Sarvam API / vLLM | `LLM_PROVIDER=sarvam_cloud`, `SARVAM_API_KEY` | OK — matches | None |
| Observability | (not in Manus table) | **Missing from prod compose** | No prometheus/grafana/jaeger in prod compose | Add observability stack or use external APM (see values-production.yaml: `jaeger.enabled: false`, "Use external APM") |
| Celery worker | — | **Missing from prod compose** | Async ingestion worker not in prod | Add celery-worker service to prod compose |

**Biggest gaps:** Neo4j absent from prod compose, no observability stack in prod, no S3, celery-worker missing.

## E7.2 — K8s Helm chart

`k8s/helm/mukthiguru/` exists with full chart: Chart.yaml, values.yaml, values-production.yaml, 12 templates.

**HPA:** `templates/hpa.yaml` present (autoscaling/v2). `values-production.yaml` configures minReplicas=3, maxReplicas=20, CPU+memory metrics, scale-up/down behavior. ✅ Complete.

**PDB:** `templates/pdb.yaml` present (policy/v1). `values-production.yaml` sets `minAvailable: 1`. ✅ Complete.

**Other templates:** backend, frontend, qdrant, redis, neo4j, jaeger, ingress, configmap, secrets, namespace. Ingress supports TLS + cert-manager annotations.

**Gaps:**
- HPA/PDB only target backend deployment — no HPA for frontend (low traffic, acceptable) or celery-worker (not templated at all).
- No celery-worker K8s Deployment template — async ingestion can't run in K8s prod.
- `values-production.yaml` image repos are placeholders (`<YOUR_REGISTRY>/...`) — must fill before deploy.
- No NetworkPolicy templates — pod-to-pod isolation not enforced.

## E7.3 — Security checklist

Created `docs/SECURITY_CHECKLIST.md` (22 items across API security, auth, input validation, secrets, WAF, DDoS, dependency scanning, data protection).

**Done (12):** rate limiting, OAuth2, JWT, session mgmt, test-key backdoor lock, Pydantic validation, guardrails, distress detection, secrets out of git, service-role key isolation, PII redaction, audit logging, backend not public-exposed.

**TODO (10):** TLS cert automation, CORS allowlist verification, external secrets operator (ESO), WAF, DDoS protection, container image scanning (Trivy), SBOM generation, encrypted volumes, S3/Sarvam key rotation policy.

E11 already covered SAST + red-team. See checklist for priority remediation order.

## E7.4 — OpenTelemetry / Jaeger

**Jaeger:** `mukthiguru-jaeger` container `Up 14 hours`. UI at http://localhost:16686. API returns service `mukthiguru-backend` with live traces.

**Instrumentation:** `backend/app/observability.py` initializes OTel on FastAPI startup:
- `FastAPIInstrumentor.instrument_app()` — auto-spans for HTTP requests.
- `LangChainInstrumentor().instrument()` — auto-spans for LLM/chain calls.
- OTLP exporter → `http://jaeger:4317` (gRPC).
- Graceful no-op if packages missing (`OTEL_ENABLED` flag).

**RAG node spans:** `backend/app/tracing.py` provides `trace_rag_node()` decorator + `rag_span()` context manager. **BUT neither is applied to any RAG node** — only appears in docstrings/examples. Traces currently span only FastAPI HTTP + LangChain LLM calls, not individual graph nodes (retrieve/rerank/generate).

**Gap:** Apply `@trace_rag_node("retrieve")` etc. to RAG node functions to get per-node spans in Jaeger. Low-effort — decorators already written, just need to add to node defs in `graph_stage.py` / wherever nodes live.

## E7.5 — Prometheus / Grafana dashboards

`infrastructure/grafana/provisioning/dashboards/mukthiguru_dashboard.json` — existing 4 panels, now extended to 8:

| Panel | Metric | Status |
|-------|--------|--------|
| API Request Latency (p50/p95) | `guru_request_latency_seconds` | Pre-existing ✅ |
| Cache Hit Ratio | `guru_cache_hit_ratio` | Pre-existing ✅ |
| Token Usage Rate | `guru_llm_tokens_total` | Pre-existing ✅ |
| System Error Rate | `guru_llm_errors_total`, `guru_node_errors_total` | Pre-existing ✅ |
| **TTFT (p50/p95)** | `guru_ttft_seconds` | **Added in E7** (E3 metric was defined but had no panel) ✅ |
| **LLM Call Latency (p50/p95)** | `guru_llm_latency_seconds` | **Added in E7** ✅ |
| **Qdrant/Retrieval Latency (p95)** | `guru_retrieval_latency_seconds`, `guru_search_latency_ms` | **Added in E7** ✅ |
| **Circuit Breaker State** | `guru_circuit_breaker_state` | **Added in E7** ✅ |

**Remaining gaps:**
- No Neo4j-specific panel (query latency) — Neo4j doesn't expose Prometheus metrics by default; would need a custom exporter.
- No embedding cache panel (`guru_embedding_cache_ops`) — low priority.
- Dashboard auto-reloads: Grafana provisioning reads the JSON on container restart; to pick up new panels without restart, the dashboard folder mount must be refreshed (restart grafana container or rely on file-provider polling).

## Summary

| Area | Status |
|------|--------|
| Prod compose | Partial — missing Neo4j, observability, celery, S3 |
| K8s Helm | Strong — HPA ✅, PDB ✅; gaps: celery-worker template, NetworkPolicy |
| Security | 12/22 done; WAF + TLS + ESO + image scanning are the prod-launch blockers |
| OTel/Jaeger | Live but shallow — auto-instrumentation only; RAG node decorators unused |
| Grafana | 8 panels now cover LLM latency, cache hit, error rate, TTFT, retrieval, circuit breaker |

## Files changed/created

- `docs/SECURITY_CHECKLIST.md` (new)
- `docs/DEPLOYMENT_GAP_ANALYSIS.md` (new, this file)
- `infrastructure/grafana/provisioning/dashboards/mukthiguru_dashboard.json` (added 4 panels)

## Concerns

1. **Neo4j missing from prod compose** — dev stack has it, prod doesn't. Graph RAG will fail in prod without it. Quick fix: copy neo4j block from dev compose.
2. **RAG node tracing not wired** — `tracing.py` decorators exist but are dead code. Jaeger shows HTTP + LLM spans but not per-node breakdown. One-line fix per node.
3. **K8s celery-worker absent** — ingestion pipeline can't run in K8s prod; only dev compose has it.
4. **No image scanning in CI** — GHCR images pushed without Trivy/Grype scan; security risk for prod deploy.