# Faculty preview runbook (updated 2026-11-22)

What exists in code today for putting the app in front of faculty, what is proven, and what is not.
Nothing below was run against a live backend: Railway is stopped by decision. Items marked UNPROVEN have tests or config but no live run behind them.

## 1. Access gate and reviewer identity

**Current release verdict: NO-GO.** A shared passcode was never a faculty
identity system (everyone who knew it was indistinguishable and could not be
individually revoked), and it has been removed.

The faculty-label surface requires either the trusted JWT claim
`app_metadata.role = "faculty_reviewer"` or an existing admin (a row in
`public.user_roles`, checked with `has_role(auth.uid(), 'admin')`, the same
mechanism as the admin console). Migrations
`20261122000000_faculty_labels_reviewer_role.sql` and, superseding it,
`20261128120000_faculty_labels_admin_role.sql` (owner decision 2026-11-28; NOT
yet applied, owner approval needed) make that predicate and
`auth.uid() = user_id` mandatory at the database row-security boundary. The
client-side role check is only a visibility convenience; it is not authority.
The migration has focused static tests, but has **not** been applied or proven
against a disposable or hosted Supabase database in this run.

Before any controlled beta, an owner must:

1. create isolated, named test accounts and obtain their consent;
2. use an admin account for review, or, only if a non-admin reviewer is needed,
   set the reviewer claim with the Supabase admin API (never `user_metadata`);
3. apply the migration to staging and prove allow/deny/revocation with two
   reviewer/admin identities and one ordinary signed-in identity;
4. record the migration version, test date, and revocation result; and
5. give teachers and volunteers only the role and synthetic packet they need.


### Passcode gate removed (2026-11-28)

The shared passcode gate (`FACULTY_ACCESS_CODE`, `X-Faculty-Code`, the browser
passcode screen) was removed by owner decision. Faculty reviewers sign in with
Google like any user; abuse is bounded by per-identity rate limits and the cost
caps below.

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
