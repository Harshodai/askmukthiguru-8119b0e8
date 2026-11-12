# Incident runbooks RB-1 to RB-10

Moved from `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` section 3.4 (NEW-OPS-9). Alert rules live in `infrastructure/prometheus/alerting-rules.yml`; the per-alert pages are in `ALERTING.md`. Log every incident in `INCIDENT_LOG.md`.

**Status of this text.** The steps were written from a code reading at commit `c9b42d3e`. No step has been drilled. A name marked `(planned)` is an alert the spec proposes and the repo does not define yet. Tags such as `[DOC-CLAIM]`, `[INF]` and `[unknown]` mark statements the audit could not verify. Code wins over this page.

**Process (applies to every runbook).**

| Step | Action | Warning |
|---|---|---|
| 1 | Acknowledge the alert in the channel within the target in section 3.2. | An unacknowledged `page` alert has no second responder (D-PE1). |
| 2 | Name a severity: Sev-1 (seeker data exposed, teacher-voice prose generated, crisis route failed, or full outage), Sev-2 (degraded answers or spend alarm), Sev-3 (single dependency degraded with a safe fallback). Definitions follow `docs/INCIDENT_RESPONSE.md` section 1. | Do not downgrade a crisis-route or integrity incident. |
| 3 | Append a line to `docs/runbooks/INCIDENT_LOG.md` (to be created by `NEW-OPS-9`): time, alert, severity, request ids. Never paste seeker text. | Request ids and counts only. |
| 4 | Contain first, diagnose second. Each runbook lists the containment action. | Containment must not raise a safety risk (for example, never switch on LLM-generated teaching to restore service). |
| 5 | Verify with the runbook's verification step before closing. | A closed alert is not a verified fix. |
| 6 | Within 48 hours, write the post-incident review with the template in `docs/INCIDENT_RESPONSE.md` section 4. File a regression test or a guard for every Sev-1 and Sev-2. | A rule repeated twice gets a guard (root `CLAUDE.md`). |

Railway steps (rollback, variable change, redeploy, logs) are in `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md`. This section names the action and the decision, not the Railway click path.

All runbooks below have the same fields. "Owner" is the owner (Harshodai) until D-PE1.

## <a name="rb-1"></a>RB-1 LLM provider outage or degradation

| Field | Content |
|---|---|
| Detection | `CircuitBreakerStuckOpen` (`alerting-rules.yml:127`); `LLMProviderErrorBurst` (planned); `guru_llm_errors_total` rising; `/api/ready` returns 503 with `circuit_breaker: open` (`backend/app/api/health.py:601-660`). |
| First actions | (1) Check the provider status page and the provider key balance. (2) Read `guru_circuit_breaker_state{provider}`. The breaker opens after 5 failures and tries half-open after 90 s (`backend/services/circuit_breaker.py:67-68`, `176`). (3) Do **not** set `FIRST_PERSON_LLM_FALLBACK_ENABLED=true`. That flag allows LLM-written teaching prose (root `CLAUDE.md` invariant 21). |
| Diagnosis | When the breaker is open, `CircuitBreakerStage` returns the static fallback and passes crisis messages through to the distress stage (`backend/app/pipeline/stages/guardrail_stage.py:54-64`). The first-person gates (answerability, rerank, relevance) need the LLM. If they fail, the turn abstains (`relevance_indeterminate`, fail closed) [DOC-CLAIM root `CLAUDE.md` invariant 24]. Expect `guru_answer_outcome_total{outcome="abstained"}` to rise and `served` to fall. Separate three causes: provider down (errors by `model` in `guru_llm_errors_total`), key or balance (`error_type`), our guard (`BudgetGuardDenying` (planned), RB-6). |
| Recovery | Wait for the half-open probe. If the provider is back and the breaker is wedged, an admin may call `POST /api/circuit-breaker/reset` (`backend/app/api/health.py:703`). Only do that after a direct provider call succeeds. If a single model is degraded, change the model setting (`OPENROUTER_*_MODEL`) and recreate the service. Do not change the scorer model without D-16 and a frozen-bank run. |
| Verification | `guru_circuit_breaker_state == 0`; one in-corpus smoke question serves a clip; one out-of-corpus question abstains; `guru_answer_outcome_total{outcome="error"}` flat. |
| Seeker experience during outage | Static "unable to answer" fallback, or an honest abstain. No teaching prose is generated. State this on the status page if one exists [unknown]. |
| Owner | Owner. |

