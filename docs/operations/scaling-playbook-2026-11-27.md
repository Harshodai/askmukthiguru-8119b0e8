# AskMukthiGuru scaling playbook (2026-11-27)

Status: research only. No load test was run. Every capacity figure below is **MODELLED** unless marked MEASURED. Railway is stopped, so nothing here describes the live service.

## Verdict

"100 users" is not one number. The unit that matters is **chat messages per minute**.

- **Steady traffic: yes.** One container handles about 100 users who each send a message every 7 minutes or so (about 15 msgs/min) at about 5-7 s per answer (MODELLED). The binding limit is our own `OPENROUTER_RPM_LIMIT=120`, not CPU.
- **Simultaneous burst: no.** If 100 people press send in the same second, the in-process queue (5 running plus 50 queued) takes about 55. The rest get 429. Even the 55 who get in finish over minutes, not seconds, because about 11 LLM calls per chat at 120 RPM per model drains at about 15-17 chats/min. The last answers in the queue would take about 3-4 minutes (MODELLED).
- **Shared Wi-Fi caveat.** At a satsang on one Wi-Fi network, everyone shares one public IP. The 20 requests/min per-IP bucket on `POST /api/chat` trips first, after about 20 messages per minute from the whole room. Cloudflare's free and Pro rate limiting also counts by IP only, so putting it in front does not fix this.

**The first lever is the self-imposed RPM limit, not `WEB_CONCURRENCY`, and not more replicas.**

## 1. What limits us first, in order (evidence)

1. **LLM call budget (self-imposed).** `services/openrouter_service.py` enforces `openrouter_rpm_limit` per model through a Redis-backed sliding window (`RedisBackedRateLimiter`, key `openrouter:rpm`). The code comments say it is global "across every process/worker/replica". So adding workers or replicas does **not** raise LLM throughput. About 7 Haiku scorer calls per chat at 120 RPM gives about 17 chats/min on the Haiku bucket.
   - **What happens at the limit (code-read):** the limiter waits `_MAX_RATE_LIMIT_WAIT_ROUNDS`, then logs "proceeding anyway" and sends the request. Overload therefore shows up as **rising latency, then possible upstream 429s**. Those 429s turn into `relevance_indeterminate` abstains (invariant 24), not clean 429s to the user.
   - **Upstream headroom:** OpenRouter says paid (non-`:free`) variants have "no platform-level request cap" but "different rate limits for different models" (values not published). Anthropic's own Start tier lists Haiku 5.5 at 4,000 RPM / 2M ITPM. That applies to OpenRouter's Anthropic account, **not to ours**, so it shows upstream headroom but is not our ceiling.
   - **Ramp limits:** Anthropic also enforces ramp limits. A "sharp increase in usage" can return 429 below the rate limit. OpenRouter's provider fallback is what absorbs this.
2. **Queue admission.** `JobQueueService` holds an in-memory `asyncio.Queue(maxsize)` per process, with a per-process worker semaphore. A shared Redis "exec slot" counter, capped by `max_concurrent_chat`, applies across replicas. Crisis requests bypass the slot. Over the cap, the queue returns `QueueFullError`, which becomes 429.
3. **Per-IP limit.** slowapi `chat_rate_limit` (20/min) on `POST /chat`, `/chat/v2` and `/chat/stream`, stored in Redis (`app/core/limiter.py`). The poll GET is **not** decorated, so polling does not drain the bucket (code-read).
4. **Memory, not CPU,** for any multi-worker change. Models take about 2.7 GB per process. FastAPI's docs: "each process will consume an equivalent amount of memory". Two workers would need about 5.4 GB of the 6 GB cap.
5. **CPU for local models.** The embedder, reranker, intent model and LettuceDetect run on about 2 vCPU. Retrieval plus rerank is about 9% of wall time (L-LATENCY-1), so this is not first. It becomes second once the LLM budget is raised. **Unmeasured** under concurrency.

## 2. Railway-specific scaling

**Replicas (docs read):**
- Replicas are "exact copies" of the service.
- "Each replica has access to the full resources allocated by your plan."
- Replica count changes "without a full redeploy", and removed replicas drain gracefully.
- Set the count from the dashboard, `railway.toml` `numReplicas`, or the CLI.

**Load balancing (sources conflict):**
- The scaling reference says requests are distributed "randomly" across replicas within a region, and multi-region traffic goes to the nearest region.
- The scaling guide says "round-robin".
- Either way, there is **no stickiness**: "Railway does not support sticky sessions."

