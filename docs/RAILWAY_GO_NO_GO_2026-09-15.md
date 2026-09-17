# Railway $25/mo Deploy — Go/No-Go (2026-09-15)

**Scope: prepare only. No `railway up`, no `railway redeploy`, no `railway variables --set`, no
docker commands were run.** Railway inspection below is entirely read-only (`railway status`,
`railway logs`, `railway variables --kv` with values redacted, `railway deployment list`).

## Verdict: **NO-GO**

**The gap that decides it in one sentence:** the local stack only survives the reproduced
container wedge because of `willfarrell/autoheal` polling Docker's own healthcheck every 10s
(`backend/docker-compose.yml:165,705-712`) — Railway has no declared equivalent anywhere in
`railway.json`, and `restartPolicyType: ON_FAILURE` only fires on process exit, which a wedged-but-alive
event loop never produces. On Railway, this wedge would not self-heal.

Independently of that: **production is down right now.** `railway status` reports
`askmukthiguru-8119b0e8` as `● Crashed`, and the crash log is a literal OOM abort
(`memory allocation of 67028844 bytes failed` / `Fatal Python error: Aborted`) during
`BAAI/bge-m3` model loading — the exact signature `docs/OOM_RAILWAY_INCIDENT.md` already
describes as "Fixed, deployed," except its own text says the fix was never redeployed
("needs manual approval"), and the live service confirms that: it is still crashing on this
signature. Two live blockers, either one is a no-go on its own.

---

## Blockers, ranked by severity

### 1. [SEV-1] Production is currently crashed on a known, allegedly-fixed OOM signature

**Evidence:**
```
$ railway status
askmukthiguru-8119b0e8
    status:        ● Crashed
    deployment ID: 2d75a191-1d1c-420c-b4c5-e7340bec28ea

$ railway deployment list --service askmukthiguru-8119b0e8
2d75a191-... | CRASHED | 2026-09-12 01:53:46 +05:30

$ railway logs --service askmukthiguru-8119b0e8 --deployment 2d75a191-...
2026-09-11 20:41:14,690 [INFO] Loading encoder: BAAI/bge-m3 on device: cpu
Fetching 30 files:  67%|██████▋   | 20/30 [00:00<00:00, 34.65it/s]memory allocation of 67028844 bytes failed
...
Fatal Python error: Aborted
```
`docs/OOM_RAILWAY_INCIDENT.md:1-24` documents this exact stack trace as a prior incident, claims
`railway.json` memory was raised `4Gi → 6Gi` and `PYTHON_MEMORY_LIMIT_MB` `3584 → 5632` (both
confirmed present in current repo/env), but line 12 of that doc admits: *"redeploy (`railway up`)
to confirm the fix — deploy is gated by this environment's permission classifier, needs manual
approval."* That redeploy evidently never happened, or happened and still crashes — either way,
the service is crashed on this signature today, not hypothetically.

**A second, unresolved wrinkle in the same crash:** the log shows `BAAI/bge-m3` fetching **30
files over the network** at runtime ("Fetching 30 files"). `Dockerfile.railway:53` pre-caches a
different, much smaller repo at build time — `gpahal/bge-m3-onnx-int8` (the ONNX INT8 quantized
model) — plus only the `BAAI/bge-m3` **tokenizer**, not the full 30-file sentence-transformers
repo. A 30-file network fetch at container startup means either `EMBEDDING_BACKEND` isn't
resolving to `onnx_int8` at runtime (it's absent from `railway variables --kv` for this service —
present only as a Dockerfile `ENV` default, `Dockerfile.railway:81`) or `embedding_service.py`'s
onnx path is falling back to the full model. `OOM_RAILWAY_INCIDENT.md:11` already looked at a
revision-mismatch theory and ruled it out without finding the real cause — **this is unresolved,
and it's the direct trigger of the OOM abort.** Off-limits to me (`backend/services/embedding_service.py`
is owned by another agent) — flagging, not fixing.

