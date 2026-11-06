# Load and cost model for "Ask Mukti Guru" (specification and staging load-test plan)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Give the owner and an implementation agent a defensible model of cost and capacity for the first-person (FP) route, built from code and the repository's own recorded numbers, plus a ready-to-run staging load-test plan. |
| Status | **Model only. UNPROVEN.** The product has never been deployed. No load, cost or latency figure here was measured on a deployed stack. No test was run. No provider was called. |
| Date | 2026-11-06 |
| Code head | `004f3cf5` on `feature/audit-strengthen-rag-qdrant` (code read in the working tree at this head) |
| Gate served | Gate B item B8 (`FINAL_PRODUCTION_RELEASE_READINESS.md:39`: real-provider load test at target concurrency) |
| Findings touched | SYS-003, SYS-006, SYS-008, SYS-004 (closed at head, see section 5), CQ-011, DATA-18, RET-10, AI-007, NFR-COST-04 |
| Decisions | **D-16** (scorer model, price, timeout): price is not in the repo, so the scorer cost is a free variable in this model. **D-PE7** (final SLO and spend caps after two weeks of staging data): every threshold below is **target (proposed)**. D-26 (Qdrant hosting) sets the Qdrant host limits. |
| Inputs read | `15-reliability-performance-cost-observability.md`; `04-non-functional-requirements-slos-and-benchmarks.md`; `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` (3.1, 3.6, 3.8); `RETRIEVAL_AND_RAG_SPEC.md` (2.4, 3.6, 5); `RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` (13); `FINAL_PENDING_WORK_REGISTER.md` (SYS-003, SYS-008, CQ-011, DATA-18); `CONVENTIONS.md`. |
| Arithmetic | Offline scripts in the session scratchpad (`costmodel.py`, `scen.py`). Plain Python, no network. |

Evidence labels: `[V-STATIC]` read from code or config (path:line); `[DOC-CLAIM]` the repository's own local measurement, not re-run; `[INF]` my assumption, stated; **target (proposed)** a threshold I propose. "Price not in repo" means no price entry exists in the repository.

Rules that bind this document:
1. No number here is a measurement of the deployed product. Local figures come from one Mac (`15` section 1).
2. The only price table in the repo is `_OPENROUTER_FALLBACK_RATES_PER_MILLION` (`backend/services/openrouter_service.py:112-124`). It is an accounting fallback, "verified 2026-08-22" in the code comment. It is not a quote. Re-check before any budget decision.
3. `anthropic/claude-haiku-5.5` (the documented relevance scorer) has no price entry. Unknown models are costed at 0.0 by the fallback (`openrouter_service.py:405-418`, `.get(model, (0.0, 0.0))`). That 0.0 is not a real cost and must never be summed as one.

---

## 1. Existing coverage and what it lacks

| Existing source | What it covers | What it lacks (this document adds it) |
|---|---|---|
| `15` section 5 | Cost-per-useful-answer formula, one scenario table with `c_rel` unknown | Per-call token estimates from the actual prompts, three labelled scenarios, formula for gate-abstain mix and cache share |
| `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` 3.6 | Definition of useful answer, metrics, dashboards | Pre-staging numeric model |
| same, 3.8 | Capacity table; says "keep `max_concurrent_chat` at or below the thread pool size [INF]" | The thread-pool size as a function of vCPU, the per-model RPM ceiling, the 4-worker answerability pool, throughput by Little's law |
| `RETRIEVAL_AND_RAG_SPEC.md` 2.4 | LLM call inventory L1-L8 | Order of calls, which request outcomes skip which call, cost by outcome |
| `docs/runbooks/CAPACITY.md` | Mock-LLM sweep at c20/c50; real LLM only to c5 | Nothing usable for real-provider capacity (SYS-008) |
| `backend/benchmarks/locustfile.py`, `.github/workflows/nightly-load.yml` | Locust sweep, single repeated question, mock LLM, 5xx check only | Real-provider scenarios, outcome mix, cost capture, abort rules (section 6) |
| `backend/scripts/ops/gate1_load_test.py`, `backend/benchmarks/concurrent_load_test.py` | asyncio/httpx load tests with strata and percentiles | They use the benchmark key; neither records cost or outcome counters |

---

## 2. Per-request call graph on the live first-person route

Scope: the legacy (v8-style) path in `FirstPersonPipeline.execute`, which is the code default. The v10 context-harness path (`first_person_context_harness_enabled`, default False, `config.py:282`) is listed separately in 2.4.

### 2.1 Order of work and where a request can stop

| Step | Work | Compute type | LLM? | Evidence |
|---|---|---|---|---|
| 0 | Admission: per-worker semaphore of `max_concurrent_chat` (12); 10 ms try-acquire; 503 + `Retry-After` 3-8 s if full; crisis-keyword requests use a separate pool of the same size and are not shed | event loop | No | `config.py:1030`; `chat.py:213-219, 278-325` |
| 1 | Chat pipeline front stages (cache check, guardrail, distress, off-topic, casual short-circuit) run before the FP bridge. A greeting, off-topic, blocked-topic or crisis turn ends here with no FP LLM call | CPU, regex/rules | L1 only if the ambiguous-domain router fires (0.45 s cap, `config.py:2017-2018`); model and tokens not read | `CLAUDE.md` pipeline order; `RETRIEVAL_AND_RAG_SPEC.md` 2.4 |
| 2 | Query embedding (BGE-M3 INT8 ONNX, dense + sparse) via `asyncio.to_thread(encode_single_full)`. Runs for every request that reaches the bridge, cache hit or not | CPU, ONNX in the backend process; slots limited by `native_inference_max_concurrent` = 6 | No | `app/container.py:439`; `config.py:1050`; `Dockerfile.railway` ENV `EMBEDDING_BACKEND=onnx_int8` |
| 3 | Bridge hands the sync pipeline to the shared default executor: `asyncio.to_thread(pipeline.execute, ...)`. **One default-executor thread is held for the whole `execute` wall time** | thread | No | `app/pipeline/stages/first_person_bridge.py:880` |
| 4 | Exact Redis cache lookup, key `(language, message)` + policy fingerprint; hit re-checks `points_servable`; TTL 24 h. **Cache hit ends the request: zero LLM calls** | Redis + Qdrant retrieve | No | `first_person_pipeline.py:134, 3191-3487, 3706-3765` |
| 5 | Retrieval: Qdrant hybrid RRF `search_hybrid`, `limit=max(80, 16 x clips)` = 80, REST (`prefer_grpc=False`), timeout 30 s, one retry on a dropped connection. Runs in the pipeline thread, **in parallel with step 5a** | network + Qdrant CPU | No | `first_person_pipeline.py:4660-4900`; `services/qdrant/client.py:100-120` |
| 5a | **L2 Answerability gate** submitted to a separate bounded executor (4 workers) before retrieval, joined after integrity gates. A firm NO or indeterminate verdict ends the request (abstain `answerability_withheld`); rerank and scorer do not run | thread + LLM | **Yes (always, on a cache miss)** | `first_person_pipeline.py:1311-1339, 4873, 5040-5110` |
| 6 | Integrity, allowlist/blocklist, dedupe, standalone checks (deterministic). Zero verified clips ends the request (abstain) with no further LLM call | CPU | No | `first_person_pipeline.py:4806-4830` |
| 7 | Optional cross-encoder rerank (`first_person_rerank_enabled`, default False) | CPU (ONNX MiniLM) | No | `config.py:233`; `first_person_pipeline.py:5196` |
| 8 | **L3 LLM rerank** if `first_person_llm_rerank_enabled` (default True) and more than 1 verified clip | LLM | **Yes, conditional** | `config.py:240`; `first_person_pipeline.py:5231-5240` |
| 9 | **L4 Relevance scorer**: top 3 clips scored 0-3 in one call (speculative cascade off by default, so 1 call). Below min score or scorer failure ends the request as an abstain | LLM | **Yes, conditional** | `config.py:470-482, 1049-1125`; `first_person_pipeline.py:5452-5492` |
| 10 | Assembly (quote weaver is deterministic), citations, exact-cache write | CPU | No | `quote_weaver.py:1085-1100` [from RAG spec 2.4] |

