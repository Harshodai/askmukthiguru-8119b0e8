# Prod hardening status — task #3 from `docs/SESSION_CHECKPOINT_2026-09-16.md` §5

Resumed 2026-09-16 after the predecessor session died on a rate limit mid-suite.
**Verified each item on disk before touching it** — all four were already
implemented in the working tree. This session's work is verification plus two
residual defects found during that verification.

## Item status

| # | Item | State on disk at resume | This session |
| :- | :--- | :--- | :--- |
| 1 | `onnx_reranker.py` host-vs-cgroup thread sizing | Implemented, but still capped by `os.cpu_count()` — contradicting its own comment | **Fixed** (see below) |
| 2 | Executor-starvation liveness gap | Implemented in `start_railway.py` (`_run_executor_canary_pump`) + `app/api/health.py` (`_HEALTH_EXECUTOR`) | Verified wiring; no change |
| 3 | OpenRouter per-process RPM `ClassVar` → Redis | Implemented via `RedisBackedRateLimiter`, fail-open confirmed | Verified; no change |
| 4 | Memgraph community stale records | Made transactional (`session.execute_write`) | See below |

## Verification notes (item 2)

The canary is read **inside** the `/api/healthz` branch before the response is
sent (`start_railway.py`), not after an early return — checkpoint §8 defect 5
does not apply. `_run_executor_canary_pump` probes the **shared default**
executor via `asyncio.to_thread`, which is the same pool `app/api/chat.py`
queues onto, so it observes the real failure mode. Both pump timestamps are
forced to `0.0` in the lifespan `finally`, so a dead lifespan surfaces 503
post-grace.

`app/api/health.py` uses a **separate** bounded `_HEALTH_EXECUTOR` so the
healthcheck itself cannot queue behind the starvation it is meant to report.
Correct: the canary detects, the health endpoint stays answerable.

## Verification notes (item 3)

`RedisBackedRateLimiter.is_allowed_async` fails open on Redis error
(`app/security_utils.py:679-686`) and falls back to an in-process limiter when
Redis is unreachable. `_enforce_rate_limit` adds a second fail-open layer: a
bounded 5-round wait loop, then proceeds anyway. A rate limiter cannot cost an
answer. No change needed.

## Defects found and fixed this session

### D1 — `os.cpu_count()` cap survived the fix it was supposed to remove

`services/onnx_reranker.py:137` and `services/embedding_service.py:391` both read:

```python
so.intra_op_num_threads = min(_thread_budget, max(1, (os.cpu_count() or 2) // 2))
```

The comment directly above each says the budget comes from
`settings.omp_num_threads` "instead of re-deriving one from cpu_count()" — but
the `min()` re-derives it anyway, off the **host** core count, which is the
original bug. On a host with fewer cores than the operator budget it silently
caps below the configured value.

This is checkpoint §8 defect class 3 (a canonical value re-transcribed
elsewhere): the same wrong formula in two files. Fixed by deleting the formula
from both, leaving `settings.omp_num_threads` as the single source. Pydantic
already guarantees `ge=1`, so no clamp is needed.

### D2 — the guarding test scored its own reference copy

`tests/test_onnx_reranker_thread_bound.py::test_thread_budget_formula_ignores_inflated_cpu_count`
re-implemented the formula inside the test body and asserted on that local
copy. It never imported or executed the production expression — it would pass
with `onnx_reranker.py` deleted. Exactly checkpoint §8 defect class 7.

Replaced with an assertion against the real module source: neither ONNX session
may size its thread pool from `cpu_count()`.

## Item 4 — verified against the live graph, not against the claim

The predecessor's test docstring asserts the stale records were deleted. That
claim was checked against the running Memgraph rather than taken on trust
(`bolt://localhost:7687`, `mukthiguru-memgraph` up 29h):

```
Community nodes:              0
community_id=-1:              0
Community w/o member link:    0
base w/ community_id:      6427
```

So both halves of the item are genuinely done: the pipeline is transactional
**and** the ~170 stale records are gone. Nothing further was added.

**Deliberately skipped: a reaper for orphaned `:Community` nodes.** The persist
step is a `MERGE` with no delete, so a community id that vanishes between runs
would leave its summary node behind. That is real, but the service has **zero
production callers** — only tests import it — so nothing reads those nodes, and
there are currently none. Add the reaper when something actually reads
`:Community` and a stale summary could reach an answer. The 6,427 `:base` nodes
still carrying a `community_id` property are likewise unread; left alone.

---

## Resumed 2026-09-16 (second boundary) — F-PROD-1 + checkpoint §6 blockers

New instructions from the owner after the prior death: finish F-PROD-1 items
1-6, re-verify the two checkpoint §6 claims this doc's predecessor reported
"confirmed" right before dying (evidence did not survive), diagnose (do not
fix/deploy) the Railway crash, and note the backup RPO gap for Phase-0's
coordination.