**Smallest fix:** confirm `EMBEDDING_BACKEND=onnx_int8` is actually set (not just a Dockerfile
default) via `railway variables set EMBEDDING_BACKEND=onnx_int8 --service askmukthiguru-8119b0e8`,
then redeploy and watch the crash log for whether it still fetches 30 files. If it does, the bug is
in the runtime encoder-selection path, not the env var — hand back to the embedding_service.py owner.

---

### 2. [SEV-1] Reproduced container wedge has no Railway-side recovery path

**Evidence (from the coordinator, reproduced locally, root cause owned elsewhere — I'm assessing
the deployment consequence only):**
```
docker ps    : mukthiguru-backend  Up 5 hours (unhealthy)
curl /api/health -m 10  ->  exit 000, hung the full 10s (no response)
docker stats : mem=4.124GiB/6GiB (68.74%)  cpu=3.73%  pids=266
last log line: AUDIT POST /api/chat -> 200 (187.863s)
then: Exception ignored in audit hook: / MemoryError: / <total silence>
```
266 PIDs plus a `MemoryError` inside a sync audit hook matches the documented L-DOCKER-18 pattern
in root `CLAUDE.md` (Root `CLAUDE.md`, "FastAPI Async Dependency Invariant") almost exactly: a
sync `Depends(...)` callable forces Starlette through AnyIO's threadpool
(`run_in_threadpool`/`glibc` thread-stack allocation), and under load that exhausts before the
process runs out of heap — memory sits at 69%, CPU at 3.7%, it's blocked, not overloaded.

**Why Railway would not catch this — answering the three questions directly:**

1. **Does Railway restart on this?** `railway.json:11-21` (repo HEAD) declares
   `healthcheckPath: /api/healthz`, `healthcheckTimeout: 330`, `restartPolicyType: ON_FAILURE`,
   `restartPolicyMaxRetries: 5`. `restartPolicyType: ON_FAILURE` restarts on **process exit with a
   non-zero code** — a wedged-but-still-running event loop (open socket, no exit) never triggers
   it. There is no separate, continuously-polled liveness-probe field in Railway's schema the way
   Kubernetes has one; `healthcheckTimeout` is a single deploy-time value, not a recurring
   interval — consistent with Railway healthchecks being a **rollout gate** (decide whether to cut
   traffic to a new deployment during the `overlapSeconds`/`drainingSeconds` window) rather than an
   ongoing liveness prober. **I could not find, in this repo or in `railway.json`'s schema, any
   config that re-checks an already-healthy, already-live deployment on a timer.** Marking this
   **unverified against Railway's actual runtime behavior** (I don't have platform-internals
   visibility) — but the static config gives no evidence FOR continuous re-polling, and the
   observed 5-hour local wedge only ended because `autoheal` (an external, Docker-only watchdog)
   intervened. Treat "no automatic recovery on Railway" as the operative assumption until Railway
   support confirms otherwise.

2. **Would a hanging (not erroring) health endpoint even be seen?** `start_railway.py:200-224`
   (the `/api/healthz` handler) answers **inside the wrapper's own coroutine**, doing no I/O — just
   `time.monotonic()` comparisons and a direct `send()`. Critically, it runs on **the same single
   asyncio event loop** as everything else (`WEB_CONCURRENCY=1`, one uvicorn worker, the wrapper
   *is* the top-level ASGI app and only proxies non-healthz paths to `_real_app`,
   `start_railway.py:230-238`). If the threadpool exhaustion also starves or freezes that single
   event loop — which the observed "total silence, all logging stopped" strongly suggests, since
   even the wrapper's own 5-second heartbeat pump (`start_railway.py:127-134`) would stop
   incrementing `_last_heartbeat` under a fully frozen loop — then `/api/healthz` **hangs instead
   of returning 503**, exactly matching the reproduced `/api/health` behavior (hung the full 10s,
   exit code 000, not an HTTP error). A TCP-connect-and-wait healthchecker sees an open connection
   with no response, which most platforms treat as a slow app, not a down one, until their own
   timeout — and per point 1, it's unverified whether Railway is even still asking at that point.

