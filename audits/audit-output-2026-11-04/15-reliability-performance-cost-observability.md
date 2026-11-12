# 15 — Reliability, performance, cost and observability

> **2026-11-06:** Superseded in part by `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` (SLO, alert, runbook and cost-attribution contracts; alert defects OPS-003 to OPS-008). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S1. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Related: request flow (05), code debt (13), security (14), Railway runbook (22b), NFRs (04, lead), evaluation (18, S3).

## 1. Summary

| # | Statement | Label |
|---|---|---|
| 1 | There is no production baseline for anything. Railway has been down since 2026-08-23; every number is from one Mac. | [DOC-CLAIM] task list §1 cause 4 |
| 2 | Local uncached first-person (FP) answers take p50 6.8–7.6 s and p95 12.3–13.9 s; a served answer needs 3 LLM calls. | [DOC-CLAIM] task list lines 454, 626-627, 1344; [V-STATIC] call count |
| 3 | Only about 1 in 9 on-topic questions ends in a clip a blind judge would show. Abstention, not token price, dominates cost per useful answer. | [DOC-CLAIM] line 627 (16–20 of 87 served; 8–11 "SHOW") + [INF] |
| 4 | The OpenRouter spend cap exists but is off by default in code and not set in the Railway image or deploy script. | [V-STATIC] SYS-004 |
| 5 | Observability is broad (87 Prometheus metrics, 14 alert rules, OTEL to Jaeger, Supabase telemetry sink) but measures the system, not whether the seeker was helped. | [V-STATIC] |
| 6 | Backups: Qdrant/Memgraph cron not installed; Supabase backup refuses to run against a public repo. RPO is unbounded. | [DOC-CLAIM] CLAUDE.md backup caveat; task list N2 |

## 2. Reliability mechanisms

| Mechanism | Where | Assessment | Label |
|---|---|---|---|
| Admission semaphore, 10 ms try-acquire, 503 + Retry-After | `chat.py:278-325`; `max_concurrent_chat` = 12 code / 8 compose; `docs/runbooks/CAPACITY.md` says 20 | Correct pattern; three different documented values (drift) | [V-STATIC] |
| Crisis never-shed pool | `chat.py:286-312` | Correct | [V-STATIC] |
| Pipeline timeout | `pipeline_timeout=105` (+5 s wait_for) (`config.py:119`, `pipeline_coordinator.py:286-292`) | Long; a seeker waits up to 110 s for an abstain | [V-STATIC] |
| Job queue | Redis queue, in-process consumer; refuse if consumer not started (`chat.py:529-545`); polling 0.5 s | Fine for one replica; poll loop holds a request open | [V-STATIC] |
| LLM retries | `llm_max_retries=2`, exponential from 0.5 s (`config.py:126`); 429 not retried in place (`openrouter_service.py:25-40`) | Reasonable | [V-STATIC] |
| Circuit breakers | `services/circuit_breaker.py`, `CircuitBreakerStage`, readiness probe uses public `is_circuit_open` | Present; 2 silent swallows in breaker module (CQ-006) | [V-STATIC] |
| FP gate timeouts | rerank 2.5 s, relevance 25 s default (12 s documented), answerability ANS executor | Relevance budget drift (SYS-006) | [V-STATIC] |
| Fail-closed on scorer failure | `relevance_indeterminate` abstain (CLAUDE.md inv. 24) | Correct | [DOC-CLAIM] + alert rule `FirstPersonRelevanceIndeterminateSpike` |
| Liveness watchdogs | heartbeat, executor canary, memory trimmer, stale-exit (`start_railway.py:166-330`) | Treat symptoms of SYS-003 | [V-STATIC] |
| Health grace | 200 for 180 s unconditionally unless lifespan failed (`start_railway.py:83, 466`) | Deliberate; masks slow boots | [V-STATIC] |
| Redis down | quota/rate-limit fall back to process-local; budget ledger falls back to 10% local cap if `fail_closed` | Multiplies limits by replica count | [V-STATIC] `app/openrouter_budget.py:1-12` |
| Graph down | general path falls back to Qdrant + BM25 | Not on FP path | [DOC-CLAIM] CLAUDE.md |

