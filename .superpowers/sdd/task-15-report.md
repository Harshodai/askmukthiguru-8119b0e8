# Task 15 Report: Nightly RLS CI Workflow

## Status: COMPLETE

## Files Changed
- **Created:** `.github/workflows/nightly-rls.yml`

## What Was Done
Added a nightly GitHub Actions workflow that runs the cross-user RLS verifier
(`backend/scripts/verify_rls_policies.py`) against the production Supabase
project, mirroring repo conventions from `.github/workflows/security-audit.yml`
and `.github/workflows/dependency-check.yml`:

- **Triggers:** `schedule` cron `'0 2 * * *'` (02:00 UTC nightly) + `workflow_dispatch` (manual).
- **Python setup:** `actions/setup-python@v5` with `python-version: '3.12'` — repo convention (security-audit.yml and dependency-check.yml both use 3.12; script's PEP 604 annotations need ≥3.10, so this is safe). Brief's suggested 3.11 deviates from repo convention.
- **Dependencies:** `pip install supabase requests` only — the script imports nothing else, avoiding a full heavy `requirements.txt` install.
- **Verifier run:** `python3 backend/scripts/verify_rls_policies.py` with `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` passed via repo secrets (`${{ secrets.* }}`). Nonzero script exit (policy breach) fails the job — no `|| true`.
- **Required repo secrets** (documented in header comment): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.

## Validation
- `python3 -c "yaml.safe_load(...)"` passes. Note: PyYAML 1.1 parses `on:` as boolean `True` — a known validator quirk, not a workflow bug; GitHub's own YAML parser handles `on:` correctly (all 9 existing workflows in this repo use `on:`).
- Asserted: cron value, `workflow_dispatch` key present, checkout@v4, setup-python@v5, install command, verifier command, and all 3 env vars reference `secrets.*` (no inline values).
- Not executed: `gh workflow run` (Step 2 of brief) — requires the workflow to exist on a branch GitHub can dispatch from and repo secrets to be configured; must be triggered from GitHub UI/CLI after merge. Sealed secrets must be set in the repo before the first scheduled run, or the job will fail with empty credentials (script fails fast with "missing env").

## Security Review of Verifier Script (flagged, not fixed — Task 4 owns the script)
- **Token logging: NONE found.** Reviewed all of `backend/scripts/verify_rls_policies.py`:
  - Keys are used only in request headers/payloads (`_request_headers`, `create_client`).
  - `_fail()` prints `SUPABASE_URL` (not a secret) in the healthcheck failure path; failure `details` come from `str(exc)` of `requests.RequestException`, which includes URLs but never auth headers. No `print`/`logging` of `SERVICE_KEY`, `ANON_KEY`, or bearer tokens anywhere.
- **FLAG for Task 4 / review:**
  1. The script creates two ephemeral test users (Alice/Bob) + seeded rows in **production** every night. Cleanup (row + user deletion) is wrapped in `try/except: pass` — a partial cleanup failure silently leaves test users/rows in prod.
  2. Test user password is a hardcoded constant (`"Password123!x"`); if prod's Supabase auth password policy requires more (length/complexity), user creation will fail and the job will report the breach.
  3. Test emails use `gmail.com` domain via `_make_test_email()`; if prod restricts allowed email domains, the same failure mode applies.
  4. No `concurrency` guard — overlapping manual + scheduled runs could collide on user creation (UUID-random emails make this unlikely, but worth noting).

## Handoff Notes
- Set repo secrets before first scheduled run (Runs: `secrets` → `Actions`):
  `SUPABASE_URL=https://ozmjeuqbholoxypfxixb.supabase.co`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
- To test immediately after merge: `gh workflow run nightly-rls.yml` then watch `gh run watch`.