3. **Railway equivalent of `autoheal`?** None found. `docker-compose.yml:697-712` runs
   `willfarrell/autoheal:latest`, polling Docker's `unhealthy` status every 10s
   (`AUTOHEAL_INTERVAL=10`) and restarting the container externally — this is what actually
   recovers the local stack, not anything in the app or in `start_railway.py`. `railway.json` has
   no field for an external watchdog, and Railway offers no first-party feature by that name in
   this repo's configuration.

**Does the 20-concurrent pilot target hold up?** No. The wedge was reproduced at a concurrency
level the coordinator describes as "well inside" the documented 20-user target — i.e., inside
normal pilot load, not an adversarial stress test. `max_concurrent_chat=8` (`app/config.py:550`)
sheds anything above 8 concurrent with a graceful `503`, but the wedge was triggered at or below
that same order of magnitude, and its failure mode is categorically worse than shedding: shedding
is visible and recoverable per-request; the wedge is silent, serves nothing, and (per point 1)
probably doesn't self-heal on Railway at all. A pilot running at its documented target concurrency
is one long conversation away from a silent full outage with no auto-recovery.

**Smallest fix:** not mine to make (root cause is owned elsewhere, and `backend/app/main.py`,
`backend/app/core/threading_config.py` are both off-limits to me). For the deployment side
specifically: until the threadpool-exhaustion root cause is fixed, either (a) confirm with Railway
support/docs whether they run a continuous liveness re-check independent of the deploy-time
`healthcheckTimeout`, or (b) add an external watchdog equivalent to `autoheal` — e.g. a cheap
second Railway service or a scheduled Railway cron job that curls `/api/health` on an interval and
calls `railway service restart` on failure. Either is a real fix; a $25/mo deploy today has neither.

---

### 3. [SEV-1] Live graph database is Neo4j, not Memgraph — contradicts the documented architecture

**Evidence:**
```
$ railway status
All resources
    Services
      - gb-neo4j-railway-template: ● Online

$ railway variables --service askmukthiguru-8119b0e8 --kv | grep -i neo4j
NEO4J_URI=<redacted>      NEO4J_USER=<redacted>      NEO4J_PASSWORD=<redacted>
NEO4J_server_memory_heap_initial__size=<redacted>
NEO4J_server_memory_heap_max__size=<redacted>
NEO4J_server_memory_pagecache_size=<redacted>
# no MEMGRAPH_* variable exists anywhere on this service or on gb-neo4j-railway-template

$ railway variables --service gb-neo4j-railway-template --kv | grep -i railway_neo4j
RAILWAY_NEO4J_IMAGE_TAG=<redacted>
```
Root `CLAUDE.md`'s "Graph Database Architecture & Memgraph Migration Decision" section documents
a completed migration to `memgraph/memgraph-mage:latest` specifically to fix Neo4j's "700MB to
1.5GB+ RAM idle/under load" JVM footprint, and says the Railway deploy should provision Memgraph
with `NEO4J_URI="bolt://memgraph.railway.internal:7687"`. The **actual live Railway environment**
has a service literally named `gb-neo4j-railway-template` (a Railway Neo4j template, JVM), wired
via `NEO4J_server_memory_heap_*`/`pagecache_size` — Neo4j-specific config keys that don't exist for
Memgraph — and the runtime log for the crashed deployment confirms it's really talking to Neo4j:
`"This Neo4j instance does not support creating databases. Try to use Neo4j Desktop/Enterprise..."`
is a Neo4j-Community-specific message.

`deploy_railway.sh:127-152` *does* default `GRAPH_DB="${GRAPH_DB:-memgraph}"` and would provision
Memgraph on a fresh run — so the script itself is not stale, but whatever produced the current live
topology (a manual dashboard action, an old run before the migration decision, or a fallback path
inside the script silently taking the `railway deploy --template memgraph` failure branch and
falling through) left Neo4j live. Either way: **the memory-footprint benefit CLAUDE.md cites as
the reason for the migration (Memgraph's ~60-100MB vs. Neo4j's 700MB-1.5GB+) is not real on the
current live deployment**, and that matters directly for point 5 below.

