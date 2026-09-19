#!/usr/bin/env bash
#
# Migrate the local graph into the Railway graph service.
#
# Bolt (7687) is NOT routable from outside Railway's private network, so this
# requires a TCP proxy on the graph service first. Create one ONCE:
#
#     railway link --project resilient-embrace --service gb-neo4j-railway-template
#     # then, via the Railway dashboard or MCP: create a TCP proxy on port 7687
#
# The proxy gives you a host:port on *.proxy.rlwy.net. Pass it as RAILWAY_BOLT.
# Remove the proxy after the migration -- it exposes the database to the internet.
#
# Usage:
#     RAILWAY_BOLT=host:port RAILWAY_GRAPH_PASSWORD=... \
#         backend/scripts/ops/railway_graph_migrate.sh
#
# Env:
#     RAILWAY_BOLT              required, "host:port" from the TCP proxy
#     RAILWAY_GRAPH_USER        default "neo4j"
#     RAILWAY_GRAPH_PASSWORD    required
#     SOURCE_BOLT               default "bolt://localhost:7687"
#     SOURCE_USER               default "neo4j"
#     SOURCE_PASSWORD           default "mukthiguru_neo4j_pass"
#     DUMP                      default "backups/neo4j/graph_dump_<utc>.json"
#     ALLOW_NONEMPTY_TARGET     set to 1 to import into a target that already has data

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT/backend"

PY="${PY:-.venv/bin/python}"
MIGRATE="$PY -m scripts.ops.migrate_neo4j_to_memgraph"

: "${RAILWAY_BOLT:?set RAILWAY_BOLT to the TCP proxy host:port}"
: "${RAILWAY_GRAPH_PASSWORD:?set RAILWAY_GRAPH_PASSWORD}"
RAILWAY_GRAPH_USER="${RAILWAY_GRAPH_USER:-neo4j}"
SOURCE_BOLT="${SOURCE_BOLT:-bolt://localhost:7687}"
SOURCE_USER="${SOURCE_USER:-neo4j}"
SOURCE_PASSWORD="${SOURCE_PASSWORD:-mukthiguru_neo4j_pass}"
DUMP="${DUMP:-backups/neo4j/graph_dump_$(date -u +%Y%m%dT%H%M%SZ).json}"
TARGET_URI="bolt://${RAILWAY_BOLT}"

echo "==> source: $SOURCE_BOLT"
echo "==> target: $TARGET_URI"
echo "==> dump:   $DUMP"

echo
echo "==> [1/5] export source"
$MIGRATE export --uri "$SOURCE_BOLT" --user "$SOURCE_USER" \
    --password "$SOURCE_PASSWORD" --output "$DUMP"

echo
echo "==> [2/5] refuse to overwrite a populated target"
# A Railway graph that already holds data is either a completed migration or a
# different dataset. Either way, importing on top of it silently merges two graphs.
EXISTING="$($MIGRATE verify --uri "$TARGET_URI" --user "$RAILWAY_GRAPH_USER" \
    --password "$RAILWAY_GRAPH_PASSWORD" 2>&1 | grep -oE '[0-9]+ nodes' | head -1 | cut -d' ' -f1)"
if [ "${EXISTING:-0}" -gt 0 ] && [ "${ALLOW_NONEMPTY_TARGET:-0}" != "1" ]; then
    echo "REFUSING: target already holds $EXISTING nodes." >&2
    echo "Re-run with ALLOW_NONEMPTY_TARGET=1 only if you intend to merge into it." >&2
    exit 2
fi

echo
echo "==> [3/5] import into target (idempotent, retry-safe)"
$MIGRATE import --uri "$TARGET_URI" --user "$RAILWAY_GRAPH_USER" \
    --password "$RAILWAY_GRAPH_PASSWORD" --input "$DUMP"

echo
echo "==> [4/5] verify target against dump"
if ! $MIGRATE verify --uri "$TARGET_URI" --user "$RAILWAY_GRAPH_USER" \
    --password "$RAILWAY_GRAPH_PASSWORD" --against "$DUMP"; then
    echo >&2
    echo "VERIFY FAILED. Migration markers are still in place, so re-running this" >&2
    echo "script (or just the import step) will repair the gap. NOT finalizing." >&2
    exit 1
fi

echo
echo "==> [5/5] finalize (strip migration markers)"
$MIGRATE finalize --uri "$TARGET_URI" --user "$RAILWAY_GRAPH_USER" \
    --password "$RAILWAY_GRAPH_PASSWORD"

echo
echo "==> done. Dump retained at $DUMP"
echo "==> REMINDER: remove the Railway TCP proxy now -- it exposes Bolt publicly."
