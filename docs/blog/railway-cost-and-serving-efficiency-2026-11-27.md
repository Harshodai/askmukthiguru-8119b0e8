# Our cloud bill was memory, our deploys never reached users, and a "merged" fix wasn't running

*An engineering write-up from AskMukthiGuru, a retrieval-grounded spiritual-teachings assistant. Draft for the owner to review before publishing. Numbers are tagged **measured**, **modelled** or **unverified**.*

---

## The symptom

Two complaints arrived together: deployments on our host (Railway) weren't working, and the bill had jumped. It would have been easy to guess ("traffic spike", "bots") and start tuning. We did the unglamorous thing first: read the live configuration, the usage line items, the metrics and the deployment logs.

## What we found: five problems, not one

**1. The bill was memory, almost entirely.** Of $14.31 of current usage, $13.95 (98%) was memory (measured). CPU was $0.16. Our API service averaged 4.8 GB over a week while using about 0.02 vCPU. The reason: the service ran two uvicorn workers, and each worker loaded its own copy of the embedding and reranking models. Railway bills memory per GB-month ([Railway pricing](https://railway.com/pricing)), so duplicated models were the bill.

**2. Production had drifted from the repository, and nothing could see it.** A feature flag that a binding product decision said must be off was on in production. LLM spend caps were five times higher than the repository's defaults. Two database services existed where we expected one, and one of them was an empty 50 GB volume. Our repository tests couldn't catch any of it, because the infrastructure-as-code file can only express a small part of what's configured live.

**3. "Merged" was not "deployed".** The API was running a build 146 commits behind `main`. A background worker that exists to run a two-second job once a night was rebuilding a full image, with ML libraries and model downloads, on every push to `main`: thirty times in about 25 hours. Its last five deployments failed with an unexplained container-creation error (cause still unknown; we have a support ticket to file).

**4. Rolling deploys sent users to a container that couldn't answer.** Our health endpoint returned `200` unconditionally for the first 180 seconds after boot, while the chat endpoint returned `503` until startup finished. Railway keeps the old deployment live until the new one answers its healthcheck with any `2xx`, and only then switches traffic ([Railway healthchecks](https://docs.railway.com/deployments/healthchecks)). A health endpoint that says "fine" too early is a gate that opens before the room is ready.

**5. The first question after every restart took 23 to 29 seconds**, against about 5 seconds when warm (measured).

## What we did

We changed configuration directly where the owner approved it, and shipped every code change **default-preserving**: new behaviour sits behind a flag that is off, or is a cache with the old behaviour as its default.

- **Memory:** one worker instead of two. API memory went from 4.8 GB to 2.7 GB (measured), roughly 44% lower. We also removed the empty database and its volume after verifying it held zero nodes, cut LLM spend caps to $15/day and $150/month, and narrowed the background worker's watch patterns so docs, tests and CI pushes stop rebuilding it.
- **Drift:** a small read-only script compares the live variables and usage against the repository's invariants and exits non-zero on critical drift. We run it before and after any infrastructure change.
- **Readiness:** an opt-in gate that keeps the health endpoint at `503` until the application has really finished starting, so a deploy that never becomes ready fails and the old container keeps serving.
- **Cold start:** a startup "canary" that exercises the real retrieval path once, after the app is already marked ready, so the first user doesn't pay for lazy initialization.
- **Smaller memory per process (all opt-in):** a direct use of the Rust `tokenizers` library instead of the full `transformers` tokenizer, a memory-mappable prepacked model file, and an optional shared model server so extra API workers don't each hold a copy.
- **Scaling hygiene:** one shared health probe instead of a full backend check per anonymous call, a cache and `ETag` on a public capabilities endpoint, a cheaper telemetry consumer, bounded in-process maps, and blocking calls moved off the event loop.

## What we decided *not* to do

- **More workers as the scaling lever.** Our chat is dominated by about 11 LLM calls and waiting, not CPU. [FastAPI's deployment guidance](https://fastapi.tiangolo.com/deployment/server-workers/) notes each process consumes its own memory, and ours holds about 2.7 GB. More workers would multiply the bill without lifting the real limit, which is our own client-side LLM rate limit.
- **Pre-fork model sharing, for now.** Loading the model before forking is a well-known way to share memory ([Rippling](https://www.rippling.com/blog/rippling-gunicorn-pre-fork-journey-memory-savings-and-cost-reduction) reports large savings; I did not reproduce their numbers). In one early test our forked children hung on first inference. A careful re-test of the same idea could **not** reproduce the hang, so we record the cause as unproven, not "rejected". Creating the inference session after the fork is safe by construction and is the better pattern if we ever need it.
- **Railway's sleep mode to save money.** Railway's serverless mode counts any outbound packet as activity, including private-network calls, and sleeps a service only after 5 to 10 minutes of silence ([Railway Serverless](https://docs.railway.com/deployments/serverless)). Our service polls Redis, so it never sleeps.
- **A "fix" that fixed nothing.** An early audit proposed a setting to block traffic to the platform's default domains. An independent reviewer showed the framework already rejected those hosts, so the setting would have changed nothing. We removed it, and that finding changed a question: if those hosts were rejected, how did the scanner traffic arrive? We haven't answered that yet.

## Can it serve 100 users?

Honest answer: **it depends on the traffic shape, and we have not load-tested it.** From measured inputs (about 5 s per answer, 5 job workers, a 120-requests-per-minute client-side limiter per model), our model says:

- *Steady traffic:* about 100 users sending a message every few minutes is fine (modelled).
- *A simultaneous burst of 100:* about 55 are admitted and the rest get a clean "busy" response; the last admitted answers arrive after minutes, not seconds (modelled).
- *Everyone on one Wi-Fi network:* a per-IP limit trips first, and edge providers' rate limits that count by IP don't fix that.

The first limit is our own LLM rate limiter, not the number of web workers. Adding replicas does not raise it, because it's enforced across all of them. The scaling playbook ranks what to do next, with the cost of each step estimated from the platform's published usage-based pricing, and marks which steps need a spending decision.

Two ideas from other teams' engineering write-ups shaped it: routing LLM traffic through one gateway with provider fallbacks and shared cooldown state ([LiteLLM routing](https://docs.litellm.ai/docs/routing), [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits)), and layered limiters that always reserve capacity for critical requests ([Stripe on rate limiters](https://stripe.com/blog/rate-limiters)). For us the critical class is a person in distress, and our crisis detection is deliberately a fast pattern matcher that never waits on an LLM or a rate limiter.

## What review caught

Every change got an independent review before merging, from a reviewer who hadn't written it. In this batch the reviews found: a startup canary that, on an unexpected error type, would have left chat answering `503` until restart; a cache-wipe path that a failed model build could have triggered; the phantom domain fix above; and several numbers that had been written as "measured" when they were extrapolated. Each was fixed or reworded. The cheapest bug is the one a second reader finds before it deploys.

## What we haven't verified

- The tokenizer swap's equivalence against the newest tokenizer library version, on the final code (one command, once a build machine has enough memory).
- The memory savings of the prepacked model on our production CPU architecture, and whether the platform bills mapped file cache.
- Real memory and latency of the shared model server.
- Any live load test; the 100-user figures are modelled.
- The 23 to 29 second cold start is only partly explained; the canary has not yet run against the real stack.

## Lessons

1. **Look at the line items before you look for traffic.** The bill was memory; traffic was innocent.
2. **Config you can't express in the repo will drift.** Guard the live system, not just the repo.
3. **Merged is not deployed.** Check the running build.
4. **A health check is a promise.** If it says ready before the app is ready, it is a promise you'll break on every deploy.
5. **A result you can't reproduce isn't a root cause.** We had to walk back a confident "tested and rejected".
6. **Say what you didn't measure.** It makes the parts you did measure believable.

---

*Sources opened while writing: Railway [healthchecks](https://docs.railway.com/deployments/healthchecks) and [Serverless](https://docs.railway.com/deployments/serverless) docs, [Railway pricing](https://railway.com/pricing), [FastAPI server workers](https://fastapi.tiangolo.com/deployment/server-workers/), [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits), [LiteLLM routing](https://docs.litellm.ai/docs/routing), [Stripe on rate limiters](https://stripe.com/blog/rate-limiters). The Rippling link is cited for its reported results only. Full internal evidence: ADR 0006 and the operations docs it lists.*