### 2.2 LLM call table (legacy path)

| # | Call | Runs when | Model setting and default | max_tokens | Timeout | Failure behaviour | Evidence |
|---|---|---|---|---|---|---|---|
| L2 | Answerability YES/NO (question text only, 429-word system prompt) | Every cache-miss request that reaches step 5a | `_generate_fast` -> classify model `openrouter_classify_model` = `meta-llama/llama-3.1-8b-instruct` | 16 (temperature 0.0) | `_ANSWERABILITY_TIMEOUT_S` = 12.0 s | Indeterminate -> abstain | `first_person_pipeline.py:1311, 1475-1500`; `config.py:597` |
| L3 | LLM rerank of up to 8 clips (each cut to 350 characters) | After L2 is joined, if more than 1 clip survived and the flag is on | `llm_service.generate` -> generation model `deepseek/deepseek-chat`; on failure the service falls back to `meta-llama/llama-3.3-70b-instruct` (a possible extra call) | **not set by the caller; on the live OpenRouter provider the default is 2048 (`backend/services/openrouter_service.py:495`), capped by the policy output ceiling (`backend/app/model_policy.py:172-175`; `llm_max_tokens_fast` = 800 at `backend/app/config.py:144`); 8192 is the Sarvam and NIM default (corrected by the lead, 2026-11-06)** (reply is about 10 tokens) | 2.5 s (`timeout_s` default) | Keep retrieval order | `first_person_pipeline.py:1216-1260`; `openrouter_service.py:996-1030`; `config.py:595-596` |
| L4 | Relevance scorer, top 3 clips, full clip text | After rerank, if `first_person_relevance_gate_enabled` (default True) | `first_person_relevance_model`: code default empty (generation model); documented live value `anthropic/claude-haiku-5.5` [DOC-CLAIM `CLAUDE.md` inv. 24] | Haiku: **2048** with `reasoning_effort="low"`, `operation="verify"`; other named models 1024; `deepseek/deepseek-chat` 16 | `first_person_relevance_timeout_s` = 25.0 s in `Settings`, 15.0 in `docker-compose.yml`, 12 in `docker-compose.graded.yml`, 12 in `CLAUDE.md` (drift, SYS-006/D-16) | `relevance_indeterminate` abstain, no fallback | `first_person_pipeline.py:1088-1120`; `config.py:476-478`; `docker-compose.yml:325` |
| L1 | Ambiguous-domain router | Ambiguous spiritual question only | `jev_model` (None -> legacy `intent_router_jev_model` = `typesafe/jev-1.14`) | Unknown | 0.45 s | Neutral general lane | `config.py:1998, 2010, 2017-2018` [model host and price not read] |
| L5-L8 | Facet split, HyDE, glue translation, v10 context selector | Flags off by default, or Indic-language safety notices only | Various | Various | 2.5 s / 2.5 s / 5 s / unknown | Fail open or skip | `RETRIEVAL_AND_RAG_SPEC.md` 2.4 |

Reasoning-token cost of L4 is **unknown**: Haiku "reasons internally" (`CLAUDE.md` inv. 24) and the output cap is 2048 [V-STATIC], but the real output length has never been recorded in the repo. [LIVE-L]

### 2.3 Calls by request outcome (legacy path, speculative parallelism off)

| Outcome | LLM calls | Which | Share of traffic [INF] |
|---|---|---|---|
| Greeting, off-topic rail, blocked topic, crisis (regex lane) | 0 (L1 maybe) | none | Unknown; section 3 sets it as parameter `1-q` |
| FP exact-cache hit | 0 | none | Parameter `h` |
| Gate NO or indeterminate, or zero verified clips (abstain) | 1 | L2 | Parameter `g` of on-topic misses |
| Relevance below min or indeterminate (abstain) | 3 | L2, L3, L4 | rest of non-served |
| Served clip | 3 | L2, L3, L4 | `s` = 17-31% of on-topic [DOC-CLAIM] |
| Same, L3 skipped (one clip only) | 2 | L2, L4 | small [INF] |
| Failure with fallback model on L3 | 4 | + llama-3.3-70b | rare [INF] |

`LLM_CALLS_PER_REQUEST = 3` is the code constant used for pool sizing (`config.py:29`) [V-STATIC]. It matches the served path.

### 2.4 v10 context-harness path (flag, local `.env` only)

With `first_person_context_harness_enabled` and `..._terminal_enabled` true (`CLAUDE.md` inv. 25), the answerability gate runs sequentially before scoring (`first_person_pipeline.py:4020-4045`), and the scorer runs per candidate context, in parallel when `first_person_harness_parallel_enabled` (default True, `config.py:288`). Candidate count is `max_clips` (3) or up to 8 in the editorial path (`first_person_pipeline.py:3983`). So scorer calls per request can be 1 to 8 [INF from code]. The model in section 3 uses 1 scorer call. If the v10 path is the staging target, multiply the scorer term by the measured call count. The v10 path has no LLM rerank call that I could confirm [INF; `grep` of the harness file found no LLM call].