### SYS-004 — OpenRouter spend cap is off by default and not set for Railway
| Field | Value |
|---|---|
| Pillars | P1 |
| Category | Cost control |
| Severity | P1 |
| Type | Confirmed defect (configuration) |
| Confidence | High |
| Evidence | `app/config.py:645` `openrouter_budget_guard_enabled: bool = False`; `647` `openrouter_budget_fail_closed: bool = False`. Enabled only in `backend/docker-compose.yml:261-262` and `.env.example:44-45`. Absent from `backend/Dockerfile.railway` (ENV block lines 102-125) and `scripts/deploy/deploy_railway.sh` (`set_var` list). |
| Actual behaviour | A Railway deploy built from the repo runs with no spend ceiling unless an operator adds the variable by hand. |
| Expected behaviour | Secure-by-default: guard ON, fail-closed ON, daily and monthly caps set, in code. |
| Root cause | Default kept off for local development and tests. |
| User impact | With SEC-001, an abuse burst can exhaust the provider balance and take chat down. |
| Remediation | Flip both code defaults to `True`; set them explicitly in tests that need them off. |
| Acceptance criteria | `Settings()` with no env has the guard on; startup log prints caps; a test asserts the default. |
| Regression test | `tests/test_budget_guard_default.py` (new). |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### SYS-007 — No reproducible deployed environment and no staging
| Field | Value |
|---|---|
| Pillars | P1, P6 |
| Severity | P1 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | `.railway/railway.ts` declares one service (backend). Qdrant, Memgraph and Redis exist only as manually created Railway services [DOC-CLAIM `docs/operations/railway-production-status-2026-09-20.md`]; Celery worker only with `--with-worker` (`deploy_railway.sh:301-310`). No staging environment exists [DOC-CLAIM task list §1 cause 4]. |
| Actual behaviour | No load, latency, rollback or recovery evidence on any deployed stack. |
| Expected behaviour | One declared environment (IaC) for staging and production, with smoke tests and a rollback path. |
| Remediation | See doc 22b. |
| Acceptance criteria | Staging deploy from a clean checkout passes the 22b smoke suite. |
| Verification | [V-STATIC]; [LIVE-R] |

### SYS-008 — Load evidence uses a mock LLM
`docs/runbooks/CAPACITY.md:23-29`: p95 < 8 s and "no 5xx" are asserted at concurrency 20/50 in **mock mode**; real-LLM runs go to concurrency 5 only [DOC-CLAIM]. Real gate latency and provider rate limits are not exercised under load. Severity P2, Product gap. Fix: a staging run at concurrency 20 with real models and the budget guard on, recorded in `CAPACITY.md`.

## 3. Performance

### 3.1 Baselines that exist (all local)

| Measurement | Value | Source | Label |
|---|---|---|---|
| FP retrieval-only (pre-gates, 2026-09-25) | p50 63 ms, p95 210 ms | `first-person-path-to-prod.md` §1 | [DOC-CLAIM]; obsolete for the current path |
| FP uncached, gates on (2026-10-15) | p50 6.82 s, p95 12.57 s | task list line 1344 | [DOC-CLAIM] |
| FP uncached, A vs B (LLM rerank vs cross-encoder) | A p50 7.48 / p95 13.74 s; B p50 6.92 / p95 9.25 s | task list line 627 | [DOC-CLAIM] |
| General path, per-node | `navigate_and_hyde` 5.4 s, `generate_answer` 12.5 s, `reflect_on_answer` 2.4 s; retrieval+graph+rerank 2.1 s | CLAUDE.md L-LATENCY-1 | [DOC-CLAIM] |
| Backend memory when running | ~1.81 GB | `railway-production-status-2026-09-20.md` | [DOC-CLAIM] |

### 3.2 Where the time goes on the FP path [INF from code order]

| Step | Expected cost | Lever |
|---|---|---|
| Embed query (BGE-M3 ONNX, CPU) | tens–hundreds of ms | cache embeddings (exists) |
| Qdrant hybrid search | tens of ms | none needed |
| LLM rerank (up to 8 clips, 2.5 s cap) | up to 2.5 s | replace with cross-encoder (measured faster tail) |
| Answerability (16 tokens) | ~0.5–1.5 s | run concurrently with retrieval (partly done, line 4591) |
| Relevance scorer (reasoning model, ≤1,024 out) | 2–10 s | smaller output budget; JSON score only; or a fine-tuned cross-encoder once gold labels exist |
| Thread hop and executor queueing | 0 to unbounded under load | SYS-003 |

### 3.3 Streaming