**Smallest fix:** this is a Railway state fix (add memgraph service, migrate NEO4J_URI, decommission
`gb-neo4j-railway-template`), which is out of scope for "prepare only" — flagging for the owner to
execute deliberately, not something to paper over in docs.

---

### 4. [SEV-2] Celery worker is live in production, not opt-in-paused

**Evidence:**
```
$ railway status
Services
  - celery-worker: ● Online

$ railway variables --service celery-worker --kv | grep SERVICE_TYPE
SERVICE_TYPE=<redacted>   # present; celery-worker's start_railway.py branch only runs when this is set
```
`deploy_railway.sh:355-363` and `railway-worker-pause`/`railway-worker-resume` in `Makefile:239-245`
both frame the Celery worker as opt-in, off by default, specifically to protect the $25 ceiling.
The live environment has it running continuously right now (`Online`, last deploy `SUCCESS`). This
is a live, unaccounted-for compute cost against the $25 budget that the "prepare" documentation
doesn't currently reflect as active.

**Smallest fix:** `make railway-worker-pause` (a documented, existing target — not something I ran,
since it mutates Railway state) once the owner confirms the worker isn't needed for pilot traffic.

---

### 5. [SEV-2] Memory envelope: cannot be sized confidently, and the one real data point is bad

The brief asks whether backend + graph DB + Qdrant + Redis fit a $25 Railway plan. I can't give a
clean sum — Railway's Pro plan bills usage, not a shared pool, so this isn't "do N services fit in
one box," it's "does each service's actual footprint keep total usage under $25/mo." The one
concrete measurement available is bad: the backend alone aborts with a literal `malloc` failure
during startup model-loading (Blocker 1), before the container ever reaches steady state, on a
container declared to have a 6Gi cap. `docs/OOM_RAILWAY_INCIDENT.md` frames this as a soft-limit
(`PYTHON_MEMORY_LIMIT_MB`, `RLIMIT_DATA`) vs. hard-cap (`railway.json` `deploy.limits.memory`)
collision, already "fixed" on paper — and it's still crashing. Until that's actually confirmed
resolved by a real successful boot, there's no trustworthy peak-memory number to size a budget
against. Separately, Blocker 3 means whatever number CLAUDE.md cites for the graph DB (Memgraph's
capped 512MB `--memory-limit=512`, `docker-compose.yml:41`) is not what's actually running — Neo4j
JVM defaults, unknown live values (deliberately not printed), are.

**Smallest fix:** get one clean successful boot (fix Blocker 1), read `docker stats`-equivalent
Railway metrics for the actual steady-state RSS, then re-run this sizing question with a real number.

---

### 6. [SEV-3] `FORWARDED_ALLOW_IPS` — set, but value unverifiable from here