### 2.5 Non-LLM compute per request

| Item | Size | Evidence |
|---|---|---|
| Embedding model | BGE-M3 INT8 ONNX, about 560 MB resident; one encode per request | `railway-production-status-2026-09-20.md` [DOC-CLAIM] |
| Cross-encoder reranker | ONNX MiniLM-L6, about 570 MB resident, loaded at startup; used by FP only if the flag is on; used by the general lane | same [DOC-CLAIM]; `Dockerfile.railway` ENV |
| LettuceDetect (350 MB) | Loaded at startup; not on the FP served path | `app/main.py:537, 705` [V-STATIC]; FP serves verbatim text [INF] |
| ONNX inference slots | 6 per process (memory bound only) | `config.py:1050` |

---

## 3. Cost model

### 3.1 Formulas

Symbols: `N` requests; `q` share of requests that are on-topic (reach the FP gates); `h` share of those answered from the exact cache (no LLM); `g` share of on-topic cache misses that stop after L2; `s` served share of on-topic; `u` useful share of on-topic (`u = s x r_show`).

```
c_L = (tok_in x p_in + tok_out x p_out) / 1,000,000          per call, repo price table
C_req = q x (1 - h) x [ c_L2 + (1 - g) x ( c_L3 + k x c_L4 ) ]   LLM cost per request (k = scorer calls, 1 on the legacy path)
C_day = N_day x C_req + F_infra_day                           F_infra = fixed hosting, not modelled here
N_useful = N x q x u                                          (as in 15 section 5.1)
C_useful = C_req / (q x u)                                    LLM cost per useful answer
Req_cap_day = D_cap / C_req                                   requests per day the daily cap allows
Useful_cap_day = Req_cap_day x q x u
```

Cache hits are counted in `N_useful` at the same `u` (a replayed served clip is still a useful answer). This is the conservative choice for the denominator and it assumes the hit rate does not bias `u` [INF].

### 3.2 Inputs, each labelled

