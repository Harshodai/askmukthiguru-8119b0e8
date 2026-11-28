# Capacity model and load-test status, 2026-11-27

Question: can one Railway container (1 uvicorn worker, ~2 vCPU, 6 GB, in-process BGE-M3 INT8 +
ONNX reranker, LLM over OpenRouter) serve 100 users at once?

**Short answer: not with the shipped defaults. 100 people typing at the same moment would see most
requests wait minutes or be shed; 100 people online at a normal chat pace is workable once four
environment settings are raised (section 6).** The 100-user numbers below are a model, not a
measurement. Section 2 says why no live 100-user run was made.

## 1. What was measured and what was not

| Item | Source | Trust |
|---|---|---|
| Warm uncached chat 5.0 s end to end (pipeline 4.2-4.3 s), abstain 7.4 s, exact-cache 2.2 s | owner, live | measured, used as service time S |
| LLM calls per chat: about 7 Haiku relevance scorers + 1 Haiku distress check + 3 Llama-8B (answerability, HyDE, classify) = about 11 | my local run, counted at the stub (7 relevance calls on each of 3 consecutive chats) | measured, repeatable |
| Single-user latency 24-87 s and 3.9 CPU-s per chat | my local run | **discard**: host load average was 17-28 and the shared Docker VM had swap full; Qdrant GETs took 25 ms to 10 s from one second to the next |
| CPU-seconds per chat on the Railway box | not measured | open, see section 5 |
| Anything at N = 10, 25, 50, 100 | not run | not measured |

## 2. Why there is no live N = 1..100 table

The coordinator's rule for this session: run only in a throwaway container capped at 3 GB, and abort
if Docker VM free memory is under 2 GB. At the time of the runs the VM showed 666 MB to 1.3 GB
available with 1 GB swap full, `mukthiguru-backend` had been restarted by other sessions twice, and
other sessions' containers were at 90-125% CPU. The abort condition held, so I stopped. Details:

- Before that rule arrived I had started the backend **on the macOS host**, not in the VM, from this
  worktree, against the shared Qdrant/Memgraph (reads only), Redis **db 7** (its own keys; flushed
  afterwards, 57 keys) and an LLM/Supabase stub on 127.0.0.1:9099. No call left the machine (API key
  replaced with `stub-key`, Supabase pointed at the stub). `mukthiguru-backend` and other sessions'
  containers were not touched. I killed the process when the rule arrived and ran no load beyond
  1-user smoke tests (about 8 chats).
- The tooling is staged (not committed: the i18n pre-commit hook blocked it) and was smoke-tested on about 8 chats only, not at load: `scripts/ops/load_test_chat.py` (refuses non-loopback
  `--base-url`; `--users --duration --think-time --same-ip --pid`) and
  `scripts/ops/load_test_llm_stub.py` (OpenRouter and PostgREST stub with lognormal latency).
  To run the table: start a throwaway backend container (`--memory 3g --cpus 2`) with
  `OPENROUTER_BASE_URL` and `SUPABASE_URL` pointed at the stub, a spare Redis database, then
  `load_test_chat.py --users N` for N = 1, 10, 25, 50, 100 and `--think-time 60 --duration 300`,
  sampling `docker stats`. Do it when the VM has more than 2 GB free.

## 3. Layered limits, from the code

Request path: `POST /api/chat` returns 202 after enqueue; `JobQueueService` workers run the
pipeline; the client polls `/api/jobs/{id}` (250 ms, +250 ms per poll, cap 1 s).