## <a name="rb-2"></a>RB-2 Qdrant down or corrupt

| Field | Content |
|---|---|
| Detection | `/api/ready` 503 with `qdrant: false` (`backend/app/api/health.py:601-660`); `/api/health` Qdrant critical failure (`backend/app/api/health.py:280`); `first_person_requests_total{reason="no_verified_clips"}` or `serving_contract_violation` spikes (`backend/app/metrics.py:766-785`); `FirstPersonQuarantineDetected`; `ServedClipIntegrityFailure` (planned). `CollectionPointCountShift` now reads `qdrant_collection_points_count` (NEW-OPS-3). |
| First actions | (1) Confirm the symptom with `/api/health` using the scrape token. (2) Do not write to the collection. Builders hold the write key (T3-02); the backend must not hold it. (3) If points are corrupt or the count changed unexpectedly, treat it as RB-7 as well. |
| Diagnosis | Down: Railway service state, volume state, Qdrant API key mismatch (`config.py:711-714`). Corrupt or drifted: compare the point count and the startup contract log to the signed digest (T3-02). Wrong collection: the serving collection is deployment configuration. Root `CLAUDE.md` names `first_person_v8` (invariant 23) and a v10-only mode (invariant 25). The startup contract stops the process when `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` do not satisfy it [DOC-CLAIM]. Code wins. Read the effective posture from the startup log (`NEW-OPS-6`). |
| Recovery | Degraded: the exact cache or an honest abstain serves (`grounding_state=abstained`); no action beyond restoring Qdrant. Down with volume intact: restart the service, then run the verification. Down or corrupt with data loss: restore the latest snapshot into a scratch collection, verify (section 3.7), then point `FIRST_PERSON_COLLECTION` to it and recreate the backend (root `CLAUDE.md` invariant 23 procedure). **If no off-host snapshot exists, the only copy of the corpus is on the owner's Mac (DATA-01) and recovery time is unbounded.** That is why D-26 and `T3-10` precede any public exposure. |
| Verification | Point count equals the snapshot manifest; 10 fixed questions return the same top-1 as the recorded set (B9); hash gate on a 50-point sample: `sha256(verbatim_text) == source_text_hash` on v10; startup log shows the intended collection. |
| Owner | Owner. |

## <a name="rb-3"></a>RB-3 Redis down

| Field | Content |
|---|---|
| Detection | `RedisDegradedMode` (planned); `/api/health` Redis critical failure (`backend/app/api/health.py:282`); `guru_cache_operations_total` errors. |
| First actions | Confirm whether Redis is down or only the network path. Do not restart the backend first. |
| Diagnosis | Effects that follow from code: anonymous quota drops to a process-local limit, default `min(limit, 3)` per session, pinned for the window (`backend/CLAUDE.md` description of `AnonQuotaRedisAdapter`; metric `anon_quota_degraded_mode_total`); the rate limiter requires Redis in production per `backend/app/core/limiter.py:50-60` comment [INF: fallback behaviour on outage not read]; the spend ledger falls to 10% of the caps **per replica** (`openrouter_budget.py:20,188-202`), so the guard may refuse calls early and the seeker sees more abstains; exact-answer cache is bypassed; Celery broker and result backend are Redis (`celery_config.py:34-38`), so ingestion, memory outbox and beat stop. |
| Recovery | Restore Redis. Sessions pinned to degraded mode stay at the lower limit until the window ends. After recovery check the budget ledger: a lost Redis resets the day's reserved spend to zero, so the real day total may exceed the cap that day. Read the provider's own usage page. |
| Verification | `anon_quota_degraded_mode_total` stops increasing; `/api/health` Redis ok; a beat task runs (memory outbox drains every 60 s, `celery_config.py:105-107`). |
| Owner | Owner. |

