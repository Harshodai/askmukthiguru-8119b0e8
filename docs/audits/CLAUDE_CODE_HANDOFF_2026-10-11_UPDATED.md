# Claude Code Handoff: Full Production Readiness, Faculty Preview, and Public User Readiness

**Date:** 2026-10-11 (updated; supersedes a8843b71-era claims below where they conflict)
**Repository:** `Harshodai/askmukthiguru-8119b0e8`
**Working directory:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
**Target branch:** `main`
**Current `main` / `origin/main`:** `22883a25` (verify with `git rev-parse` — moves fast)
**Operating mode:** Local Mac Docker stack, current main checkout (compose project `mukthiguru_clean`; always pass `COMPOSE_PROJECT_NAME=mukthiguru_clean` — orphan volumes hold the live Qdrant data, do not rename)
**Release posture at handoff:** **NO-GO for public; faculty-preview GO only within its explicit scope once CI is green**

---

## 1. Purpose

Same as the original handoff (§1 of the prior revision): repo/runtime context, Manus's work, verified evidence, doc-vs-live conflicts, remaining tasks, faculty + public criteria, copy-paste prompt. This update reconciles the a8843b71-era claims with the current tree. Do not treat any historical "100% green" as current proof; rerun gates on the current tree and runtime.

---

## 2. Non-negotiable operating rules

Prior rules stand (preserve tree, no reset/stash/branch moves, no deleting `.work/` or untracked files, no commit/push unless authorized, SOLID/DRY/YAGNI/KISS, no FLUSHALL, dry-run→snapshot→apply for data writes, no secrets in output, local Docker evidence is not production evidence, exit-5/timeout/skip is not a pass). Additions:

- Read `AGENTS.md`, `backend/CLAUDE.md`, `src/CLAUDE.md`, `lessons.md` (top first — binding), `docs/architecture/first-person-path-to-prod.md` before modifying code.
- Binding lessons: `L-FP-HYBRID-SCAFFOLD-1` (LLM frames, code quotes; never map teacher_id→name), `L-FP-PROMISE-1`, `L-FP-BENCHMARK-VALIDITY-1`, `L-PINNED-DATASET-BYTES-1` (never whitespace-fix `backend/evaluation/datasets/`).
- Human-only gates live in `CLAUDE.md` ("Human-only gates (2026-10-11)"): reviewers, 299-pair B1 batch, gold restore, WA creds. Surface them; never fake-close.
- Full pytest needs `ulimit -n 61440` (default 1024 starves → Errno 24; that is env-limit, not a leak — proven by 9795-pass rerun). CI now bumps it.
- Vitest bounded: `npx vitest run --coverage.enabled=false --maxWorkers=2`.
- Qdrant 3236 pts in volume `mukthiguru_clean_qdrant_data`. `reconcile` (no `--dry-run` flag; default run is dry) must say mismatches: 0.

---

## 3. Current repository and runtime state (verified 2026-10-11)

### Git state

- Branch: `main`, == `origin/main` at time of writing (re-verify).
- Recent main history: `86cc77f6` follow-ups → `f17cf14e` audit fixes → `cddf906b` lint → `bbcf8f39` drift reconciles → `ec771e8a` repo-wide ruff baseline → `dabdc3c2` WhatsApp journey → `b191e3b4` pre-commit bandit/WS → `22883a25` CLAUDE.md human gates.
- Tree clean expected; confirm with `git status`.

### Docker state observed

- `mukthiguru-backend` / `mukthiguru-frontend` healthy (rebuilt on latest main), Redis/Qdrant/Memgraph healthy, `/api/health` ready/healthy, embedding dim 1024, Qdrant `first_person_v7` 3236 pts.
- Backend bind-mounts source: worktree edits are live without rebuild (verify with `docker exec` grep when it matters).

### Cache evidence

- `make flush-cache` equivalent run with project name + `verify_cache_empty.py` exit 0 (all query namespaces 0; sessions/quotas/telemetry preserved) + backend restart + healthy. Frontend `localStorage` cache is separate (manual DevTools step).

---

## 4. Evidence already verified (current tree)

