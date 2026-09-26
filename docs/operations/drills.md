# Production-readiness drills: first-person load test & backup/restore

Two prepared, non-executed drills. Neither has been run against the live
stack as of this writing — see each section's "status" line. Context:
root `CLAUDE.md` "Native model concurrency invariant", "SPOF & Replication
Policy", and "Backup caveat" sections.

## 1. First-person load test (`backend/scripts/ops/gate1_load_test.py --mode first-person`)

Extends the existing Gate 1 chat load test (`gate1_load_test.py`) with a
`--mode first-person` path that drives `POST /api/first-person/query`
instead of `/api/chat`, against the fixed bakeoff question set
(`~/mukthiguru_attribution_data/bakeoff_2026-09-25/questions.json`, 116
questions). It reuses `RequestResult`, `compute_percentiles`, and
`ContainerWatch` from the chat path rather than duplicating them.

**Status: prepared, not run for real.** A `--dry-run` was executed during
prep (config validation only, zero traffic) — see sample output below.

### When to run

Before enabling `first_person_route_enabled` in production, and after any
change to `services/first_person_pipeline.py`, `services/first_person_store.py`,
or the crisis-engine wiring the route shares with chat (`serene_mind`).

### How to run

```bash
cd backend

# 1. Dry run first — validates the question file and current settings, sends
#    no traffic at all. Safe to run anytime, including against a live stack.
.venv/bin/python scripts/ops/gate1_load_test.py --mode first-person --dry-run --sweep 1,8,32,64

# 2. Real sweep, in-process (no server needed) — the numbers in "Pass
#    criteria" below assume this invocation:
.venv/bin/python scripts/ops/gate1_load_test.py --mode first-person \
    --sweep 1,8,32,64 --container mukthiguru-backend

# 3. Real sweep against a live docker-compose stack instead of in-process:
.venv/bin/python scripts/ops/gate1_load_test.py --mode first-person \
    --sweep 1,8,32,64 --base-url http://localhost:8000
```

`--concurrency N` still works for a single level if you don't want the full
sweep. `--limit-questions N` caps the question set for a fast smoke run.
`--questions-file PATH` overrides the bakeoff set.

### Pass criteria

- **p95 ≤ 1000ms at concurrency 8** (checked specifically — root CLAUDE.md's
  concurrency invariant notes the crash that motivated `ContainerWatch` was a
  burst *below* the configured ceiling, not the highest level tested).
