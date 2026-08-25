# AskMukthiGuru Staging Security Verification Runbook

## Purpose and release posture

This runbook defines repeatable staging checks for runtime readiness, database migration safety, row-level security, adversarial HTTP behavior, and retrieval quality. It is designed for a dedicated staging environment containing synthetic test data only.

The package does not authorize production execution. The synthetic-user verifier creates and deletes test users and rows, so the target must be protected by the GitHub `staging` environment and the explicit environment guards below. A passing local run is useful engineering evidence, but is not staging or production evidence.

> **Rollback distinction:** Supabase migrations are forward-only history. The transaction-only rollback script proves that the SQL can be applied and rolled back before commit; it is not a production disaster-recovery restore drill and it does not create a down migration. A real staging rollback must use an approved snapshot/PITR restore or a reviewed, versioned compensating migration.

## Automation inventory

| Script or workflow | Purpose | Persistent application mutation | Target |
|---|---|---:|---|
| `scripts/ops/verify_migration_rollback.sh` | Applies the three latest grants/trigger migrations inside one transaction, asserts the schema contract, rolls back, and compares pre/post state | None; transaction is rolled back | Staging Postgres or disposable local Postgres |
| `backend/scripts/verify_rls_policies.py` | Creates randomized Alice/Bob users and owned rows, checks cross-user denial, then cleans up | Synthetic rows/users only | Local Supabase or dedicated staging Supabase |
| `scripts/ops/verify_runtime_gate.sh` | Checks health, required runtime artifacts, security headers, metrics auth, CORS, missing-asset 404, admin gating, and malformed chat behavior | None | Staging origin |
| `scripts/ops/verify_retrieval_gate.sh` | Runs strict Qdrant integration evaluation with `REQUIRE_QDRANT_EVAL=1` and protects the checked-in baseline | None by default | Approved staging Qdrant corpus |
| `scripts/ops/staging_red_team.sh` | Orchestrates the RLS and HTTP probes | Synthetic rows/users only | Dedicated staging only |
| `.github/workflows/staging-security-verification.yml` | Manual, environment-protected CI job that runs all gates and uploads evidence | Depends on scripts; no production target allowed | GitHub `staging` environment |

## One-time GitHub staging setup

Create a GitHub environment named `staging` and require reviewer approval before its secrets become available. Configure only staging values under that environment. Never put service-role keys, database passwords, Qdrant keys, or bearer tokens in repository files, workflow logs, issue comments, or shell transcripts.

| Secret | Meaning | Required safety condition |
|---|---|---|
| `STAGING_BASE_URL` | HTTPS origin of the staging application | HTTPS, or localhost for local rehearsal |
| `STAGING_DB_URL` | Percent-encoded Postgres connection string | Staging database only |
| `SUPABASE_URL` | Staging Supabase API URL | Must not be a production project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Staging-only setup/cleanup key | Never use it as a browser credential |
| `SUPABASE_ANON_KEY` | Staging anon key for user-scoped RLS probes | Must match the staging project |
| `QDRANT_URL` | Approved staging Qdrant endpoint | HTTPS, or local-only |
| `QDRANT_API_KEY` | Staging Qdrant credential | Minimum required scope; never print |
| `QDRANT_COLLECTION` | Collection matching the approved golden labels | Explicitly configured; no default assumption |

The workflow sets `STAGING_ENVIRONMENT=staging`, `ALLOW_STAGING_SYNTHETIC_USERS=1`, and `ALLOW_NONDESTRUCTIVE_DB_VERIFY=1`. Do not remove or weaken those guards.

## Safe local rehearsal

Use only disposable local Supabase. Start and reset it only when no other local test needs its state:

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
npx supabase start
npx supabase db reset --local --yes
```

Load local keys into the current process without printing them:

```bash
set -a
source <(npx supabase status --output env)
set +a
export SUPABASE_URL="${API_URL:-$SUPABASE_URL}"
export SUPABASE_ANON_KEY="${ANON_KEY:-$SUPABASE_ANON_KEY}"
export SUPABASE_SERVICE_ROLE_KEY="${SERVICE_ROLE_KEY:-$SUPABASE_SERVICE_ROLE_KEY}"
export STAGING_ENVIRONMENT=staging
export ALLOW_STAGING_SYNTHETIC_USERS=1
```

Run the transaction-only migration proof and synthetic-user RLS proof:

```bash
STAGING_ENVIRONMENT=staging \
ALLOW_NONDESTRUCTIVE_DB_VERIFY=1 \
STAGING_DB_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres' \
EVIDENCE_DIR=/tmp/askmukthi_audit/migration-rollback-local \
bash scripts/ops/verify_migration_rollback.sh

backend/.venv/bin/python backend/scripts/verify_rls_policies.py \
  > /tmp/askmukthi_audit/rls-verifier-local.json
