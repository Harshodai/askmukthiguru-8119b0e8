# Backup / Restore Drill Runbook

## Purpose

Verify monthly that critical project data in the `backups/` subdirectories can be restored and that the application still passes basic smoke tests after restore. This runbook also defines the issue template used by the monthly GitHub Actions reminder.

## Scope

The drill covers all backup subdirectories under `backups/`:

- `backups/supabase/` — Postgres logical dumps (`pg_dump`), schema-only exports, table-level exports.
- `backups/qdrant/` — Qdrant collection snapshot files and vector metadata exports.
- `backups/neo4j/` — Neo4j dump files produced by `neo4j-admin dump`.
- `backups/redis/` — Redis `SAVE`/`BGSAVE` `.rdb` dumps.
- `backups/s3/` *(if used)* — Object-storage manifests / critical bucket exports.

If a subdirectory does not exist in a given deployment, the drill still verifies that the absence is intentional and documented.

## Schedule

Run the drill on the first Monday of every month. The GitHub Actions workflow `.github/workflows/backup-drill-reminder.yml` opens a tracking issue automatically.

## Prerequisites

- Access to a non-production restore target (local Docker Compose stack, staging Railway environment, or an isolated cloud Postgres/Qdrant/Neo4j instance).
- Read access to the backup storage location (local disk, S3 bucket, Railway volume, etc.).
- Current `.env` or environment overrides for the restore target.

## Step-by-Step Procedure

### 1. Prepare the restore target

1.1. Spin up a clean restore environment matching the production versions documented in `docker-compose.yml` or Railway service config.

1.2. Confirm service endpoints and credentials are isolated from production. Use non-production ports/hostnames only.

### 2. Restore each backup type

#### Supabase / Postgres

```bash
# Schema-only restore (run first to create objects)
psql -h <restore-host> -U <restore-user> -d <restore-db> -f backups/supabase/schema_<date>.sql

# Data restore for selected critical tables (adjust list as schema evolves)
pg_restore -h <restore-host> -U <restore-user> -d <restore-db> --data-only \
  -t chat_sessions -t chat_messages -t user_profiles -t user_brain_nodes \
  backups/supabase/data_<date>.dump
```

If restore fails on ownership or extensions, fix with:

```sql
ALTER SCHEMA public OWNER TO <restore-user>;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
```

#### Qdrant

```bash
# Restore a collection snapshot into the target Qdrant instance
curl -X POST "http://<restore-qdrant>:6333/collections/<collection_name>/snapshots/upload" \
  -H "api-key: <restore-key>" \
  -F "snapshot=@backups/qdrant/<collection_name>_<date>.snapshot"
```

Verify collection count and vector dimensions:

```bash
curl "http://<restore-qdrant>:6333/collections/<collection_name>" -H "api-key: <restore-key>"
```

#### Neo4j

```bash
# Stop the target Neo4j container, then load the dump
neo4j-admin load --from=backups/neo4j/neo4j_<date>.dump --database=neo4j --force
```

Restart the target Neo4j service and run a smoke Cypher query:

```cypher
MATCH (n) RETURN count(n) AS nodes;
```

#### Redis

```bash
# Stop target Redis, replace .rdb, restart
sudo systemctl stop redis
sudo cp backups/redis/dump_<date>.rdb /var/lib/redis/dump.rdb
sudo systemctl start redis
redis-cli ping
```

### 3. Smoke tests after restore

Run these checks and record results in the monthly issue:

| Check | Command / Step | Expected result |
| --- | --- | --- |
| Postgres reachable | `pg_isready -h <host>` | `accepting connections` |
| Critical tables present | `\dt public.*` in `psql` | Core tables exist |
| Row counts plausible | `SELECT count(*) FROM chat_sessions;` | Non-negative, matches backup metadata |
| Qdrant healthy | `GET /` on `:6333` | `status: "ok"` |
| Collection count | `GET /collections/<name>` | Matches source |
| Neo4j reachable | `bolt` ping or browser | Connected |
| Node count | `MATCH (n) RETURN count(n)` | Plausible |
| Redis reachable | `redis-cli ping` | `PONG` |
| Backend health | `GET http://localhost:8000/api/health` | `ready: true` |
| Frontend serves | Open `http://localhost` | Page loads, no blank screen |
| Sign-in page renders | Open `/auth` | Form visible |
| Chat query returns | POST `/api/chat` with test query | 200 and non-empty response |

### 4. Validate backup freshness

Confirm each backup used in the drill is no older than the retention window:

- Postgres: 7 days for daily, 30 days for weekly, 90 days for monthly.
- Qdrant snapshots: same as Postgres.
- Neo4j: weekly.
- Redis: daily (`.rdb` written by `save` config).

If any backup is stale, file an ops issue immediately.

### 5. Log results

Append a result block to the monthly tracking issue created by the reminder workflow:

```markdown
## Backup/Restore Drill — YYYY-MM-DD

Engineer: @<handle>
Environment: <local/staging>

### Restored
- [ ] Postgres schema
- [ ] Postgres data (critical tables)
- [ ] Qdrant snapshot(s)
- [ ] Neo4j dump
- [ ] Redis RDB

### Smoke-test results
| Check | Result |
| --- | --- |
| Postgres reachable | PASS / FAIL |
| Critical tables present | PASS / FAIL |
| Row counts plausible | PASS / FAIL |
| Qdrant healthy | PASS / FAIL |
| Collection count | PASS / FAIL |
| Neo4j reachable | PASS / FAIL |
| Node count | PASS / FAIL |
| Redis reachable | PASS / FAIL |
| Backend health | PASS / FAIL |
| Frontend serves | PASS / FAIL |
| Sign-in page | PASS / FAIL |
| Chat query returns | PASS / FAIL |

### Issues found
- <none / list>

### Follow-up tickets
- #<issue>
```

## Escalation

If any restore step fails or smoke tests do not pass:

1. Stop the drill and preserve logs.
2. File a P1 incident issue with label `ops` and `backup`.
3. Do not mark the monthly reminder issue as complete until the root cause is fixed and the drill is re-run.

## References

- `docs/runbooks/INCIDENT_RESPONSE.md`
- `docs/runbooks/SECRET_ROTATION.md`
- `.github/workflows/backup-drill-reminder.yml`