**Limits (sources conflict):**
- The scaling reference: Pro replicas get up to 24 vCPU / 24 GB each.
- The pricing page: per-service maximums of Hobby 48 vCPU / 48 GB with 6 replicas, and Pro 1,000 vCPU / 1 TB with 42 replicas.
- The autoscale guide: "a maximum of 50 replicas total across all regions."
- **Owner must confirm the plan.** Our 2 vCPU / 6 GB cap looks self-set, not a plan limit.

**Autoscaling:**
- Built-in autoscaling is **vertical only** ("scale your service up to the specified vCPU and Memory limits of your plan").
- Horizontal autoscaling is do-it-yourself. Railway's guide runs a separate worker that polls an app-exposed load metric (in-flight requests, queue depth, p95), averages several samples because routing is random, and calls the GraphQL `serviceInstanceUpdate` with `numReplicas`.
- It recommends "scale up fast, scale down slow" (5-minute cooldown), and requires a stateless service with a healthcheck.
- It also notes that "replicas don't help with memory bottlenecks."
- **KEDA/HPA are Kubernetes tools and do not apply on Railway.**

**Private networking:**
- Services are reachable at `<service>.railway.internal` over WireGuard, using `http://`.
- New environments are dual-stack; legacy ones are IPv6-only.
- Cross-region traffic works but is slower.
- The docs I read do **not** say how a multi-replica target resolves (one address or many). Treat calls to a replicated model server as unverified load balancing.

**Does our in-process queue break under N replicas? Mostly no (code-read):**
- Job metadata and results live in a Redis hash.
- Each job is claimed with a Redis lease (`job:{id}:lease`, owner `instance_id:worker_id`, TTL 300 s).
- The stale sweeper only fails jobs whose `started_at` is older than the 300 s lease. Real jobs take 5-7 s, so one replica will not reclaim another's live job.
- A poll that lands on replica B reads Redis, so it works.

**Real caveats:**
- (a) The queue's `maxsize` is **per replica**, so total admission scales with N while the exec-slot cap stays global. Size both deliberately.
- (b) If Redis is unreachable, `_degrade_to_memory()` switches that replica to a local store. Polls landing on other replicas then miss the job. Multi-replica therefore makes Redis a hard dependency.
- (c) Each replica re-downloads or loads 2.7 GB of models unless `SERVICE_TYPE=model-server` is used.

**Cost (pricing page, usage-based, per second):**
- About $10 per GB-month of RAM and about $20 per vCPU-month, on top of $5 (Hobby) or $20 (Pro) plan fees that include the same amount of usage.
- A full-fat replica averaging 2.7 GB and about 0.5 vCPU costs roughly **$37/month** (MODELLED from average usage, not cap).
- A thin API replica (models in the shared model server) at about 0.5 GB and 0.3 vCPU costs roughly **$11/month**.
- Egress is $0.05/GB. It is negligible for JSON.

## 3. How others scale LLM/RAG backends (100 to 10k concurrent)

What the sources show:

- **Treat the provider budget as the scarce resource and route around it.**
  - **LiteLLM Router:** spreads requests across "deployments" that each carry their own key, with per-deployment `rpm`/`tpm`, cooldowns after failures, retries with exponential backoff on 429, ordered fallbacks, and Redis to share cooldown and usage state "across instances".
  - **OpenRouter** gives much of this natively:
    - Provider routing defaults to load balancing weighted by price, throughput, latency and reliability.
    - `allow_fallbacks` defaults to true.
    - `sort: "throughput"` or `:nitro` prefers fast providers.
    - A `models` array falls back on "Rate-limiting" and "Downtime", and you pay for the model that served.
