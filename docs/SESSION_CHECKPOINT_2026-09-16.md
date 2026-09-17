# Session checkpoint — 2026-09-16, written before a plan-limit boundary

**Read this first in the next session.** It is written so a cold session can
resume from files alone, because the things that do NOT survive a session
boundary are listed below and they include the running agents.

---

## 1. What survives, and what does not

| Survives | Does not survive |
| :--- | :--- |
| Every file edit on disk (142 changed files, uncommitted) | The 4 running subagents — their ids are session-scoped and cannot be resumed from a new session |
| This document | In-flight agent reasoning that was never written to a file |
| Qdrant / Memgraph data written this session | The task-output transcripts under the session scratchpad |
| Test results, once re-run | |

**So: re-spawn the agents from the briefs summarised in §5, do not try to
resume them.**

## 2. The working tree is UNCOMMITTED and three peer sessions are live

`git status` shows **98 modified + 44 untracked**. Nothing is committed.
`ListAgents` shows three other interactive Claude sessions attached to this
same repo. A `git checkout`/`stash`/`reset` in any of them would destroy this
work. **First action in the next session: verify the tree still contains the
changes below, then commit.** The owner has approved "commit and push once all
tasks are done" — see §6 for what "done" means.

## 3. Decisions the owner made (do not re-litigate)

- **Voice: Option A — third person with attributed quotes.** Reason, verbatim:
  *"this product is also a disciple of the gurus"*. A disciple transmits a
  teaching and attributes it; it does not speak as the teacher. Recorded in
  `docs/VOICE_SAMPLE_AB.md`; the contradicting rules in
  `services/guru_brain/guru_brain_service.py` are deleted. **Settled.**
- **Corpus fix depth**: provenance stamp + retrieval preference + fix the
  chunking code. **No re-ingest.**
- **Railway: prepare only, do not deploy.**
- **Engineering standards, named explicitly**: the `ponytail` skill (laziest
  thing that works, reuse before writing, shortest diff, no speculative
  scaffolding) and **pydantic over hardcoded values**.
- **Next demo audience: the Gurus themselves and their prime disciples.**
  Misattribution is therefore the top-severity failure class, above refusal
  and above latency.

## 4. Verified state at checkpoint time

- Backend container healthy on :8000. Memgraph / Qdrant / Redis healthy.
- Full suite was **1 failed / 4345 passed** before the last agent round; at
  checkpoint it is **~3 failed / 4347 passed**, the deltas being new
  `evaluation/*` files from the benchmark agent (direct `os.environ` reads
  tripping `test_settings_guards`) — that agent was told to fix them.
- `test_repo_layout` now PASSES: the duplicate `scripts/ops/canonicalize_teacher_aliases.py`
  was deleted (the canonical copy lives at `backend/scripts/ops/`, which is what
  the Makefile runs).
- Live probe, anonymous, no cache: "What is Soul Sync?" → ~667-893 chars,
  3 citations, **0 bullet markers**, Guru Voice Distance ~1.26. "Suffering vs
  Beautiful State" → GVD **0.41** (verbatim-guru median 0.37, machine prose
  1.64, old-prompt baseline median 8.52).

## 5. The four agents that were running — re-spawn these

1. **Unified benchmarks** (`backend/benchmarks/**`, `backend/evaluation/**`,
   `scripts/eval/**`). Unify ~25 scattered entry points into ONE harness with
   one CLI and one result schema; evaluate EVERY question by default
   (`--sample` off by default); per-question results, not just aggregates; add
   abstention-correctness (refusing "the Fifth Sacred Secret" is CORRECT),
   attribution-correctness, node-level error and zero-retrieval canary signals;
   thresholds as pydantic settings. **Outstanding:** fix its own direct
   `os.environ` reads in `evaluation/eval_runner.py`, `priority_language_eval.py`,
   `run_golden_eval.py` WITHOUT adding them to the guard's allowlist.
2. **SDE / CI gates** (`.github/workflows/**`, `Makefile`, lint+type config,
   the three guard test files). Coverage floor at the measured baseline, type
   baseline, lint enforcement, a perf-regression guard, `make quality`. Ratchets,
   never cliffs.
