# Faculty preview runbook (updated 2026-11-22)

What exists in code today for putting the app in front of faculty, what is proven, and what is not.
Nothing below was run against a live backend: Railway is stopped by decision. Items marked UNPROVEN have tests or config but no live run behind them.

## 1. Access gate and reviewer identity

**Current release verdict: NO-GO.** The older passcode gate below is a useful
traffic/cost throttle, but it is not a faculty identity system: everyone who
knows its value is indistinguishable and cannot be individually revoked. It
must never be the sole control for teachers, volunteers, or reviewers.

The faculty-label surface now requires the trusted JWT claim
`app_metadata.role = "faculty_reviewer"`, and migration
`20261122000000_faculty_labels_reviewer_role.sql` makes the same claim and
`auth.uid() = user_id` mandatory at the database row-security boundary. The
client-side role check is only a visibility convenience; it is not authority.
The migration has focused static tests, but has **not** been applied or proven
against a disposable or hosted Supabase database in this run.

Before any controlled beta, an owner must:

1. create isolated, named test accounts and obtain their consent;
2. set the reviewer claim with the Supabase admin API (never `user_metadata`);
3. apply the migration to staging and prove allow/deny/revocation with two
   reviewer identities and one ordinary signed-in identity;
4. record the migration version, test date, and revocation result; and
5. give teachers and volunteers only the role and synthetic packet they need.

Do not set `FACULTY_GATE_DISABLED=true` as a shortcut around these controls.
It disables the traffic gate; it does not establish a permitted cohort.

### Legacy passcode traffic gate

Two halves, both off by default.

| Half | Switch | Where |
| --- | --- | --- |
| Server (the real lock) | `FACULTY_ACCESS_CODE` in the backend env | `backend/app/middleware/faculty_gate.py`, wired in `backend/app/main.py` |
| Browser (collects the code) | `VITE_FACULTY_GATE_ENABLED=true` at build time | `src/components/common/FacultyAccessGate.tsx`, `src/lib/facultyAccess.ts` |

Behaviour:
- With the server code set, `/api/chat*`, `/api/first-person*` and `/api/jobs*` return 401 unless the request carries `X-Faculty-Code: <code>`. This happens before any retrieval or LLM call, so a stranger who finds the URL cannot spend money.
- `/api/health`, `/api/healthz`, metrics and CORS preflights stay open. The 401 carries CORS headers, so the browser can read it.
- The browser build shows a passcode screen, checks the code against the backend, keeps it in `sessionStorage` (cleared when the tab closes) and adds the header to backend requests.
- The frontend flag alone protects nothing: the Vite bundle is public. Always set the server code too. Never put the code in a `VITE_*` variable.

If it is retained for a short, isolated staging exercise, set
`FACULTY_ACCESS_CODE` on the backend and build with
`VITE_FACULTY_GATE_ENABLED=true`. Treat it only as an outer traffic gate; do
not distribute it as reviewer authorization and do not use it to grant access
to labels or user data. Turn it off for real users by unsetting both.

Evidence: `backend/tests/test_faculty_gate.py` (11 tests: missing/wrong/right code, SSE streaming, health open, preflight, CORS on the 401) and `src/test/facultyAccess.test.tsx` (4 tests) pass. UNPROVEN: behaviour on the deployed stack behind Railway or Lovable, and whether any other client (mobile app, admin console) calls gated routes without the header; a gated build would break those until they send it. The `/api/auth/anon-session` and other routes outside the three prefixes are not gated.

Limit: one shared code, no per-person revocation. Rotate it after any exposure.

## 2. Cost caps (already in code; nothing changed here)

| Cap | Setting | Default | Behaviour |
| --- | --- | --- | --- |
| Global daily / monthly LLM spend (OpenRouter) | `OPENROUTER_DAILY_BUDGET_USD` / `OPENROUTER_MONTHLY_BUDGET_USD` | $10 / $40 (lowered from $100 on 2026-10-09, Harsha delegated the call) | Redis reservation before each call, fail closed (`openrouter_budget_fail_closed`). Tests: `test_openrouter_budget.py`, `test_llm_budget_guard.py`. |
| Per-request ceiling | `OPENROUTER_MAX_REQUEST_COST_USD` | $0.03 | Same guard. |
| Per-user daily | `USER_DAILY_BUDGET_USD` | $0.50 | `CostTracker.is_user_over_budget`, 429 on `/api/chat`, `/api/chat/v2`, `/api/chat/stream`. Covers `anon:<session>` ids; the literal `anonymous` is exempt. **Fails open if Redis is down.** |
| Soft alert | `MONTHLY_COST_BUDGET_USD` | $36 | Alert/degrade flag only, not a hard cap. |

Hard monthly default is now $40 (soft alert stays at $36). Still set `OPENROUTER_MONTHLY_BUDGET_USD` explicitly in the deploy env so the cap is deliberate, not inherited. UNPROVEN live: none of these were exercised against real Redis in this pass.

## 3. Supabase backup and restore

Already documented and scheduled: `docs/BACKUP_RESTORE.md` ("Supabase Postgres Free Path" and "Supabase Restore Procedure") and `.github/workflows/backup.yml` (daily dump via the Supabase CLI).
- Requires the `SUPABASE_DB_URL` repository secret. The workflow fails loudly when it is missing. Whether the secret is set, and whether a dump has ever succeeded, was not checked here: UNPROVEN.
- A restore drill into a scratch database has not been recorded. Do one before real users: download the latest artifact, restore into a throwaway project following the doc, run `backend/scripts/ops/audit_supabase_readiness.py` against it, and write the date and result below.

| Date | Dump artifact | Restored into | audit_supabase_readiness result | By |
| --- | --- | --- | --- | --- |
| (none yet) | | | | |

Free plan has no platform backups or PITR (checked 2026-09-14, not re-checked). Upgrading is Harsha's call.

## 4. RLS cross-user e2e without secrets

`tests/e2e/rls-cross-user.spec.ts` needs a real Supabase. `scripts/prelaunch.sh` fails it loudly when none is reachable, which is why the Pre-launch gate went red on every PR. The workflow now starts a throwaway local stack (`supabase start`, migrations from `supabase/migrations`) and passes its keys to the spec, so no repository secrets are used and no real project is touched (`.github/workflows/prelaunch-gate.yml`).

UNPROVEN: this workflow change has not run. First run may expose a migration that does not apply on a clean local database, or runner time/disk limits. If it fails there, the failure is real information about the migrations; do not skip the spec. The nightly staging check (`nightly-rls.yml`) still needs its staging secrets and is unchanged.

## Only Harsha can do
Name the content reviewer; phone-confirm helplines; supply audio rights evidence; sign off outcome claims; choose where the backend runs and set the secrets above; run the Mac pushes; decide the hard monthly cap; do the restore drill and record it.
