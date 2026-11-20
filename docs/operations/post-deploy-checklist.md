# Post-deploy checklist

Run these in order for every Railway deploy. Each guard exits non-zero on failure and never
prints a secret. They exist because each failure below happened at least once (lessons.md,
2026-11-19).

| # | When | Command (from `backend/`) | Catches |
|---|---|---|---|
| 1 | Before setting variables | `.venv/bin/python scripts/ops/validate_production_env.py --env-file proposed.env --current-env-file current.env` | `IS_PRODUCTION=false`, `ENABLE_TEST_AUTH=true`, loopback / `host.docker.internal` / bare service-name hosts, the local Supabase demo key, and overwriting `BRAIN_KEK`, JWT or Supabase keys on a service that already holds data. `current.env` is the target service's current variables (`railway variables --kv > current.env`, kept out of git). Rotate a protected secret through `BRAIN_KEK_NEXT` + `scripts/ops/rotate_brain_kek.py`. Never overwrite it. |
| 2 | Before deploy | `.venv/bin/python scripts/ops/check_schema_drift.py --applied-versions applied.txt` | A repo migration that was never applied, an applied migration that is missing from the repo, and a row model (`UserProfile(**row)`) whose fields have no column. Build `applied.txt` read-only with `psql "$SUPABASE_DB_URL" -At -c 'select version from supabase_migrations.schema_migrations' > applied.txt` (`-At` drops the header and footer lines). Add `--live-columns cols.json` to check against the live `information_schema` instead of the migrations. |
| 3 | CI (every PR) | `.venv/bin/pytest tests/test_cors_allows_spa_headers_2026_11_19.py` | A custom request header the SPA sends that the production CORS allow-list does not allow. The browser preflight fails and the UI only shows "failed (—)". |
| 4 | Before deploy | `QDRANT_API_KEY=… FIRST_PERSON_COLLECTION=… FIRST_PERSON_CONTEXT_COLLECTION=… .venv/bin/python scripts/ops/check_qdrant_token_scope.py` | A collection in the serving config that the backend's scoped Qdrant JWT cannot read, or an expired token. Every turn would abstain. |
| 5 | After deploy | `make verify-stack-fresh` (local) / Railway deploy health `/api/healthz` | A stale image or container. |
| 6 | After deploy | `.venv/bin/python scripts/ops/live_smoke_battery.py https://<backend-host>` | healthz, CORS from the Lovable origin, closed admin/metrics/docs, crisis helpline, jailbreak and out-of-corpus refusal, an in-domain serve-rate floor (10 questions), a follow-up floor (6 conversations), and a Hindi turn. About 30 chat turns (cost: about 30 times the per-turn cost recorded in lessons.md). Run it once per deploy; do not loop it on production. |
| 7 | After deploy | `.venv/bin/python scripts/ops/railway_answer_smoke.py https://<backend-host>` | The faculty-demo questions. |

The cold-start wait (the first request after sleep can take 25–40 s) is covered by
`tests/test_railway_cold_start_wait.py`, and the smoke battery polls for up to 120 s.

Exit codes: 0 pass, 1 guard failed, 2 usage error (drift checker). A failure blocks the deploy.
Write the cause into `lessons.md` before you retry.

## Deploy and rollback steps (merged from the 2026-11-19 runbook draft)

1. After the owner pushes `main`, re-attach the backend to the new commit (Railway
   `connect-service-source` with `commitSha`; the backend is pinned to a commit, so nothing
   deploys otherwise), then redeploy the backend and the `celery-worker` so new variables apply.
2. Run rows 5-7 above against the backend host (not the Lovable host, which serves the SPA).
3. Publish the Lovable project (GitHub is already synced to the same commit) and check that
   the chat page loads.
4. Manual spot checks: one Hindi message answers (no error); a suicidal-intent message gets
   the helpline only, no teacher clip; "What is the capital of France?" abstains with no
   citations; `/second-brain` initializes without a 500.
5. Rollback: re-attach the previous commit SHA, redeploy, then repeat rows 5-7 and step 4.