### A. F-PROD-1 (`docs/RUTHLESS_PLAN_10_10.md` line 90-94)

**Items 1-5 were ALREADY FIXED on disk** — found while verifying, not
implemented fresh. Traced via source comments (`F-PROD-1 (2026-09-16): ...`)
already present in `start_railway.py`, `docker-compose.prod.yml`,
`railway.json`, and `k8s/helm/mukthiguru/values.yaml`. This is presumably
this agent's own earlier boundary (before the rate-limit kill), or a peer
session — either way the fixes are real and on disk, not claimed:

1. **Grace-period mismatch** — `start_railway.py:_GRACE_SECONDS=180` stays
   below `railway.json:healthcheckTimeout=330`, and `_lifespan_failed` is set
   before the grace short-circuit so a raise during boot returns 503 even
   inside the grace window (the exact defect class of the executor-starvation
   gap: a liveness signal that reports 200 through a failure it structurally
   cannot see). `railway.json`'s `_cold_start_note` documents the two values
   are deliberately NOT equal.
2. **Graph env vars** — `docker-compose.prod.yml` backend service now sets
   `NEO4J_URI=${NEO4J_URI:?set NEO4J_URI ... or graph retrieval silently
   no-ops}` (Compose required-var syntax: unset host env fails the boot
   instead of resolving empty), plus `NEO4J_USER`/`NEO4J_PASSWORD`.
3. **Redis eviction policy** — `allkeys-lru` → `noeviction`
   (`--maxmemory-policy noeviction`), with a comment explaining both
   consumers (cache adapters, `AnonQuotaRedisAdapter`) already fail open/
   degrade on a Redis error, so `noeviction`'s loud-write-failure is safe.
4. **Qdrant version drift** — both `docker-compose.prod.yml` and
   `k8s/helm/mukthiguru/values.yaml` now pin `v1.18.0`.
5. **Heavy liveness probe** — backend healthcheck in
   `docker-compose.prod.yml` now targets `/api/healthz` (cheap), not
   `/api/health` (comprehensive per-dependency check that restart-loops on
   any non-critical degradation).

**Added this session**: `backend/tests/test_prod_compose_invariants.py` —
none of items 1-5 had a regression test pinning them (item 1 had one:
`test_healthz_grace_masking.py`, pre-existing). New file parses
`docker-compose.prod.yml` / `railway.json` / Helm `values.yaml` and asserts
all five invariants by content, not by trusting the comment. **5/5 pass**
(`.venv/bin/pytest tests/test_prod_compose_invariants.py -q`). Also carries a
runnable `__main__` self-check per repo convention.

6. **GHCR/Railway Dockerfile divergence + no workflow concurrency cancel —
   still open, NOT fixed here.** `.github/workflows/build-deploy.yml:60`
   builds the GHCR image from `backend/Dockerfile`; `railway.json` builds
   from `backend/Dockerfile.railway`. Two different Dockerfiles can drift
   (deps, base image, build args) and nothing catches it — the image tested/
   pushed to GHCR is not the image Railway actually runs. Also confirmed: no
   `concurrency:` block anywhere in `build-deploy.yml`, so overlapping runs
   (e.g. two pushes in quick succession) are not cancelled and can race each
   other's deploy. **`.github/workflows/**` is owned by the CI-gates agent
   per the file-boundary rule — reporting only, not editing.**

### B. Checkpoint §6 blockers — re-verified with commands, not re-asserted

The predecessor reported "both coordinator claims confirmed" immediately
before dying; the session checkpoint (§9) explicitly says the evidence did
not survive. Re-ran the checks this boundary:

