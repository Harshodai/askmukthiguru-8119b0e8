# Railway cost and deploy review (2026-11-27)

Evidence: Railway usage, metrics, deployment history and logs read through the Railway CLI and MCP on 2026-11-27.
Nothing here was changed except the one setting listed under "Changed". The guard
`scripts/ops/railway_live_audit.py` re-checks the live configuration against these findings.

## Cost
- Billing period Nov 11 to Dec 11: **$14.31 so far, projected $41.94**; soft limit $30, hard limit $60 (a hard limit takes every workload offline). The previous period cost $0.45 because the stack was scaled down, so the "upsurge" is mostly the stack being switched back on.
- **Memory is $13.95 of the $14.31 (98%).** CPU $0.16, volumes $0.17, backups $0.01, egress under $0.01. The 50 GB volume is not a cost problem.
- Memory by service (7-day average): backend 4.8 GB (peak 18 GB, 6 GB container cap, CPU 0.02 vCPU, so idle), celery-worker 1.2 GB, the two Memgraph services 0.5 and 0.7 GB, Qdrant 0.4 GB, Redis 0.02 GB.
- Not cost drivers: HTTP traffic (a one-hour burst of 459 `GET /api/capabilities` from 303 IPs in two ISP ranges, one identical user agent, aimed at the default Railway domain; 9 ms each), chat volume (201 requests over Nov 23 to 25, 2 source IPs), GitHub Actions (public repo, free minutes), egress.
- Not visible from here: OpenRouter spend, Vercel build minutes, Supabase usage. Check those dashboards directly.

