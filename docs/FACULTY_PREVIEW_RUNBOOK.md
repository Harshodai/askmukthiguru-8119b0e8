# Faculty preview runbook (2026-10-09)

What exists in code today for putting the app in front of faculty, what is proven, and what is not.
Nothing below was run against a live backend: Railway is stopped by decision. Items marked UNPROVEN have tests or config but no live run behind them.

## 1. Access gate (new)

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

Turn on for faculty: set `FACULTY_ACCESS_CODE` on the backend (generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(16))'`), build the frontend with `VITE_FACULTY_GATE_ENABLED=true`, share the code with faculty out of band. Turn off for real users by unsetting both.

Evidence: `backend/tests/test_faculty_gate.py` (11 tests: missing/wrong/right code, SSE streaming, health open, preflight, CORS on the 401) and `src/test/facultyAccess.test.tsx` (4 tests) pass. UNPROVEN: behaviour on the deployed stack behind Railway or Lovable, and whether any other client (mobile app, admin console) calls gated routes without the header; a gated build would break those until they send it. The `/api/auth/anon-session` and other routes outside the three prefixes are not gated.

Limit: one shared code, no per-person revocation. Rotate it after faculty feedback closes.

## 2. Cost caps (already in code; nothing changed here)

| Cap | Setting | Default | Behaviour |
| --- | --- | --- | --- |
| Global daily / monthly LLM spend (OpenRouter) | `OPENROUTER_DAILY_BUDGET_USD` / `OPENROUTER_MONTHLY_BUDGET_USD` | $10 / $100 | Redis reservation before each call, fail closed (`openrouter_budget_fail_closed`). Tests: `test_openrouter_budget.py`, `test_llm_budget_guard.py`. |
| Per-request ceiling | `OPENROUTER_MAX_REQUEST_COST_USD` | $0.03 | Same guard. |
| Per-user daily | `USER_DAILY_BUDGET_USD` | $0.50 | `CostTracker.is_user_over_budget`, 429 on `/api/chat`, `/api/chat/v2`, `/api/chat/stream`. Covers `anon:<session>` ids; the literal `anonymous` is exempt. **Fails open if Redis is down.** |
| Soft alert | `MONTHLY_COST_BUDGET_USD` | $36 | Alert/degrade flag only, not a hard cap. |

Decision still Harsha's: the hard monthly default ($100) is nearly 3x the $36 envelope the soft alert uses. Pick the number and set `OPENROUTER_MONTHLY_BUDGET_USD` explicitly in the deploy env. UNPROVEN live: none of these were exercised against real Redis in this pass.

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