```

Expected results are `rollback=state_unchanged`, `mutated_rows=0`, and a JSON RLS report with `ok: true` and `failures: 0`. Stop only this disposable stack afterward:

```bash
npx supabase stop
```

## Migration apply and rollback verification procedure

### Pre-apply snapshot and ledger check

Before a staging migration window, record a database snapshot or PITR marker according to the provider runbook. Record the migration ledger and schema fingerprint without printing credentials:

```bash
npx supabase migration list --db-url "$STAGING_DB_URL" > "$EVIDENCE_DIR/migration-list-before.txt"
psql "$STAGING_DB_URL" -X -v ON_ERROR_STOP=1 -At \
  -c "select version, name from supabase_migrations.schema_migrations order by version" \
  > "$EVIDENCE_DIR/migration-ledger-before.tsv"
```

Run the CLI dry-run first. The dry-run must report the expected migrations and must not apply them:

```bash
npx supabase db push --db-url "$STAGING_DB_URL" --dry-run \
  > "$EVIDENCE_DIR/db-push-dry-run.txt"
```

### Apply window

Apply through the approved staging migration mechanism, not by editing the migration ledger manually:

```bash
npx supabase db push --db-url "$STAGING_DB_URL" \
  > "$EVIDENCE_DIR/db-push-apply.txt"
npx supabase migration list --db-url "$STAGING_DB_URL" \
  > "$EVIDENCE_DIR/migration-list-after.txt"
```

Immediately run the transaction verifier, the migration source-contract tests, the synthetic-user RLS verifier, and the relevant authenticated application smoke tests. The new activity-grants migration is required because the first disposable RLS run found permission failures on `meditation_sessions` and `user_profiles`; after the fix, the local verifier passed all 12 probes.

### Rollback decision and recovery

If the apply or smoke phase fails, stop further writes, preserve evidence, and invoke the approved staging restore procedure. Do not run `DROP TABLE`, `TRUNCATE`, `supabase db reset`, or a guessed reverse SQL against a shared staging database. Restore the pre-apply snapshot/PITR target, verify the migration ledger and schema fingerprint, rerun the synthetic RLS probes, and record measured RPO/RTO. If a restore is unavailable, use a separately reviewed compensating migration with explicit ownership and an idempotency test; do not rewrite an already-applied migration file.

## Automated red-team checklist

Every row below is a release gate. A skipped check is not a pass and must be explained in the evidence register.

| Area | Automated attack or boundary | Pass condition | Fail action |
|---|---|---|---|
| Target safety | Run scripts against a non-staging URL or without explicit flags | Script exits before network/database mutation | Stop; inspect environment wiring |
| RLS read isolation | Bob selects Alice conversation, message, session, and profile rows | Empty result or policy denial | Block release; inspect grants and policies |
| RLS write isolation | Bob updates Alice rows | Zero updated rows or policy denial | Block release; inspect `USING` and `WITH CHECK` |
| RLS delete isolation | Bob deletes Alice rows | Zero deleted rows or policy denial | Block release; restore synthetic fixture if needed |
| Cleanup | Synthetic users and rows are removed | Cleanup succeeds and residual count is zero | Stop future runs; manually reconcile staging synthetic data |
| Admin gating | Unauthenticated request to `/api/admin/kpis` | 401/403 | Block release; review auth dependency |
| Metrics privacy | Unauthenticated request to `/api/metrics` | 401/403 and no sensitive body | Block release; inspect authorization and telemetry projection |
| CORS | Request with `Origin: https://evil.example` | Evil origin is not allowed | Block release; review allowlist |
| Asset integrity | Request to a definitely missing hashed asset | HTTP 404, not SPA HTML 200 | Block release; review static fallback rules |
| HTTP method surface | PUT/PATCH/DELETE against chat stream | 405/401/403/404/422 | Block release; review router method exposure |
| Malformed input | Empty JSON to chat stream | 400/401/403/422; no 500 | Block release; add validation regression |
| Runtime readiness | `/api/health` and required artifact fields | `ready=true`, `readiness_ok=true`, no required missing artifacts | Block release; fix image/artifact packaging |
| Security headers | Health response headers | CSP, frame, MIME, referrer, and permissions controls present | Block release; fix edge config |
| Retrieval availability | Qdrant endpoint, collection, points, and golden labels | Strict test runs, not skipped | Block release; do not lower thresholds or manufacture corpus |
| Retrieval quality | Dense, hybrid, and reranked NDCG plus baseline regression | All configured thresholds pass | Block release; investigate corpus/retrieval change |
| Prompt injection | Malicious instructions in user text and retrieved content | System rules remain authoritative; no secret/prompt leakage | Block release; preserve adversarial fixture |
| Crisis safety | Acute self-harm and ambiguous distress prompts | Crisis path is deterministic, bounded, and provider-failure safe | Block release; safety takes precedence over availability |
| Upload/SSRF | Oversized, wrong-type, malformed, and private-network URLs | Rejected or safely bounded; no internal egress | Block release; inspect parser and network guards |
| Replay/idempotency | Duplicate callback/job/migration invocation | No duplicate user-visible side effect | Block release; inspect idempotency key and transaction boundary |
| Observability | Correlated request, queue, model, token, and error fields | Metadata-only traces are queryable without sensitive content | Block release; add alert/runbook coverage |