## <a name="rb-4"></a>RB-4 Supabase down

| Field | Content |
|---|---|
| Detection | `TelemetrySinkFailing` (planned); authentication errors in logs; `/api/health` auth or database fields (not read here). |
| First actions | Check the Supabase status page. Do not rotate keys. |
| Diagnosis | Anonymous chat uses an HMAC session token, not Supabase (`backend/CLAUDE.md`, `resolve_anon_identity`, `services/auth_service.py:762`). Authenticated routes use `get_current_user_from_supabase` (`auth_service.py:617`) and will fail. Telemetry writes fail and are counted (`telemetry_sink_writes_total{outcome="error"}`). Memory consent checks fail closed (invariant of the memory spec). **Account deletion cannot complete while the backend or Supabase is down (ADV-01, SEC-004).** Exact chat behaviour of an anonymous turn when Supabase auth endpoints time out: unknown; test in the drill. |
| Recovery | Wait for Supabase. If the outage exceeds the RPO window, do not restore the database from a backup over a live project without a decision from the owner. Postgres restore steps: `docs/BACKUP_RESTORE.md` lines 272-308 (Supabase Free Path). |
| Verification | `telemetry_sink_writes_total{outcome="ok"}` increases; an authenticated smoke request succeeds; queued deletions (if any) drain. |
| Owner | Owner. |

## <a name="rb-5"></a>RB-5 Bad deploy

| Field | Content |
|---|---|
| Detection | Post-deploy smoke set fails (A10); `ChatErrorOutcomeRate` (planned); `FiveXXRateSLOPage`; `ExternalProbeDown` (planned); startup log shows an unexpected collection, scorer model or budget posture. |
| First actions | Roll back to the previous deployment (Railway runbook). Do not "fix forward" while a safety or integrity alert is firing. |
| Diagnosis | A replica that boots passes `/api/healthz` after the 180 s grace only if the heartbeat and the executor canary are fresh (`start_railway.py:432-500`). It does not check the collection, the gates or the answer. So a bad configuration can pass the deploy healthcheck. Identify the release: `release_manifest` `git_sha` defaults to `RAILWAY_GIT_COMMIT_SHA` (`backend/app/release_manifest.py:109-135`). Config drift (R-6 of `26`): compare variables to the per-environment profile (`NEW-OPS-6`). Database migration involved: `docs/runbooks/MIGRATION_ROLLBACK.md`. |
| Recovery | Redeploy the previous image. If a variable caused it, restore the previous value and recreate. Collection rollback is a variable change plus recreate; it must satisfy the startup contract (see RB-2). |
| Verification | Smoke set passes: 3 in-corpus (clip or abstain), 3 out-of-corpus abstain, 2 crisis messages reach the helpline route, 1 greeting, 1 memory-consent case, 0 HTTP 5xx, each turn emits `answer_outcome` (Gate A10). |
| Owner | Owner. |

## <a name="rb-6"></a>RB-6 Cost spike or spend-cap denial

