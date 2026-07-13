#!/usr/bin/env bash
# ============================================================================
# MASTER DEPLOYMENT SCRIPT: askmukthiguru → Railway + Lovable
# ============================================================================
# Run: chmod +x deploy_all.sh && ./deploy_all.sh
# ============================================================================

set -euo pipefail

# ─── Colors ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()    { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
success(){ echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $*"; }
warn()   { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${NC} $*"; }
error()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*"; }

# ─── Config ────────────────────────────────────────────────────────────────
LOVABLE_DOMAIN="https://askmukthiguru.lovable.app"
PROJECT_DIR="/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8"
LOG_FILE="$PROJECT_DIR/deploy_all_$(date +%Y%m%d_%H%M%S).log"

# ─── Helpers ───────────────────────────────────────────────────────────────
# Run command as argument array (no eval). Log a redacted representation.
run() {
    local redacted=()
    for arg in "$@"; do
        case "$arg" in
            *=*)
                local key="${arg%%=*}"
                case "$key" in
                    *SECRET*|*PASSWORD*|*TOKEN*|*KEY*|*PASS*|*AUTH*|*PRIVATE*)
                        redacted+=("${key}=***REDACTED***")
                        ;;
                    *)
                        redacted+=("$arg")
                        ;;
                esac
                ;;
            *)
                redacted+=("$arg")
                ;;
        esac
    done
    log "${redacted[*]}"
    "$@" 2>&1 | tee -a "$LOG_FILE"
}
require() { command -v "$1" >/dev/null || { error "Missing: $1"; exit 1; }; }

# Redact sensitive values from a string for safe logging
redact() {
    local s="$1"
    s="${s//JWT_SECRET=*/JWT_SECRET=***REDACTED***}"
    s="${s//NEO4J_PASSWORD=*/NEO4J_PASSWORD=***REDACTED***}"
    s="${s//REDIS_PASSWORD=*/REDIS_PASSWORD=***REDACTED***}"
    s="${s//PGPASSWORD=*/PGPASSWORD=***REDACTED***}"
    s="${s//SUPABASE_KEY=*/SUPABASE_KEY=***REDACTED***}"
    s="${s//OPENROUTER_API_KEY=*/OPENROUTER_API_KEY=***REDACTED***}"
    s="${s//SARVAM_API_KEY=*/SARVAM_API_KEY=***REDACTED***}"
    s="${s//NIM_API_KEY=*/NIM_API_KEY=***REDACTED***}"
    printf '%s\n' "$s"
}

log_safe() { log "$(redact "$*")"; }

# Check if service exists
service_exists() {
    railway service list --json 2>/dev/null | jq -e ".[] | select(.name == \"$1\")" >/dev/null 2>&1
}

# Get service ID by name
get_service_id() {
    railway service list --json 2>/dev/null | jq -r ".[] | select(.name == \"$1\") | .id" | head -1
}

# Get variable from specific service
get_var_from_service() {
    local var=$1 service=$2
    railway variables get "$var" --service "$service" 2>/dev/null || echo ""
}

# ─── Pre-flight ────────────────────────────────────────────────────────────
cd "$PROJECT_DIR"
log "=== MASTER DEPLOYMENT STARTED ===" | tee "$LOG_FILE"
log "Project: $PROJECT_DIR" | tee -a "$LOG_FILE"
log "Log: $LOG_FILE" | tee -a "$LOG_FILE"

require railway
require docker
require curl
require openssl
require jq

# Check Railway login
if ! railway whoami >/dev/null 2>&1; then
    error "Not logged in to Railway. Run: railway login"
    exit 1
fi

# ─── PHASE 1: RAILWAY SERVICES (idempotent) ────────────────────────────────
log "=== PHASE 1: Provision Railway Services ==="

# Postgres via 'railway add --database'
if service_exists "Postgres"; then
    success "Postgres already exists"
else
    log "Adding PostgreSQL..."
    run "railway add --database postgres"
    sleep 10
fi