## Runtime gate commands

From the repository root, run the exact local static gates first:

```bash
bash -n scripts/ops/verify_runtime_gate.sh \
  scripts/ops/verify_retrieval_gate.sh \
  scripts/ops/verify_migration_rollback.sh \
  scripts/ops/staging_red_team.sh

git diff --check
npm run lint
npm run typecheck
npm test -- --run
backend/.venv/bin/python -m ruff check backend
backend/.venv/bin/python -m bandit -r backend --ini backend/.bandit -ll
backend/.venv/bin/python -m compileall -q backend/app backend/services backend/ingest
```

Against staging, run only with approved staging environment variables:

```bash
export STAGING_BASE_URL='https://staging.example.invalid'
export EVIDENCE_DIR="/tmp/askmukthi_audit/staging-$(date -u +%Y%m%dT%H%M%SZ)"
export STAGING_ENVIRONMENT=staging
export ALLOW_STAGING_SYNTHETIC_USERS=1

bash scripts/ops/verify_runtime_gate.sh
bash scripts/ops/staging_red_team.sh
```

The runtime script fails closed on missing required artifact readiness, missing security headers, public metrics/admin access, permissive CORS, missing-asset SPA fallback, or a 500-class malformed chat response.

## Retrieval gate commands

The retrieval gate requires explicit staging Qdrant variables and is read-only by default:

```bash
export QDRANT_URL='https://staging-qdrant.example.invalid'
export QDRANT_COLLECTION='spiritual_wisdom'
export STAGING_QDRANT_API_KEY='load-this-from-your-secret-manager'
export QDRANT_API_KEY="$STAGING_QDRANT_API_KEY"
export EVIDENCE_DIR="/tmp/askmukthi_audit/retrieval-$(date -u +%Y%m%dT%H%M%SZ)"
export UPDATE_QDRANT_BASELINE=0

bash scripts/ops/verify_retrieval_gate.sh
```

The underlying strict command is:

```bash
REQUIRE_QDRANT_EVAL=1 UPDATE_QDRANT_BASELINE=0 \
backend/.venv/bin/python -m pytest -q -m integration \
  backend/tests/test_qdrant_search_quality.py
```

Do not accept a skip as a pass. The test intentionally fails when the collection is empty or when sampled source labels do not intersect the approved golden set. Baseline authoring is a separate, reviewed action:

```bash
UPDATE_QDRANT_BASELINE=1 \
backend/.venv/bin/python -m pytest -q -m integration \
  backend/tests/test_qdrant_search_quality.py
```

That command must never run automatically in the staging verification workflow.

## Canonical repository loop

Run the repository loop with evidence outside the checkout so it does not add generated evidence to the commit:

```bash
FULL_BACKEND=1 \
LOOP_EVIDENCE_DIR="/tmp/askmukthi_audit/canonical-$(date -u +%Y%m%dT%H%M%SZ)" \
UPDATE_QDRANT_BASELINE=0 \
bash scripts/ops/loop_validate.sh
```

The acceptance condition is `LOOP_RESULT=PASS`, zero nonzero non-skipped gates, and an unchanged SHA-256 for `memory/qdrant_quality_baseline.json`.

## Evidence format and retention

Each run should preserve a machine-readable summary with target, source revision, start/end timestamps, gate name, exit status, sanitized endpoint identity, and evidence paths. Never store secret values or full user content. Retain staging evidence for the period defined by the incident/audit policy and retain failure artifacts longer when they are needed for release analysis.

Minimum evidence files are:

```text
migration-list-before.txt
migration-list-after.txt
migration-transaction.result
migration-rollback.result.json
rls-verifier.json
runtime/health.json
runtime/health.headers
runtime/metrics.status
runtime/admin.status
runtime/missing-asset.status
retrieval/retrieval-gate.log
summary.tsv
```

## Current implementation evidence and limits

The newly added local proof passed the transaction-only migration rollback check and all 12 synthetic-user RLS probes after the `meditation_sessions` and `user_profiles` grants migration was added. The latest canonical repository loop passed with **2,420 passed, 30 skipped, and one known `langchain_text_splitters` stub warning**. Frontend checks passed with 512 tests and 31 non-blocking lint warnings.

These results do not prove staging readiness. The staging Qdrant corpus, required runtime artifacts, provider/worker fault behavior, clean capacity and cost envelope, restore/RPO/RTO, and native mobile/push/audio paths still require authorized environment-specific evidence.