`FORWARDED_ALLOW_IPS` **is present** in `railway variables --kv` for `askmukthiguru-8119b0e8` (name
only — per instructions, values are never printed). `start_railway.py:339-361` still hard-fails
startup (`raise SystemExit(1)`) if it's unset or `"*"`, and `app/config.py:1701-1705` independently
rejects a wildcard in production via `pydantic` validation. Since the crashed deployment's log shows
it dying during model load — **before** reaching the uvicorn startup block that checks this
(`start_railway.py`'s `if __name__ == "__main__":` path runs the ASGI app which does the FastAPI
lifespan first; the `forwarded_allow_ips` check happens only when launching `uvicorn.run(...)`,
i.e., before the process is *started*, not blocked by lifespan) — I can't confirm from these logs
whether the value would actually pass validation. Given the variable is present and the two
independent guards (`start_railway.py` + `config.py`'s pydantic validator) both actively reject a
wildcard, this is the one item on the CLAUDE.md gotcha list I'd call **likely fine**, not a blocker
— but genuinely unverified since I can't see the value.

---

### 7. [Informational, not a blocker] Live deployed config lags repo HEAD

`railway status --json`'s active-deployment manifest for the last deployed commit
(`47bec786...`, 3 commits behind current HEAD `1216eaa8`) shows `overlapSeconds: 120`,
`drainingSeconds: 60`, `healthcheckTimeout: 120` — all older values. Current repo `railway.json`
has `overlapSeconds: 45`, `drainingSeconds: 30`, `healthcheckTimeout: 330`, with a comment
(`_budget_note`) explaining the 45s change specifically cuts the dual-replica memory-burst window
during deploys by >60%. **None of that improvement is live yet** — expected, given no deploy has
happened, but worth noting: today's actual risk profile (if someone deployed right now without
this file's other fixes) is the *older*, riskier overlap window, not the one documented as current
in CLAUDE.md. Not a blocker on its own; resolves itself on the next deploy.

---

## What's verified clean

- **`git diff --check`**: exit 0, clean. No whitespace/conflict-marker issues in the working tree.
- **Full regression suite**: `./.venv/bin/pytest tests/ -k "not integration"` from `backend/` →
  **1 failed, 4328 passed, 6 skipped, 75 deselected, 3 warnings, 200.69s**. Re-ran fresh this
  session; matches the count given in the brief exactly, no drift from other agents' concurrent
  edits. The one failure is `tests/test_repo_layout.py::test_ops_script_trees_do_not_share_filenames`
  — a duplicate `canonicalize_teacher_aliases.py` in both `scripts/ops/` and
  `backend/scripts/ops/`, deletion blocked by permissions per the brief, owner-tracked, not mine to
  fix.
- **Celery ingestion worker default-off in code**: `start_railway.py` only branches into the
  Celery-worker code path when `SERVICE_TYPE=celery` is explicitly set
  (`start_railway.py:260,283`) — nothing in `app/config.py` auto-enables it, confirming the
  *code's* default is genuinely opt-in. (The live environment has it on anyway — see Blocker 4 —
  but that's an operator action, not a code defect.)
- **`memory/okf/` shipped in both Dockerfiles**: `backend/Dockerfile.railway:65` and
  `backend/Dockerfile:77` both `COPY memory/ ./memory/` — the CLAUDE.md invariant about OKF
  injection silently returning zero documents in the image holds.
- **Required env vars present** (names only, confirmed via `railway variables --kv` on the live
  service — never printed values): `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`,
  `QDRANT_URL`, `REDIS_URL` (assembled), `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD`,
  `IS_PRODUCTION`, `FORWARDED_ALLOW_IPS`, `WEB_CONCURRENCY`, `JWT_SECRET`. **Not present**:
  `EMBEDDING_BACKEND`, `RERANKER_BACKEND` (relying on Dockerfile `ENV` defaults — see Blocker 1),
  any `MEMGRAPH_*` variable (see Blocker 3), `QDRANT_API_KEY` (unclear if Qdrant's Railway
  deployment requires one on the internal network — not chased further, low priority).
- **`FORWARDED_ALLOW_IPS` guard code itself**: confirmed present and active in two independent
  places (`start_railway.py:339-361`, `app/config.py:1701-1705`) — see item 6 above for why the
  live value can't be confirmed from here.

---

## Bottom line

Two SEV-1s stand on their own regardless of anything else: production is crashed right now on a
"fixed" OOM signature that clearly isn't fixed, and the reproduced threadpool-exhaustion wedge has
no Railway-side recovery path (`autoheal` is Docker-only, `restartPolicyType: ON_FAILURE` doesn't
fire on a hang). Add a third: the live graph DB is Neo4j, not the Memgraph the whole memory-budget
story in CLAUDE.md is built around. None of these are close calls, and none are fixed by anything
in `deploy_railway.sh`/`railway.json`/`start_railway.py` alone — they need the embedding-service and
threading owners to land fixes, and someone with Railway write access to reconcile the graph DB and
pause the worker, before this is worth a `railway up`.

**No-go until:** (1) a real successful boot with no OOM abort, confirmed by logs, not by re-reading
a doc that says it's fixed; (2) either Railway confirms continuous healthcheck re-polling with
restart-on-hang, or an external watchdog is added; (3) the graph DB is actually Memgraph, or the
memory story in CLAUDE.md is corrected to Neo4j's real numbers and re-budgeted.