`/api/chat/stream` exists (SSE, `app/stream_orchestrator.py`) and metrics `guru_ttft_seconds` exist (`app/metrics.py`). For the FP lane the answer is a single clip, so "time to first token" equals "time to decision". The architecture document's goal of "clip first, chat below" (`first-person-path-to-prod.md` §3) is not built for the current gate chain [INF]. A useful TTFT target is "first visible content (acknowledgement plus 'finding a teaching') ≤ 1 s; decision ≤ target in doc 04".

## 4. Model inventory and token estimates

| Use | Model setting | Model (default / documented) | Input tokens [INF] | Output | Price per 1M in/out | Label |
|---|---|---|---|---|---|---|
| FP answerability | fast model | `meta-llama/llama-3.1-8b-instruct` | ~300–500 | ≤16 | $0.02 / $0.04 | price [DOC-CLAIM] in-code fallback table `openrouter_service.py:111-125`, "verified 2026-08-22" |
| FP LLM rerank | generation model | `deepseek/deepseek-chat` | ~1,200–2,200 (8 clips) | ~10 | $0.14 / $0.28 | same |
| FP relevance scorer | `first_person_relevance_model` | `anthropic/claude-haiku-5.5` (local, CLAUDE.md inv. 24); code default empty | ~700–1,100 (3 clips) | 100–1,024 (reasoning) | **unknown** — not in the in-code table; not verified | [V-STATIC] / price unknown |
| General generation | `OPENROUTER_GENERATION_MODEL` | `deepseek/deepseek-chat`; fallback `llama-3.3-70b` | several thousand (context) | hundreds | $0.14/$0.28; $0.12/$0.30 | [DOC-CLAIM] |
| Distress second opinion (flag) | fast model | 8B | ≤512 chars | small | $0.02/$0.04 | [V-STATIC] flag off by default |

Prices must be re-verified on OpenRouter model pages before any budget decision. The in-code table is an accounting fallback, not a quote.

## 5. Cost per successfully resolved useful question

### 5.1 Definition

A **useful resolution** is a request that ends in (a) a served clip that a reviewer would show ("SHOW" in the blind-judge rubric), or (b) a correct safety route (helpline) for a crisis message, or (c) an honest abstain for an out-of-corpus question. (c) is correct behaviour but is not "help with the question"; report it separately.

```
C_useful = (C_llm + C_infra + C_ops) / N_useful
C_llm    = Σ_requests Σ_calls (tok_in × p_in + tok_out × p_out)
N_useful = N_requests × r_on_topic × r_served × r_show
```

### 5.2 Inputs and their status

| Symbol | Value used | Status |
|---|---|---|
| `r_served` (served / on-topic) | 0.18–0.23 (16–20 of 87) | [DOC-CLAIM] line 627 |
| `r_show` (SHOW / served) | 0.50–0.55 (8 of 16, 11 of 20) | [DOC-CLAIM] line 627, n small, "noisy" |
| `r_useful` = `r_served × r_show` | ~0.09–0.13 | [INF] |
| FP LLM cost without scorer | ≈ $0.0003 per request (rerank ≈ $0.00024 + answerability ≈ $0.00001) | [INF] from §4 tokens × in-code prices |
| Relevance scorer cost `c_rel` | unknown | must be read from `guru_provider_reported_cost_usd_total` on a real run |
| Infra `C_infra` | unknown | Railway bill [LIVE-R] |

### 5.3 Scenarios (LLM cost only; `c_rel` shown as a variable)

Assumption [INF]: 80% of questions are on-topic; every on-topic question runs all three gates; off-topic and greetings cost 0.

| Scenario | Questions / day | LLM cost / day | LLM cost per useful answer (r_useful = 0.11) |
|---|---|---|---|
| Low | 100 | 80 × ($0.0003 + c_rel) | ($0.0003 + c_rel) / (0.8 × 0.11) ≈ 11.4 × ($0.0003 + c_rel) |
| Expected | 1,000 | 800 × ($0.0003 + c_rel) | same per-useful value |
| Growth | 10,000 | 8,000 × ($0.0003 + c_rel) | same per-useful value |

Worked illustration (placeholder, not a quote): if `c_rel` were $0.003, the per-request LLM cost is about $0.0033 and the LLM cost per useful answer is about $0.038. At the default daily cap of $10 (`openrouter_daily_budget_usd`, `config.py:642`) the cap is reached near 3,000 on-topic questions per day.

### 5.4 What the model shows