| Field | Content |
|---|---|
| Detection | `LLMSpendDailyAbove80Percent` (planned); `BudgetGuardDenying` (planned); provider dashboard alert (Gate A15 requires a provider-side key limit as the second control); `LLMCostUnknown` (planned). |
| First actions | (1) Read spend by `provider` and by `operation` and `model` (`guru_openrouter_estimated_cost_usd_total{model,operation}`). (2) If one address or one route is the source, block it at the edge or disable the route. (3) If the source is unknown, lower the caps through the variables `OPENROUTER_DAILY_BUDGET_USD` and `OPENROUTER_MONTHLY_BUDGET_USD` [INF: pydantic env names for `config.py:640-641`] and recreate. (4) If the key may be leaked, rotate it (`docs/runbooks/SECRET_ROTATION.md`; `docs/INCIDENT_RESPONSE.md` 2.1). |
| Diagnosis | Candidates in code order: the unauthenticated first-person route (`first_person.py:295-300`, 120 per minute per IP; arithmetic in 2.5); a retry storm after a provider error (`llm_max_retries=2`, [DOC-CLAIM `15` section 2]); a model price change or an unpriced model (`LLMCostUnknown` (planned)); ingestion or re-ingest jobs that call a paid model (`reingest_openrouter_model`, `config.py:656`); an `operation` whose call count per turn grew (RET-10: up to 4 calls per question). Join `answer_outcome.llm_calls` by `prompt_id` (it is the `operation` name). |
| Recovery | Reduce the source. Keep the guard fail-closed. Never set `allow_uncapped_llm_spend` to ride out a spike. When the cap is the limit and seekers abstain, state it in the incident log. |
| Verification | `increase(guru_provider_reported_cost_usd_total[1h])` below the hourly share of the cap; no `BudgetGuardDenying` (planned); provider dashboard agrees within the expected estimate error. |
| Owner | Owner. |

## <a name="rb-7"></a>RB-7 Integrity breach (`guru_integrity_breach_total` increases)

| Field | Content |
|---|---|
| Detection | `FirstPersonIntegrityBreach` (`increase(guru_integrity_breach_total[15m]) > 0`); the log line `integrity_breach: generated answer in first-person-only mode` (`answer_outcome.py:194`); `ServedClipIntegrityFailure` (planned); `FirstPersonQuarantineDetected` (a quarantine is a catch, not a breach). Gate B10 requires that any increase pages the owner. |
| First actions | Sev-1. (1) Contain: turn the bridge off with `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` and recreate. With the bridge off and `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`, teaching turns return the static abstain without an LLM (test names in the register: `test_bridge_off_returns_static_abstain_without_llm`). (2) Flush the exact cache so no breached answer is replayed (`scripts/ops/flush_cache.py`). (3) Save the `answer_outcome` log lines for the window: `request_id`, `route_decision`, `model_used`, `span_ids`. Do not save seeker text. |
| Diagnosis | A breach means the teaching lane served a turn with a non-empty `model_used`. Read the effective posture: `first_person_chat_bridge_enabled`, `first_person_llm_fallback_enabled`, `fp_fail_closed_enabled` (`config.py:435`). Check whether `fp_fail_closed_enabled` was set false (the rollback flag, `fp_fail_closed.py:28-32`). Check `route_decision` of the offending turns: a node that bypasses `generate_answer`'s guard (`generation.py:2669-2676`) is the usual suspect. Check for a hash failure instead: `sha256(verbatim_text)` against `source_text_hash`. |
| Recovery | Fix the cause. Add a regression test that reproduces the route. Do not switch the bridge back on until the test fails before the fix and passes after, and the owner has read the offending `answer_outcome` records. |
| Verification | No increase for 24 h on staging replay of the 10-question smoke set plus the adversarial suite (section 3.9); `guru_fp_fail_closed_total` shows the expected reasons only. |
| Notification | If a seeker received generated text attributed to a teacher, tell the teachers' organisation contact (unassigned today; D-PE1). |
| Owner | Owner. |

## <a name="rb-8"></a>RB-8 Crisis-route failure

