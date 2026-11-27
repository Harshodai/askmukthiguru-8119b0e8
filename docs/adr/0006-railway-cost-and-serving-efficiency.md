# ADR 0006: Railway cost, deploy readiness and serving efficiency

- **Status:** Accepted for the default-off changes shipped on 2026-11-27. Not accepted: enabling the opt-in flags listed under "Rollout"; each needs the measurement named there first.
- **Date:** 2026-11-27
- **Deciders:** Project owner
- **Evidence:** `docs/operations/railway-cost-and-deploy-review-2026-11-27.md`, `docs/operations/scaling-and-efficiency-audit-2026-11-27.md`, `docs/operations/capacity-and-load-test-2026-11-27.md`, `docs/operations/model-memory-sharing-research-2026-11-27.md`, `docs/operations/fast-tokenizer-2026-11-27.md`, `docs/operations/shared-model-server.md`, `docs/handoffs/OPEN_WORK_LOOP_2026_11_27.md`.

Convention in this document: **measured** = observed on the live stack or a real run; **modelled** = computed from measured inputs; **unverified** = not run.

## Problem statement

Railway deployments were failing and the bill was rising. Reading the live configuration, metrics and logs found five separate problems, not one:

1. **Cost was memory.** Memory was $13.95 of $14.31 current usage (98%, measured). The backend averaged 4.8 GB over seven days at 0.02 vCPU (measured), because `WEB_CONCURRENCY=2` started two uvicorn workers and each loaded its own copy of the embedding and reranker models.
2. **Live configuration had drifted from the repository, invisibly.** `FIRST_PERSON_LLM_FALLBACK_ENABLED` was `true` against a binding owner directive of `false`; OpenRouter spend caps were $50/day and $500/month against repo defaults of $10 and $40; the backend and the Celery worker used different serving postures; and two Memgraph services existed, one an empty 50 GB volume with a public database port. The repository's drift tests could not see any of it, because `.railway/railway.ts` cannot express most live settings.
3. **Merged did not mean deployed.** The backend was running a build 146 commits and 302 files behind `main`. The Celery worker rebuilt a full image (torch plus model downloads) on every push to `main`, 30 times in about 25 hours, for a job that exits after about two seconds once a night; its last five deployments failed at `CREATE_CONTAINER` with an unexplained error (cause unknown; Railway support ticket pending).
4. **Rolling deploys routed users to a container that could not answer.** `/api/healthz` returned 200 unconditionally for the first 180 s, while `/api/chat` answered 503 until startup finished. Railway promotes a deployment on a successful health response.
5. **The first query after every restart took 23 to 29 s** against about 5 s warm (measured), and the system's real capacity for concurrent users was unknown.

## Decision

Fix the configuration directly where the owner approved it, ship every code change **default-preserving** with an opt-in flag, review each change independently before it merged, and say plainly what is unverified.

**Direct changes (owner approved):** `WEB_CONCURRENCY` 2 to 1 (backend memory 4.8 GB to 2.7 GB, measured); fallback flag to `false`; OpenRouter caps to $15/day and $150/month; the empty 50 GB Memgraph service and volume deleted after verifying 0 nodes; Celery watch patterns narrowed so docs, tests, CI and frontend pushes no longer rebuild it; a read-only guard, `scripts/ops/railway_live_audit.py`, that compares live variables and usage with the repository's invariants.

**Code changes (default-preserving):**

| Change | What it does | Default |
|---|---|---|
| Fast tokenizer | Uses the `tokenizers` library directly instead of `transformers.AutoTokenizer` | opt-in (`onnx_tokenizer_backend`) |
| Shared model server | One process holds the models; API workers call it over the private network | opt-in (`MODEL_SERVER_URL`) |
| mmap-prepacked ONNX | Builds the quantised model once into a memory-mappable file | opt-in (`ONNX_MMAP_PREPACKED_ENABLED`) |
| Startup retrieval canary | Warms the real first-person retrieval path after startup is complete | **on**, never blocks readiness |
| Readiness gate | `/api/healthz` stays 503 until `startup_complete` | opt-in (`HEALTHZ_REQUIRE_READY`) |
| Scaling audit fixes | Shared public health probe (10 s), `/api/capabilities` cache and ETag (60 s), cheaper telemetry consumer, bounded in-process maps, blocking calls moved off the event loop, lazy scikit-learn import | **on**, TTLs configurable |
| Configurable per-IP bucket | Same defaults (20 burst, 20/min) now settings | unchanged |

## Alternatives considered

