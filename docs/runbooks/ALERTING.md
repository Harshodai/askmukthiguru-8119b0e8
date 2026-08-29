# Alerting Runbook

Every Prometheus alert in `infrastructure/prometheus/alerting-rules.yml`, with the runbook to follow when it fires. SLO definitions live in `docs/SLO.md`.

## Alert inventory

| Alert | Severity | Meaning | Runbook |
|-------|----------|---------|---------|
| `ChatLatencySLOPage` | page | Chat p95 latency budget burning (multi-window >2x) | #chatlatencyslopage |
| `ChatLatencySLOHigh` | warn | p95 chat latency > 8s for 6h | #chatlatencyslohigh |
| `HealthReadySLOPage` | page | >0.5% of readiness probes not_ready in 15m | #healthreadyslopage |
| `FiveXXRateSLOPage` | page | 5xx rate > 0.1% over 30m | #fivexxrateslopage |
| `FiveXXRateElevated` | warn | 5xx rate > 0.05% over 1h | #fivexxrateelevated |

## <a name="chatlatencyslopage"></a>ChatLatencySLOPage

1. Check LLM provider latency: `GET /api/metrics` → `llm_request_duration_seconds` p95 per provider. Provider degradation is the usual cause (OpenRouter/Sarvam/NIM).
2. Check `guru_requests_total` for a traffic spike; check `queue_size` (backpressure) and Redis `commandstats` for slowness.
3. If provider: consider flipping `LLM_PROVIDER` failover in Railway env (see `docs/RELEASE_READINESS_2026_07_30.md` rollback section) and re-deploy.
4. If queue: concurrency limit tune (`max_concurrent_chat` config).
5. Update `INCIDENT_LOG.md`.

## <a name="chatlatencyslohigh"></a>ChatLatencySLOHigh

Same triage as above but lower urgency (6h window). Verify the trend over the previous day before acting.

## <a name="healthreadyslopage"></a>HealthReadySLOPage

1. `GET /api/health` — which service is failing? (qdrant / redis / neo4j / llm / embedding / graphs)
2. Use `docs/INCIDENT_RESPONSE.md` — scenario "LLM hallucination"/"cross-tenant" do not apply; use "DoS/OOM" or service-specific recovery:
   - Qdrant down → `QDRANT_VAULT.md` (collection recovery), verify `spiritual_wisdom` count.
   - Redis down → caches degrade gracefully by design; verify via `/api/health`.
   - LLM down → circuit breaker opens → `/api/circuit-breaker/status` endpoint.
3. If restart needed: `railway redeploy` (linked service) — but note `railway up` is the reliable path for code changes; plain redeploy restarts the same build.

## <a name="fivexxrateslopage"></a>FiveXXRateSLOPage / FiveXXRateElevated

1. Pull error samples: `railway logs` (deploy logs show `AUDIT <method> <path> -> 5xx` lines) and search for `error_id`.
2. Match error_id to `docs/INCIDENT_RESPONSE.md` scenarios:
   - Timeout flood → global request timeout (504) → check LLM latency (see #chatlatencyslopage).
   - Validation 422s are not 5xx; ignore.
   - `Exception` handler → read stack trace from logs; hotfix via `railway up` with a real change.
3. If the errors are from `/api/chat` only → pipeline crash; check `NODE_ERROR_TOTAL` metric for the failing stage.

## Synthetic alert test (T5)

Local staging: `docker compose up -d prometheus alertmanager` (add to compose if absent), then simulate a 10s latency by pausing the backend container (`docker pause backend`) — the `ChatLatencySLOPage` burn rule will fire within ~2-3 min (`for: 2m` + group_wait 30s). Verify the alert appears in Prometheus UI (`http://localhost:9090`), then `docker unpause backend`.