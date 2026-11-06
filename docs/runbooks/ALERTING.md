# Alerting Runbook

Every Prometheus alert in `infrastructure/prometheus/alerting-rules.yml`, with the runbook to follow when it fires. SLO definitions live in `docs/SLO.md`.

## Alert inventory

Severity values: `critical` and `page` page the owner; `warn` and `info` go to Slack. Alertmanager routes exactly these four (`test_alerting_pipeline.py` fails on any other value). Incident process, severity definitions and RB-1 to RB-10: `INCIDENT_RUNBOOKS.md`. Log every incident in `INCIDENT_LOG.md`.

The Prometheus scrape path is `/internal/metrics` with the `METRICS_SCRAPE_TOKEN` bearer. `/metrics` is admin plus AAL2 and is for people. Do not point Prometheus at `/api/metrics` (a per-user JSON route).

| Alert | Severity | Meaning | Runbook |
|-------|----------|---------|---------|
| `ChatLatencySLOPage` | page | Chat p95 latency budget burning (multi-window >2x) | #chatlatencyslopage |
| `ChatLatencySLOHigh` | warn | p95 chat latency > 8s for 6h | #chatlatencyslohigh |
| `SLOViolationPresent` | info | Some SLO latency violations are occurring; no burn yet | #chatlatencyslohigh |
| `HealthReadySLOPage` | page | >0.5% of readiness probes not_ready in 15m | #healthreadyslopage |
| `FiveXXRateSLOPage` | page | 5xx rate > 0.1% over 30m | #fivexxrateslopage |
| `FiveXXRateElevated` | warn | 5xx rate > 0.05% over 1h | #fivexxrateelevated |
| `CircuitBreakerStuckOpen` | page | LLM provider breaker OPEN for over 5 minutes | #circuitbreakerstuckopen |
| `FirstPersonQuarantineDetected` | warn | Integrity gate quarantined a clip (a catch, not a breach) | #firstpersonquarantinedetected |
| `FirstPersonLatencySLOBreach` | warn | First-person route p95 above 1s for 10m | #firstpersonlatencyslobreach |
| `FirstPersonErrorRateHigh` | critical | First-person route error rate above 5% for 10m | #firstpersonerrorratehigh |
| `FirstPersonAbstainRateElevated` | warn | More than 50% of first-person requests abstained for 15m | #firstpersonabstainrateelevated |
| `FirstPersonRelevanceIndeterminateSpike` | warn | More than 25% of requests abstained because the relevance scorer failed | #firstpersonrelevanceindeterminatespike |
| `FirstPersonIntegrityBreach` | page | A turn returned generated teaching text in first-person-only mode | #firstpersonintegritybreach |
| `CollectionPointCountShift` | critical | A first-person collection changed by more than 100 points in 1h | #collectionpointcountshift |
| `BackupStale` | warn | No verified backup report for 48h, or nothing reporting | #backupstale |
| `CeleryBeatOrWorkerSilent` | warn | The beat heartbeat has not run for 3 minutes | #celerybeatorworkersilent |
| `CeleryQueueBacklog` | warn | A Celery queue holds over 100 messages for 15m | #celeryqueuebacklog |

## <a name="chatlatencyslopage"></a>ChatLatencySLOPage

1. Check LLM provider latency: `GET /internal/metrics` (bearer `METRICS_SCRAPE_TOKEN`) → `llm_request_duration_seconds` p95 per provider. Provider degradation is the usual cause (OpenRouter/Sarvam/NIM).
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

## <a name="fivexxrateslopage"></a><a name="fivexxrateelevated"></a>FiveXXRateSLOPage / FiveXXRateElevated