3. **Prod hardening** (`onnx_reranker.py`, `openrouter_service.py`,
   `memgraph_community_service.py`, `app/api/health.py`, `start_railway.py`).
   Four items: the `os.cpu_count()//2` bug still live at `onnx_reranker.py:128`;
   the executor-starvation liveness gap (the healthz heartbeat catches an
   event-loop FREEZE but not executor starvation — loop alive, pump beating,
   healthz 200, every chat hanging); move `OpenRouterService`'s per-process RPM
   `ClassVar` to Redis; make the community pipeline transactional or delete the
   ~170 stale records nothing reads.
4. **Guru demo readiness** (read-only, produces `docs/GURU_DEMO_READINESS.md`).
   Trace every attributed claim back to its chunk's `provenance` + `teacher_id`;
   flag anything sourced only from `machine_summary`/`third_party_prose` but
   presented as the Gurus' words; name the demo-safe subset.

## 6. Prod-readiness blockers still open

1. Railway backend is **`● Crashed`** (`railway status`).
2. Production runs **Neo4j**, not Memgraph — contradicts the migration docs and
   the memory budget that justified the $25 plan.
3. **Celery worker is `● Online`**, not opt-in-paused; it bills against the ceiling.
4. **Zero backups** anywhere. Supabase Free (`pitr_enabled: false`, `backups: []`),
   no cron installed, newest graph dump 2026-08-23. RPO unbounded.
5. Executor-starvation wedge is invisible to the healthcheck (agent 3 owns it).
6. `OpenRouterService` RPM is per-process — blocks `WEB_CONCURRENCY > 1`.
7. Free-plan-blocked and already documented: leaked-password protection off,
   `password_min_length: 6`, no captcha.

## 7. Environment gotchas that cost real time tonight — do not rediscover

- **Authenticated `POST /api/chat` returns `202 + job_id` and must be polled at
  `poll_url`.** Anonymous answers synchronously. Reading `response` off the 202
  looks exactly like a broken backend.
- **`incognito` is a PRIVACY flag, not a cache bypass.** Use `cache_bypass: true`.
- **Memgraph auth**: `GraphDatabase.driver(uri, auth=(settings.neo4j_user, settings.neo4j_password))`.
  `auth=None` and `os.getenv(...)` both fail with `Unauthenticated`.
- **`SUPABASE_URL=http://host.docker.internal:54321` does NOT resolve on the host.**
  Use `localhost` when running anything from the host venv. Do not edit `.env`.
- Embedding method is `EmbeddingService().encode_single_async(text)`.
- Any retrieval measurement MUST pass **dense AND sparse** vectors; dense-only
  understates the retriever badly and has already forced one baseline retraction.
- Ephemeral Supabase test users must use a **gmail/hotmail/outlook** address —
  a DB trigger rejects `@example.com`.
- If answers suddenly become refusals, retrieval is THROWING. Check
  `docker logs mukthiguru-backend` for `Node 'retrieve_documents' failed`.

## 8. Defect classes proven in this codebase — design against these

1. A registered service silently `None` in production (`set_guru_brain` had zero callers).
2. A flag gating code inside an unreachable node (`atomic_graphrag_enabled` inside a disabled node).
3. A canonical string re-transcribed elsewhere — cost two outages tonight.
4. A payload key-name collision (`provenance` string vs dict) — took retrieval down entirely.
5. A gate placed after the early-return it was meant to guard (Indic HyDE).
6. A setting declared nowhere but set in `.env` — silently dropped by `extra="ignore"`
   (`supabase_anon_key`, which made callers act as **service_role** instead of anon).
7. A benchmark that scores its own reference and reports a perfect score.

---

## 9. Second boundary — 2026-09-16 ~07:50, all four agents killed again

**All four died on the session rate limit (resets 12:20pm IST), and all four
were running `claude-opus-5`** — including the three spawned with no `model`
override. The session default subagent model is opus, not sonnet. That is why
the budget lasted ~15 minutes. **Re-spawn agents 1-3 with an explicit
`model: sonnet`**; agent 4 (guru demo) keeps opus by owner decision.

### What survived