- Backend full suite: **9795 passed, 2 failed** (both manifest-drift detectors, since reconciled: preflight E003 isolation test + helm path → `infrastructure/`), 0 errors at fd 61440. Post-format run: 9803 passed + 2 WhatsApp-freeze pins updated for quote normalization (identical semantics).
- Frontend: **804 passed**, typecheck + build clean (bounded workers).
- CI: Production Readiness, Security, CodeQL, Hard Gates green; Lint & Test chased repo-wide baseline (999 check errors cleared, format baseline, bandit justified, trailing WS) — confirm current head's CI run before claiming green.
- Live probes on exact head, empty-cache proof: Beautiful State → weak_match + 1 citation; anxiety → weak_match + 1 citation; France → honest decline, 0 citations. Correct for uncalibrated default (zero direct answers by design).
- Prior focused suites (145-test, 26-test) are historical; superseded by full-suite runs above.

---

## 5. Scenario evidence (two generations — do not mix)

### Manus S1–S4 (pre-patch, a8843b71 era, `.work/live-audit/`)

Preserved as reported: S1 substantive but `citations_verified=null`, unverified speakers, no timestamps; S2 honest abstained partial; S3 five-step meditation with stop condition; S4 honest refusal with irrelevant citations attached (fixed since: bounded refusals return zero public citations — `generation.py`, verified in tree).

### Fresh live probes (current tree, 2026-10-11)

- Doctrine Q: 12/12 claims grounded, faithfulness 1.0, no hallucination flag, 3 YouTube citations — but citations lack timestamps, one `Unknown` speaker, and the verdict object is textually contradictory (`details` says "passed", `passed:false`, `method:null`, `grounding:abstained`). UI keys on `citationsVerified:false` → renders "Unverified attribution" (verified in `ChatMessage.tsx`). No user-facing lie, but the details-string cleanup is owed.
- OOC: clean decline, 0 citations (off-topic gate proven live on chat path).

---

## 6. Changes landed since the original handoff

Manus's list (verification.py fail-closed, grounding.py derivation, chat.py/orchestrator.py `citations_verified` + `orphan_citations_stripped` propagation, generation.py zero-citation refusals) verified present in tree. Appended this session:

- Ingest hardening: shared `store_point_id_for_clip()` (write + verify paths), H4 drop-not-crash (27 clips), per-batch dedup mirror, reconcile 0/3236, clean driver exit 0. W2 salvage correctly SKIPPED (band n=3 < 10).
- Hybrid scaffold (LLM frames, code quotes; editorial behind explicit opt-in) + seam-guard tests; off-topic wall ON (35/35 recall, 0/20 FPR); speaker-verification lane (ECAPA predicate + `speaker_verified` plumbing, ~300 Times Now flips on next rebuild — rebuild NOT yet run for this).
- FP liking signal (per-clip feedback + KPI slice); probe v4 (real-LLM-or-exit-2, answerability assertions); proposition/bulk-ingest P0 gates; CI fd guard; repo-wide lint/format baseline; WhatsApp journey (auth/citations/single-send/media/rate-limit, 47 tests — live send needs owner creds).
- Prompt docs: baseline addendum + master state refresh; handoff prompt for Claude Code at `docs/agent/NEXT_CLAUDE_CODE_HANDOFF_2026-10-11.md`.

---

## 7. Pending work (P0/P1/P2 as before, updated)

### Done since original list

- Full backend suite green-modulo-2 (now reconciled); frontend green bounded; typecheck/build clean.
- Refusals carry zero public citations; gateway/lacking-evidence cannot override local claims (tested).
- `citations_verified` + `orphan_citations_stripped` confirmed on direct path (grepped in tree); queued/stream paths carry the fields via orchestrator (re-verify live if release depends on it).

### Still open (do not claim otherwise)