1. The cost per useful answer is about 9–11 times the cost per request, because about 89% of on-topic requests do not produce a showable clip. Raising `r_useful` is the cheapest cost lever. That is a data and segmentation problem (doc 06/07, S2), not an inference problem.
2. The relevance scorer is probably the largest LLM line item. Measure it before choosing a model.
3. At low and expected traffic, fixed infrastructure (backend with 1.8 GB models, Qdrant, Memgraph, Redis, Supabase) almost certainly dominates [INF]. Removing Memgraph from the serving stack (it is not on the FP path) is a direct infra saving; decision belongs to S2/lead (doc 08, 17).
4. The general path costs more per request and its usefulness is unmeasured.

### 5.5 Quality–cost frontier (ordered by benefit per cost) [INF]

| # | Change | Cost effect | Quality effect |
|---|---|---|---|
| 1 | Improve clip segmentation so more candidates survive gates | none at serve time | raises `r_served` (task list: never-quarantined bucket serves 75%) |
| 2 | Replace LLM rerank with cross-encoder | −$0.00024/request, −latency | measured: more served, mixed judge results |
| 3 | Cap relevance output tokens; JSON score only | lower `c_rel` | neutral if rubric holds (verify on gold) |
| 4 | Exact cache on normalised question + collection version | fewer calls on repeats | neutral |
| 5 | Remove Memgraph/LightRAG from production stack if general graph is not required | infra saving | neutral for FP |
| 6 | Fine-tuned cross-encoder relevance gate (needs human gold) | removes scorer call | quality depends on gold |

## 6. Observability

### 6.1 What exists

| Element | Evidence | Label |
|---|---|---|
| 87 Prometheus metrics: latency, TTFT, TPOT, LLM tokens/errors, cache, circuit breakers, Redis namespaces, Qdrant optimizer/snapshot age, corpus orphan/drift, provider-reported cost, cost-unknown count, distress detections, verification results | `backend/app/metrics.py` | [V-STATIC] |
| 14 alert rules incl. `FirstPersonQuarantineDetected`, `FirstPersonAbstainRateElevated`, `FirstPersonRelevanceIndeterminateSpike`, `CollectionPointCountShift`, `BackupStale`, SLO latency and 5xx | `infrastructure/prometheus/alerting-rules.yml` | [V-STATIC] |
| Alertmanager to PagerDuty/Slack (prod file) and a local-only variant | `infrastructure/prometheus/alertmanager*.yml` | [V-STATIC]; not deployed [LIVE-R] |
| OTEL spans per node to Jaeger | `backend/app/tracing.py` | [V-STATIC] |
| Telemetry sink to Supabase (`chat_queries`, `chat_responses`, `trace_spans`, `safety_events`, `router_decisions`) and admin trace viewer with prompt-version filter | `app/telemetry_sink.py`, `app/api/admin.py:76-95` | [V-STATIC] |
| `/metrics` admin+AAL2; scrape via `/internal/metrics` with token | CLAUDE.md; `backend/app/api/health.py:741-760` | [V-STATIC] |

### 6.2 Gaps

| Gap | Why it matters | Label |
|---|---|---|
| No outcome metric that joins answer → user reaction | "HTTP 200" counts abstains and weak clips as success | [V-STATIC] |
| No per-request cost attribution on the FP path by gate | Cannot find the expensive gate | [INF]: tokens are counted (`token_sink`), cost per gate not exported |
| No release/collection/prompt version label on outcome metrics | Cannot compare releases | [INF] |
| Langfuse or an equivalent prompt-trace store is absent | Prompt regressions are hard to inspect | [V-STATIC] rg finds no `langfuse` import |
| Alerts are not deployed | Rules exist on paper | [LIVE-R] |

### SYS-011 — No signal separates "HTTP 200 but spiritually poor" from real help
| Field | Value |
|---|---|
| Pillars | P1, P2, P5 |
| Severity | P1 |
| Type | Product gap |
| Confidence | High |
| Evidence | §6.1: metrics are system-level; `answer_route_total` and abstain alerts exist, but nothing records whether the seeker found the answer useful or rephrased. |
| Remediation | Implement the outcome event in §7 and the dashboard below; sample-based judging. |
| Acceptance criteria | Dashboard shows weekly `useful_resolution_rate` by intent, language and collection version; alert on a 20% relative drop. |
| Verification | [V-STATIC] |

## 7. Failure-detection design