- **One gateway in front of all LLM traffic.** Uber's GenAI Gateway centralises auth, PII redaction, logging and budget across about 30 teams at 16M queries/month with a 25 QPS peak. **Lesson for us:** even large organisations' LLM traffic is modest in QPS. The gateway is about control, not raw throughput. Our `OpenRouterService` is already this choke point.
- **Prompt caching raises throughput, not only cost efficiency.** Anthropic: ITPM counts "only uncached input tokens" ("80 percent cache hit rate" means about 5x effective input). OpenRouter supports `cache_control` for Claude, with a 512-token minimum on Haiku 5.5, reads at 0.1x and writes at 1.25x, default TTL 5 minutes. Our 7 scorer calls share one rubric/system prompt, which makes them a direct fit. It does **not** reduce RPM, which is our current binding limit.
- **Exact response caching at the edge.** Cloudflare AI Gateway caches "exact match of the entire request" only, with semantic caching "planned", TTL from 60 s to one month. That page does not mention OpenRouter. We already have the exact Redis cache, and invariant 8 forbids a semantic cache on the first-person route.
- **Layered limiters and load shedding (Stripe):**
  - Request-rate limiter first, then a concurrent-request limiter.
  - A fleet load shedder that "always reserve[s] a fraction of our infrastructure for critical requests".
  - A worker-utilisation shedder as "the final line of defense".
  - Fail open on limiter errors, dark-launch before enforcing, and keep kill switches.
  - **Our mapping:** crisis traffic is the "critical request" class. It already bypasses the exec slot; that should become an explicit invariant.
- **Stateless API plus a separate inference tier.** FastAPI recommends "a single Uvicorn process per container" under an orchestrator and scaling by containers. Hugging Face TEI serves embedders and rerankers with "token-based dynamic batching" on CPU images, plus Prometheus metrics. It lists XLM-RoBERTa embedders and `bge-reranker-base/large`. **It does not list BGE-M3 sparse output** (unverified for our hybrid sparse vectors), so TEI could replace the dense embedder and reranker but probably not the sparse side.
- **Queue-depth autoscaling.** KEDA's Redis list scaler targets an average `listLength`. That is Kubernetes-only; the Railway equivalent is the DIY `numReplicas` worker above, fed by our queue depth.
- **Vector DB scale-out.** Qdrant distributed mode (`QDRANT__CLUSTER__ENABLED=true`) uses `replication_factor` per collection (default 1). Changing it after creation "doesn't do anything" on self-hosted. With 13k points, this is a 10k-tier concern at most.
- **Not sourced in this pass (claims omitted):** SSE vs polling at scale, Redis read replicas, vLLM/Triton. We call no self-hosted LLM, so vLLM is irrelevant anyway.

## 4. Roadmap

### Tier A: about 100 active users (15-60 msgs/min)

Changes:
- **Env, existing:**
  - Raise `OPENROUTER_RPM_LIMIT` in steps (for example 120, 300, 600) while watching OpenRouter 429 rate.
  - Set `QUEUE_MAX_SIZE`/`QUEUE_CONCURRENCY` so queue wait is at most about 30 s at the target rate.
  - Keep `WEB_CONCURRENCY=1`.
- **Code, small:**
  - Explicit OpenRouter `provider.sort: "throughput"` and `allow_fallbacks: true` on the scorer calls. Same model, so no graded run is needed.
  - `cache_control` on the scorer system prompt, if it is at least 512 tokens. Same model and same prompt, so output is unchanged. Confirm with a short A/B check.
  - Surface queue position and ETA to the client.
  - Raise or reshape the per-IP limit for known event networks (per-session or per-user key, with IP as a backstop).
- **Infra:** none.

Capacity: about 40-80 msgs/min if the provider accepts 300-600 RPM (MODELLED). After that, CPU for local models is the next ceiling. **Unmeasured.**

Cost: Railway +$0. LLM spend scales linearly with messages; price per call not computed here.

Risks: the fail-open limiter hides overload as latency or abstains; upstream ramp-limit 429s during bursts.

### Tier B: about 1,000 users (150-500 msgs/min)

Changes:
- **Infra:**
  - Turn on the existing `SERVICE_TYPE=model-server` as its own service.
  - Run 2-4 thin API replicas (`MODEL_SERVER_URL`).
  - Healthcheck-gated rolling deploys, which already exist.
- **Code:**
  - DIY Railway autoscaler worker on queue depth (Railway guide pattern).
  - Expose a `/load` metric per replica.
  - Make the Redis dependency explicit for multi-replica: fail closed with 503 instead of degrading to memory when N>1.
  - Dashboards: queue wait, abstain-by-reason, OpenRouter 429s.
- **Edge:** Cloudflare in front for bot and abuse blocking (Free gives 1 rule, IP-counted, 10 s period). It is not a fix for NAT'd groups.
- **Decision:** the RPM limit at 1,000-3,000 needs confirmation that OpenRouter's per-model limits allow it (values unpublished). Ask OpenRouter or add a second key or provider path.

Capacity: MODELLED 150-300 msgs/min. CPU on the single model server becomes the bottleneck; TEI-style batching is the fix (sparse caveat). **Unmeasured.**