- **P0 contract**: queued/streaming serialization regression tests; verdict-string cleanup; citation timestamps/speakers.
- **P0 provenance**: gold-video presence; no `Unknown` as teacher (label path, not mapping); exact title/channel/transcript checks per cited source.
- **P1 scenarios**: S2 supported-steps-or-insufficiency; S4 absent-term explanation quality.
- **P1 first-person**: verified-speaker clip tests; mixed speakers; multilingual; speaker rebuild + apply (~300 flips) NOT yet run.
- **P1 safety**: full matrix green in-tree; native-speaker + clinician review still owed (packets in `evals/`).
- **P1 frontend/UX**: responsive/keyboard/SSE/localStorage validation for new labels.
- **P1 ops**: gold restore → harness → real thresholds; 299-pair B1 batch; Railway `FORWARDED_ALLOW_IPS` + unpause (owner); NDCG env confirmation.
- **P2 docs**: V10 verdict rewrite; lessons for new invariants.

---

## 8. Validation commands (updated)

Baseline: `git status`, `git rev-parse HEAD/origin(main)`, `git diff --check`. Backend: `ulimit -n 61440; cd backend && .venv/bin/pytest tests/ -q`. Frontend: `npx vitest run --coverage.enabled=false --maxWorkers=2`, `npm run typecheck`, `npm run build`. Static: `backend/.venv/bin/ruff check .`, `ruff format --check .`, `git diff --check`. Docker: `COMPOSE_PROJECT_NAME=mukthiguru_clean` for all compose ops; flush script + `verify_cache_empty.py`; `/api/health`. Live: signed anon-session, `/api/chat?wait=true` with `messages:[]`, doctrine + OOC probes, inspect full JSON (never the summary). Launch gates per repo; load matrix only on approved targets.

---

## 9. Faculty-preview criteria (unchanged scope + score table from original)

Minimum 85/100 with zero P0/P1 defects. Faculty preview is controlled/password-protected, not public launch.

## 10. Public-user criteria (unchanged + current deltas)

Everything in §9 plus: clinician sign-off, native-speaker review, production env + Railway gates, prod Qdrant/Redis/Memgraph evidence, backup/rollback/monitoring, privacy/age/terms/deletion, no crawler exposure unless intentional, prod load evidence, no local-only creds/hostnames, real signed-session smoke. **Faculty-ready does not imply public-ready.** Current deltas blocking public: human reviews, 299 pairs, gold restore, Railway.

## 11. Required final output (same 14 items as original)

Branch/commit, files changed, tests with exact counts, Docker health, cache evidence, S1–S4 table, safety table, faculty + public scores, P0–P3 register, GO/CONDITIONAL/NO-GO × 2, remaining tasks, no invented evidence.

---

# Copy-paste Claude Code prompt (updated)

You are Claude Code in `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8` (main; verify `HEAD`/`origin/main` first — it moves). Mission: genuine faculty-preview readiness and a truthful path to public launch. Rerun every gate on the current tree; historical greens are provenance, not proof.

Constraints: preserve tree (no reset/stash/branch moves); never delete `.work/`/reports/untracked; no commit/push unless asked; read AGENTS.md, backend+src CLAUDE.md, lessons.md top, first-person arch doc before edits; SOLID/DRY/YAGNI/KISS; no FLUSHALL (targeted cache cmds); dry-run→snapshot→apply for data; no secrets in output; local Docker ≠ production.

Known state: backend ~9795 green (fd 61440 required), frontend 804 green, Qdrant 3236 reconcile-clean, hybrid scaffold + off-topic wall live, uncalibrated default serves zero direct answers, golden-25 top1 0.0 is a validity artifact (gold videos absent), speaker lane code-complete but rebuild not run, calibration needs 299 human pairs, reviewer packets in `evals/`, WhatsApp journey complete but creds missing, Railway paused.

Compose ops need `COMPOSE_PROJECT_NAME=mukthiguru_clean`. Backend bind-mounts source. Lessons are binding, especially L-FP-HYBRID-SCAFFOLD-1. Human gates in CLAUDE.md are owner-only — surface, never fake-close.

Execute: baseline → contract → fail-closed verification → provenance → S1-S4 fresh → first-person → safety → full gates → cache-free runtime validation → UX → release decision with faculty + public scores and GO/NO-GO each. Adversarial and specific; implement safe fixes with regression tests; mark UNPROVEN where a gate cannot run.