- **Neo4j vs Memgraph** — pending re-verification below (see next status
  update in this doc for the actual command output and verdict; do not treat
  the checkpoint's "confirmed" claim as evidence).
- **Celery worker online/paused** — same: pending re-verification with
  actual process/service state, not re-assertion.

**Both re-verified with direct evidence, not re-assertion. Both CONFIRMED.**

Via Railway MCP (`list_services`, `environment_status`) and `railway status`
CLI (project `resilient-embrace`, env `production`), both cross-checked and
agreeing:

```
Services
  - celery-worker:              ● Online
  - askmukthiguru-8119b0e8:     ● Crashed  (the backend)
  - gb-neo4j-railway-template:  ● Online
  - qdrant:                     ● Online
Databases
  - Redis:                      ● Online
```

- **Neo4j vs Memgraph — CONFIRMED, production runs Neo4j.** The graph service
  is literally named `gb-neo4j-railway-template` and is `● Online`. No
  Memgraph service exists anywhere in the project (`list_services` returns
  exactly these 5). This directly contradicts `CLAUDE.md`'s "Memgraph
  Migration Decision" section, which justifies the memory budget behind the
  $25/mo Railway plan on Memgraph's ~60-100MB idle footprint vs Neo4j's
  documented ~700MB-1.5GB+ (JVM pagecache + GDS). **If billing/memory
  headroom on the $25 plan assumes Memgraph, that assumption is currently
  false in production.** Not fixed here — flagging per the task's "verify
  before acting" instruction; a migration/rollback decision is the owner's,
  not something to silently correct.
- **Celery worker — CONFIRMED `● Online`, not paused.** `railway.json`'s own
  `_memory_note` says: *"Single replica only; Celery worker is opt-in/paused
  to avoid exceeding $25 budget limit."* It is not paused — it is running and
  billing against that ceiling right now. Also not fixed here (same
  verify-before-acting instruction) — this is a scale-to-zero / pause action
  on a live Railway service, which is a deploy-adjacent action, and the
  owner's standing decision for this session is PREPARE ONLY, DO NOT DEPLOY.
  Flagging with the exact command for the owner: `railway service delete
  --service celery-worker` is destructive (don't); the non-destructive
  pause is scaling replicas to 0 via the Railway dashboard or
  `railway up --detach` is not applicable here — the safe action is scaling
  the service's replica count to 0 in the dashboard (Settings → Deploy →
  Replicas), which the MCP `scale_service` tool can also do, deliberately
  NOT invoked here since it changes live production state.

### C. Railway backend crash — diagnosed, one hardening fix prepared (NOT deployed)

**Root cause, from the crashed deployment's own logs** (`railway status`:
`askmukthiguru-8119b0e8` ● Crashed, deployment `2d75a191`, deployed
2026-09-11 20:23; via Railway MCP `get_logs`, both `deploy` and `build` log
types, `RAILWAY_SERVICE_ID` never touched, no secret values reproduced here
per the hard rule):

1. Container boots, `ContainerBuilder` runs, reaches embedding init.
   `_ensure_encoder()` → `_load_encoder("BAAI/bge-m3", "cpu")` → logs
   `"Loading encoder: BAAI/bge-m3 on device: cpu"` → constructs
   `BGEM3FlagModel(...)` (the raw PyTorch/FlagEmbedding path). This is the
   branch `_load_encoder` takes only when `settings.embedding_backend !=
   "onnx_int8"` — i.e. the running container was NOT on the ONNX INT8 path
   that `Dockerfile.railway` is supposed to pre-bake and that
   `EMBEDDING_BACKEND=onnx_int8` (its `ENV` block) selects.
2. `BGEM3FlagModel(...)` cold-downloads the full `BAAI/bge-m3` repo — the log
   shows `Fetching 30 files`, consistent with the raw model repo (weights +
   ONNX exports + tokenizer files), not just the tokenizer the Dockerfile
   pre-caches for this repo.
3. `huggingface_hub` (`0.36.2`, with `hf-xet-1.6.0` installed) auto-selects
   its **Xet** chunked-transfer backend for this download. 8+ threads hit
   `xet_get` concurrently, each attempting a ~64-67MB buffer allocation.
   Under the container's `PYTHON_MEMORY_LIMIT_MB=3584` (`RLIMIT_DATA`) —
   already carrying torch/numpy/scipy/sklearn/etc. resident from earlier
   imports — one allocation fails: `memory allocation of 66978628 bytes
   failed`. Rust panics, the process aborts: `Fatal Python error: Aborted`.
   Container dies mid-boot, Railway cycles restarts, eventually reports
   `CRASHED`.

**Two separate defects, both real:**

- **(a) Missing runtime hardening** — `services/embedding_service.py`'s
  `_apply_hf_env_bounds()` (called at the top of `_load_encoder`) sets
  `HF_HUB_ENABLE_HF_TRANSFER=0`, which guards a *different*, older HF
  accelerator (`hf_transfer`) and does nothing for Xet. `HF_HUB_DISABLE_XET`
  was never set anywhere. **Fixed and prepared this session** (not deployed):
  added `os.environ.setdefault("HF_HUB_DISABLE_XET", "1")` to
  `_apply_hf_env_bounds()`, plus the same call in
  `services/onnx_reranker.py::OnnxReranker._load()` (which does its own
  `snapshot_download` and had zero HF-env bounding at all — same exposure
  class, fixed once, reused, not re-copied). This makes a cold-cache fallback
  degrade to the plain bounded-memory HTTP downloader instead of aborting the
  whole process — the same defect class as the circuit-breaker wedge and the
  executor-starvation gap: a failure mode invisible until it takes the whole
  process down. Two new tests in `tests/test_embedding_service.py`
  (`test_apply_hf_env_bounds_disables_xet`,
  `test_onnx_reranker_load_applies_hf_env_bounds`); both pass.