- **More uvicorn workers.** Rejected as the scaling lever: the service is I/O-bound on about 11 LLM calls per chat, so extra workers multiply memory without adding much throughput. The audit guard now flags `WEB_CONCURRENCY` above 1.
- **Load the model before `fork()` (gunicorn-style preload) to share pages.** Not adopted. One early test here hung children on first inference; a controlled re-test with four runs could **not** reproduce a deadlock, so the cause is unproven. Creating the ONNX session after the fork is safe by construction and is the better pattern for more than one worker, but it needs a worker-bootstrap change not made here.
- **Railway sleep mode.** Not a lever: Railway documents that private-network calls count as outbound activity, and the backend polls Redis, so it never sleeps.
- **Parallelising or batching the roughly 7 relevance-scoring LLM calls per chat.** Rejected for now: early exit saves about one call and changes which clip is served; batching changes the judging context; deduplication has no evidence of applicability. Gate semantics are not changed for performance.
- **Adding a Railway-default-domain host filter.** Dropped after review: Starlette's `TrustedHostMiddleware` already rejects `foo.up.railway.app` (a `.x` entry is not a wildcard), so the proposed setting described behaviour that does not exist.

## Consequences

**Good (measured):** backend memory down about 44%; the main drift items closed and now checked by a guard; no docs-only push rebuilds the Celery worker. **Good (measured in tests):** a full backend run of 15,769 passed, 77 skipped, 0 failed on the integrated branch.

**Costs and risks:**
- A canary that runs by default adds startup work. It is scheduled after readiness, so it cannot hold chat on 503; an independent review found that an earlier version could, and it was changed.
- The readiness gate fails a deploy whose boot never finishes (the old container keeps serving) instead of promoting it. That is intended, and it is off until enabled.
- The telemetry consumer now keeps its cursor in memory: overlapping consumers during a rolling deploy duplicate events for the overlap, and the stored cursor only moves forward. The real fix is `XREADGROUP`.
- Shorter-lived caches mean a health result can be up to 10 s stale for anonymous callers; token callers always get a fresh probe.

**Unverified, and why it matters:**
- Equivalence of the fast tokenizer with `transformers` 5.19 (what serving uses) is **not re-run on the final code**. `scripts/ops/verify_fast_tokenizer_in_image.sh` does it in one command once the Docker VM has more than 3 GB free. The tokenizer swap should not be enabled before it shows zero skips.
- mmap-prepacked: the 909 MB to 597 MB single-process saving was measured on aarch64 after only 5 encodes; the N=2 saving is against an **extrapolated** baseline; Railway's x86_64 hardware and whether Railway bills mapped file cache are **unverified**.
- Model server: transport overhead about 2 to 4 ms p50 (measured with fake models); real memory and latency numbers were **not** measured because a measurement run OOM-killed the local backend twice.
- Capacity: a live 100-user load test was **not** run (Docker VM memory-starved). The 100-user figures are **modelled** from measured inputs (about 5 s warm chat, 5 job workers, a client-side 120/min OpenRouter limiter).
- Cold start: the startup canary has never run against real Qdrant, Memgraph and ONNX, so the before/after first-query numbers are not measured, and the 23 to 29 s delay is only partly attributed.

## Rollout

1. Deploy with every opt-in flag off. Verify `/api/capabilities` is 200, a smoke query returns a verbatim clip, and the live audit reports no critical findings.
2. Enable `HEALTHZ_REQUIRE_READY=true`. Safe failure mode: a deploy that never becomes ready fails and the old container keeps serving.
3. Enable `ADMIN_ROLE_NEGATIVE_CACHE_TTL_S=600` only after weighing a revoked-admin delay of up to ten minutes.
4. Trial `ONNX_MMAP_PREPACKED_ENABLED` against Railway's own memory metric for 24 hours; revert if the metric does not drop by about 200 MB. Plan: `docs/handoffs/OPEN_WORK_LOOP_2026_11_27.md`.
5. Capacity settings (`OPENROUTER_RPM_LIMIT`, `QUEUE_CONCURRENCY`, `QUEUE_MAX_SIZE`, `HTTP_MAX_CONNECTIONS`) raise provider spend and CPU use: owner decision, after a real load test.

## Lessons

- A configuration that cannot be expressed in the repository will drift. The fix is a read-only guard against the live system, run before and after any change.
- "Merged" is not "deployed". Verify the running build, not the branch.
- Memory, not CPU or traffic, was the bill. Look at the line items before looking for traffic.
- Independent review earned its cost. It found a canary that could have left chat on 503 forever, a cache-wipe path that a failed build could have triggered, a phantom fix for behaviour that did not exist, and several claims presented as measured that were extrapolated.
- A result that cannot be reproduced is not a root cause. The fork hang was recorded as "tested and rejected" and had to be softened to "not reproduced".