| Layer | Value | Where | What it bounds |
|---|---|---|---|
| Per-IP token bucket on `/api/chat*` | 20 burst, 20/min, key = peer IP | `app/middleware/rate_limit.py` (was hard-coded in `main.py`; now settings, defaults unchanged) | everyone behind one NAT shares it |
| Per-IP slowapi | `CHAT_RATE_LIMIT` 120/min | `app/core/limiter.py` | per IP |
| Anon quota | code default 25 / 24 h; 5 per day in prod is **UNVERIFIED** (env files not read; the local container showed 100) | `anon_quota_*` | total chat volume from anonymous users; if 5 holds, a "100 users" crowd is capped at 500 anonymous chats per day |
| Admission semaphore | `MAX_CONCURRENT_CHAT` (12 default, 8 in compose) | `app/api/chat.py` | held only while the handler enqueues (ms for anonymous, 0.1-0.3 s for signed-in users because history comes from two Supabase round trips). It does **not** bound pipelines. Try-acquire with a 10 ms wait, then 503 + Retry-After 3-8 s |
| Job queue | 5 workers (`QUEUE_CONCURRENCY`), queue of 50 (`QUEUE_MAX_SIZE`), then 429 | `job_queue.py` | **the real in-flight cap: 5 pipelines, 55 admitted** |
| OpenRouter RPM limiter | 120 per minute **per model** (code default and local container env; `docker-compose.yml:266` defaults it to **20** when unset; Railway value unknown), Redis sliding window, sleeps up to the window, 5 rounds, then proceeds | `openrouter_service.py` | about 8 Haiku calls per chat means 15 chats/min |
| Relevance scorer timeout | 25 s (code default); 15 s seen in the local container env, **UNVERIFIED** for Railway | `first_person_pipeline.py` | a throttled scorer call that waits longer abstains as `relevance_indeterminate` |
| HTTP pool | 55 connections; validator assumes 3 LLM calls per request | `config.py` | real fan-out is about 11 calls with up to 4-5 concurrent per chat, so 5 workers use about 25; fine, but the validator comment is stale |
| ONNX gate | 6 slots, session runs are lock-free, 2 intra-op threads | `native_inference_gate.py`, `embedding_service.py` | memory, not a serializer. No lock serializes embedding or rerank |
| Thread pools | asyncio default executor, `fp-io` 32, answerability 4, enrichment cap 8 | various | not reached at 5 workers |
| Event loop | 1 worker, uvloop | `start_railway.py` | polls and JSON on one core; ASGI stack has 5 `BaseHTTPMiddleware` layers |

Also found and left alone (no measurement to justify a change): the enrichment-window step walks
the retrieved parents **sequentially** with a 1.5 s deadline each (`first_person_pipeline.py`
`_widen`). Healthy Qdrant makes it about 0.1-0.3 s; a slow Qdrant makes it up to 9 x 1.5 s inside a
worker, which lowers throughput exactly when load is highest. Parallelizing it needs the 8-slot
`_ENRICH_SLOTS` cap raised first, otherwise it would silently skip enrichment.

## 4. Little's law

Service time S = 4.3 s (job run), W = 5 workers.

- Worker ceiling: W / S = 1.16 chats/s = 70/min.
- Provider ceiling at the code-default RPM (at the compose default of 20 it is 6x lower, 2.5 chats/min): 120 / (60 x 8 Haiku calls) = **0.25 chats/s = 15/min**. This is
  the first bottleneck. It binds before workers.
- With `OPENROUTER_RPM_LIMIT` 900: 900 / 480 = 1.9 chats/s, so workers bind (1.16/s).
- CPU ceiling = 2 vCPU / c, c = CPU-seconds per chat. If c is 0.5, 4/s; if 1.5, 1.3/s. Poll handling
  adds about 7 polls per chat; at roughly 2 ms each (estimate) that is 14 ms per chat, about 0.28
  core at 20 chats/s, so polls matter only at high rates.
- In flight L = lambda x S. At 0.33 chats/s (see below) L = 1.4, far below 5 workers.

## 5. Scenarios (modelled, not measured)

**A. 100 users each send one message at the same instant**

- Anonymous users: all 100 POSTs are accepted at the handler (10-20 ms each). Signed-in users: the
  8-slot admission semaphore holds about 0.25 s per request, so about 30 requests/s pass and a burst
  of 100 inside a second gets about 70 x 503; the frontend retries after 3-8 s.
- Queue: 5 running + 50 queued = 55 admitted, 45 get 429 and retry up to 3 times (about 27 s). At
  1.16 chats/s about 31 slots free in that time, so roughly half of the 45 get in later; about 20-25
  see a final "busy" error.
- With default RPM (0.25 chats/s): the 55th queued job waits about 220 s, beyond the client's 120 s
  poll limit. Scorer calls also wait past 15 s and the chat abstains. Expect about 25-30 usable
  answers of 100, the rest timeouts or abstains.