## Deploys
- **celery-worker rebuilt on every push to `main`**: 30 deployments in about 25 hours, each a full image build (torch plus model downloads), for a service whose job is `celery-on-demand: no queued work, exiting` once a night (cron `0 0 * * *`, about 2 seconds).
- The last 5 celery deployments (from the #114 merge at 05:39 UTC on Nov 26) **failed at `CREATE_CONTAINER` with "An unknown error"**. The build itself succeeds and the image is pushed; there are no runtime logs. The last good one is the #119 commit (`9551c2d`). Production is unaffected because the cron keeps running that last good image. Cause not determined: take a failing deployment id to Railway support.
- **The backend was running a Nov 24 build (`7d9cde2`), 146 commits / 302 backend files behind `main`** (the service config also lists a `commitSha` of `285f2d4`, which is not what was deployed). Merged is not deployed: today's safety fix (bereavement SEVERE no longer downgraded) was not in production. Changing a variable later that day rebuilt the service from current `main`.
- A staged patch from Nov 22 (a `META_APP_SECRET` variable and a backend resource update) was never applied.

## Configuration drift found (live vs repo invariants)
| Finding | Live value | Required |
|---|---|---|
| `FIRST_PERSON_LLM_FALLBACK_ENABLED` on the backend | **true** | false (binding owner directive 2026-11-23); it also makes unanswered questions cost LLM money |
| OpenRouter caps | $50/day, $500/month | repo defaults $10 and $40 |
| Serving posture | backend `v13_shadow`, celery `v10_only` | one posture |
| Memgraph | two services (3.12.0 with a 50 GB volume, 3.14.0 with 2 GB); apps use `memgraph.railway.internal`; the 50 GB one also has a public TCP proxy | one service, no public database port |
| Wait for CI on celery-worker | off | on |

## Changed (all with the owner's approval unless noted)
- `WEB_CONCURRENCY` 2 to 1 on the backend (live drift from the repo's `WEB_CONCURRENCY=1`): backend memory 4.8 GB week-average to 2.7 GB. Each uvicorn worker holds its own models.
- `FIRST_PERSON_LLM_FALLBACK_ENABLED` true to false on the backend. The variable change also redeployed the backend from current `main` (deployment `23746d76`, healthy).
- The Railway Memgraph the apps use (`memgraph.railway.internal`) had the old graph (2,760 units, 429 resolving in v13). After a Railway snapshot, the `TU*` layer was dropped and rebuilt from Railway's Qdrant: 2,999 of 2,999 resolve, 511 concept and 104 topic nodes, non-TU data unchanged.
- The unused 50 GB Memgraph service (0 nodes) set to sleep with a 0.5 GB cap. Deleting it and closing its public proxy were denied by the permission layer and remain for the owner.
- `celery-worker` watch patterns set to `/backend/**`, `!/backend/tests/**`, `!/backend/**/*.md`, `/memory/**`, `/config/helplines.yaml`, `/scripts/ops/rotate_brain_kek.py` and the rights manifest, so docs, tests, frontend, CI and workflow pushes no longer rebuild it. Rollback: set the service's watch patterns back to empty.

## Not done
- Railway Qdrant still has the 13 pre-fix `passage` points as `speaker_verified=true` (2,540 vs 2,527 local); the backend's key is read-only and the admin key was not used without the owner's go-ahead. Every other collection count matches local.
- Delete the empty 50 GB Memgraph service and its volume, and remove its public TCP proxy.

## Decisions for the owner
1. Done 2026-11-27 with the owner's approval: `FIRST_PERSON_LLM_FALLBACK_ENABLED=false` on the backend. Setting a variable rebuilds the service from current `main`, so it also deployed `main` (see item 2).
2. That deploy of `main` is the owner-approved side effect to verify: it keeps the old container serving until the new one passes `/api/healthz`. Confirm the Railway Qdrant has `first_person_v13_shadow`, review the staged patch, and run the smoke battery against the live domain.
3. Which Memgraph to keep; close the public TCP proxy unless something needs it; snapshot before deleting anything.
4. Lower the OpenRouter caps (suggested ceiling $15/day, $150/month unless a graded run needs more).
5. Limits: after the cuts the projection should fit; keep the hard limit as a guardrail but raise the soft limit above the expected bill so the alert means something.
6. Backend memory: a 4.8 GB average for an idle service is the bill. Options: keep sleep mode and accept cold starts, cap the container, or move the models out of the request process.

## More changes after the first pass (owner-approved)
- Deleted the empty 50 GB Memgraph service and its detached volume (0 nodes verified first). Its public database proxy went with it.
- OpenRouter caps on the backend and the celery worker lowered to $15/day and $150/month (were $50 and $500). Soft usage limit raised from $30 to $45; the $60 hard limit is unchanged because it is the guardrail that takes everything offline.
- Railway Qdrant: the 13 pre-fix `passage` points patched after a Railway snapshot; fingerprint now identical to local (`speaker_verified=true` 2,527).

## Running more than one worker without duplicating models: research and decision
In the backend image, python and libraries are about 0.5 GB and the BGE-M3 INT8 session about 0.9 GB (estimates). One live process measured ~2.6 GB RSS (Railway average 2.7 GB), and with two workers the 7-day average was 4.8 GB, so every extra uvicorn worker adds roughly the same again.
- **Load before fork (gunicorn `--preload`, copy-on-write).** Reported savings are real in the literature ([Rippling](https://www.rippling.com/blog/rippling-gunicorn-pre-fork-journey-memory-savings-and-cost-reduction), [Bolna](https://www.bolna.ai/blog/cutting-per-pod-memory-gunicorn-preload), [Trendyol](https://medium.com/trendyol-tech/sharing-large-language-models-among-gunicorn-workers-reducing-memory-usage-and-boosting-18c0efd8e942)), but sharing erodes as CPython touches pages and the child only sees a snapshot. **Not adopted:** in one early test here, children forked after the ONNX session was loaded hung on their first inference. A later, controlled re-test (4 runs, intra-op 1/2/4, with and without the compose env) could NOT reproduce a deadlock; the cause is unproven (fork keeps only the calling thread, so ORT's intra-op worker threads are missing in the child; the slowdowns seen on a starved VM looked like CPU starvation). Do not rely on pre-fork sessions: creating the session after the fork is safe by construction. See `docs/operations/model-memory-sharing-research-2026-11-27.md` once merged.
- **Separate model server (the other pattern large systems use, e.g. TEI or Triton).** Weights load once; API workers call it over the private network. This is the supported way to scale workers here. It pays off only above one worker (1 server plus 2 API workers is about 3.5 GB against about 5 GB for 2 duplicated workers); at one worker the in-process model is cheaper. Built as an opt-in `SERVICE_TYPE=model-server` / `MODEL_SERVER_URL` mode, default off (see `docs/operations/shared-model-server.md` when merged).
- **Decision:** production stays at `WEB_CONCURRENCY=1` (the service is I/O-bound on LLM calls; one async process is enough). Use the model-server mode before raising the worker count. The audit guard flags `WEB_CONCURRENCY>1`, and the boot log warns when it is above 1 without a model server.
- **Railway sleep mode is not a lever here:** private-network calls count as outbound activity ([Railway docs](https://docs.railway.com/reference/app-sleeping)), so a backend that polls Redis never sleeps.

## Local vs Railway data parity (verified 2026-11-27)
- **OKF:** identical (`compiled.json` sha256 prefix `6e0fde67`, 493 entries); it ships inside the image.
- **Qdrant:** `first_person_v13_shadow` (4,730), `first_person_v12_shadow` (4,086), `spiritual_wisdom_contextual` (13,458), the three LightRAG collections and `second_brain_vault` have identical id and payload fingerprints on both sides. Railway-only: `first_person_v10` (4,224, the old generation the celery config still references) and runtime caches/memory vectors. Local-only: `guru_tone_podcast` (9 points, seeded by a script, not read by serving).
- **Memgraph:** curated layers identical (base 6,427, TU layer 2,999 units / 511 concepts / 104 topics, Concept, Teacher, Practice, Quarantined). Left local on purpose: 128 `TeachingUnit` + 37 `Video` nodes written by `ingest/video_pipeline.py` with an `ingest_namespace` (ingestion-shadow artifacts, never read by serving) and local test-conversation provenance (`GuruResponse`, `InferenceActivity`, `SeekerTurn`).

## Query timing on the live backend (2026-11-27, anonymous session, uncached questions)
| Case | End to end | Pipeline |
|---|---|---|
| First query after a container (re)start | 28 to 29 s | 25 to 28 s |
| Warm, in-domain (served verbatim clip) | 5.0 s | 4.2 to 4.3 s |
| Warm, abstain | 7.4 s | 5.5 s |
| Repeat of the same question (exact cache) | 2.2 s | 0.02 s |
| Out-of-corpus control (off-topic boundary) | 1.3 s | n/a |
In-container timings: Memgraph connect 0.26 s then 4 to 5 ms per query; Qdrant dense search 4 to 36 ms; BGE-M3 encode 60 to 210 ms warm but about 24 s on the first call in a fresh process (includes model load). The ~23 s first-query block is unlogged and sits between HyDE and the context harness; the startup warm-ups (embedder, reranker, intent, router) finish minutes earlier, so a lazy initialization on the real retrieval path is missed. A startup retrieval-path canary is being added. Models are healthy after warm-up: no abstain-on-timeout, correct off-topic abstain, verbatim citation served with `model_used=null`.

## Guard
`python3 scripts/ops/railway_live_audit.py` (read only; exit 0 clean, 1 warnings, 2 critical). Run it before and after any Railway change.