Cost (MODELLED, pricing page):
- Model server at about 3 GB and 1-2 vCPU: about $50-70/month.
- Each thin replica: about $11/month.
- Total about $80-120/month Railway, plus LLM.
- Pro plan ($20) if more than 6 replicas or Pro limits are needed.

Risks: random load balancing plus a slow model server makes p95 noisy; the model server becomes a SPOF (run two).

### Tier C: about 10,000 users (1,500+ msgs/min)

Changes:
- **Code plus graded run (owner):**
  - Collapse the 7 per-clip Haiku scorer calls into one batched call. This cuts LLM RPM about 5x, which is the biggest lever at this tier, but it **changes the gate**, so it must go through a registered graded run per invariant 24.
  - Or precompute question-to-clip relevance for frequent questions (also gated).
- **Infra:**
  - Replicated model servers, or TEI for dense and rerank.
  - Qdrant with `replication_factor=2` on a new collection.
  - Redis HA. Railway Redis HA options were not researched.
  - Multi-region replicas only if users are spread out.
  - Multi-key or multi-provider gateway (LiteLLM-style) with shared Redis cooldowns.
- **Ops:** load-shedding tiers per Stripe, with crisis always admitted; budget alarms.

Capacity: unknown. Do not claim without a load test.

Cost: Railway likely $300-800/month (MODELLED, very rough). LLM spend dominates.

Risks: invariant drift from gate changes; provider concentration.

## 5. Things not to do

- **Do not raise `WEB_CONCURRENCY`.** It duplicates 2.7 GB per worker (FastAPI docs) and adds **zero** LLM throughput, because the RPM limiter is global.
- **Do not add replicas before raising the RPM budget.** They share the same global budget.
- **Never use `FIRST_PERSON_LLM_FALLBACK_ENABLED=true` as a load valve** (binding owner directive).
- **No semantic cache on the first-person route** (invariant 8).
- **No scorer model swap, batching or min-score change without a graded run** (invariant 24). Provider-level fallback on the same model is fine.
- **Never shed, queue-cap or LLM-gate crisis traffic.** Distress assessment must not depend on the RPM budget in a way that can fail open to "no distress". The distress LLM call likely shares the limiter; its failure behaviour under throttling was checked by the main session (code read, `backend/app/pipeline/stages/distress_stage.py` `_maybe_llm_escalate_below_crisis`, `backend/services/openrouter_service.py` `_enforce_rate_limit`): the primary crisis detector (`assess_distress`) is pure regex and never calls the LLM; the LLM layer is escalate-only (default ON, `distress_llm_escalation_enabled`), skipped entirely when the regex level is already CRISIS, and a timeout, error or unparseable reply keeps the regex level. So the distress path cannot fail open BELOW the regex floor under throttling. What can degrade under overload is the LLM's extra recall for phrasing the regex misses (for example romanized Indic): the call shares the per-model RPM limiter, which can sleep up to 5 rounds, and that time counts against `distress_llm_escalation_timeout_s`. Exempting this call from RPM waits would restore that recall under load, but it is a safety-path change: it needs a safety review and an owner decision, and it was NOT made. Not run under load.
- **No premature microservices** beyond the one model-server split that already exists.
- **No KEDA/Kubernetes migration** to get autoscaling. Railway's DIY loop is enough until Tier C.

**Must be load-tested before claiming capacity** (needs Railway resumed: owner-gated; the local Docker VM is too small to be meaningful):
- Sustained 15, 30, 60 msgs/min for 10 minutes.
- A burst of 100 in 5 s.
- Mixed polling.
- Measure: p50/p95 end-to-end, queue wait, 429 count, abstain-by-reason (especially `relevance_indeterminate`), OpenRouter 429s, RSS per replica, model-server CPU.
- Verify the crisis path still answers inside budget during the burst.

## 6. Ten next actions, ordered by value per effort

