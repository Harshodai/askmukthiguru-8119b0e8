# Backup / Restore Drill Runbook

## Purpose

Verify that each stateful store has a real, readable backup and that a restore succeeds into an isolated, non-production target. A file existing on disk is not restore evidence.

This runbook distinguishes local Docker backups from hosted-service backups. Do not report a store as covered merely because a script or checklist exists.

## Coverage and current limitations

| Store | Backup mechanism | Restore evidence / limitation |
| --- | --- | --- |
| Qdrant | \`scripts/ops/backup_qdrant.py\` creates a collection snapshot, downloads it, verifies its checksum/archive, and performs a scratch-restore check. It sends \`QDRANT_WRITE_API_KEY\` (or \`QDRANT_API_KEY\`) when configured. | Restore into an isolated Qdrant instance/collection and compare point count, vector config and a sample scroll. A snapshot upload is asynchronous; wait for the collection to become green. |
| Memgraph | \`scripts/backup/snapshot_manager.py\` uses \`mgconsole\` and \`DUMP DATABASE;\`. New backups include SHA-256, node count and relationship count. | Restore only into an empty isolated Memgraph container using the same snapshot manager. It must reject a non-empty target. Verify both counts. \`scripts/ops/backup_neo4j.py\` is a legacy Neo4j/APOC/neo4j-admin utility; it is not the Memgraph backup path. |
| Redis | \`scripts/backup/redis_rdb_backup.py backup\` requests and waits for a completed \`BGSAVE\`, copies the configured RDB file from the Redis container, and writes/verifies a SHA-256 sidecar. | Restore manually into a fresh isolated Redis instance with AOF disabled, then verify Redis loads the RDB and key counts are plausible. The utility deliberately has no automatic restore command. This is not currently scheduled. |
| Local Supabase/Postgres | \`scripts/backup/snapshot_manager.py\` can export local Supabase container data only. It is a data-only seed export, not a complete roles + schema + data database backup. | Restore only into a disposable local Postgres/Supabase target and verify the selected tables. |
| Hosted Supabase/Postgres | \`.github/workflows/backup.yml\` is intended to dump roles, schema and data. | The workflow correctly fails while this GitHub repository is public, because unencrypted database dumps must not be stored as public workflow artifacts. Hosted database backup coverage is therefore **not verified** until a private encrypted destination is approved and the workflow completes. |
| Hosted Railway graph / Qdrant / Redis | No scheduled off-host backup has been verified from this repository state. | Do not infer coverage from local Docker backups. A Railway backup/restore drill and measured RPO/RTO remain open. |

The backup directory is gitignored. Never commit RDBs, database dumps, Qdrant snapshots, credentials or user data.

## Schedule

Run on the first Monday of each month. The GitHub Actions reminder opens at most one issue per UTC calendar month, including when manually dispatched. The automation creates a tracking issue; it does not run the restore drill.

## Prerequisites

- An isolated local Docker target or disposable cloud database project.
- Correct source environment values supplied through a local secret manager or shell environment.
- Docker access to the local Qdrant, Memgraph and Redis containers.
- Enough disk space for snapshots and scratch restores.
- Never point restore commands at a live production service.

## 1. Preflight

From the repository root:

\`\`\`bash
docker compose -f backend/docker-compose.yml ps
docker inspect mukthiguru-qdrant mukthiguru-memgraph mukthiguru-redis
\`\`\`

Record the exact image versions, source collection names, current Qdrant point counts, Memgraph node/relationship counts, and Redis \`DBSIZE\`. Confirm that the restore targets are separate from source containers and have separate volumes.

Do not run \`docker compose down -v\`, \`FLUSHALL\`, \`FLUSHDB\`, \`DROP DATABASE\`, or any restore command against the source services.

## 2. Create backups

### Qdrant

Run once for each collection that must be recoverable. Use the write-scoped key because snapshot creation requires write permission:

\`\`\`bash
QDRANT_URL="$QDRANT_URL" \
QDRANT_WRITE_API_KEY="$QDRANT_WRITE_API_KEY" \
python scripts/ops/backup_qdrant.py \
  --collection spiritual_wisdom_contextual \
  --retention 7
\`\`\`

Repeat for the active first-person serving and context collections declared by the current serving contract. Do not hardcode an old version such as v10 or v12.

Pass criteria: the script prints \`Backup verified\`, creates a \`.sha256\` sidecar, and its internal test restore succeeds. Record source point count and snapshot path.

### Memgraph

The comprehensive local snapshot manager also attempts Qdrant and local Supabase. For a graph-only backup:

\`\`\`bash
GRAPH_CONTAINER=mukthiguru-memgraph \
NEO4J_PASSWORD="$NEO4J_PASSWORD" \
python -c '
from scripts.backup.snapshot_manager import setup_directories, backup_neo4j
setup_directories()
raise SystemExit(0 if backup_neo4j() else 1)
'
\`\`\`

The output is stored under \`backups/neo4j/backup.cypher\` with a \`.sha256\` sidecar. The filename is retained for compatibility; the default graph engine is Memgraph.

Pass criteria: the output reports both node and relationship counts, a non-empty graph yields a non-empty dump, and a checksum sidecar is written.

### Redis

\`\`\`bash
REDIS_PASSWORD="$REDIS_PASSWORD" \
python scripts/backup/redis_rdb_backup.py backup \
  --container mukthiguru-redis \
  --output-dir backups/redis
\`\`\`

Verify the new artifact:

\`\`\`bash
python scripts/backup/redis_rdb_backup.py verify backups/redis/<artifact>.rdb
\`\`\`

Pass criteria: BGSAVE completes successfully, the RDB header is valid, and the SHA-256 sidecar matches. The helper does not claim a restore merely because the RDB header is present; the isolated restore below is still required.

### Local Supabase/Postgres

Only when the local Supabase stack is running:

\`\`\`bash
NEO4J_PASSWORD="$NEO4J_PASSWORD" \
QDRANT_URL="$QDRANT_URL" \
python scripts/backup/snapshot_manager.py backup
\`\`\`

This command also backs up the Qdrant collections declared by the serving configuration and the local graph. Its Supabase path is data-only and optional; it is not a substitute for the hosted roles/schema/data workflow.

## 3. Restore into isolated targets

### Qdrant

Use a separate Qdrant instance or a uniquely named scratch collection. Restore the snapshot with the upload endpoint using \`priority=snapshot\` and the write key. Wait until the collection reports green. Compare point count and vector dimensions with the recorded source values, then scroll a sample and verify payload/vector availability.

Do not restore over the live collection.

### Memgraph

Create an empty scratch Memgraph container and point the snapshot manager at it:

\`\`\`bash
GRAPH_CONTAINER=mukthiguru-memgraph-restore \
NEO4J_PASSWORD="$RESTORE_NEO4J_PASSWORD" \
python -c '
from scripts.backup.snapshot_manager import setup_directories, restore_neo4j
setup_directories()
raise SystemExit(0 if restore_neo4j() else 1)
'
\`\`\`

The restore implementation refuses to replay over a non-empty graph. A new-format backup is checked against its checksum, node count and relationship count. The scratch graph must match both counts. A populated target being left untouched is a **failed drill**, not a successful restore.

### Redis

Use a fresh, disposable Docker volume and Redis container. Do not copy the RDB into the running source Redis instance.

1. Verify the backup and checksum with \`redis_rdb_backup.py verify\`.
2. Copy the verified RDB to \`/data/dump.rdb\` in a fresh volume before starting a disposable Redis container.
3. Start that container with AOF disabled so Redis loads the RDB at startup.
4. Check startup logs for successful RDB loading, then run \`redis-cli DBSIZE\` and compare a bounded sample of expected keys.
5. Destroy only the scratch container and scratch volume after recording the result.

Do not treat Redis AOF, a running process, or the source \`redis_data\` volume as an independent backup artifact.

### Postgres

Restore local data-only exports only into a disposable local database with the matching schema already applied. For hosted Supabase, no restore drill is permitted until a complete private roles/schema/data artifact exists and its checksum has been verified.

## 4. Smoke tests after restore

| Check | Evidence required | Expected result |
| --- | --- | --- |
| Qdrant reachable | Health endpoint | HTTP success |
| Qdrant collection | Point count + vector config | Matches backup manifest |
| Qdrant sample | Scroll selected points | Payloads and vectors present |
| Memgraph reachable | Bolt query | Connected |
| Memgraph nodes | \`MATCH (n) RETURN count(n)\` | Exact manifest count |
| Memgraph relationships | \`MATCH ()-[r]->() RETURN count(r)\` | Exact manifest count |
| Redis reachable | \`redis-cli PING\` | \`PONG\` |
| Redis loaded | Startup log + \`DBSIZE\` | RDB load completed; plausible key count |
| Postgres reachable | \`pg_isready\` | Accepting connections |
| Critical tables | \`\\dt public.*\` and selected counts | Expected schema and plausible rows |
| Backend | \`GET /api/healthz\` | Healthy on the isolated stack |
| Frontend | Open local app | Page renders |
| Chat | One safe smoke question | Expected response from the isolated restored stack |

## 5. Backup freshness and evidence

Record per store:

- Backup timestamp and age.
- Source image/version and collection/database name.
- Artifact path, byte size and SHA-256.
- Source and restored counts.
- Restore target identity.
- Exact commands and exit statuses.
- Missing stores and reasons.

A missing backup or absent hosted backup is **FAIL / NOT COVERED**, not SKIPPED-as-success.

## 6. Log results in the monthly issue

\`\`\`markdown
## Backup/Restore Drill — YYYY-MM-DD

Engineer: @<handle>
Environment: <isolated local / disposable staging>

| Store | Backup artifact | SHA-256 | Restore result | Counts verified |
| --- | --- | --- | --- | --- |
| Qdrant | <path> | <hash> | PASS/FAIL | <points> |
| Memgraph | <path> | <hash> | PASS/FAIL | <nodes>/<relationships> |
| Redis | <path> | <hash> | PASS/FAIL | <keys> |
| Local Postgres | <path / absent> | <hash / n/a> | PASS/FAIL/NOT COVERED | <tables/rows> |
| Hosted Postgres | <artifact / blocked> | <hash / n/a> | PASS/FAIL/NOT COVERED | <tables/rows> |
| Railway stores | <evidence / absent> | <hash / n/a> | PASS/FAIL/NOT COVERED | <counts> |

### Smoke-test results
| Check | Result | Evidence |
| --- | --- | --- |
| Qdrant | PASS/FAIL | <count/config> |
| Memgraph | PASS/FAIL | <nodes/rels> |
| Redis | PASS/FAIL | <DBSIZE/log> |
| Postgres | PASS/FAIL/NOT COVERED | <tables> |
| Backend / frontend / chat | PASS/FAIL | <evidence> |

### Gaps and follow-up tickets
- <list>
\`\`\`

## Escalation

If any required local restore fails, stop and preserve logs. File a P1 operations issue. Do not close the monthly drill until the restore passes.

Hosted Supabase, Railway Qdrant/Memgraph/Redis, off-host storage and measured RPO/RTO remain explicit coverage gaps until separate backup artifacts and restore evidence exist.

## References

- \`docs/BACKUP_RESTORE.md\`
- \`scripts/backup/snapshot_manager.py\`
- \`scripts/backup/redis_rdb_backup.py\`
- \`scripts/ops/backup_qdrant.py\`
- \`.github/workflows/backup.yml\`
- \`.github/workflows/backup-drill-reminder.yml\`
- \`docs/runbooks/INCIDENT_RESPONSE.md\`