# Redis via 'railway add --database'
if service_exists "Redis"; then
    success "Redis already exists"
else
    log "Adding Redis..."
    run "railway add --database redis"
    sleep 10
fi

# Neo4j via template
if service_exists "gb-neo4j-railway-template" || service_exists "neo4j"; then
    success "Neo4j already exists"
else
    log "Adding Neo4j (template)..."
    run "railway deploy --template neo4j"
    sleep 15
fi

# Qdrant via template
if service_exists "qdrant"; then
    success "Qdrant already exists"
else
    log "Adding Qdrant (template)..."
    run "railway deploy --template qdrant"
    sleep 15
fi

# Wait for all services to be ready
log "Waiting for services to be ready..."
sleep 20

# ─── PHASE 2: EXTRACT CREDENTIALS FROM EACH SERVICE ────────────────────────
log "=== PHASE 2: Extract Credentials ==="

# Get service names (use actual deployed names)
NEO4J_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("neo4j|Neo4j")) | .name' | head -1)
POSTGRES_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Postgres|postgres")) | .name' | head -1)
QDRANT_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("qdrant|Qdrant")) | .name' | head -1)
REDIS_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Redis|redis")) | .name' | head -1)

log "Service names detected:"
echo "  Neo4j: ${NEO4J_SVC:-not found}"
echo "  Postgres: ${POSTGRES_SVC:-not found}"
echo "  Qdrant: ${QDRANT_SVC:-not found}"
echo "  Redis: ${REDIS_SVC:-not found}" | tee -a "$LOG_FILE"

# Extract credentials from each service
NEO4J_PASSWORD=$(get_var_from_service NEO4J_PASSWORD "$NEO4J_SVC")
[[ -z "$NEO4J_PASSWORD" ]] && NEO4J_PASSWORD=$(get_var_from_service NEO4J_PASSWORD "neo4j")
[[ -z "$NEO4J_PASSWORD" ]] && NEO4J_PASSWORD=$(get_var_from_service NEO4J_AUTH "$NEO4J_SVC" | cut -d'/' -f2)

