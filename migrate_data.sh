#!/usr/bin/env bash
# Data Migration Script - Run AFTER Railway services are healthy

set -euo pipefail
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
LOG="migrate_$(date +%Y%m%d_%H%M%S).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ─── Neo4j ────────────────────────────────────────────────────────────────
log "=== Neo4j: Dump & Import ==="
docker exec mukthiguru-neo4j neo4j-admin database dump neo4j --to-path=/data/dumps 2>&1 | tee -a "$LOG"
docker cp mukthiguru-neo4j:/data/dumps/neo4j.dump ./neo4j.dump 2>&1 | tee -a "$LOG"
log "→ Upload neo4j.dump via Railway Neo4j Browser (LOAD DATABASE neo4j FROM 'neo4j.dump' OVERWRITE)"

# ─── Qdrant ───────────────────────────────────────────────────────────────
log "=== Qdrant: Snapshot & Upload ==="
SNAPSHOT_RESPONSE=$(curl --fail-with-body -X POST http://localhost:6333/collections/spiritual_wisdom/snapshots 2>&1 | tee -a "$LOG")
SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESPONSE" | jq -r '.result.name // .result.snapshot.name // empty')
if [[ -z "$SNAPSHOT_NAME" ]]; then
  log "ERROR: Failed to extract snapshot name from response: $SNAPSHOT_RESPONSE"
  exit 1
fi
log "Created snapshot: $SNAPSHOT_NAME"

curl --fail-with-body "http://localhost:6333/collections/spiritual_wisdom/snapshots/$SNAPSHOT_NAME" -o qdrant_snapshot.snapshot 2>&1 | tee -a "$LOG"
log "→ Upload qdrant_snapshot.snapshot via Railway Qdrant API"
log "→ Upload qdrant_snapshot.snapshot via Railway Qdrant API"

# ─── PostgreSQL ───────────────────────────────────────────────────────────
log "=== PostgreSQL: Dump & Restore ==="
docker exec supabase_db_fynkjimvuimakgtidvuq pg_dump -U postgres -d postgres --no-owner --no-acl > supabase_dump.sql 2>>"$LOG"
log "PostgreSQL dump completed, saved to supabase_dump.sql"
log "→ Restore: psql \"postgresql://...\" < supabase_dump.sql"

# ─── Redis ────────────────────────────────────────────────────────────────
log "=== Redis: BGSAVE & Restore ==="
if [[ -z "${REDISCLI_AUTH:-}" ]]; then
  log "ERROR: REDISCLI_AUTH environment variable not set. Set it to your Redis password."
  exit 1
fi
export REDISCLI_AUTH
log "Capturing baseline LASTSAVE before BGSAVE..."
BASELINE_SAVE=$(docker exec -e REDISCLI_AUTH mukthiguru-redis redis-cli LASTSAVE 2>&1 | tail -1)
docker exec -e REDISCLI_AUTH mukthiguru-redis redis-cli BGSAVE 2>&1 | tee -a "$LOG"
log "Waiting for BGSAVE to complete..."
BGSAVE_DEADLINE=120
BGSAVE_ELAPSED=0
while [[ $BGSAVE_ELAPSED -lt $BGSAVE_DEADLINE ]]; do
  CURRENT_SAVE=$(docker exec -e REDISCLI_AUTH mukthiguru-redis redis-cli LASTSAVE 2>&1 | tail -1)
  if [[ "$CURRENT_SAVE" != "$BASELINE_SAVE" ]]; then
    log "BGSAVE completed successfully (lastsave: $CURRENT_SAVE)"
    break
  fi
  log "BGSAVE in progress... (lastsave: $CURRENT_SAVE)"
  sleep 2
  BGSAVE_ELAPSED=$((BGSAVE_ELAPSED + 2))
done

if [[ "$CURRENT_SAVE" == "$BASELINE_SAVE" ]]; then
  log "ERROR: BGSAVE did not produce a new LASTSAVE within ${BGSAVE_DEADLINE}s"
  exit 1
fi
docker cp mukthiguru-redis:/data/dump.rdb ./redis_dump.rdb 2>&1 | tee -a "$LOG"
log "→ Restore: redis-cli -h your-redis.railway.internal -p 6379 --rdb ./redis_dump.rdb"

log "=== Migration scripts ready. Run manually after verifying Railway services. ==="