1. Pull error samples: `railway logs` (deploy logs show `AUDIT <method> <path> -> 5xx` lines) and search for `error_id`.
2. Match error_id to `docs/INCIDENT_RESPONSE.md` scenarios:
   - Timeout flood → global request timeout (504) → check LLM latency (see #chatlatencyslopage).
   - Validation 422s are not 5xx; ignore.
   - `Exception` handler → read stack trace from logs; hotfix via `railway up` with a real change.
3. If the errors are from `/api/chat` only → pipeline crash; check `NODE_ERROR_TOTAL` metric for the failing stage.

## <a name="circuitbreakerstuckopen"></a>CircuitBreakerStuckOpen

Follow RB-1 in `INCIDENT_RUNBOOKS.md#rb-1`. Do not enable `FIRST_PERSON_LLM_FALLBACK_ENABLED` to restore service: it allows LLM-written teaching.

## <a name="firstpersonquarantinedetected"></a>FirstPersonQuarantineDetected

A quarantine means the serve-time gate caught a bad clip. It did not reach a seeker.

1. Read `first_person_quarantined_total` and the quarantine log lines for the window (clip ids only).
2. Compare `sha256(verbatim_text)` with `source_text_hash` on a sample (on v10 this is the field the gate checks).
3. If the count keeps rising, treat the collection as corrupt: `INCIDENT_RUNBOOKS.md#rb-2`.

## <a name="firstpersonlatencyslobreach"></a>FirstPersonLatencySLOBreach

The first-person route calls the LLM for the answerability gate, the rerank and the relevance scorer. Uncached latency is about 4 to 6 s by design (root `CLAUDE.md` invariant 22). Check provider latency first (RB-1), then Qdrant. This rule's 1 s threshold is older than that finding. Do not tune it without a measurement.

## <a name="firstpersonerrorratehigh"></a>FirstPersonErrorRateHigh

1. Group `first_person_requests_total{status="error"}` by `reason`.
2. Provider errors: RB-1. Qdrant errors: RB-2. Budget refusals: RB-6.
3. A crisis message must still reach the helpline route. Send the two canary messages (RB-8).

## <a name="firstpersonabstainrateelevated"></a>FirstPersonAbstainRateElevated

Abstains are honest, so a spike is a quality or dependency signal, not an outage by itself.

1. Group `first_person_requests_total{status="abstained"}` by `reason`.
2. `relevance_indeterminate` dominant: see #firstpersonrelevanceindeterminatespike.
3. `no_verified_clips` or `serving_contract_violation` dominant: RB-2.
4. Budget denials (`guru_budget_denied_total`): RB-6.

## <a name="firstpersonrelevanceindeterminatespike"></a>FirstPersonRelevanceIndeterminateSpike

The relevance scorer timed out, errored or returned an unparseable reply, so the turn abstained (fail closed).

1. Check provider status and `guru_circuit_breaker_state` (RB-1).
2. Check `FIRST_PERSON_RELEVANCE_TIMEOUT_S` (default 25 s in `Settings`; D-PG13 is open) and the scorer model named in the startup `Serving posture:` log line.
3. Do not change the scorer model without the owner's decision (D-16) and a frozen-bank run.

## <a name="firstpersonintegritybreach"></a>FirstPersonIntegrityBreach

Sev-1. Follow RB-7 in `INCIDENT_RUNBOOKS.md#rb-7` now. Contain first: bridge off, flush the exact cache, save the `answer_outcome` log lines (request ids only, no seeker text).

## <a name="collectionpointcountshift"></a>CollectionPointCountShift

The count comes from `qdrant_collection_points_count`, read at scrape time with the read-only key. A series that disappears means Qdrant could not be read, which is RB-2, not this alert.

1. Was a promotion or a rebuild running? Ingestion must never write to a serving collection directly (RB-10).
2. If not, treat it as corruption: RB-2 and RB-7.

## <a name="backupstale"></a>BackupStale

The metric `backup_last_success_timestamp_seconds{store,target}` is written by `scripts/ops/backup_metrics.py` after a backup verifies. It fires when the series is absent, too.

1. `tail /var/log/mukthiguru/backup-qdrant-fp.log` and `backup-qdrant.log` on the backup host.
2. A line `not reported: set BACKUP_METRICS_DIR or PUSHGATEWAY_URL` means the backup ran and nothing carries the metric. Fix the env file (`infrastructure/cron/mukthiguru-backup`).
3. A `FAIL` line means verification failed. The artefact was renamed `*.failed`; keep it for inspection.
4. Restore rehearsal and off-host copy are `T3-10` (not done). Until then a backup exists only on the host.

## <a name="celerybeatorworkersilent"></a>CeleryBeatOrWorkerSilent

The `beat_heartbeat` task runs every 30 s on the `memory` queue. A stale tick means beat is down, no worker consumes `memory`, or Redis is unreachable.

1. Are `celery-beat` and `celery-worker` running? Check the Railway service states.
2. `redis-cli -n 1 GET mukthi:celery:beat_last_tick`.
3. Redis down: RB-3. Otherwise RB-9. The memory outbox (consent behaviour) is not draining while this fires.

## <a name="celeryqueuebacklog"></a>CeleryQueueBacklog

RB-9. Read the tasks in a queue before purging it. Never purge `memory` without checking consent receipts.

## Synthetic alert test (T5)

Local staging: `docker compose up -d prometheus alertmanager` (add to compose if absent), then simulate a 10s latency by pausing the backend container (`docker pause backend`) — the `ChatLatencySLOPage` burn rule will fire within ~2-3 min (`for: 2m` + group_wait 30s). Verify the alert appears in Prometheus UI (`http://localhost:9090`), then `docker unpause backend`.