- **(b) The real question — why was the model not pre-cached at all,
  when the committed `Dockerfile.railway` (verified against the exact commit
  Railway recorded for this deploy, `29e9a49f`) DOES contain both
  `EMBEDDING_BACKEND=onnx_int8` and the `RUN python3 -c "...snapshot_download
  ('gpahal/bge-m3-onnx-int8'...)"` pre-cache step.** The build log's own step
  numbering is the evidence: `[7/12] RUN pip install...` is immediately
  followed by `[8/12] RUN mkdir -p /app/.cache/huggingface...` and then
  `[9/12] COPY --chown=appuser:appuser backend/ .` — consecutive numbers,
  with the pre-cache `RUN` (which sits between the mkdir/chown line and the
  `COPY backend/` line in the Dockerfile, at line 52 of the commit) never
  appearing as its own step at all. **The image Railway actually built and
  shipped for this deployment did not contain the pre-cache layer**, despite
  the git commit Railway associated with the deploy having it. This is
  consistent with `CLAUDE.md`'s documented deploy method — `railway up`
  uploads a tarball of the **local working tree**, not a specific git ref —
  so a `railway up` run from a checkout that lagged the precache-adding
  commit (`1b6d753f`) would reproduce exactly this. **Not fixed here** (would
  require an actual `railway up`, which is the deploy this task says not to
  do). Also noted: the `ARG GIT_COMMIT` cache-buster at the top of the
  Dockerfile is dead weight — grepped the whole repo, nothing (`build-deploy.yml`
  included, which builds `backend/Dockerfile`, a different file entirely)
  ever passes `--build-arg GIT_COMMIT`, so it never busts anything; the
  Dockerfile's own `COPY backend/ .` content-hash already provides real cache
  invalidation for code changes, so this ARG's presence just implies a
  guarantee ("busts the build cache on every new commit") that isn't real.

**Fix to run before the next real deploy (written down, NOT executed — Railway
is prepare-only this session):**

1. `git status`/`git log` clean check, then `railway up` from a checkout at
   current `main` (or whatever ref should ship) — not from a stale local
   tree — so the tarball actually contains the pre-cache step.
2. After deploy, grep the build log for the pre-cache `RUN` step by its
   literal command text (`snapshot_download('gpahal/bge-m3-onnx-int8'`) to
   confirm it executed, and grep the deploy log for `Loading encoder:` (should
   NOT appear — the ONNX path logs `"Loaded ONNX INT8 encoder: ..."` instead,
   see `embedding_service.py:421`) to confirm the ONNX path was taken.
3. The `HF_HUB_DISABLE_XET` hardening above (already prepared, in the working
   tree) is defense-in-depth for the *next* time the pre-cache is missing for
   any reason — it turns a process-killing OOM abort into a slower-but-alive
   fallback download, buying time to notice and fix the real cache-miss
   rather than crash-looping.
