# Log events, fields and how to query them on Railway (2026-11-28)

Scope: what the backend writes to stdout/stderr on the chat path, what is new behind
flags, the privacy rules every log line must keep, and how to query it. Source of the
design: the per-question trace audit of 2026-11-28 (branch
`chore/railway-live-audit-2026-11-27`). Nothing here changes an answer: logging only.

## 1. Privacy rules (hold for every log line, any level, DEBUG included)

Seekers write about grief, abuse and suicide. A log line may carry:

- ids: trace/request/job/correlation ids, clip/point/video/parent ids;
- counts, scores (integers 0 to 3), durations, booleans;
- gate names, model ids, bounded reason codes (`[a-z0-9_]`, at most 48 characters);
- `q_len` and `lang`.

A log line must never carry: question text, clip text, prompts, LLM replies, user ids,
IPs, phone numbers, or text derived from the question (expanded anchors, editorial
facets, teacher or tradition names found in the question). Exception text is also out on
paths that handle those strings (a validation error can echo its input): log
`type(exc).__name__`.

Question tags: `app/log_safe.q_tag` gives `len=<n> sha=<8 hex>`. The hash is an HMAC under
a random per-process key, so a short common question cannot be recovered by hashing a
dictionary. The cost is that a tag matches only lines from the same process (it changes on
restart and differs between replicas). Never use an unsalted hash of seeker text.

Guards: `tests/test_no_seeker_text_in_logs.py` (AST ratchet, budget 0),
`tests/test_log_privacy_sentinels_2026_11_28.py` (a sentinel question, clip text and LLM
reply are pushed through the first-person pipeline and bridge with DEBUG on and must not
appear in any record), `tests/test_debug_logs_no_exception_text_2026_11_28.py` (no
DEBUG/INFO line in the first-person modules formats a bare exception).

## 2. Settings (all default OFF; rollback of each is to unset it)