REDIS_PASSWORD=$(get_var_from_service REDIS_PASSWORD "$REDIS_SVC")
[[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(get_var_from_service REDISPASSWORD "$REDIS_SVC")
[[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(get_var_from_service REDIS_AUTH "$REDIS_SVC")

PGHOST=$(get_var_from_service PGHOST "$POSTGRES_SVC")
[[ -z "$PGHOST" ]] && PGHOST=$(get_var_from_service POSTGRES_HOST "$POSTGRES_SVC")
[[ -z "$PGHOST" ]] && PGHOST=$(get_var_from_service RAILWAY_PRIVATE_DOMAIN "$POSTGRES_SVC")

PGPORT=$(get_var_from_service PGPORT "$POSTGRES_SVC")
[[ -z "$PGPORT" ]] && PGPORT=$(get_var_from_service POSTGRES_PORT "$POSTGRES_SVC")
[[ -z "$PGPORT" ]] && PGPORT="5432"

PGDATABASE=$(get_var_from_service PGDATABASE "$POSTGRES_SVC")
[[ -z "$PGDATABASE" ]] && PGDATABASE=$(get_var_from_service POSTGRES_DB "$POSTGRES_SVC")
[[ -z "$PGDATABASE" ]] && PGDATABASE="postgres"

PGUSER=$(get_var_from_service PGUSER "$POSTGRES_SVC")
[[ -z "$PGUSER" ]] && PGUSER=$(get_var_from_service POSTGRES_USER "$POSTGRES_SVC")
[[ -z "$PGUSER" ]] && PGUSER="postgres"

PGPASSWORD=$(get_var_from_service PGPASSWORD "$POSTGRES_SVC")
[[ -z "$PGPASSWORD" ]] && PGPASSWORD=$(get_var_from_service POSTGRES_PASSWORD "$POSTGRES_SVC")

# Qdrant URL
QDRANT_URL=$(get_var_from_service QDRANT_URL "$QDRANT_SVC")
[[ -z "$QDRANT_URL" ]] && QDRANT_URL=$(get_var_from_service RAILWAY_SERVICE_QDRANT_URL "$QDRANT_SVC")

log "Credentials extracted:"
log_safe "  NEO4J_PASSWORD: ${NEO4J_PASSWORD:-(not set - will generate)}"
log_safe "  REDIS_PASSWORD: ${REDIS_PASSWORD:-(not set - will generate)}"
log "  PGHOST: ${PGHOST:-(not set)}"
log "  PGDATABASE: ${PGDATABASE:-(not set)}"
log "  PGUSER: ${PGUSER:-(not set)}"
log_safe "  QDRANT_URL: ${QDRANT_URL:-(not set)}" | tee -a "$LOG_FILE"

# Generate if missing (never log the generated values)
[[ -z "$NEO4J_PASSWORD" ]] && NEO4J_PASSWORD=$(openssl rand -hex 16) && log_safe "Generated NEO4J_PASSWORD"
[[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(openssl rand -hex 16) && log_safe "Generated REDIS_PASSWORD"
[[ -z "$PGPASSWORD" ]] && PGPASSWORD=$(openssl rand -hex 16) && log_safe "Generated PGPASSWORD"

# ─── PHASE 3: SET ENVIRONMENT VARIABLES ────────────────────────────────────
log "=== PHASE 3: Set Environment Variables ==="

set_var() {
    local key=$1 value=$2
    if railway variables get "$key" >/dev/null 2>&1; then
        warn "$key already set"
    else
        run "railway variables set $key=\"$value\""
    fi
}

# Core
JWT_SECRET=$(openssl rand -hex 32)
set_var JWT_SECRET "$JWT_SECRET"
set_var CORS_ORIGINS "$LOVABLE_DOMAIN"
set_var LLM_PROVIDER "openrouter"
set_var GUARDRAILS_PROVIDER "lightweight"
set_var WEB_CONCURRENCY "1"
set_var PYTHON_MEMORY_LIMIT_MB "2048"

# Models
set_var SARVAM_CLOUD_MODEL "sarvam-30b"
set_var EMBEDDING_MODEL "BAAI/bge-m3"
set_var RERANKER_MODEL "BAAI/bge-reranker-v2-m3"

# Service URLs (internal Railway DNS)
if [[ -n "$NEO4J_PASSWORD" && -n "$NEO4J_SVC" ]]; then
    set_var NEO4J_URI "bolt://${NEO4J_SVC}.railway.internal:7687"
    set_var NEO4J_USER "neo4j"
    set_var NEO4J_PASSWORD "$NEO4J_PASSWORD"
elif [[ -n "$NEO4J_PASSWORD" && -z "$NEO4J_SVC" ]]; then
    warn "NEO4J_PASSWORD set but NEO4J_SVC not detected — set NEO4J_URI manually after deploy"
fi

if [[ -n "$REDIS_PASSWORD" && -n "$REDIS_SVC" ]]; then
    set_var REDIS_URL "redis://:${REDIS_PASSWORD}@${REDIS_SVC}.railway.internal:6379/0"
elif [[ -n "$REDIS_PASSWORD" && -z "$REDIS_SVC" ]]; then
    warn "REDIS_PASSWORD set but REDIS_SVC not detected — set REDIS_URL manually after deploy"
fi

if [[ -n "$PGHOST" && -n "$PGPASSWORD" && -n "$PGUSER" && -n "$PGDATABASE" ]]; then
    set_var SUPABASE_URL "postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
else
    warn "Postgres credentials incomplete — set SUPABASE_URL manually after deploy"
fi

if [[ -n "$QDRANT_URL" ]]; then
    set_var QDRANT_URL "$QDRANT_URL"
else
    set_var QDRANT_URL "http://${QDRANT_SVC}.railway.internal:6333"
fi

# API Keys (user must provide if not already set)
for key in OPENROUTER_API_KEY SARVAM_API_KEY NIM_API_KEY SUPABASE_KEY; do
    if ! railway variables get "$key" >/dev/null 2>&1; then
        warn "$key NOT SET — set in Railway dashboard after deploy"
    fi
done

# ─── PHASE 4: DEPLOY BACKEND ───────────────────────────────────────────────
log "=== PHASE 4: Deploy Backend ==="
run "railway up --detach"

# ─── PHASE 5: CELERY WORKER ────────────────────────────────────────────────
log "=== PHASE 5: Create Celery Worker ==="
if service_exists "celery-worker"; then
    warn "celery-worker already exists"
else
    log "Creating celery-worker service..."
    run "railway add --service celery-worker --json"
    success "celery-worker service created — configure Dockerfile/command in Railway dashboard"
    warn "In Railway dashboard: celery-worker → Settings → Dockerfile: backend/Dockerfile, Start Command: celery -A celery_config worker --loglevel=info --queues=transcription,embedding,indexing,ingestion,okf --concurrency=1"
fi

# ─── PHASE 6: GET URLs & HEALTH CHECK ──────────────────────────────────────
log "=== PHASE 6: Get URLs & Health Check ==="
run "railway domain"

BACKEND_URL=$(railway domain --service askmukthiguru-8119b0e8 2>/dev/null | grep -oE 'https://[^ ]+' | head -1)
if [[ -z "$BACKEND_URL" ]]; then
    BACKEND_URL=$(railway domain 2>/dev/null | grep -oE 'https://[^ ]+' | head -1)
fi

log "Backend URL: $BACKEND_URL"

if [[ -n "$BACKEND_URL" ]]; then
    log "Waiting for health endpoint..."
    for i in {1..20}; do
        if curl -sf "$BACKEND_URL/api/health" >/dev/null 2>&1; then
            success "Backend healthy!"
            break
        else
            warn "Attempt $i/20: waiting..."
            sleep 15
        fi
    done
fi

# ─── PHASE 7: DATA MIGRATION SCRIPT ────────────────────────────────────────
log "=== PHASE 7: Data Migration Prep ==="

cat > "$PROJECT_DIR/migrate_data.sh" <<'MIGRATE_EOF'
#!/usr/bin/env bash
# Data Migration Script - Run AFTER Railway services are healthy

set -euo pipefail

# Use explicit Docker binary path per project standards
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
export DOCKER_CONFIG=".docker_clean"

LOG="migrate_$(date +%Y%m%d_%H%M%S).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ─── Neo4j ────────────────────────────────────────────────────────────────
log "=== Neo4j: Dump & Import ==="
docker exec mukthiguru-neo4j neo4j-admin database dump neo4j --to-path=/data/dumps 2>&1 | tee -a "$LOG"
docker cp mukthiguru-neo4j:/data/dumps/neo4j.dump ./neo4j.dump 2>&1 | tee -a "$LOG"
log "→ Upload neo4j.dump via Railway Neo4j Browser (LOAD DATABASE neo4j FROM 'neo4j.dump' OVERWRITE)"

# ─── Qdrant ───────────────────────────────────────────────────────────────
log "=== Qdrant: Snapshot & Upload ==="
curl -X POST http://localhost:6333/collections/spiritual_wisdom/snapshots 2>&1 | tee -a "$LOG"
sleep 5
SNAPSHOT=$(curl -s http://localhost:6333/collections/spiritual_wisdom/snapshots | jq -r '.result[-1].name')
curl "http://localhost:6333/collections/spiritual_wisdom/snapshots/$SNAPSHOT" -o qdrant_snapshot.snapshot 2>&1 | tee -a "$LOG"
log "→ Upload qdrant_snapshot.snapshot via Railway Qdrant API"

# ─── PostgreSQL ───────────────────────────────────────────────────────────
log "=== PostgreSQL: Dump & Restore ==="
docker exec supabase_db_fynkjimvuimakgtidvuq pg_dump -U postgres -d postgres --no-owner --no-acl > supabase_dump.sql 2>&1 | tee -a "$LOG"
log "→ Restore: psql \"postgresql://...\" < supabase_dump.sql"

# ─── Redis ────────────────────────────────────────────────────────────────
log "=== Redis: BGSAVE & Restore ==="
# Use REDISCLI_AUTH env var instead of hardcoded password
# Set REDISCLI_AUTH=mukthiguru_redis_pass before running, or export from env
docker exec mukthiguru-redis redis-cli -a "${REDISCLI_AUTH:-}" BGSAVE 2>&1 | tee -a "$LOG"
sleep 5
docker cp mukthiguru-redis:/data/dump.rdb ./redis_dump.rdb 2>&1 | tee -a "$LOG"
log "→ Restore: redis-cli -h your-redis.railway.internal -p 6379 -a \$REDISCLI_AUTH --rdb ./redis_dump.rdb"

log "=== Migration scripts ready. Run manually after verifying Railway services. ==="
MIGRATE_EOF

chmod +x "$PROJECT_DIR/migrate_data.sh"
success "Created migrate_data.sh"

# ─── PHASE 8: LOVABLE SETUP GUIDE ──────────────────────────────────────────
log "=== PHASE 8: Lovable Configuration ==="

cat > "$PROJECT_DIR/lovable_setup.md" <<LOVABLE_EOF
# Lovable Setup for askmukthiguru

## 1. Set API URL
1. Open https://askmukthiguru.lovable.app
2. Settings → Environment Variables
3. Add: \`VITE_API_URL = $BACKEND_URL\`
4. Click "Deploy"

## 2. Verify Connection
- Open browser devtools → Network
- Send a chat message
- Verify request goes to $BACKEND_URL/api/chat

## 3. Custom Domain (if purchased via Lovable)
- Settings → Domains → Add custom domain
- Follow DNS instructions (CNAME to lovable.app)

## 4. Credits
- Pro plan: 20 credits/month + 5 daily
- Each deploy uses ~1-5 credits
- Monitor: Settings → Credit Usage
LOVABLE_EOF

success "Created lovable_setup.md"

# ─── PHASE 9: SUMMARY ──────────────────────────────────────────────────────
log "=== DEPLOYMENT COMPLETE ===" | tee -a "$LOG_FILE"
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                    DEPLOYMENT SUMMARY                                 ║"
echo "╠════════════════════════════════════════════════════════════════════════╣"
echo "║ Backend URL:     $BACKEND_URL"
echo "║ Railway Project: resilient-embrace"
echo "║ Log File:        $LOG_FILE"
echo "╠════════════════════════════════════════════════════════════════════════╣"
echo "║ NEXT STEPS (MANUAL):                                                  ║"
echo "╠════════════════════════════════════════════════════════════════════════╣"
echo "║ 1. Set API keys in Railway Dashboard:                                ║"
echo "║    OPENROUTER_API_KEY, SARVAM_API_KEY, NIM_API_KEY, SUPABASE_KEY     ║"
echo "║ 2. Run data migration:                                               ║"
echo "║    ./migrate_data.sh                                                 ║"
echo "║ 3. Configure Lovable:                                                ║"
echo "║    Open https://askmukthiguru.lovable.app → Settings → Env Vars      ║"
echo "║    VITE_API_URL = $BACKEND_URL"
echo "║    Deploy                                                            ║"
echo "║ 4. Test end-to-end:                                                  ║"
echo "║    curl $BACKEND_URL/api/health"
echo "║    Send chat message from Lovable UI                                 ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"

# Save summary
cat > "$PROJECT_DIR/DEPLOYMENT_SUMMARY.txt" <<EOF
Backend URL: $BACKEND_URL
Railway Project: resilient-embrace
Deployed: $(date)
Log: $LOG_FILE

Next Steps:
1. Set API keys in Railway Dashboard
2. Run ./migrate_data.sh
3. Configure Lovable VITE_API_URL=$BACKEND_URL
4. Test end-to-end
EOF

success "All done! Summary saved to DEPLOYMENT_SUMMARY.txt"
success "Run: ./migrate_data.sh  (after setting API keys)"
success "Read: lovable_setup.md"