- **Zero 5xx responses** at any concurrency level.
- **Zero container restarts** and peak memory under budget (`ContainerWatch`,
  shared with the chat gate; skips gracefully if `docker` or the named
  container isn't reachable).
- 429s are recorded but do **not** fail the gate — `chat_rate_limit` is
  `20/minute` by default and the route has no benchmark-auth bypass wired in
  (unlike `/api/chat`), so 429s at higher concurrency are expected signal, not
  a bug.

Exit code is non-zero on any breach above. `first_person_route_enabled` must
be `true` and `first_person_mode` must not be `disabled` in `backend/.env`
before a real run — otherwise every request 404s (the dry-run flags this).

### Sample dry-run output (captured during prep, 2026-09-26)

```
$ .venv/bin/python scripts/ops/gate1_load_test.py --mode first-person --dry-run --sweep 1,8,32,64
{
  "questions_file": "/Users/harshodaikolluru/mukthiguru_attribution_data/bakeoff_2026-09-25/questions.json",
  "sweep": [1, 8, 32, 64],
  "endpoint": "/api/first-person/query",
  "breach_criteria": {
    "any_5xx": true,
    "any_container_restart": true,
    "p95_ms_at_concurrency_8_over": 1000.0
  },
  "ok": true,
  "problems": [],
  "warnings": [
    "settings.first_person_route_enabled is False / first_person_mode is 'disabled' — a real run against this config would 404 every request. Set both in backend/.env before running for real."
  ],
  "n_questions": 116,
  "sample_question": "Why hasn't getting more money and success made me any happier?",
  "first_person_route_enabled": false,
  "first_person_mode": "retrieval_only"
}

DRY RUN: config structurally OK, but see 'warnings' above before running for real.
```

This confirms, at prep time: the question file parses (116 questions), and
`first_person_route_enabled=False` in the current environment — a real run
today would 404 on every request until that's flipped.

### Where results go

`benchmarks/reports/first_person_load_test_report.json` (per-level latency
percentiles, status-code distribution, container survival verdict). No `.md`
report is generated for this mode (the chat gate's `--check-report` flow is
chat-specific and was left unchanged — additive only, see boundaries below).

### Unit tests

`backend/tests/test_gate1_first_person_mode.py` — question-file loading,
dry-run validation, and the worker's request/response parsing, all against a
mocked HTTP client. No network, no live server. Run with:

```bash
cd backend && .venv/bin/pytest tests/test_gate1_first_person_mode.py -q
```

---

## 2. Backup/restore drill (`backend/scripts/ops/restore_drill.py`)

Proves a Qdrant backup is actually restorable — snapshot a live collection,
restore that snapshot into an isolated **scratch** collection, verify point
count and a sample vector query, then delete only the scratch collection.
Covers the two collections `app.config.settings` actually names:
`first_person_collection` (`first_person_v1`) and `qdrant_collection`
(`spiritual_wisdom_contextual`) — read from settings, not hardcoded, so a
future collection rename doesn't silently drill the wrong name.

Memgraph has no per-collection scratch concept (one graph namespace per
server instance), so its half of the drill is a **documented manual
procedure** printed by `--dry-run`, not executed by this script — it points
at the already-proven `backend/scripts/ops/migrate_neo4j_to_memgraph.py`
export/import/verify commands and the real cross-instance drill recorded in
`docs/BACKUP_RESTORE.md`'s "Graph migration over Bolt" section (2026-09-19).

**Status: prepared, not run for real.** The default dry-run (with its
read-only `get_collection` probes) was executed during prep — see sample
output below. No snapshot, restore, or delete has been performed.

### Hard guard

Every restore/delete call in the script passes through `_assert_scratch()`,
which rejects any collection name not starting with
`restore_drill_scratch_` — a prefix the script itself generates
(`restore_drill_scratch_<collection>_<unix_ts>`), never user-supplied. Tested
in `backend/tests/test_restore_drill.py` (guard rejection, and that
`restore_one_collection` never calls `delete_collection` on the source name,
even on a verification failure).

### How to run

```bash
cd backend

# 1. Dry run (default) — lists the plan; makes at most two read-only
#    get_collection() GETs (skip even those with --no-probe). Never writes.
.venv/bin/python -m scripts.ops.restore_drill
.venv/bin/python -m scripts.ops.restore_drill --no-probe   # zero network calls at all

# 2. Owner reviews the printed plan/report.

# 3. Real execution — snapshot -> scratch-restore -> verify -> delete scratch.
#    BOTH flags are required; either alone does nothing:
.venv/bin/python -m scripts.ops.restore_drill --apply --i-have-owner-approval

# Narrow to one collection:
.venv/bin/python -m scripts.ops.restore_drill --apply --i-have-owner-approval --collections chat
```

Flow, printed by the script itself: **dry-run → report → owner reviews →
owner approves → `--apply --i-have-owner-approval`** creates the real
snapshot and runs the restore/verify/delete-scratch sequence in that same
invocation.

### Pass criteria

- Scratch collection reaches Qdrant status `green` within the poll timeout
  (default 120s).
- `points_count` on the scratch collection exactly matches the source
  collection at snapshot time.
- A sample point's own vector, re-queried against the scratch collection,
  returns that same point as the top hit.
- The scratch collection is deleted afterward; the source collection is
  never touched by a restore or delete call (enforced by the guard, not just
  by convention).

### Sample dry-run output (captured during prep, 2026-09-26, read-only probe against the live local stack)

```
$ .venv/bin/python -m scripts.ops.restore_drill
{
  "qdrant_url": "http://localhost:6333",
  "targets": {
    "first_person": "first_person_v1",
    "chat": "spiritual_wisdom_contextual"
  },
  "scratch_prefix": "restore_drill_scratch_",
  ...
  "apply_requirements": [
    "Real execution needs --apply AND --i-have-owner-approval together; neither flag alone runs anything.",
    "Flow: dry-run (this) -> owner reads the report -> --apply creates a real snapshot -> owner approves proceeding -> restore/verify/delete-scratch happens in the same run."
  ],
  "probes": {
    "first_person": {"collection": "first_person_v1", "exists": true, "points_count": 580, "status": "green"},
    "chat": {"collection": "spiritual_wisdom_contextual", "exists": true, "points_count": 14033, "status": "green"}
  }
}

DRY RUN only — nothing was written. Pass --apply AND --i-have-owner-approval to execute for real.
```

Both target collections exist and are `green` at prep time (580 /
`first_person_v1`, 14,033 / `spiritual_wisdom_contextual` — the latter
reflects the corpus/re-transcription work described in root `CLAUDE.md`'s
"#1 priority" section, not the 12,904 figure quoted in older doc entries).

### Where results go

Printed to stdout as JSON on both dry-run and `--apply`; not written to a
report file (unlike the load test above — this is a manual, low-frequency
drill an operator reads directly, not a CI gate). If you want a durable
record of a real run, redirect stdout, e.g. `--apply --i-have-owner-approval
> backups/restore_drill_$(date +%F).log`.

### Unit tests

`backend/tests/test_restore_drill.py` — the scratch-name guard, a fully
mocked-client restore (happy path + point-count-mismatch + query-mismatch
failure modes, confirming the source collection is never deleted), the
dry-run's read-only-only invariant, and a subprocess check that `--apply`
without `--i-have-owner-approval` refuses and exits non-zero. Run with:

```bash
cd backend && .venv/bin/pytest tests/test_restore_drill.py -q
```

---

## Boundaries observed while preparing both drills

Per the task that produced this document: neither drill was executed for
real. The only network activity performed during preparation was read-only
Qdrant `get_collection` probes (explicitly permitted for dry-run validation)
against the local stack — no writes, no snapshot, no restore, no delete, no
requests to `/api/chat` or `/api/first-person/query`, and no Docker restarts.