| Input | Value | Label |
|---|---|---|
| L2 input tokens | 429 words in the system prompt + question, at 1.3 tokens per word (the repo's own `estimate_tokens` ratio, `rag/compressor.py:58-69`) = about 583 tokens in, 3 out | [INF] from `first_person_pipeline.py:1346-1385` |
| L2 price | $0.02 in / $0.04 out per 1M | [V-STATIC] `openrouter_service.py:120` |
| L2 cost per call | about $0.0000118 | [INF] arithmetic |
| L3 input tokens | 75-word system prompt + query + 3 to 8 clips of at most 350 characters, about 70-90 tokens each = 327 to 837 tokens in; about 8 out | [INF]; clip size from 18-25 s windows (`CLAUDE.md` inv. 11) |
| L3 price | $0.14 / $0.28 per 1M | [V-STATIC] `openrouter_service.py:112` |
| L3 cost per call | about $0.000048 (3 clips) to $0.000119 (8 clips) | [INF] arithmetic |
| L4 input tokens | 110-word system prompt + question + 1 to 3 full clips = 231 to 524 tokens in; output up to 2048 including reasoning | [INF]; cap [V-STATIC] |
| L4 price | **price not in repo** | finding NFR-COST-04, AI-007, D-16 |
| L4 cost per call `c_L4` | free variable. Sweep values 0.0005, 0.002, 0.008 USD per call. These are sweep points, not a claim about any model's price | [INF] |
| `q` | 0.8 | [INF] carried from `15` section 5.3 |
| `s` served share | 0.24-0.31 on the 29-question set; 0.17 (26 of 150) on the live 150-question pool | [DOC-CLAIM] `CLAUDE.md` inv. 24; task list line 144 |
| `u` useful share | 0.09-0.13, centre 0.11. From served 16-20 of 87 and SHOW 8-11 of those; small n, "noisy" | [DOC-CLAIM] task list line 636; `15` section 5.2 |
| `h` cache hit share | 0.0 / 0.10 / 0.30 | [INF] no traffic exists. The cache key is exact `(language, message)`, so real hit rates are likely low for free-text questions |
| `g` stop-after-L2 share | 0.10 / 0.25 / 0.40 | [INF]. Live data: 8 of 150 withheld by the gate, 94 below min score (task list line 144, v9, 26 served), so `g` may be near 0.05 on on-topic traffic and higher with out-of-corpus traffic |
| Reservation per call | $0.03 | [V-STATIC] `config.py:644` |

### 3.3 Worked table (three scenarios)

All scenarios: legacy path, `k = 1`, `q = 0.8`. LLM cost only. Fixed infrastructure is not included (section 3.5).

| Scenario | `h` | `g` | `c_L3` | `c_L4` (sweep) | `u` | `C_req` (USD) | `C_useful` (USD) | Calls per request |
|---|---|---|---|---|---|---|---|---|
| Low | 0.30 | 0.40 | 0.000048 | 0.0005 | 0.13 | **0.00019** | **0.0018** | 1.23 |
| Expected | 0.10 | 0.25 | 0.000086 (600 tokens in) | 0.002 | 0.11 | **0.00114** | **0.0129** | 1.80 |
| High | 0.00 | 0.10 | 0.000119 | 0.008 | 0.09 | **0.00586** | **0.0813** | 2.24 |

Arithmetic from `scen.py`; every cell is [INF]. The range of `C_useful` is about $0.002 to $0.08 per useful answer, a factor of 45. The factor comes almost entirely from the unknown `c_L4` and from `u`. Do not quote any single cell as the cost of the product.

Daily and monthly volume under the table's `C_req`:

| Scenario | 100 req/day | 1,000 req/day | 10,000 req/day | Requests/day the $10 daily cap allows | Useful answers/day at the cap |
|---|---|---|---|---|---|
| Low | $0.02 | $0.19 | $1.9 | about 52,000 | about 5,450 |
| Expected | $0.11 | $1.14 | $11.4 (over the cap) | about 8,800 | about 775 |
| High | $0.59 | $5.86 | $58.6 (over the cap) | about 1,700 | about 120 |

Monthly cap ($40, `config.py:641`): requests per month = 40 / `C_req` = about 210,000 (low), 35,000 (expected), 6,800 (high). Because $10 x 30 days is $300, the $40 monthly cap binds first. At $10 per day it binds after 4 days.

### 3.4 Reservation-bound worst case (V-STATIC logic, no estimate needed)

The guard reserves $0.03 per call before the call and refunds the difference when the provider reports `usage.cost` (`openrouter_budget.py:87-98`, `openrouter_service.py:542, 747`). It **keeps the full reservation** when cost is missing, and when a request was sent but no response arrived (timeout) (`openrouter_budget.py:62-85`). So if a model does not return `usage.cost` (the scorer is the candidate, because its price is not in the repo), each call debits $0.03:

| Case | Debit per request | Requests per day at $10 | Requests per month at $40 |
|---|---|---|---|
| Full path, every call unrecorded | 3 x $0.03 = $0.09 | 111 | 444 |
| Scorer only unrecorded (L2, L3 settle) | about $0.03 + about $0.0002 | about 330 | about 1,320 |
| Gate-only abstain, unrecorded | $0.03 | 333 | 1,333 |

This is a hard ceiling on service volume that follows from the code, not from price. Staging must check that OpenRouter returns `usage.cost` for the chosen scorer (stage S0 in section 6.4). The metric `guru_openrouter_cost_unknown_total` counts such calls (`PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` 3.6).

### 3.5 Fixed infrastructure (not modelled)

| Item | Known | Label |
|---|---|---|
| Memory when running | backend about 1.81 GB, Qdrant about 1.33 GB, Memgraph about 0.57 GB; sum about 3.72 GB | [DOC-CLAIM] `railway-production-status-2026-09-20.md:11` |
| Railway unit prices | Older note quotes $10 per GB-month RAM and $20 per vCPU-month | [DOC-CLAIM] `railway-deployment.md:12`, not re-verified. The runbook says to get current prices. I do not use them for a total. |
| Supabase, Redis, egress | not in repo | unknown |

At low volume the fixed cost almost certainly exceeds the LLM cost (`15` section 5.4, [INF]). Compute `C_useful_total = (C_llm + F_infra) / N_useful` only after the Railway bill exists.

---

## 4. Capacity model (one backend replica)

### 4.1 Limits read from code

| Limit | Value | Evidence |
|---|---|---|
| Uvicorn workers | `WEB_CONCURRENCY` = 1 (image ENV and default); each extra worker duplicates models and has its own semaphore | `start_railway.py:127-160`; `Dockerfile.railway` ENV |
| Chat admission | 12 in flight per worker; 13th gets 503 + `Retry-After` 3-8 s; crisis has its own pool of 12 | `config.py:1030`; `chat.py:213-262, 278-325`. Docs disagree: 8 in compose (`docker-compose.yml:379`), 20 in `CAPACITY.md` |
| Job queue concurrency | 5 | `config.py:1017` |
| Provider HTTP pool | needs `(12 + 5) x 3 = 51`; configured 55 | `config.py:29, 1797, 2164, 2574` |
| Default thread-pool executor | not configured anywhere in the repo (`set_default_executor` not found). CPython 3.12 default is `min(32, cpu_count + 4)` (image is `python:3.12-slim`) | [V-STATIC] grep; default rule [INF] |
| Answerability executor | 4 workers per process | `first_person_pipeline.py:1325` |
| Per-model provider RPM | 60 per minute per model, Redis-backed across replicas; sleeps up to 5 rounds, then proceeds anyway (fail open) | `config.py:598`; `openrouter_service.py:176, 286-322` |
| Native inference slots | 6 per process (memory bound) | `config.py:1050` |
| Pipeline timeout | 105 s default (`PIPELINE_TIMEOUT=180`, `LLM_TIMEOUT=90` in the Railway image: drift) | `config.py:124`; `Dockerfile.railway` ENV |
| Stall watchdog | executor canary every 5 s, 10 s probe timeout; stale after 30 s; process exits after 60 more seconds of continuous staleness | `start_railway.py:84-102` |
| Per-identity chat rate limit | 20 per minute; FP direct route 120 per minute per IP | `config.py:1209-1210`; `chat.py:736` |
| Anonymous quota | 5 messages per 24 h | `config.py:1230-1231` |

### 4.2 SYS-003 mechanism and the concurrency number

SYS-003 stays Open at head (`FINAL_PENDING_WORK_REGISTER.md:86`). Mechanism [V-STATIC]: step 3 puts the sync `execute` on the shared default executor. `execute` blocks that thread through every LLM call (`run_llm_coroutine` waits on `fut.result(timeout=...)`, `first_person_pipeline.py:1434-1460`) and through the retrieval call. The thread is therefore idle (waiting for the provider) for most of the request wall time.

Let `E` = default executor size, `A` = admitted requests (at most 12), `W` = wall time per uncached request, `T = min(A, E - R)` where `R` is the number of executor threads other work holds (embedding `to_thread`, cache stage, memory dispatch uses its own pool). `R` is 0 to 2 [INF].

| vCPU the process sees | `E = min(32, cpu + 4)` [INF] | Requests running without waiting for a thread (`R` = 1) |
|---|---|---|
| 1 | 5 | 4 |
| 2 | 6 | 5 |
| 4 (the compose limit `BACKEND_CPU_LIMIT` default) | 8 | 7 |
| 8 | 12 | 11 |
| 28 or more | 32 | 12 (admission binds) |

The Railway container may report the host CPU count instead of its limit. [LIVE-R] Check `os.cpu_count()` in the staging container before reading this table.

**Max concurrent requests per replica without executor queueing: 4 to 11 on 1 to 8 reported vCPU (about 7 at 4 vCPU), always at most 12 (admission).** [INF] from code. Requests 8 to 12 at 4 vCPU are admitted but wait for a thread. While they wait, the canary `to_thread(lambda: None)` queues behind them. The canary trips only if the queue stays full for over 90 s in total (30 s stale + 60 s), so a few busy seconds do not restart the process, but sustained saturation does.

Throughput before queueing, `X = T / W` (Little's law), uncached FP requests:

| `W` (uncached wall time) | Label | `T` = 5 | `T` = 7 | `T` = 11 |
|---|---|---|---|---|
| 4 s | low end of "4-6 s" [DOC-CLAIM `CLAUDE.md` inv. 22] | 1.25 req/s | 1.75 | 2.75 |
| 6 s | high end of the same claim | 0.83 | 1.17 | 1.83 |
| 7.5 s | measured p50 6.8-7.8 s, single user, local [DOC-CLAIM task list lines 226, 636] | 0.67 | 0.93 | 1.47 |
| 13 s | measured p95 12.3-13.9 s [DOC-CLAIM] | 0.38 | 0.54 | 0.85 |

Those local runs were serial, one user at a time. Under concurrency `W` grows (provider queueing, 60 RPM sleeps, executor waits), so the table is an upper bound [INF]. Cache hits and rail/greeting turns hold a thread for milliseconds and are not binding.

### 4.3 Three tighter ceilings that sit under the thread count

1. **Provider RPM per model.** Each call type goes to a different model, so each model has its own 60-per-minute window (`openrouter_service.py:286`). One uncached request makes one call per model, so the ceiling is about **60 uncached requests per minute, about 1.0 req/s, for the whole deployment** (all replicas share the Redis window). If L3 falls back to `llama-3.3-70b` or the same model serves two calls, the ceiling halves [INF]. Above it the call sleeps in the executor thread (holding it), then fails open after 5 rounds. This makes `W` longer and can push the starvation watchdog. This ceiling binds before the thread count at 7 or more usable threads.
2. **Answerability pool.** 4 workers, each busy for the L2 call time `t_L2`. Capacity is `4 / t_L2`: about 8 per second at 0.5 s, 2.7 per second at 1.5 s (`t_L2` is [INF]), but only 0.33 per second if L2 times out at 12 s. A provider slowdown makes this pool the first queue. The join waits at most 12 s (`first_person_pipeline.py:4892`).
3. **Per-identity rate limit and anonymous quota** (20 per minute, 5 per 24 h) shape the test, not the server (section 6.2).

Net single-replica estimate [INF]: **sustained uncached throughput about 0.5 to 1.0 req/s (30 to 60 per minute), at 5 to 8 requests in flight**. With the target mix (many cache hits and rail turns) the usable user rate is higher. This is a model to test, not a result. Scaling out multiplies threads but not the RPM window; the RPM limit is set in `openrouter_rpm_limit` and can be raised (a decision, section 7).

### 4.4 Uvicorn workers and replicas

- Raising `WEB_CONCURRENCY` to 2 doubles threads and admission (24) but duplicates about 1.8 GB of models per worker and splits the in-process caches. `docker-compose.prod.yml:100` already sets 2; the Railway image sets 1. Keep 1 until T7-02 (async lane) is done [per `RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` 258].
- Replicas split traffic randomly with no sticky sessions (F-14). Per-replica caps multiply. The degraded-Redis spend ledger is per process (10 percent of caps each, `openrouter_budget.py:20`).
- Celery worker and Beat are separate services (Beat exactly one).

### 4.5 Memory per replica

| Item | Size | Label |
|---|---|---|
| Models loaded: BGE-M3 560 MB, reranker 570 MB, LettuceDetect 350 MB, MiniLM 90 MB, Python/LangGraph 250 MB | about 1.81 GB when idle-running | [DOC-CLAIM] `railway-production-status-2026-09-20.md:11` |
| Peak under 6 concurrent general-lane chats | 4.1 GB of a 6 GB limit (a crash was investigated at that point; it turned out to be a thread-safety segfault, not OOM) | [DOC-CLAIM] code comment `config.py:1032-1046` |
| Compose limit | 6 GB, 4 CPU (`BACKEND_MEMORY_LIMIT`, `BACKEND_CPU_LIMIT`) | [V-STATIC] `docker-compose.yml:425-426` |
| Railway limit | **not declared**; `.railway/railway.ts` accepts no resource limits (F-4); set in the dashboard | [V-STATIC]; [LIVE-R] |
| Image | about 2.5 GB | `.railway/railway.ts:8` comment |
| Runbook sizing | "Set an explicit limit and watch RSS"; gives no number | runbook section 13 |

Proposed starting limit for staging, **target (proposed)**: 4 GB RAM, then set the production limit at the staging peak RSS plus 25 percent. FP-only traffic loads fewer models than the general lane (LettuceDetect is idle), so the FP peak may be below 4.1 GB [INF]; measure it. Qdrant about 1.33 GB, Redis `maxmemory` 450-512 MB (`docker-compose.yml:108`).

### 4.6 Datastore connection limits

| Store | Limit in code | Evidence | Reading |
|---|---|---|---|
| Qdrant | REST client, timeout 30 s; no pool size set in repo code (library default) | `services/qdrant/client.py:100-120` | Each in-flight request holds one HTTP call for tens of ms; 12 in flight is far below any server limit [INF]. Server-side limits depend on D-26 hosting [LIVE-R] |
| Redis | cache adapter pool 32; job queue 32; per-user cost tracker 5, socket timeout 1 s | `services/cache/redis_adapter.py:64`; `app/services/job_queue.py:325`; `services/cost_tracker.py:72` | Each chat request does about 5 to 15 Redis calls (cache, rate limit, quota, budget reserve per LLM call) [INF]. Pools of 32 are adequate at 12 in flight; the tracker's 5 connections are the smallest |
| Redis server | `maxmemory 512mb` `noeviction` (Railway runbook) | runbook section 5 | A full Redis rejects writes; rate-limit and budget keys are small [INF] |
| Supabase | `db_pool_size` 10, `db_max_overflow` 20, `db_pool_timeout` 30 s are declared; whether the telemetry path uses them is not confirmed (telemetry sink uses REST with a 3-thread invalidation executor) | `config.py:2183-2185`; `app/telemetry_sink.py:86` | Plan connection limits are not in the repo [unknown]. Telemetry writes run in the same default executor via `asyncio.to_thread` (`telemetry_sink.py:588`) and add to `R` above |
| Provider HTTP | pool 55 vs need 51 | `config.py:1797, 2574` | Passes by 4. Raising `max_concurrent_chat` above 13 without the pool fails startup (by design) |

---

## 5. Budget guard

| Item | Value | Evidence |
|---|---|---|
| Guard and fail-closed | both default `True` (SYS-004 closed at head: `FINAL_PENDING_WORK_REGISTER.md:87`; production refuses to start with the guard off unless `allow_uncapped_llm_spend`) | `config.py:640-648`, validator `config.py:2490-2502` |
| Daily cap | $10 | `config.py:640` |
| Monthly cap | $40 | `config.py:641` |
| Reservation per call | $0.03 | `config.py:644` |
| Redis down | process-local ledger at 10 percent of the caps ($1 per day, $4 per month) per process | `openrouter_budget.py:20, 188-203` |
| Denial signal | `OpenRouterBudgetExceeded` / `OpenRouterBudgetUnavailable`; no Prometheus counter counts either (spec 2.5) | spec `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md:114` |
| Per-user daily cap | `user_daily_budget_usd` $0.50; enforcement on a request path not confirmed | `config.py:1250` |
| Provider-side limit | recommended at OpenRouter as a second cap | runbook section 13 |

What the caps allow (from section 3.3 and 3.4, [INF]):

| Case | Daily $10 allows | Monthly $40 allows |
|---|---|---|
| Low scenario | about 52,000 requests per day | about 210,000 per month |
| Expected | about 8,800 per day (about 775 useful) | about 35,000 per month (about 3,100 useful) |
| High | about 1,700 per day (about 120 useful) | about 6,800 per month (about 490 useful) |
| Reservation-bound, scorer cost unrecorded | about 330 per day | about 1,320 per month |
| Reservation-bound, all three calls unrecorded | 111 per day | 444 per month |

In-flight reservations also count: 12 requests x 3 calls x $0.03 = $1.08 can be reserved at one moment. The 120-per-minute direct FP route (`/api/first-person/query`, no auth, SEC-001/D-07) can reserve $3.60 per minute, so the daily cap can be exhausted in minutes by one address [spec 2.5, INF]. The caps are a safety net, not a capacity plan. Final values are D-PE7.

---

## 6. Staging load-test plan with the real provider (Gate B item B8)

Closes SYS-008 and evidences SYS-003 before T7-02 (async lane). Nothing in this section has been run.

### 6.1 Tool

**Locust.** It is already in the repo: `locust>=2.31,<3` in `backend/requirements-dev.txt`; `backend/benchmarks/locustfile.py`; `.github/workflows/nightly-load.yml`; `HttpUser` classes and a stop-event hook exist. Alternatives in the repo: `backend/scripts/ops/gate1_load_test.py` (asyncio/httpx, percentiles, chaos) and `backend/benchmarks/concurrent_load_test.py`. k6 is not in the repo. The existing locustfile sends one repeated question, checks only 5xx and uses the benchmark key; NEW-LOAD-1 adds a new file rather than editing it.

### 6.2 Preconditions and a known blocker

| # | Precondition | Why | Evidence |
|---|---|---|---|
| P1 | Staging environment on the same commit, with the serving collection loaded and Qdrant count verified | Corpus exists only on the owner's Mac (DATA-01, P7-33) | `FINAL_RAILWAY_STAGING_READINESS.md:72` |
| P2 | Budget guard ON, fail-closed ON, caps set to the **test cap** (below), and a provider-side key limit at the same value | Abort control | `config.py:640-648` |
| P3 | A way past the identity limits. `/api/chat` allows 20 per minute per identity and the anonymous quota is 5 per 24 h. The `X-Test-Key` bypass is refused when `is_production` is true (`config.py:2479`), and the Railway image sets `IS_PRODUCTION=true`. Choose one and record it: (a) staging with `IS_PRODUCTION=false`, `ENABLE_TEST_AUTH=true`, `BENCHMARK_SECRET`, and the budget guard set explicitly (a deviation from production: validators for production do not run); or (b) 20+ real test accounts with `FACULTY_ACCESS_CODE` and a raised `CHAT_RATE_LIMIT` | Without this the test measures the limiter, not the pipeline (`nightly-load.yml` comments) | `config.py:1209, 1230, 2479` |
| P4 | `MAX_CONCURRENT_CHAT` set to one explicit value per run (12 default) and recorded; `HTTP_MAX_CONNECTIONS`/`HTTP_POOL_MAX_CONNECTIONS` at least `(cap + 5) x 3` | Startup validator | `config.py:2574` |
| P5 | Cold runs need unique questions or the cache disabled: use `LATENCY_BENCHMARK_CACHE_DISABLED=true` (read at `first_person_pipeline.py:3702`) for the cold scenarios, and leave the cache on for the cache-hit scenario | The exact cache key is `(language, message)` | `first_person_pipeline.py:3120-3152` |
| P6 | Scorer model fixed (D-16) and `OPENROUTER_EXTRA_ALLOWED_MODELS` set | Else the policy blocks it and 100% abstain as indeterminate | `CLAUDE.md` inv. 24 |
| P7 | Metrics scrape works (`/internal/metrics` with `METRICS_SCRAPE_TOKEN`) | Counters below | spec 2.4 (alert-path defects OPS-003/004) |
| P8 | Owner approval for spend and for sending the question set to the provider | Real provider | D-PE7 |

### 6.3 Data set

| Pool | Source | Size | Use |
|---|---|---|---|
| On-topic, answerable | `evals/gold_set_v1/questions.jsonl` kind `on_topic` | 150 | cold and cache-hit scenarios. **Synthetic, AI-written** (file header); results show load behaviour, not answer quality |
| Frozen on-topic | `evals/first_person/frozen29.jsonl` | 29 | the set behind the 24-31 percent served-share claim, for comparison |
| Out-of-corpus and adversarial | `evals/gold_set_v1/questions.jsonl` (40 + 15); `evals/first_person/ooc13.jsonl` | 68 | abstain scenario |
| Crisis | `evals/pr_suite/distress_crisis.jsonl` | 5, not clinician-reviewed | crisis scenario at low volume only; reuse sparingly |
| T2-02 retrieval bank | `evals/retrieval_bank/bank.jsonl` | **8 rows** | too small for load; use for a correctness smoke only |
| Larger bank | `backend/benchmarks/question_bank.py` `QUERIES` | 36 | extra variety |

With 150 unique on-topic questions, cold throughput is limited by the number of distinct prompts; reuse is fine when the cache is disabled by P5.

### 6.4 Scenarios, ramp and duration

Run in this order. Each stage starts only if the previous stage's abort rules did not fire.

| Stage | Scenario | Mix | Users (ramp) | Duration | Purpose |
|---|---|---|---|---|---|
| S0 | Smoke | 1 of each type | 1 user | 5 min | Verify identity bypass, metrics, `usage.cost` present for all three models |
| S1 | Cache-hit | 150 on-topic, cache on, second pass | 5 -> 20 users, +5 per min | 10 min | Cache path p95, no LLM spend |
| S2 | Served/uncached | 150 on-topic, cache off | 1, 3, 5, 8, 12 users, 8 min plateau each | 45 min | Single-replica capacity curve; find the knee |
| S3 | Abstain | 68 out-of-corpus + adversarial | 5 -> 12 users | 10 min | Cost of the gate-only path; leak count must be 0 |
| S4 | Crisis | 5 crisis rows, at most 1 per 10 s, mixed into S2 background | 1 stream | during S2 plateau at 12 | Crisis p99 under load; crisis never shed |
| S5 | Mixed target (the B8 run) | 55% on-topic uncached, 15% cache-hit, 20% out-of-corpus, 5% greeting/off-topic, 1% crisis, 4% other | 20 users (the NFR-SCAL-01 target) held 30 min, with one 5 min burst to 40 users | 40 min | Pass conditions for B8 |
| S6 | Burst | 0 -> 40 users in 10 s, hold 3 min, drop | 40 | 5 min | Admission control: 503 with `Retry-After`, no 5xx, recovery |

The mix in S5 is [INF]; real traffic is unknown. Think time `between(2, 6)` s [INF] to mimic reading; S2 uses 0.5-2 s (the existing locustfile value) to find saturation.

### 6.5 Spend cap for the test

Estimate with the model: S2 about 1,200 uncached requests, S3 about 400, S5 about 800 on-topic uncached, others small, so about 2,400 requests of full or gate-only path. At the high scenario `C_req` $0.0059 that is about $14 [INF]; at the reservation-bound worst case (scorer cost unrecorded) it is about 2,400 x $0.03 = $72 [INF].

- **Test cap (proposed): $25**, set as `OPENROUTER_DAILY_BUDGET_USD=25` on staging and as a provider-side key limit of $25. Monthly cap $40 stays.
- The default $10 daily cap will deny mid-run in the high case; the denial then fails closed and ends the run, which is the desired stop. Do not raise the production default for the test.
- Record `guru_provider_reported_cost_usd_total` before and after each stage.

### 6.6 Metrics to record

| Metric | Source | Per stage |
|---|---|---|
| Latency p50 / p95 / p99, by scenario | Locust; `guru_answer_latency_seconds{lane}` | yes |
| Error rate: 5xx, timeouts, 429, 503 shed (separate) | Locust; `guru_requests_total` | yes |
| Outcome mix | `guru_answer_outcome_total{...}` (served, abstained, crisis, boundary, error) | yes |
| Useful answers | `guru_useful_answer_total{lane,signal}`; the load test cannot click, so `useful` is taken from the served count x the offline judged share, not from this counter | note |
| Cost: total, per request, per served clip, and **per useful answer** (formula in 3.1) | `guru_provider_reported_cost_usd_total{provider}`; `answer_outcome.total_cost_usd`; Redis spend keys `askmukthiguru:openrouter-spend:day:*` read by the operator | end of each stage |
| Unknown-cost calls | `guru_openrouter_cost_unknown_total` | yes |
| LLM calls per request | `answer_outcome.llm_calls` | S2, S5 |
| Starvation canary | `/api/health` fields, log line "Executor canary timed out", watchdog line "exiting non-zero", container restart count | continuous |
| Admission | `chat_backpressure.in_flight` on `/api/health`; shed count | continuous |
| RPM throttling | log line "OpenRouter rate limit hit — sleeping" count; "rate limiter still blocked" count | continuous |
| Resource use | Railway CPU, RSS, restarts for backend, Qdrant, Redis | continuous |
| Qdrant | search latency, optimizer state | continuous |
| Out-of-corpus leaks | served count in S3 | S3 |
| Scorer reasoning length | tokens out for L4 (`answer_outcome.llm_calls`) | S2 (fills the main unknown) |

### 6.7 Pass conditions, **target (proposed)**

These are placeholders until D-PE7 fixes them from two weeks of staging data (spec 3.1).

| ID | Condition | Source of the number |
|---|---|---|
| PC-1 | At 20 users (S5): 5xx rate below 1 percent, excluding controlled 503 shed (with `Retry-After`) | NFR-SCAL-01 |
| PC-2 | Uncached FP p95 at most 10 s; cache-hit p95 at most 0.5 s; crisis p99 at most 2 s | NFR-PERF-01/02/04; SLO-2, SLO-5 |
| PC-3 | Terminal state (`served`, `abstained`, `crisis`, `boundary`) for at least 99.5 percent of requests within 20 s | NFR-REL-01 |
| PC-4 | Zero executor-canary trips and zero watchdog exits | B8 acceptance |
| PC-5 | Zero served out-of-corpus items in S3 (68 items) | NFR-AIQ-02 |
| PC-6 | Zero crisis requests shed or answered by a non-crisis route | SLO-2 |
| PC-7 | Zero requests with `general_generated` route while FP-only is on | `15` section 7.2 |
| PC-8 | Zero calls with unknown cost (`usage.cost` present for all three models) | section 3.4 |
| PC-9 | Measured `C_req` and `C_useful` written to this document's section 3 with the date; scorer price entered in the repo table (D-16) | NFR-COST-04 |
| PC-10 | Peak RSS at most 80 percent of the staging limit; zero OOM restarts | section 4.5 |
| PC-11 | Burst (S6): shed responses carry `Retry-After`; p95 of admitted requests stays within PC-2 + 50 percent; recovery within 60 s | section 4 |

### 6.8 Abort rules (any one stops the run)

| ID | Rule | Action |
|---|---|---|
| AB-1 | Cumulative spend reaches 80 percent of the test cap ($20) | stop load; keep results |
| AB-2 | Budget denial (`OpenRouterBudgetExceeded`) seen in logs | stop load |
| AB-3 | 5xx rate above 5 percent over 2 minutes | stop load |
| AB-4 | Executor canary timeout logged twice, or any watchdog exit | stop load; capture thread dump if possible; this is the SYS-003 evidence |
| AB-5 | Any served clip in S3 (out-of-corpus leak) | stop S3; file an integrity finding |
| AB-6 | Any crisis request returns a non-crisis route or 503 | stop all stages; safety finding |
| AB-7 | Unknown-cost calls above 0 in S0 | stop; fix pricing/usage before spend continues |
| AB-8 | Backend RSS above 90 percent of the limit | stop load |
| AB-9 | Provider 429 rate above 20 percent for 2 minutes | stop; record the RPM ceiling reached |
| AB-10 | Qdrant or Redis restarts | stop; record |

### 6.9 Outputs

One dated evidence file under `audits/evidence/` (path decided by D-08) holding: config snapshot (`MAX_CONCURRENT_CHAT`, cap values, scorer model, collection, commit), the S0-S6 results, the measured `W`, `T`, RPM sleeps, `C_req`, `C_useful`, and a list of each pass condition as pass or fail. Then update section 3 and 4 of this document and `docs/runbooks/CAPACITY.md`.

---

## 7. Tasks

| ID | Task | Files | Non-goals | Rollback |
|---|---|---|---|---|
| NEW-LOAD-1 | Write `backend/benchmarks/locustfile_fp_staging.py`: weighted scenarios S1-S6, data loaded from the eval files in 6.3, per-class response checks (served, abstain, crisis, shed 503 with `Retry-After`), spend counter with a hard stop at AB-1, `--tags` per stage | `backend/benchmarks/locustfile_fp_staging.py` (new); `backend/tests/test_locustfile_fp_staging.py` (parse and mix test, no network) | No change to `locustfile.py` or `nightly-load.yml`; no auth bypass in production config | Delete the new files |
| NEW-LOAD-2 | Add outcome and cost capture to the load run: a small script that reads `/internal/metrics` before and after each stage and writes the table in 6.6 | `scripts/ops/load_run_report.py` and its `backend/scripts/ops/` copy (must be byte-identical, `test_repo_layout.py`) | No new metrics in the app | Delete |
| NEW-LOAD-3 | Record scorer price (D-16): add the scorer model to `_OPENROUTER_FALLBACK_RATES_PER_MILLION` with a dated source after the owner checks the price page; add a test that every configured model has an entry | `backend/services/openrouter_service.py`; `backend/tests/test_model_price_table.py` (new) | Do not guess a price. Do not change routing | Revert the commit |
| NEW-LOAD-4 | Make the three timeouts and the RPM limit one budget table (RET-16 / SYS-006): relevance timeout single source, test that Settings, both compose files and docs agree | `backend/services/first_person_budgets.py` (new per RAG spec 3.6); compose files; tests | Do not pick the timeout value (D-16) | Revert |
| NEW-LOAD-5 | Executor sizing guard: log `os.cpu_count()`, the default executor `_max_workers`, `max_concurrent_chat` at startup, and warn when `max_concurrent_chat` exceeds executor size minus 2 (SYS-003 mitigation until T7-02) | `backend/app/main.py` or `start_railway.py`; test | No `set_default_executor` change, no async rewrite (that is T7-02) | Revert |
| NEW-LOAD-6 | Set L3 `max_tokens` (about 16) so a rerank cannot run to the provider default (2048 capped at the 800-token fast ceiling on OpenRouter; 8192 on Sarvam or NIM; corrected by the lead, 2026-11-06), and count denials: add `guru_budget_denied_total` | `backend/services/first_person_pipeline.py` (L3 call); `backend/app/metrics.py`; tests | No change to the reservation amount | Revert |
| NEW-LOAD-7 | Run the staging load test (section 6) and write the evidence file; update `docs/runbooks/CAPACITY.md` (reconcile 8/12/20) | evidence file; `docs/runbooks/CAPACITY.md` | Not before P1-P8 hold | Delete evidence; staging stays |
| NEW-LOAD-8 | Decision memo inputs for D-PE7: after two weeks of staging data fill caps and SLO values | `FINAL_DECISION_AND_RISK_REGISTER.md` (owner edit) | Agent does not decide | n/a |

Dependencies: NEW-LOAD-1 and -2 before -7; -3 before PC-9; T7-02 (async lane, reserved) is the structural fix for SYS-003 and is not part of this document. DATA-18 (runtime state in container files: `data/feedback*.jsonl`) matters for replicas: two replicas see different files, so the test must run on one replica and count the `data/` writes separately. CQ-011 (`asyncio.run` in Celery) is outside the chat path; the load test does not exercise it, so it stays an unknown.

---

## 8. Verified, Assumptions, Unknowns

### Verified (read in code or config at head `004f3cf5`, not run)

- Call order, models, `max_tokens`, timeouts and skip conditions for L2, L3, L4 (section 2.2). L3 has no `max_tokens` argument, so the provider default applies: 2048 capped by the policy ceiling (800, fast) on OpenRouter; 8192 on Sarvam or NIM (corrected by the lead, 2026-11-06).
- `max_concurrent_chat` 12, crisis pool 12, 10 ms try-acquire; `WEB_CONCURRENCY` 1; answerability executor 4 workers; provider RPM 60 per model; native inference slots 6; pool 55 vs 51 needed; no `set_default_executor` in the repo.
- Budget guard defaults on, fail-closed on, $10 / $40, $0.03 per call, reservation kept when cost is missing or a sent call gets no response; local fallback 10 percent.
- The only price table holds 8b ($0.02/$0.04), deepseek-chat ($0.14/$0.28) and others; no entry for `anthropic/claude-haiku-5.5`; unknown models cost 0.0 in the fallback estimator.
- Locust and `locust>=2.31,<3` are in the repo; the nightly locustfile uses a mock LLM and the benchmark key, which production config refuses.
- The T2-02 retrieval bank has 8 rows; `evals/gold_set_v1/questions.jsonl` has 205 synthetic rows (150 on-topic, 40 out-of-corpus, 15 adversarial per its header counts).

### Assumptions (all [INF])

- Tokens are words x 1.3 (repo estimator); clip size 70-90 tokens; prompts as read.
- Default executor size follows the CPython rule `min(32, cpu + 4)` and the container sees its CPU limit.
- `q` 0.8, `h` 0.0-0.3, `g` 0.10-0.40, think time, S5 mix.
- `u` 0.09-0.13 transfers from a 29-question synthetic-judged set to real seekers.
- `R` (other executor threads) is 0 to 2.
- Scorer cost sweep 0.0005 / 0.002 / 0.008 USD per call bounds the unknown; it is not a price.
- Cache hits have the same usefulness as misses.

### Unknowns (need staging)

- Scorer price, whether OpenRouter returns `usage.cost` for it, and its real output (reasoning) length. This is the largest cost unknown.
- Real uncached `W` under concurrency, the knee of the throughput curve, and whether the 60 RPM per-model window binds first.
- `os.cpu_count()` and memory limits on the Railway container; FP-only peak RSS.
- Real traffic: `q`, `h`, `g`, volume, abstain share, and real `u` (all four exist only as proxies).
- Whether the v10 harness path (1 to 8 scorer calls) is the staging target.
- Fixed hosting cost and current Railway prices; Supabase plan connection limits and whether the telemetry path uses the declared DB pool.
- Qdrant server concurrency limits under D-26 hosting; Qdrant client pool defaults.
- Whether the executor canary trips under sustained 12-in-flight load (SYS-003 behaviour), and effect of DATA-18 on two replicas.
- Provider 429 behaviour at the account's real rate limit.
- Everything in this file is UNPROVEN until the B8 run (section 6) is done and recorded.