- With RPM raised: the last admitted waits about 45-50 s; roughly 75-80 of 100 get an answer.

**B. 100 users each sending one message per 60 s** (lambda = 1.67/s): above the worker ceiling
(1.16/s) even with RPM raised, so the queue stays full and about 30% are shed. Not sustainable on
one container. This is also unrealistic: it is 100 people typing without pause.

**C. 100 users online at a realistic pace** (one message per 2-5 min, lambda 0.33-0.8/s): L is 1.4-3.4
of 5 workers. Fine once RPM is above lambda x 8 x 60 x 1.5 (240-580). At the default 120 it fails
from about 0.25 chats/s.

**D. 100 users on one venue IP**: the per-IP token bucket allows 20 messages, then 20 per minute for
the whole venue; most users get 429 regardless of every other limit. Now configurable.

## 6. Changes and recommended Railway settings

Code (default-preserving):

- `CHAT_TOKEN_BUCKET_CAPACITY` (20) and `CHAT_TOKEN_BUCKET_REFILL_PER_MINUTE` (20) replace the
  hard-coded values in `main.py`. Test: `tests/test_token_bucket_fallback.py`.
- Load tooling and its test: `backend/tests/test_load_test_scripts.py`.

Environment (not applied; owner decision, all raise provider spend or CPU):

| Setting | Now | For about 100 online users |
|---|---|---|
| `OPENROUTER_RPM_LIMIT` | 120 per model (code); 20 if compose default applies | 900 |
| `QUEUE_CONCURRENCY` | 5 | 8 (2 vCPU: more only queues CPU work) |
| `QUEUE_MAX_SIZE` | 50 | 100 |
| `HTTP_MAX_CONNECTIONS`, `HTTP_POOL_MAX_CONNECTIONS` | 55 | 100 (validator: (admission + workers) x 3 <= pool) |
| `CHAT_TOKEN_BUCKET_*` | 20 / 20 | raise only for a known shared-IP event |

Scale vertically first (4 vCPU) if CPU per chat turns out above about 1 s; the opt-in model server
being built elsewhere removes embedding and rerank CPU from this process and is the next step, not
duplicated here. A second replica works without code changes except that `WEB_CONCURRENCY` stays 1
per replica and the Redis-backed RPM, quota and exec-slot counters are shared.

Spend protection: `OPENROUTER_BUDGET_GUARD_ENABLED` with `OPENROUTER_DAILY_BUDGET_USD` 100 and
monthly 300, fail-closed; `OPENROUTER_MAX_REQUEST_COST_USD` 0.03 per request; per-user daily cap
(`cost_tracker.is_user_over_budget`); anon quota; the RPM limiter. Estimated cost per chat from the
code's own rate table (Haiku 5.5 at 0.10 / 0.50 USD per million tokens): about 0.001-0.002 USD, so a
100 USD day is on the order of 50,000 chats. That table is the code's, not an invoice.

## 7. Verdict

- Defaults, 100 simultaneous senders: no. The provider RPM limiter (15 chats/min) and the 5-worker
  queue shed or time out most of them.
- Defaults, 100 users online at a normal pace: no, fails above about 15 chats/min.
- With the section 6 settings: yes for 100 online users in normal use (about 0.3-0.8 chats/s), and
  about 1 chat/s sustained as the single-container ceiling. A true 100-way spike still sheds or
  delays about a quarter of requests; the frontend's retries soften it.
- Unverified: CPU per chat on the Railway box. Measure it first when the Docker VM has more than
  2 GB free, before relying on the 4 vCPU or model-server decision.

## 8. Caveats on the tooling

- `--same-ip` off gives each simulated user a distinct `X-Forwarded-For`. That only becomes the
  client IP if the backend trusts the peer for forwarded headers (`FORWARDED_ALLOW_IPS`, uvicorn
  `--forwarded-allow-ips`); otherwise every user shares the loopback peer and the per-IP limits
  skew the result.
- The generator only follows a host-relative `poll_url` and never sends the session token or
  `X-Faculty-Code` to another host.