| Agent | Status doc | Outcome |
| :--- | :--- | :--- |
| Prod hardening | `docs/PROD_HARDENING_STATUS.md` | All 4 items were already implemented; it verified them and found 2 NEW defects, both fixed (see below) |
| Guru demo readiness | `docs/GURU_DEMO_READINESS.md` (23KB, 8 findings) | The highest-value output of the session. F1 was a live DEMO BLOCKER |
| Unified benchmarks | none | died mid-edit updating a guard docstring |
| SDE / CI gates | none | died mid-edit writing a new guard |

### Fixed this boundary (main session, not an agent)

**F1 — the circuit-breaker wedge. Was a live demo blocker; now fixed and
verified on this host.** `can_execute()` reserves a half-open slot that only
`record_success()`/`record_failure()` release. Four providers implemented their
read-only `is_circuit_open()` probe as `not breaker.can_execute()`, so three
probes exhausted the budget and wedged the breaker OPEN permanently — every
chat returned "The Guru is unable to answer this question" in 11ms for ~5 hours
while `/api/health` stayed green.

- Added `BaseCircuitBreaker.is_open()` — non-reserving, one place, all
  subclasses inherit.
- Switched five probe sites: `openrouter_provider.py:87`, `ollama_provider.py:86`,
  `sarvam_provider.py:88`, `nim_provider.py:87`, and `nim_service.py:802`
  (an availability predicate the audit did not reach — a fifth leaking site).
- Proven against the shipped class: old idiom leaves `half_open_in_flight=3` and
  refuses the next real call; new idiom admits it.
- 5 new tests in `tests/test_circuit_breaker.py`, including a source assertion
  over all four providers so the idiom cannot come back. 24/24 pass.
- Container restarted; live anonymous probe returns `grounded`, 1 citation,
  929 chars, 10.1s, `tier2_simple`.

The prod-hardening agent separately fixed D1 (`os.cpu_count()` cap surviving in
`onnx_reranker.py:137` and `embedding_service.py:391`) and D2 (a guard test that
re-implemented the formula in its own body and would pass with the module
deleted — defect class 7).

### Correction to §7 of this document

**§7 says anonymous `POST /api/chat` answers synchronously. It does not.** With
a signed anon-session token it returns `202 + job_id` and must be polled at
`poll_url`, exactly like the authenticated path. Measured this boundary. Any
harness reading `response` off the 202 will report a working backend as broken.

### Still open, unchanged

F2 (attributed teaching shipping with zero citations — TOP SEVERITY), F3-F8 in
the demo-readiness doc, and all seven §6 blockers. **F2 is intermittent**: one
post-fix probe of the same question returned `grounded` with 1 citation, which
is a single stochastic sample and proves nothing about F2 either way.

`docs/RUTHLESS_PLAN_10_10.md` is now also in the queue — an ECC-agent audit,
8/8 P0 findings independently confirmed on disk, with a verification section
appended recording what it got wrong (cookies.txt severity) and what it missed
(prod-on-Neo4j, Celery billing, Phase 2's non-existent entry condition, and a
score trajectory with no independent scorer).

---

## 10. Six agents respawned — 2026-09-16, ownership map

Model chosen per task after the opus-burst failure in §9. **File boundaries are
in every brief**: six agents edit this tree concurrently, and two agents in one
file is how work gets lost.

| # | Track | Model | Owns | Status doc |
| :- | :--- | :--- | :--- | :--- |
| 1 | **F2 attribution fix** (NEW) | opus | `rag/nodes/citation_extractor.py`, `generation.py`, `utils.py`, `services/voice/**` | `docs/F2_ATTRIBUTION_FIX_STATUS.md` |
| 2 | Guru demo readiness F3-F8 | opus | `docs/GURU_DEMO_READINESS.md` only (read-only audit) | same file |
| 3 | **Ruthless-plan Phase 0** (NEW) | sonnet | `nginx.conf`, `infrastructure/cron/**`, `.claude/settings.local.json`, `app/api/endpoints/auth.py`, `app/pipeline/stages/glue_stages.py`, ingest upload paths, `bulk_ingest_video.py` | `docs/PHASE0_STATUS.md` |
| 4 | Unified benchmarks | sonnet | `backend/benchmarks/**`, `backend/evaluation/**`, `scripts/eval/**` | `docs/BENCHMARK_UNIFICATION_STATUS.md` |
| 5 | SDE / CI gates | sonnet | `.github/workflows/**`, `Makefile`, `pyproject.toml`, `scripts/ops/loop_validate.sh`, guard tests | `docs/CI_GATES_STATUS.md` |
| 6 | Prod hardening | sonnet | `start_railway.py`, `app/api/health.py`, `openrouter_service.py`, `onnx_reranker.py`, `docker-compose.prod.yml` | `docs/PROD_HARDENING_STATUS.md` |