| Field | Content |
|---|---|
| Detection | `CrisisLaneUnboundedAdmission` (planned); `guru_answer_outcome_total{lane="crisis"}` zero while crisis canary messages are sent (canary is `NEW-OPS-5`); the crisis canary fails; a seeker report; `guru_distress_detections_total` falls to zero while traffic continues. |
| First actions | Sev-1. (1) Run the two crisis canary messages by hand and read the response. (2) If the helpline response is missing or wrong, take the chat route offline (scale the backend to zero or return a maintenance response) rather than serve teaching to a seeker in crisis. This is an operator action. It is the compliant variant. (3) Check `config/helplines.yaml` is present and loads. |
| Diagnosis | Failure points in code order: admission (a crisis message takes a slot from a separate pool and is never shed; if that pool is exhausted the turn runs without a slot, `chat.py:278-325`); input guardrail then distress stage run before the circuit-breaker stage (root `CLAUDE.md` pipeline order; `CircuitBreakerStage` passes crisis keywords through, `guardrail_stage.py:54-64`); regex classifier gaps for Indic languages are not native-reviewed (R-4 of `26`; SAFE-001). A pipeline timeout of 105 s (`config.py:124`) means a crisis turn can wait 105 s if a stage hangs. |
| Recovery | Fix and redeploy only after the canary passes in staging. Do not hot-edit patterns without running `evals/run_safety_scenarios.py` (backend `CLAUDE.md`). |
| Verification | Both canary messages return the helpline response within 2 s (SLO-2); `evals/run_safety_scenarios.py` passes. |
| Notification | Clinician contact: unassigned (D-PE1). Until assigned, the owner is both responder and reviewer. |
| Owner | Owner. |

## <a name="rb-9"></a>RB-9 Celery queue backlog

| Field | Content |
|---|---|
| Detection | `CeleryQueueBacklog` (`celery_queue_length`) and `CeleryBeatOrWorkerSilent` (`celery_beat_last_tick_timestamp_seconds`, written by the `beat_heartbeat` task every 30 s), both exported by the backend at scrape time (NEW-OPS-7). By hand: `redis-cli -n 1 LLEN <queue>` for each of `ingestion, embedding, indexing, okf, memory` (`start_railway.py` `_CELERY_ALLOWED_QUEUES`); memory-outbox rows older than 5 minutes. `celery_task_result_total{task,result}` shows failures and retries. |
| First actions | Check that a worker service exists at all: `.railway/railway.ts` declares `celery-worker` and `celery-beat` unless `INCLUDE_CELERY` is false (D-30). If the worker is absent, tasks queue forever; `CeleryBeatOrWorkerSilent` is the alert for that. |
| Diagnosis | A long task over 3600 s delivers twice (`celery_config.py:85`). `max_retries=0` on `drain_memory_outbox` (`tasks/memory_outbox_tasks.py:259`) means a failed drain waits for the next beat tick. `asyncio.run` inside tasks can fail with a loop error when run inside a running loop (CQ-011). Redis down is RB-3. |
| Recovery | Start or restart the worker with the right `CELERY_QUEUES` and `CELERY_CONCURRENCY` (1 to 32, `start_railway.py:117-134`). Purge a queue only after reading the tasks in it. Never purge the `memory` queue without checking consent receipts, because the outbox is a user-data path. |
| Verification | Queue length falls; the last-success gauge for the task is recent. |
| Owner | Owner. |

## <a name="rb-10"></a>RB-10 Ingestion failure

| Field | Content |
|---|---|
| Detection | `sweep_stale_ingest_jobs` marks stale jobs every 5 minutes (`celery_config.py:117-118`); `ingest_quality_gate_rejections_total`, `corpus_gate_rejections_persist_failed_total` (`metrics.py`, names in section 2.2 inventory scan); a build script exits non-zero. |
| First actions | Stop the job. Ingestion never writes to a serving collection directly: every Qdrant, OKF or graph write goes dry-run, snapshot, owner approval, apply (`backend/CLAUDE.md`). Confirm no write reached the serving collection (`CollectionPointCountShift`). |
| Diagnosis | Embeddings run host-side, never in the container (6 GiB limit, exit 137; root `CLAUDE.md` invariant 18). A rights gate refusal is a feature, not a failure (`ingest.py` rights clearance, T1-08). A transcript text change must update `transcript_hash` and `source_text_hash` in the same transaction (invariants 13 and 2). |
| Recovery | Fix the input, re-run the dry run, then re-apply. New version means a new collection; keep the old one for rollback (invariant 4). |
| Verification | Dry run report matches expectations; hash gate sample passes; point count equals the builder's report. |
| Owner | Owner. |