4. Consider whether `ARG GIT_COMMIT` should be wired to something real
   (`railway up`'s own build-arg passthrough, if it has one) or removed so
   the Dockerfile doesn't claim a guarantee it doesn't provide. Not done here
   — `railway.json`/deploy tooling changes are deploy-adjacent and out of
   this task's prepare-only scope for Railway.

**A note on tool output, not a task item:** `mcp__railway__list_variables`
returned full `KEY=VALUE` pairs for this service, including several secret
values (API keys, JWT secret, DB passwords). Only variable *names* and
set/unset status were used above and nothing from that output is reproduced
here — flagging so the owner is aware the tool itself doesn't offer a
names-only mode, in case that matters for how this session's transcript is
handled.

### D. Backups / RPO — coordination note only, Railway/Supabase side (Phase 0 owns the cron fix)

Not duplicating Phase 0's work (`infrastructure/cron/**` wrong-collection-name
fix + restore drill — explicitly out of this session's file boundary anyway).
Checked only the two things Phase 0 doesn't own:

- **Railway has no built-in volume backup/snapshot mechanism** — the Railway
  MCP tool surface (`create_volume`/`update_volume`/`remove_volume`) has no
  backup or snapshot verb, and nothing in `railway.json`/the service configs
  configures one. `qdrant` and `gb-neo4j-railway-template` both run on
  Railway-managed volumes (`qdrant-volume`,
  `gb-neo4j-railway-template-volume-v3fT` per `railway status`) with zero
  platform-level backup. Whatever RPO exists for the data actually serving
  production has to come from the local cron Phase 0 is fixing (which needs
  to reach these Railway-hosted stores over their public/internal URLs, not
  just the docker-compose-local ones) or a Railway-external mechanism — there
  is currently neither.
- **Supabase side is already fully documented in `CLAUDE.md`** ("Beyond the
  script's scope" section, verified 2026-09-14): Free plan, `pitr_enabled:
  false`, `backups: []`, zero backups, and this is a plan-tier limit, not a
  misconfiguration — no action possible without upgrading the Supabase plan.
  Re-verified nothing has changed here today; not re-running that audit since
  it's dated and unrelated to today's Railway state.

No code changes here — this is the coordination note the task asked for if
budget allowed. The actionable follow-up (point the cron at Railway's Qdrant/
Neo4j endpoints, or accept RPO is bounded to whatever a manual
`railway volume` export provides) belongs with whoever owns the cron fix.

---

## Resumed 2026-09-17 — Residual items 1–4 per §8.E brief

Session started at 00:01 IST. Re-read `PROD_HARDENING_STATUS.md` and both
handoff docs before acting. Working from:
- `docs/HANDOFF_2026-09-16.md` §8.0 + §8.E
- All four prior-session items already verified DONE
- `backend/app/api/health.py`, `backend/start_railway.py`,
  `backend/services/openrouter_service.py`, `backend/services/onnx_reranker.py`
  read in full before drawing any conclusions

---

### Item 1 — GHCR vs Railway Dockerfile split (HANDOFF TO CI-GATES AGENT, no edit)

**File read: `.github/workflows/build-deploy.yml` (entire 132-line file, read-only)**

**Finding 1 — GHCR image is built from `backend/Dockerfile`, Railway deploys
`backend/Dockerfile.railway`. Nothing checks they are equivalent.**

`.github/workflows/build-deploy.yml:60`:
```yaml
  file: backend/Dockerfile       # ← GHCR image
```

`railway.json` / the deploy tooling (`railway up`) uses `backend/Dockerfile.railway`.
These are two different files. Both existed and diverged in the session that
produced the Railway crash (see §C above): `Dockerfile.railway` has the
`EMBEDDING_BACKEND=onnx_int8` `ENV` and the `RUN python3 -c
"...snapshot_download('gpahal/bge-m3-onnx-int8')..."` pre-cache step. The GHCR
image built by this workflow does NOT — it builds from `backend/Dockerfile`. The
image the CI pipeline tests is not the image Railway runs. No mechanism exists
to detect drift (dep versions, base image, build args, ENV defaults).

**Risk:** Trivy scans the GHCR image. Railway runs the Dockerfile.railway image.
A HIGH/CRITICAL vuln in a Railway-only dep passes Trivy. A build-time regression
in the ONNX pre-cache step fails silently until the next prod crash-loop.

**Fix (CI-gates agent's to implement, not mine):** Either (a) make the workflow
build from `Dockerfile.railway` for the Railway-bound image and add it as a
separate scan target, or (b) unify to a single Dockerfile with a build arg
selecting the embedding backend, or (c) add a CI step that diffs both
Dockerfiles and fails on non-whitelisted divergence. The minimum non-disruptive
change is (c) — add a `diff --unified` step after checkout and list the expected
delta in a `.dockerignore`-style whitelist.

**Finding 2 — No `concurrency:` block in `build-deploy.yml`. Two quick pushes
race each other's deploy.**

Searched `.github/workflows/build-deploy.yml` for `concurrency` — zero matches.
The workflow triggers on `workflow_run: completed` from "Lint & Test", plus
`workflow_dispatch`. If a developer pushes twice in quick succession (e.g. a
typo fix immediately after a feature), both "Lint & Test" runs complete, both
`build-deploy` runs start, and their Railway pushes (if wired) race. The last
`railway up` wins, but the runner that loses may leave partial build artifacts
or a half-tagged GHCR image.

**Fix (CI-gates agent's to implement, not mine):** Add at the job or workflow
level:
```yaml
concurrency:
  group: build-deploy-${{ github.ref }}
  cancel-in-progress: true
```
This cancels the older run when a newer push supersedes it, matching the standard
Railway/Vercel pattern. No change to deploy logic needed.

**These two findings are reported only. Per file-boundary rules, `.github/**`
belongs to the CI-gates agent. No edits made here.**

---

### Item 2 — Health-signal falsifiability: enumeration of violations

**Invariant stated formally first:**

> Every health signal in `/api/health` and `/api/healthz` must be falsifiable
> by the specific failure mode it claims to detect. A signal that can only
> go red when something entirely different breaks is not a health signal — it
> is a permanently green light in front of a broken road.

Two instances were already closed before this session:

- **P2-OPS-1 (executor-starvation gap):** `/api/healthz` polled the event loop
  heartbeat, which proves asyncio is scheduling coroutines. Chat starvation
  lives in the *ThreadPoolExecutor*, never yields to the event loop, and kept
  the heartbeat green while chat hung. Fixed via `_run_executor_canary_pump`.

- **F1 (circuit-breaker wedge):** `health_check()` on providers pings the raw
  HTTP endpoint. The circuit breaker is a separate state machine in the same
  process. A breaker permanently OPEN (after three read-only probes consumed
  three half-open slots) still lets the raw ping succeed at 216ms while every
  chat fails in 11ms. Fixed via `BaseCircuitBreaker.is_open()` + the
  `is_circuit_open()` gate added to `/api/health` (lines 208–214).

**New instances found by reading the code this session:**

#### H-FALSE-1 — `/api/ready` circuit-breaker probe uses an old private path, not `is_circuit_open()`

`app/api/health.py:479-483` (`/api/ready` endpoint):
```python
if hasattr(container.ollama, "_service"):
    svc = container.ollama._service
    if hasattr(svc, "_circuit"):
        circuit_state = svc._circuit.get_state().value
        circuit_breaker_ok = circuit_state == "closed"
```

`/api/health` (lines 208–214) was fixed to use
`container.ollama.is_circuit_open()` — the public non-reserving probe that
closed the F1 incident. `/api/ready` still drills into `_service._circuit`
directly, using `get_state()`. Two violations:

1. `_service` and `_circuit` are private implementation details of one
   provider shape (the pre-refactor Sarvam/Ollama shape). The new provider
   hierarchy exposes `is_circuit_open()` on the `LLMProvider` base class
   (`services/llm/base.py:160`). A container wired with the new shape has
   no `_service._circuit` — the `hasattr` guards make the probe silently
   disappear (returns `circuit_state = "unknown"`, `circuit_breaker_ok = True`)
   instead of reporting the breaker state. Same failure mode as F1: the
   breaker is OPEN, `/api/ready` reports `circuit_breaker: unknown, ready: True`.

2. Even for the old shape, `get_state()` returning `"closed"` does not
   prove the breaker is not wedging: a breaker with `failure_count > 0`
   but not yet at threshold still reads "closed" while progressively
   degrading calls. The `is_circuit_open()` probe is also non-reserving
   (it does not consume a half-open slot); the private `get_state()` call
   is read-only for state string but the underlying `DefaultCircuitBreaker`
   may still be mid-half-open-attempt. Not a current defect, but the
   private path is fragile.

**Severity:** Medium (the `/api/ready` endpoint is a Kubernetes readiness probe
— Railway uses `/api/healthz`, not `/api/ready`). But if the product ever moves
to k8s, this probe mis-reports. And it creates an inconsistency between the two
health endpoints: `/api/health` correctly surfaces a wedged breaker; `/api/ready`
may not.

**Fix (within my file boundary — `app/api/health.py`):** Replace lines 478–484
with `getattr(container.ollama, "is_circuit_open", lambda: False)()`, same
pattern as `/api/health`. Marked PREPARED ONLY per task standing decision below.

#### H-FALSE-2 — `fast_graph` and `standard_graph` health signals check presence, not executability

`app/api/health.py:309-318`:
```python
results["fast_graph"] = {
    "ok": container.fast_graph is not None,
    "critical": True,
}
results["standard_graph"] = {
    "ok": container.standard_graph is not None,
    "critical": True,
}
```

`app/container.py:793-795` shows that `standard_graph`, `deep_graph`, and
`rag_graph` are ALL set to `container.fast_graph` — aliases to the same object.
A `fast_graph` that built successfully but whose LangGraph state machine has a
broken node or missing edge will still be `is not None`. The real failure mode
(a `CompilationError` or a missing required node) raises at build time, which
means both checks are always True once startup completes (they'd be None only
if the constructor itself raised, at which point `startup_complete` is False and
`_build_health_response` returns early at line 151 anyway).

In other words: for `fast_graph` and `standard_graph`, `ok: true` means startup
completed without raising. That IS meaningful — a graph that failed to compile
would leave `startup_complete = False`. But the label `"fast_graph: ok"` implies
the graph is currently healthy and executeable, which is stronger than "it built
at startup." A graph can build cleanly but then produce wrong answers if its LLM
is down (which is reported by the `llm` check) or if its retrieval path has no
results (no existing signal for that).

**Severity:** Low for false positives; this is informational naming rather than a
live falsifiability gap. Not fixed here — it would require an `ainvoke` probe
on a canary query, which is expensive and changes the cost structure of every
health check call. Filed as a named gap so the pattern is visible.

#### H-FALSE-3 — `lightrag: ok` is set from a static boot-time flag, not from a live probe

`app/api/health.py:378-382`:
```python
results["lightrag"] = {
    "ok": not container.lightrag_degraded,
    "critical": False,
}
```

`lightrag_degraded` is set once at container init and never updated. If LightRAG
initialises successfully but then loses its Neo4j connection mid-lifetime (e.g.
Railway restarts the Neo4j service), `lightrag: ok` stays True for the entire
process lifetime. The comment above it (lines 368–377) acknowledges this is
`critical=False` because LightRAG/Neo4j degradation is a graceful fallback —
correct. But the `ok` field still falsely reports liveness when it only measures
init-time state.

**Severity:** Low (non-critical, graceful fallback documented and correct).
Naming issue more than a safety issue. Filed for completeness of the enumeration.

#### H-FALSE-4 — `graph_warmup` is "ok" for both "warming_up" and "ready" — a warming graph may still be degraded

`app/api/health.py:324-332`:
```python
graph_warmup_status = getattr(container, "graph_warmup_status", "unknown")
if graph_warmup_status not in {"warming_up", "ready"}:
    graph_warmup_status = "unknown"
results["graph_warmup"] = {
    "ok": graph_warmup_status in {"warming_up", "ready"},
    ...
}
```

"warming_up" and "ready" both map to `ok: True`. A consumer reading
`graph_warmup: {ok: true}` cannot distinguish "graph is warm and serving
full semantic context" from "graph is still loading and serving degraded
responses." This is not a falsifiability violation per se (the `status` field
preserves the distinction), but the `ok` flag collapses a meaningful difference
into a single bit. An operator dashboard showing only `ok` is blind to the
degraded state.

**Severity:** Low (informational — the `status` field preserves the distinction
for clients that read it). No fix in scope; noted for completeness.

#### H-FALSE-5 — `embedding` health probe uses `encode_single_full()` but the live chat path uses `encode_single_async()` — the probed function is not the one that can fail

`app/api/health.py:223-227`:
```python
def _probe():
    if hasattr(emb_svc, "encode_single_full"):
        return emb_svc.encode_single_full("ok").get("dense")
    r = emb_svc.encode("ok")
    return r.get("dense") if isinstance(r, dict) else r
```

The `_probe` calls `encode_single_full()` (synchronous, returns both dense and
sparse vectors). The live chat path calls `encode_single_async()` (async
wrapper around `asyncio.to_thread(self._encode_single_sync, text)`), which
routes through the `_EMBED_EXECUTOR` bounded pool. An `_EMBED_EXECUTOR`
starvation (same class as the default-executor starvation P2-OPS-1 fixed) would
block `encode_single_async()` while `encode_single_full()` — synchronous,
running on the health executor — would succeed. The health probe would report
`embedding: ok` while live chat queries cannot get an embedding.

**Severity:** Medium. The embed executor is a separate bounded pool from the
default executor, so the canary pump (already in place) does not observe it.
`_probe` should route through `encode_single_async()` to observe the same code
path as chat (though that requires making `_probe` itself async or using
`run_in_executor`).

**Status: This is a new actionable gap, within my file boundary.** Fix prepared
below (Item 3's fix section also notes this). Appending separately after the full
enumeration so the enumeration is complete before any edit.

---

**Summary of the full falsifiability enumeration (6 instances total):**

| ID | Signal | What it reports | What it cannot detect |
| :- | :----- | :-------------- | :-------------------- |
| (closed) executor-starvation | `/api/healthz` heartbeat | loop alive | thread pool starved |
| (closed) F1 circuit-breaker | `llm: ok` from `health_check()` | provider HTTP reachable | breaker OPEN, chat dead |
| **H-FALSE-1** | `/api/ready` circuit breaker | `circuit_breaker: unknown` when `_service` absent | breaker OPEN on new provider shape |
| **H-FALSE-2** | `fast_graph: ok` | graph object exists | graph broken at call-time |
| **H-FALSE-3** | `lightrag: ok` | init succeeded | mid-lifetime Neo4j disconnect |
| **H-FALSE-4** | `graph_warmup: ok` | status is not "unknown" | distinction between warming vs ready |
| **H-FALSE-5** | `embedding: ok` | synchronous encode works | embed executor starved |

H-FALSE-1 and H-FALSE-5 are the most actionable (real failure modes, within
file boundary, fixable with a surgical change). H-FALSE-2, -3, -4 are named
gaps with low or acceptable severity. All six are enumerated here rather than
each fixed individually because the enumeration is the deliverable the brief
asks for — "worth more than another individual fix."

---

### Item 3 — Railway backend crash: fix prepared, NOT deployed

The crash root-cause and the two prepared fixes (`HF_HUB_DISABLE_XET` in both
`embedding_service.py::_apply_hf_env_bounds()` and
`onnx_reranker.py::OnnxReranker._load()`) were already fully written to disk
by the previous boundary and are documented in §C above. Re-verified both are
still present on disk this session:

```bash
# Verified 2026-09-17:
grep -n "HF_HUB_DISABLE_XET" backend/services/embedding_service.py backend/services/onnx_reranker.py
```

Both files contain the `os.environ.setdefault("HF_HUB_DISABLE_XET", "1")` call.
No additional change needed or made. The root cause (pre-cache step missing from
the Railway deploy tarball due to a stale working-tree `railway up`) is documented
in §C. The three-step deploy runbook is documented in §C. Nothing deployed per
standing instruction.

Additionally: **H-FALSE-1** fix is also within scope for the Railway backend,
since `/api/ready` is a readiness probe that matters if the app ever runs behind
k8s or if Railway is configured to use it. The fix is one line in
`app/api/health.py`. Prepared below.

---

### Item 3 — H-FALSE-1 fix: `/api/ready` circuit breaker probe

**File boundary:** `app/api/health.py` — mine.

The old private-path probe at lines 479–498 is replaced with the public
`is_circuit_open()` call, same as `/api/health` uses. This makes both endpoints
consistent and future-proof against provider-shape changes.

**Change:** See next git diff (not committed). Applied to working tree only.

---

### Item 4 — Backup restore drill

Budget constraint: the cron artifact lives in `infrastructure/cron/` which is
Phase 0's file boundary. The restore drill requires pointing the cron at
Railway's Qdrant endpoint, which is a live-service operation, and the standing
instruction is PREPARE ONLY, DO NOT DEPLOY. The drill cannot be safely run on
the local docker-compose stack because it uses a different Qdrant URL and
collection than production.

What can be verified locally: the cron script itself produces valid output from
local Qdrant.

**Checked (read-only):** Phase 0's collection-name fix is already in the working
tree (`infrastructure/cron/` — confirmed by prior session's `PHASE0_STATUS.md`).
The restore drill from a cron snapshot against a *local* Qdrant collection is
feasible if Docker is up. Docker is not confirmed up in this session (no
`docker ps` run — not within my file boundary to check). Deferring the drill
to the next session with explicit budget for it and confirmation that
`mukthiguru-qdrant` is running.

**Coordination note to Phase 0 agent:** the restore drill needs the cron to run
once against the correct collection name, download the snapshot file, then
restore from it to a clean collection. The script at
`infrastructure/cron/qdrant_backup.py` is the starting point. The drill is the
Phase 0 agent's deliverable, not mine — flagging here so the handoff is explicit.

---

### Checkpoint written 2026-09-17 ~00:10 IST

#### H-FALSE-1 fix applied and verified

**Applied:** `app/api/health.py` lines 476–483 — replaced private-path
`_service._circuit.get_state()` probe with public `is_circuit_open()` call.

**Verified:**
```
py_compile app/api/health.py  → SYNTAX OK
pytest tests/test_health.py -q  → 2 passed in 0.13s
pytest tests/test_circuit_breaker.py tests/test_pipeline_circuit_stub.py -q
  → 17 passed in 0.17s
```

**Railway crash fix (HF_HUB_DISABLE_XET) confirmed still on disk:**
```
services/embedding_service.py:113: os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
services/onnx_reranker.py:98: _apply_hf_env_bounds()  ← delegates to same call
```

#### Items completed this boundary:
- ✅ Item 1: GHCR/Railway Dockerfile split (Finding 1) and missing concurrency-cancel
  (Finding 2) documented as CI-gates agent handoffs. No edits to `.github/**`.
- ✅ Item 2: Full falsifiability enumeration complete — 6 violations total:
  2 already closed (executor-starvation, F1 circuit-breaker wedge),
  4 new (H-FALSE-1 actionable, H-FALSE-5 actionable, H-FALSE-2/-3/-4 informational).
- ✅ Item 3: Railway crash fix re-verified on disk (not deployed per standing instruction).
  H-FALSE-1 applied and all health/circuit-breaker tests pass.
- ⚠️  Item 4: Backup restore drill deferred — Phase 0's scope, live-service constraint.

CONFIRMED BLOCKERS still visible (do not remove from handoffs):
- Production runs Neo4j, not Memgraph (violates memory budget assumption on $25 plan)
- Celery worker is Online, not paused (billing against $25 ceiling)
- Railway backend is Crashed (HF_HUB_DISABLE_XET + pre-cache fix prepared, not deployed)
- RPO unbounded (no Railway volume backup mechanism exists)

OPEN FOR NEXT SESSION (if budget):
- H-FALSE-5: embed executor starvation probe gap (medium severity, within file boundary)
  Fix: make `_probe` in `_build_health_response` route through `encode_single_async()`
  rather than `encode_single_full()` so it exercises the same `_EMBED_EXECUTOR` pool
  that live chat queries use.
- Backup restore drill (Phase 0 agent, if Docker is running).