**Every brief mandates checkpoint-after-each-step**, not batched writes. In §9
the two agents that batched lost everything; the two that wrote incrementally
kept 23KB and 4.6KB of work. That is the whole difference.

**Owner decisions recorded this round:**
- F2 gets its own opus agent (not folded into the read-only audit).
- Phase 0 runs in parallel now, not after.
- Protect ALL tracks, and keep this checkpoint current — owner's words:
  *"all of the above and make sure our session has checkpoints as well"*.
- Endpoint of this session is still: review, commit, push, append to
  `lessons.md`. **Authorized by the owner; nothing is committed before that
  review.**

**Known collision the briefs resolve by assignment, not by luck:** plan Phase 0
item 1 (`loop_validate.sh`) and item 10 (prod compose graph env) were removed
from the Phase 0 agent's list — they belong to agents 5 and 6 respectively. The
Phase 0 agent was told so explicitly.

---

## 11. CI gates track — done, with one number corrected and one NEW blocker

**Agent 5 (CI gates) finished.** Real measured numbers, not claims:
`pytest -q` = **6 failed / 4452 passed / 12 skipped** (450.8s).
`make quality` = **FAILS at step 1/5 (ruff)**. Both re-verified by the
coordinator.

### What it landed
Most deliverables were already on disk from the killed predecessor. Genuinely
new this round: **Vitest coverage thresholds** (previously absent) in
`vitest.config.ts`, floors set a few points under the measured 2026-09-16
baseline (52/42/42/54 vs measured 54.57/44.5/44.8/57.14), wired through
`npm test` so CI and `loop_validate.sh` both enforce it without a new step.
Verified both directions: passes clean, and fails when a floor is raised above
measured.

### It declined to ship a guard, correctly
A generic AST guard for defect class 7 ("a test that re-implements the logic it
guards") measured a **21% false-positive rate — 285 of 1339 real test
functions**. Not shipped; the measurement is recorded so nobody rebuilds it
naively. A guard that fires on a fifth of the suite is disabled within a week
and is worse than no guard.

### F-GATE-1 was a FALSE POSITIVE — coordinator error, now corrected
`scripts/ops/loop_validate.sh` DOES fail. `run_gate`/`run_shell_gate` end in
`return 0` so the matrix runs every gate instead of aborting on the first; the
verdict is an `awk` aggregation at the bottom that exits 1 on any non-zero row,
and it **predates this session** (`git show HEAD:`). The coordinator read lines
14-40, never read the tail, and filed it CONFIRMED. The file's own header notes
it was "filed twice as a swallowed-exit-code bug and twice wrongly" — this was
the third. Proven empirically by the agent: a planted ruff violation produced
`backend_ruff 1`, `LOOP_RESULT=FAIL`, exit 1. `docs/RUTHLESS_PLAN_10_10.md` is
corrected to 7/8.

### NEW BLOCKER — CI's ruff gate has been red since before this session

The agent reported `make quality` failing with "678 errors / 35 files, all
belonging to other concurrent workstreams". The coordinator re-measured:
**680 errors across 182 files, and 143 of those files are UNTOUCHED this
session.** So the bulk is pre-existing debt, not concurrent-agent churn — the
agent's attribution was wrong in scale.

`.github/workflows/lint-test.yml` runs `ruff check .` with
`working-directory: backend` and no `|| true`, so that job fails on every PR.
**That step is byte-identical at `HEAD`** — this session did not introduce it.
Conclusion: either CI on `main` is already red, or nobody is running it. Both
are worth knowing before the push at the end of this session.

This does not block committing (it is not a regression), but a push will show
red CI, and the cause will not be our diff.