| # | Action | Type | Effort | Owner decision? |
|---|---|---|---|---|
| 1 | Distress call under throttling: CHECKED, cannot fail open below the regex floor; optionally exempt it from RPM waits to keep LLM recall under load | Safety-path change | S | Yes (safety review) |
| 2 | Raise `OPENROUTER_RPM_LIMIT` stepwise with 429 monitoring | Env | XS | Yes (LLM spend) |
| 3 | Resume Railway and run the load-test matrix above | Ops | M | Yes (Railway spend) |
| 4 | Add abstain-by-reason, queue-wait and upstream-429 metrics/alerts | Code | S | No |
| 5 | OpenRouter `provider.sort: throughput` + fallbacks on scorer calls | Code | XS | No |
| 6 | Prompt caching on the scorer prompt (if at least 512 tokens) | Code | S | No (verify outputs) |
| 7 | Per-user/session chat limit with IP as backstop (event NAT) | Code | S | Yes (abuse posture) |
| 8 | Size `QUEUE_MAX_SIZE`/`QUEUE_CONCURRENCY`/`max_concurrent_chat`; show queue ETA | Env + UI | S | No |
| 9 | Split model server + 2 thin replicas; Redis fail-closed when N>1 | Infra + code | M | Yes (spend, about $80-120/month) |
| 10 | Batched single-call relevance scorer | Code + graded run | L | Yes (gate change) |

## Sources (pages actually opened)

- docs.railway.com/reference/scaling: replicas get full plan resources; random distribution; no sticky sessions; vertical autoscaling default; Pro 24 vCPU/24 GB per replica.
- railway.com/guides/scaling-your-application: "round-robin" wording (conflicts with "random"); multi-region routing.
- railway.com/guides/autoscale-horizontally: DIY horizontal autoscaler via GraphQL `numReplicas`; 50-replica cap; stateless plus healthcheck; replicas don't fix memory.
- railway.com/pricing: plan replica caps (Hobby 6, Pro 42); per-service maxima; $20/vCPU-month, $10/GB-month, $0.05/GB egress; per-second billing.
- docs.railway.com/reference/private-networking and .../private-networking/how-it-works: `*.railway.internal`, WireGuard, dual-stack after 2025-10-16, cross-region slower; no replica-resolution detail.
- openrouter.ai/docs/api-reference/limits: no platform cap on paid variants; per-model limits exist but are unpublished.
- openrouter.ai/docs/features/provider-routing: default weighted load balancing, `sort`, `allow_fallbacks`, `order` (page truncated after 100k chars).
- openrouter.ai/docs/guides/routing/model-fallbacks: `models` array falls back on rate-limit and downtime; billed for the model used.
- openrouter.ai/docs/features/model-routing: defers to fallbacks page; standard-rate billing.
- openrouter.ai/docs/features/prompt-caching: Claude `cache_control`, Haiku 5.5 512-token minimum, 0.1x reads, 5-minute TTL.
- platform.claude.com/docs/en/api/rate-limits: tier RPM/ITPM tables; cache-aware ITPM; ramp limits; token bucket. These are OpenRouter's upstream limits, not ours.
- docs.litellm.ai/docs/routing: multi-deployment/key routing, rpm/tpm, cooldowns, retries, Redis-shared state.
- uber.com/blog/genai-gateway: centralised gateway; 16M queries/month, 25 QPS peak. The article does not cover caching or fallback.
- stripe.com/blog/rate-limiters: four limiter types; reserve capacity for critical traffic; fail open; dark launch.
- developers.cloudflare.com/waf/rate-limiting-rules: plan rule counts; Free/Pro count by IP only.
- developers.cloudflare.com/ai-gateway/features/caching: exact-match only; semantic planned; OpenRouter not mentioned.
- huggingface.co/docs/text-embeddings-inference (index + supported_models): dynamic batching, CPU images, XLM-RoBERTa embedders and bge rerankers; no BGE-M3 sparse mention.
- keda.sh/docs/2.16/scalers/redis-lists: `listLength` target; Kubernetes-only.
- qdrant.tech/documentation/scaling/distributed_deployment: `replication_factor` default 1; changing it after creation does nothing on self-hosted; shard guidance.
- fastapi.tiangolo.com/deployment/server-workers and /concepts: one Uvicorn process per container under orchestrators; memory multiplies per worker.

Repo code read (not web): `backend/services/openrouter_service.py` (global Redis RPM limiter, fail-open after wait rounds), `backend/app/services/job_queue.py` (Redis-backed job state, leases, global exec slot, crisis bypass, per-process queue), `backend/app/api/chat.py` and `backend/app/core/limiter.py` (per-IP limit on POST routes only, Redis storage), `backend/start_railway.py` and `backend/docker-entrypoint.sh` (`WEB_CONCURRENCY` default 1).

Snippet-only (not opened): Railway 2023 horizontal-scaling changelog and a community answer that autoscaling is vertical. Not relied on.
