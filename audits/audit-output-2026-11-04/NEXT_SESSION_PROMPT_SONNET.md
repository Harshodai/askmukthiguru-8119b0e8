# Next-session prompt: Claude Sonnet (Railway, operations, configuration, accessibility, Kubernetes, Lovable, guards, documentation)

Copy everything below the line into a new Claude Code session that runs Sonnet (high reasoning). A parallel Opus session uses `NEXT_SESSION_PROMPT_OPUS.md`. The two sessions own different files (§3), so they can run at the same time.

---

You are an implementation agent for **Ask Mukti Guru**. The repository is `Harshodai/askmukthiguru-8119b0e8`. Work on branch `feature/audit-strengthen-rag-qdrant`. Last known remote head: `12bb3225` (2026-11-06).

You own the work that makes Railway staging possible and the platform operable: Railway configuration and deploy scripts, configuration hygiene, alerting and backups, accessibility fixes, Kubernetes reference hygiene, the Lovable write path, guards, the load-test harness, and documentation. An Opus session works in parallel on safety, answer honesty, prompt-injection defences, corpus data integrity and the independent review.

## 0. Before anything else (do these in order)

1. Run `git fetch origin feature/audit-strengthen-rag-qdrant` and `git log --oneline -15 origin/feature/audit-strengthen-rag-qdrant`.
2. Look for the owner's T7-02 commits (async teaching lane, one Celery event loop, deadlock fix). Search with `git log --oneline origin/feature/audit-strengthen-rag-qdrant | grep -iE 'T7-02|async|event loop|deadlock'`.
3. **If they are not on the remote, stop.** Tell the owner: "The T7-02 commits are not on the remote. On the machine that holds them, run `git pull --rebase origin feature/audit-strengthen-rag-qdrant`, then `git push origin feature/audit-strengthen-rag-qdrant`." T7-02 touches `backend/start_railway.py` and Celery code that you also edit, so do not start until it is pushed.
4. Read, in this order:
   - root `CLAUDE.md`, `backend/CLAUDE.md`, `src/CLAUDE.md`
   - `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md`
   - `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §1 and §3
   - `FINAL_PENDING_WORK_REGISTER.md` §1, §3, §10
   - `FINAL_RAILWAY_STAGING_READINESS.md` (Gate A, A1-A21)
   - `FINAL_DECISION_AND_RISK_REGISTER.md` §2.1
   - `lessons.md` through the Nov 5 sections
   - the specification named by each task (in `audits/audit-output-2026-11-04/specifications/`)
5. Check CI for the head commit. Fix failures in files you own (§3). Write down failures in Opus-owned files and continue.

## 1. Facts you must not re-derive

- **Release decision:** staging NO (conditional), production NO, public NO. The Gate A blockers you can remove are RW-01 to RW-06 and the staging items in `FINAL_RAILWAY_STAGING_READINESS.md`. Gate A also needs owner decisions D-26, D-14, D-29 and D-30, plus the Qdrant snapshot copied off the owner's Mac.
- **Railway configuration:** `.railway/railway.ts` (Infrastructure as Code) is the current method. `railway.json` and `railway.toml` are deprecated and stop working on 2026-12-01 (docs.railway.com, checked 2026-11-05). The IaC `service()` cannot name a Dockerfile, so set `RAILWAY_DOCKERFILE_PATH`.
- **Six earlier commit messages claimed more than their diffs.** Read the code, not the message.
- **The owner's local `.env` has the spend guard off.** Production startup refuses that. Never make real LLM calls; use fakes.
- **SYS-014:** when the provider does not report `usage.cost`, each call keeps the $0.03 reservation (`backend/app/openrouter_budget.py:87-98`). The default $10 daily cap (`backend/app/config.py:640`) then allows about 111 full-path requests a day. Make it visible (NEW-OPS-8) and do not hide it.

## 2. Rules (a violation makes the work unusable)

1. **Root `CLAUDE.md` invariants apply to every change.** In your areas this means: never relax `/metrics` (admin plus AAL2; Prometheus scrapes `/internal/metrics` with `METRICS_SCRAPE_TOKEN`), never log seeker text, FastAPI dependencies stay `async`, secrets stay in environment variables, npm is canonical (never touch `bun.lockb`), and the repository root stays clean.
2. **Test first for every defect.** Write a failing test, keep its output, fix, then rerun. Before each commit, run on changed files:
   - the targeted tests
   - `python3 scripts/guards/lesson_guards.py` (applicable modes)
   - `python3 scripts/guards/pipeline_order_guard.py`
   - `ruff check` and `ruff format --check`
   - `npm run lint` and `npm run test` for frontend changes
3. **Never skip, xfail, quarantine or weaken a test or guard.** A ratchet may only tighten.
4. **Never implement a decision-gated variant before the decision is recorded.** Write the compliant default. Put gated behaviour behind a default-off flag that has a reader and tests for both states.
5. **One task per commit.** The message names the task and finding IDs, and claims only what the diff does.
6. **Git:** never force-push, rewrite history, push to `main` or merge. Before each push: `git pull --rebase origin feature/audit-strengthen-rag-qdrant`. For Markdown both sessions append to, keep both sides. Push with `git push origin feature/audit-strengthen-rag-qdrant`, retrying up to 4 times on network errors (2 s, 4 s, 8 s, 16 s). If refused for permissions, stop and give the owner the exact commands.
7. **No live infrastructure** (Railway project, Qdrant, Supabase project, OpenRouter) and no credentials. Do not run `railway up`, `railway config apply` or any deploy. Writing IaC and scripts is allowed; applying them is the owner's step.

## 3. File ownership (do not edit Opus-owned files)

**You own:**
- `.railway/railway.ts`, `.railwayignore`, `scripts/deploy/`, `backend/start_railway.py` (after T7-02 is on the remote), `backend/Dockerfile.railway`, `backend/docker-compose*.yml`
- `backend/app/config.py` (Opus may append one marked block at the end of `Settings`; keep it on rebase)
- `backend/app/openrouter_budget.py`, `backend/services/openrouter_service.py` (budget counting only), `backend/app/model_policy.py`
- `infrastructure/` (prometheus, cron, k8s), `docs/runbooks/`, `docs/`, all CLAUDE.md files, `AGENTS.md`
- `scripts/guards/`, `.github/workflows/`, `backend/benchmarks/`
- `scripts/ops/backup_qdrant.py` and the backup cron, a new `scripts/ops/fp_live_audit.py`
- `src/` (frontend), `tests/e2e/` and other frontend tests
- `supabase/functions/eval-run/`
- `backend/app/metrics.py` (shared, append-only for both sessions)

**Opus owns (do not edit):** `backend/services/first_person_*.py`, `backend/rag/nodes/first_person.py`, `backend/rag/states.py`, `backend/rag/nodes/generation.py`, `backend/app/pipeline/stages/graph_stage.py`, `first_person_bridge.py`, `backend/app/answer_outcome.py`, `backend/services/serene_mind_engine.py`, `backend/services/crisis_helplines.py`, memory extraction and persona code, `backend/app/api/teachings.py`, and the corpus builder scripts (`build_full_corpus_v10.py`, `build_first_person_index.py`, `audio_archive.py`). For cross-cutting tasks (literal replacement, log sites, exception ratchet), skip those files and list the skipped sites in your report.

## 4. Ordered work

### 4.1 Railway staging enablement (Gate A; spec: `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` §8)

1. **NEW-RW-4** (RW-03): fix `scripts/deploy/deploy_railway.sh`:
   - Redis `noeviction`
   - no random `JWT_SECRET`
   - add the missing variables: `ENVIRONMENT`, `METRICS_SCRAPE_TOKEN`, `GIT_SHA`, `FORWARDED_ALLOW_IPS=10.0.0.0/8`, `PYTHON_MEMORY_LIMIT_MB=0` (SYS-013)
2. **NEW-RW-1** (RW-01): set the drain seconds in IaC. Fix the stale comments at `backend/app/main.py:135` and `:934` (comments only; `main.py` logic stays as it is).
3. **NEW-RW-2** (RW-02): release identity. Either use a GitHub-triggered deploy with "Wait for CI", or have CI set `GIT_SHA`. Prove that startup does not abort for a missing commit SHA (`backend/services/first_person_release.py:119-125`; read only).
4. **NEW-RW-3** (RW-04): forward SIGTERM to the Celery child in worker and beat modes, with a test. Edge cases: SIGTERM during a running task; a second SIGTERM; beat holding its lock.
5. **T9-01** (RW-05): write the full `.railway/railway.ts` (backend, worker, beat, Redis; Qdrant as an external URL variable until D-26). Read the runbook §5 first. Do not apply it.
6. **NEW-RW-8** (RW-06): add the boot-time measurement logging. Add a skip flag for LightRAG init only if the measurement shows it is needed, with tests for both states.
7. **NEW-RW-7:** correct the health-gate statements (`/api/healthz`, not `/api/health`) in root `CLAUDE.md` Gotchas, `docs/agent/claude-md-archive/railway-deployment.md` and `audits/audit-output-2026-11-04/22b-railway-deployment-readiness-runbook.md` (dated note).

### 4.2 Configuration and cost visibility

1. **NEW-AI-3** (AI-013): in production, the relevance-scorer model setting is required, and startup fails closed if it is empty. Make the scorer timeout one value with one source. Keep the current `Settings` default (25.0 s) until the owner decides D-PG13, and align the compose files to it.
2. **NEW-AI-4:** add a price-table completeness test for allowed models. A model without a price must be listed in an explicit "missing price" set that the test prints, and that set may only shrink. Do not invent prices.
3. **NEW-OPS-8 and NEW-LOAD-4:** count budget denials (`guru_budget_denied_total`) and log unreported-cost reservations, so SYS-014 is visible. Put the three scorer timeouts and the RPM limit in one budget table.
4. **NEW-LOAD-5:** at startup, log `os.cpu_count()`, the executor size and `max_concurrent_chat`.
5. **CQ-010 remainder:** remove the 27 unread settings, last in the `config.py` change order. Check that each one really has no reader, including env-var aliases.

### 4.3 Observability, backups, runbooks (spec: `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` §8)

1. **NEW-OPS-1** (OPS-003, OPS-004, OPS-005):
   - Repair the alert rules that read metrics no code emits (`BackupStale` fires permanently today).
   - Scrape `/internal/metrics` with the token.
   - Route the `warning` and `info` severities.
   - Add a rule that pages on any increase of `guru_integrity_breach_total`.
2. **NEW-OPS-4** (OPS-007): the backup reads the collection from settings (not `first_person_v7`), sends the Qdrant API key, verifies the artefact, and exports a success timestamp. Then **T3-10** off-host backups. The restore drill is the owner's step.
3. **NEW-OPS-3, NEW-OPS-7:** collection point count and snapshot age; Celery queue length, task result and beat tick metrics.
4. **NEW-OPS-9:** create `docs/runbooks/INCIDENT_LOG.md`. Move the runbooks RB-1 to RB-10 from the spec into `docs/runbooks/`, with an anchor per alert. Fix `docs/runbooks/ONCALL.md`: it names `/api/metrics`, a per-user JSON route, as the Prometheus endpoint.

### 4.4 Accessibility (spec: `specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` §7 and §10)

Work through these in order:
1. **NEW-A11Y-1:** add `wcag22aa` to the axe tests and cover the journey states.
2. **NEW-A11Y-2:** contrast fixes for A11Y-01, A11Y-02, A11Y-03 (the "Related, not a direct answer" label) and A11Y-20.
3. **NEW-A11Y-3:** give the clip dialog a name and description.
4. **NEW-A11Y-6:** focus management and one polite live region; remove the extra Tab stop before Send (A11Y-18).
5. **NEW-A11Y-7:** 24 px minimum targets; the cookie banner must not cover Send at 390 px (A11Y-11).
6. **NEW-A11Y-8:** a persistent "Get help now" link.
7. **NEW-A11Y-9:** focus and errors in the delete-account flow.

Run axe before and after each fix, with the commands in §2 and §10.1 of the spec.

Never change the meaning of any label. "Related, not a direct answer" stays word for word. Copy changes need owner review before release.

### 4.5 Kubernetes reference hygiene (spec: `specifications/K8S_MANIFESTS_REVIEW.md`)

1. **NEW-K8S-5** (K8S-06, P1): remove the committed default passwords (`values.yaml:153`, `:189`; `configmap.yaml:19`) and use Helm `required`.
2. **NEW-K8S-1, NEW-K8S-2:** add a "REFERENCE ONLY, not deployed" header and a drift test. This is the proposed default for D-PK8S1.

### 4.6 Lovable write path (spec: `specifications/LOVABLE_SYNC_PATH_REVIEW.md`)

NEW-LOV-02 (CI guard for bot PRs), NEW-LOV-03 (UI-copy voice check: no teacher first person), NEW-LOV-04 (generated Supabase types check), NEW-LOV-06 (`src/CLAUDE.md` storage-contract rule), NEW-LOV-07 (frontend hosting fact sheet), NEW-LOV-08 (remove the `LOVABLE_API_KEY` from `eval-gate.yml` if no code reads it). NEW-LOV-01 (branch protection) is the owner's GitHub step. NEW-LOV-05 waits for D-24.

### 4.7 Guards, ratchets, evaluation and docs (from the register's "next 15")

1. **T1-15 remainder** (CQ-009, X-07): extend `scripts/guards/pipeline_order_guard.py` to check `backend/CLAUDE.md` and `docs/`. The lead already corrected `backend/CLAUDE.md` on 2026-11-06, so the guard should pass.
2. **T1-14 remainder** (SEC-006): pin the `Dockerfile.railway` base image; add a test that rejects `:latest` in compose; fix `memgraph-mage:latest` in `backend/CLAUDE.md`.
3. **T8-02** (GURU-010, GURU-016): replace teacher-name literals with registry lookups outside Opus-owned files. Make `scripts/guards/guru_literal_guard.py` scan for literals, not only the schema, and wire it into pre-commit and CI as a ratchet.
4. **SEC-003 remainder:** fix the remaining seeker-text log sites outside Opus-owned files and lower `KNOWN_OFFENDER_BUDGET`.
5. **T7-05 remainder** (CQ-006, CQ-007): lower the exception ceiling and remove silent swallows outside Opus-owned files; shrink the import allowlist.
6. **EVAL-003, EVAL-004 remainder:** point the legacy benchmarks at the serving lane, or label them as the dormant path.
7. **ADV-04:** retire or relabel the admin `eval-run` edge function.
8. **NEW-DQ-1, NEW-DQ-2:** a read-only `scripts/ops/fp_live_audit.py` whose output contains no text fields, and tests on local-mode Qdrant.
9. **NEW-LOAD-1, NEW-LOAD-2:** a Locust file for the staging load test, plus outcome and cost capture from `/internal/metrics`. Do not run it against any live system.
10. **T6-10 remainder** (PRD-010, UX-009, UX-011): copy changes are drafts for owner review. Do not merge copy that changes meaning without that review.

## 5. Decisions to ask the owner (give this context; do not assume answers)

| ID | Question | What it unblocks |
|---|---|---|
| D-26 | Qdrant on Railway with a volume, or Qdrant Cloud? | The Qdrant part of `.railway/railway.ts`; backups |
| D-14 | Which serving posture in staging (v8 bridge, or v10-only with both harness flags)? | Variables and the startup posture log |
| D-29 | How is staging access restricted (private domain, auth gate, tester list)? | Gate A21 |
| D-30 | Run Celery worker and beat in staging? | IaC services |
| D-PG13 | One scorer timeout: 25 s (code), 15 s (compose) or 12 s (CLAUDE.md)? | NEW-AI-3 value |
| D-PK8S1 | Kubernetes manifests: reference only, fix, or retire? | NEW-K8S-1/2 vs removal |
| D-24 | Lovable: PR-only with checks, retire, or design sandbox? | NEW-LOV-05; the bot's push rights |
| D-PA11Y6 | Approve `eslint-plugin-jsx-a11y` as a dev dependency? | Lint coverage for accessibility |

Owner-only steps to remind them of: copy the Qdrant snapshot off the Mac (DATA-01); turn on branch protection that also covers the Lovable bot (X-02, NEW-LOV-01); set the provider spend limit; set the Railway usage limit and alerts.

## 6. Definition of done and report

For each task: the failing-test output, the passing-test output, guard and formatter results, the commit SHA, the register row updated (old to new status), and what remains. Do not mark a Gate A item as passed: it needs a live Railway run. End with:
- a table of findings closed, partial and untouched
- the Opus-owned sites you skipped
- the decisions still needed
- the exact push result

Add a lesson to the top of `lessons.md` only for a proven, new failure mode. Use a unique ID (search first).