### 7.1 One outcome event per response

Fields: `trace_id`, `release_id`, `collection`, `prompt_versions`, `route` (`fp_served`, `fp_abstain_no_match`, `fp_abstain_below_min`, `fp_abstain_indeterminate`, `helpline`, `boundary`, `general_generated`, `error`), `intent_label`, `language`, `relevance_score`, `gate_latencies_ms{}`, `gate_costs_usd{}`, `cache_hit`.

### 7.2 Follow-up signals joined within the session

| Signal | Interpretation |
|---|---|
| Clip play started / watched ≥ 50% of window | engagement with the served teaching |
| Thumbs up / down, "this helped" | explicit usefulness |
| Rephrase of a similar question within 120 s | likely miss |
| Session ends within 30 s after an abstain | likely frustration |
| Follow-up "tell me more" | possible value |
| `general_generated` on a teaching-domain intent while FP-only is on | integrity breach detector for SYS-001 (should be 0) |

### 7.3 Judgement layers

1. Online heuristics above (all traffic).
2. Offline LLM judge on a 2–5% sample against the doc 18 rubric, with the judge model and rubric versioned.
3. Weekly human review of 50 sampled answers (faculty or trained reviewer) [HUMAN].

### 7.4 Proposed metrics

| Metric | Formula |
|---|---|
| `useful_resolution_rate` | useful resolutions / on-topic requests |
| `abstain_rate_on_topic` | FP abstains / on-topic requests |
| `miss_signal_rate` | (rephrase-120 s + early exit after abstain) / responses |
| `cost_per_useful_resolution` | §5.1 |
| `integrity_breach_count` | `general_generated` on teaching intents in FP-only mode |

## 8. SLOs and error budgets

Baselines exist only for local latency. Availability, error rate and real-traffic latency have no baseline.

| SLI | Baseline | Proposed initial objective | Error budget (30 days) | Status |
|---|---|---|---|---|
| Crisis message → helpline response latency | not measured (regex path) | p99 ≤ 2 s | 0.1% of crisis messages slower | measure first [LIVE-R] |
| FP served-answer latency (uncached) | local p95 12.3–13.9 s | provisional p95 ≤ 10 s on staging, then tighten to the doc 04 target | 5% of FP requests over objective | baseline exists [DOC-CLAIM] |
| Terminal state within pipeline budget | not measured | 99.5% of chat requests end in clip / abstain / helpline / boundary within 20 s | 0.5% | measure first |
| Availability of `/api/chat` | none | set after 2 weeks of staging data | — | measure first |
| 5xx rate | none | set after staging data; rule `FiveXXRateSLOPage` exists | — | measure first |
| `useful_resolution_rate` | ~0.09–0.13 local, small n | no SLO yet; track as a product KPI | — | [DOC-CLAIM] |

## 9. Backup and disaster recovery

| Store | Mechanism | State | Label |
|---|---|---|---|
| Qdrant | local cron `infrastructure/cron/mukthiguru-backup` 02:00, retention 7, disk-only; scratch restore proven queryable once (157 points) | cron not installed; disk-only | [DOC-CLAIM] CLAUDE.md |
| Memgraph/Neo4j | cron 02:30 dump; replay unproven | not installed | [DOC-CLAIM] |
| Supabase | GitHub workflow `backup.yml` refuses public-repo artefacts | no DB backup | [DOC-CLAIM] task list N2 |
| Audio archive (source truth) | owner Mac `~/mukthiguru_attribution_data/` | single copy; "copy off the Mac" pending | [DOC-CLAIM] CLAUDE.md open work |

### SYS-012 — Recovery point objective is unbounded for every store
Severity P1 (data integrity), Confirmed per docs, Confidence Medium. Remediation: private off-host backups for Supabase, Qdrant snapshots and the audio archive; one restore drill per store with evidence. Acceptance: restore drill reports with timestamps, row/point counts and a query check, stored under `audits/evidence/`. Verification [DOC-CLAIM] + [LIVE-L].

## 10. Coverage

Read: chat admission and queue code, coordinator timeout, FP gate functions, budget guard, metrics names, alert rules, compose resource limits, `start_railway.py` watchdog notes, CAPACITY runbook (grep), task-list latency rows (grep). Not executed: any load test or benchmark. Prices: in-code table only; no live price page could be fetched (OpenRouter `/api/v1/models` returned no pricing fields, accessed 2026-11-04).