| Env var | Effect when `true` |
|---|---|
| `LOG_JSON_STDOUT_ENABLED` | One JSON handler on **stdout** replaces the plain stderr handler that `start_railway.py` installs before the app imports. `level` becomes `debug/info/warn/error` (Railway's documented values), uvicorn and uvicorn.error propagate to root, so startup lines and ASGI tracebacks are JSON too. Lines logged before the app import keep the stderr handler. |
| `LOG_TURN_TRACE_ENABLED` | Per-turn trace: the `answer_outcome` line gains ids, timings and the first-person gate fields (section 4). Also enables `JOB_RESULT_FETCHED`. With it off the record and its log line are byte-identical to before. The record travels to the formatter as the `mg_fields` log attribute (namespaced so no other logger can collide). |
| `LOG_DEBUG_LOGGERS` | Comma list of **exact** logger names set to DEBUG at startup. Only the six audited first-person modules are honoured (`app.main.DEBUG_LOGGER_ALLOWLIST`: `services.first_person_pipeline`, `services.first_person_legacy`, `services.first_person_context_store`, `services.first_person_context_harness`, `services.first_person_judge`, `app.pipeline.stages.first_person_bridge`). Anything else, including a parent such as `services` or `app`, is ignored and counted in the startup INFO line, because a parent would also switch on every unaudited child. Empty means unchanged. |

Why `LOG_JSON_STDOUT_ENABLED` matters: today every line reaches Railway as plain text on
stderr, and Railway documents that stderr becomes `level.error`. That is why INFO lines show as errors, and why
no field can be queried with `@name:value`. `PIIScrubber` still runs on the surviving
handler, so this is a parseability and severity bug, not a leak. Verify after flipping it
on: lines are JSON, `@level:info` works, and the error count drops to real errors.

## 3. Events

| Event (message prefix) | Level | Fields | Where |
|---|---|---|---|
| `answer_outcome` | info | see section 4 | `app/answer_outcome.py`, emitted once per turn from `PipelineCoordinator.execute` |
| `FIRST_PERSON_BRIDGE_SERVED` | info | `trace_id clips pipeline_latency_ms cached` | `first_person_bridge.py` |
| `FIRST_PERSON_BRIDGE_ABSTAIN` | info | `trace_id status reason cause answerability fallback=disabled`. `reason` is the pipeline abstain reason (`relevance_below_min`, `answerability_withheld`, `no_verified_clips`, `joint_insufficient`, ...); it used to be the constant `llm_fallback_disabled`. | `first_person_bridge.py` |
| `[FirstPersonPipeline] status=... reason=...` | info | `status reason latency_ms confidence n_quarantined n_citations llm_tokens` | `FirstPersonPipeline._log_and_count`, every exit |
| `OPENROUTER_CALL_TIMING` | info | `operation model attempts total_ms tokens cost limiter_wait_ms pool_wait_ms connect_ms ttfb_ms read_ms status` | `openrouter_service.py` (read by `scripts/ops/check_openrouter_usage_cost.py`: keep at INFO) |
| `PIPELINE_STAGE_TIMING` | info | `job_id trace_id stage status duration_ms` | `stage_runner.py` (about 12 to 19 lines per turn; candidate to demote to DEBUG later, owner decision) |
| `JobQueue: enqueued ...` | info | `job_id stream queue_position` (no user id) | `job_queue.py` |
| `JobQueue worker N: completed ...` | info | `job_id` | `job_queue.py`; worker lines now carry the request's `correlation_id` |
| `JOB_RESULT_FETCHED` | info | `job_id fetch_lag_ms since_created_ms` (needs `LOG_TURN_TRACE_ENABLED`) | `app/api/job_routes.py`; `fetch_lag_ms` is the server-visible part of poll quantization |
| `auth failed for provided token reason=... alg=... kid=... iss_host=... suppressed=N` | warning | One line per failed bearer token, rate limited to 1 per 60 s per `(reason, kid, iss_host)` per process; `suppressed` counts the lines held back since the last one. `reason` comes from the exception **type** only: `expired, not_yet_valid, bad_signature, bad_issuer, bad_audience, bad_algorithm, missing_claim, malformed, jwks_fetch_failed, jwks_key_not_found, invalid_token, other, rejected`. `kid` is the first 8 characters of the unverified header, `iss_host` the unverified issuer host (`unknown` when unreadable). Never the token, other claims, user ids or emails. | `services/auth_service.py` |
| `Context expansion posture: N flag(s) on but documented off ... fingerprint=` | warning | One line at boot (was five). Still a WARNING: the posture is the owner's decision. | `app/runtime_budget.py` |

### Reading `FIRST_PERSON_BRIDGE_ABSTAIN`

`cause` is the public bucket (`no_evidence`, `system_unavailable`, `topic_boundary`) and
is a catch-all: `no_evidence` is anything that is neither a system error nor a topic
refusal. `reason` is what says which gate refused.

## 4. The `answer_outcome` record with `LOG_TURN_TRACE_ENABLED=true`

Existing keys are unchanged (`request_id lane route_decision route_reason outcome
grounding_state citation_count span_ids verification_method verification_passed cache_hit
latency_ms model_used stage_latencies_ms llm_calls total_tokens_in total_tokens_out
total_cost_usd`). `route_reason` is capped at 80 characters. Additive keys:

- ids: `job_id`, `correlation_id`, `pid` (the pid separates workers: the HyDE cache is per process).
- `turn`: `q_len`, `lang`, `ingress_ms` (handler entry to enqueue), `queue_wait_ms`
  (admitted to claimed), `dispatch_ms` (claimed to pipeline start), `stage_ms{stage: ms}`.
  Everything before the answer is in this block, which is what explains the gap between a
  client's end-to-end time and `pipeline_latency_ms`.
- `fp`: `n_retrieved retrieval_ms try2_used n_anchors n_try2 sizing_k sizing_ms embed_ms
  embed_calls hyde_state hyde_ms answerability answerability_ms rejected{gate: count}
  scores[] min_score n_scored judge_passed judge_indeterminate judge_retried
  comparative_used n_served n_quarantined pipeline_status abstain_reason pipeline_ms cached
  is_direct abstain_cause gate_that_rejected`.
  - `hyde_state` is one of `off, non_latin, cache_hit, no_provider, generated, failed`.
  - `answerability` is one of `yes, no, indeterminate, permissive`.
  - `rejected` gate names: `integrity, content_quality, allowlist, blocklist, boundary,
    shared_policy, antecedent, unknown_span, no_spans, prepare_error, decide_<decision>`.
  - `scores` are integers 0 to 3, at most 12.
  - `gate_that_rejected` is a label built when the record is built (never set by a gate and
    never read by one): the specific abstain reason; else the largest `rejected` bucket when
    nothing was scored; else `relevance_min_score` when every score is below `min_score`; else
    `answerability`. It is `null` for a served turn.
- `llm_calls[]` rows gain `duration_ms attempts limiter_wait_ms status` (`ok, timeout,
  cancelled, refusal, error`). Timed-out, cancelled and refused calls now appear, with zero
  tokens and zero cost, so slow-then-abstain turns are explained.
- `summary`: `llm_calls_n llm_ms_sum llm_ms_max throttle_wait_ms_sum retries_sum`.

Known gaps: values written from the sync `run_llm_coroutine` bridge do not carry the
context and are lost (only offline tools and the legacy tail use it); the streaming
OpenRouter call site records no per-call timing.

### Why the same question can take 8 s with 3 clips, then 4.5 s with 1 clip

Each candidate is now one field in the record: `hyde_state` (`generated` costs an LLM call
and an embed; `cache_hit` only if the same process serves it), `scores` against
`min_score` (a score of 2 on one run and 1 on the next changes the clip count), `n_try2`
and `judge_retried`, `limiter_wait_ms`/`attempts` per call, and `cached`.

## 5. Querying on Railway

Prerequisite: `LOG_JSON_STDOUT_ENABLED=true`. Railway documents that it parses single-line
JSON with `message`, `level` and custom attributes, queryable as `@name:value`
(docs.railway.com/guides/logs). **Not verified here:** how Railway addresses a nested
attribute (`fp.abstain_reason` as a dotted path, or only top-level keys), and whether a
numeric range such as `>6000` is supported. Check both on the first deployed line. If
nested paths do not work, the fix is to flatten `fp`/`turn` into top-level keys in
`JSONFormatter`, not to change the record.

Candidate filters (the simple ones use only documented top-level syntax):

```
@message:answer_outcome @outcome:abstained
@message:answer_outcome @lane:first_person @outcome:served
@level:warn "auth failed for provided token"
@level:error
```

To check once nested paths are confirmed to work: `@fp.abstain_reason:relevance_below_min`,
`@fp.hyde_state:generated`.

Group abstains by `fp.abstain_reason` and `fp.gate_that_rejected` to separate "the corpus
had nothing" (`rejected` buckets empty, `n_retrieved` 0) from "the gates refused everything".
Join a worker line to its request with `correlation_id`. Without JSON on, grep the
message: with `LOG_TURN_TRACE_ENABLED` the `answer_outcome` message is valid JSON.

Limits: Railway drops lines above 500 per second per replica, and retention is 7 days
(Hobby) or 30 days (Pro). One `answer_outcome` per turn is the line to keep if volume ever
forces demotion of the per-stage and per-context INFO lines.

## 6. OpenTelemetry

Open question from the audit: is the OTEL exporter failing on every batch on Railway?
(`OTEL_ENABLED` defaults to true and the endpoint to `http://jaeger:4317`, and
`.railway/railway.ts` sets no `OTEL_*` variables.) **Answered by the live logs: Railway
runs with `OTEL_ENABLED=false`, and every boot logs "OpenTelemetry tracing disabled by
OTEL_ENABLED=false". No exporter is running, so there are no exporter failures to chase.**
This change does not touch OTEL behaviour. Langfuse or an OTLP exporter remains a separate
owner decision (`docs/architecture/llm-observability-design.md`, phase 2).

## 7. Not verified, not done

- The Railway query syntax in section 5 (nested attribute paths, numeric ranges) was not run.
- Railway behaviour for the new JSON on stdout was not tested live (no Railway access in
  this change). Railway documents lowercase `debug, info, warn, error`; whether a JSON
  `level` overrides the stdout mapping is not documented. Verify after the owner flips the
  flag.
- The `PIIScanner` regexes can mangle a long digit run inside a string (about 2% of uuids
  hold a 10-digit run). Structured trace fields skip the scrubber for `*_id` keys for that
  reason; the free-text `message` still goes through it.
- No Redis field was added for `ingress_ms`: it rides `request_data["_ingress_ms"]` only
  when `LOG_TURN_TRACE_ENABLED` is on, and the worker reads `request_data` by key.
- Demoting `PIPELINE_STAGE_TIMING` and the harness per-context INFO lines to DEBUG was not
  done (owner decision once the canonical line is proven).
- A global cap on distinct auth-failure keys does not exist: the rate limit is per
  `(reason, kid, iss_host)` with a 256-key map, so an attacker who varies `kid` on every
  request defeats it. The map stays bounded; the log volume does not.

## Optional: keyed user/session id tags (`LOG_PSEUDONYM_KEY`)
`app.sanitization.pseudonymize_identity` tags the user or anonymous-session id in the pipeline coordinator log lines. By default it is an unkeyed sha256 (first 12 hex chars): stable, but an attacker with a list of candidate ids could confirm one by hashing it. Set `LOG_PSEUDONYM_KEY` to a long random value to make the tag an HMAC-SHA256: still stable across restarts and replicas (so you can follow one user), not recoverable by hashing candidates without the key. Unset = original behaviour. Question tags (`q_tag`) are different on purpose: a random per-process key, so they only correlate within one process. `LocalAuthStrategy` DEBUG lines log the exception type only.

