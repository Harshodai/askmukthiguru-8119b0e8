#!/usr/bin/env bash
# Railway Deployment Script for askmukthiguru
# Run: chmod +x deploy_railway.sh && ./deploy_railway.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
success() { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${NC} $*"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*"; }

DO_CLEAN=false
DO_REBUILD=false
WITH_WORKER=false
DRY_RUN=false

show_help() {
    echo "Usage: ./deploy_railway.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean              Run workspace cleanup and purge stale Redis caches/locks before deploy"
    echo "  --rebuild            Full clean rebuild (workspace cleanup, cache flush, Celery queue purge, cache-busting build)"
    echo "  --with-worker        Deploy/start the Celery worker (default: OFF to stay under \$25 budget ceiling)"
    echo "  --worker-pause       Pause the Celery worker on Railway to save compute"
    echo "  --worker-resume      Resume/start the Celery worker on Railway"
    echo "  --prune-deployments  Clean up dead/failed deployments in Railway history"
    echo "  --check-budget       Run Railway budget burn-rate check against the \$25 hard limit"
    echo "  --dry-run            Simulate operations without making changes"
    echo "  --help               Show this help message"
    echo ""
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean)
            DO_CLEAN=true
            shift
            ;;
        --rebuild)
            DO_REBUILD=true
            DO_CLEAN=true
            shift
            ;;
        --with-worker)
            WITH_WORKER=true
            shift
            ;;
        --worker-pause)
            python3 scripts/ops/railway_cleanup.py --worker-action pause
            exit $?
            ;;
        --worker-resume)
            python3 scripts/ops/railway_cleanup.py --worker-action resume
            exit $?
            ;;
        --prune-deployments)
            python3 scripts/ops/railway_cleanup.py --mode deployments
            exit $?
            ;;
        --check-budget)
            python3 scripts/ops/railway_cleanup.py --check-budget
            exit $?
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            error "Unknown argument: $1. Run with --help for usage."
            exit 1
            ;;
    esac
done

# Check Railway CLI
if ! command -v railway &> /dev/null; then
    error "Railway CLI not installed. Run: npm i -g @railway/cli"
    exit 1
fi

# Check linked project
if ! railway status &> /dev/null; then
    error "Not linked to Railway project. Run: railway link"
    exit 1
fi

log "=== Railway Deployment Started ==="
if [[ "$DO_REBUILD" == true ]]; then
    log "Mode: REBUILD (Full state & workspace cleanup enabled)"
elif [[ "$DO_CLEAN" == true ]]; then
    log "Mode: CLEAN DEPLOY (Workspace & cache cleanup enabled)"
fi

# Pre-flight cleanup
if [[ "$DO_CLEAN" == true ]]; then
    log "Running pre-flight workspace and state cleanup..."
    CLEAN_ARGS=("--mode" "all")
    if [[ "$DO_REBUILD" == true ]]; then
        CLEAN_ARGS+=("--purge-celery")
    fi
    if [[ "$DRY_RUN" == true ]]; then
        CLEAN_ARGS+=("--dry-run")
    fi
    python3 scripts/ops/railway_cleanup.py "${CLEAN_ARGS[@]}" || warn "Cleanup finished with warnings"
fi

# 1. Add Services (use Railway's supported template deployment command)
# Graph database selection: "memgraph" (default, lightweight C++, ~80MB) or "neo4j" (legacy JVM, ~1GB+)
GRAPH_DB="${GRAPH_DB:-memgraph}"
services=("qdrant" "postgresql" "redis")
if [[ "$GRAPH_DB" == "memgraph" ]]; then
    services=("memgraph" "${services[@]}")
else
    services=("neo4j" "${services[@]}")
fi

for svc in "${services[@]}"; do
    log "Adding service: $svc"
    if railway service list | grep -q "$svc"; then
        warn "$svc already exists, skipping"
    elif [[ "$svc" == "memgraph" ]]; then
        # Deploy Memgraph using MAGE docker image with 512MB RAM limit
        log "Deploying Memgraph (memgraph/memgraph-mage:latest)..."
        railway add --service memgraph --image memgraph/memgraph-mage:latest 2>&1 | tee -a railway_deploy.log || \
        railway deploy --template memgraph 2>&1 | tee -a railway_deploy.log || warn "Could not add memgraph template automatically, verify in dashboard"
        success "Memgraph service added"
        sleep 10
    else
        railway deploy --template "$svc" 2>&1 | tee -a railway_deploy.log
        success "$svc added"
        sleep 10
    fi
done

# 2. Get generated credentials
log "Fetching generated credentials..."
railway variables 2>&1 > /dev/null

# Discover deployed service names so we can target the right vault per service
MEMGRAPH_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("memgraph|Memgraph")) | .name' | head -1)
NEO4J_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("neo4j|Neo4j")) | .name' | head -1)
POSTGRES_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Postgres|postgres|postgresql")) | .name' | head -1)
REDIS_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Redis|redis")) | .name' | head -1)

# Helper to fetch a variable from a specific service
get_var() {
    local var=$1 service=$2
    railway variables get "$var" --service "$service" 2>/dev/null || echo ""
}

# Extract key variables from the services that own them
GRAPH_PASSWORD=""
if [[ -n "$MEMGRAPH_SVC" ]]; then
    GRAPH_PASSWORD=$(get_var MEMGRAPH_PASSWORD "$MEMGRAPH_SVC")
    [[ -z "$GRAPH_PASSWORD" ]] && GRAPH_PASSWORD=$(get_var NEO4J_PASSWORD "$MEMGRAPH_SVC")
    [[ -z "$GRAPH_PASSWORD" ]] && GRAPH_PASSWORD="mukthiguru_neo4j_pass"
fi
if [[ -z "$GRAPH_PASSWORD" && -n "$NEO4J_SVC" ]]; then
    GRAPH_PASSWORD=$(get_var NEO4J_PASSWORD "$NEO4J_SVC")
    [[ -z "$GRAPH_PASSWORD" ]] && GRAPH_PASSWORD=$(get_var NEO4J_PASSWORD "neo4j")
    [[ -z "$GRAPH_PASSWORD" ]] && GRAPH_PASSWORD=$(get_var NEO4J_AUTH "$NEO4J_SVC" | cut -d'/' -f2)
fi
NEO4J_PASSWORD="$GRAPH_PASSWORD"

REDIS_PASSWORD=$(get_var REDIS_PASSWORD "$REDIS_SVC")
[[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(get_var REDISPASSWORD "$REDIS_SVC")
[[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(get_var REDIS_AUTH "$REDIS_SVC")

PGHOST=$(get_var PGHOST "$POSTGRES_SVC")
[[ -z "$PGHOST" ]] && PGHOST=$(get_var POSTGRES_HOST "$POSTGRES_SVC")
[[ -z "$PGHOST" ]] && PGHOST=$(get_var RAILWAY_PRIVATE_DOMAIN "$POSTGRES_SVC")

PGPORT=$(get_var PGPORT "$POSTGRES_SVC")
[[ -z "$PGPORT" ]] && PGPORT=$(get_var POSTGRES_PORT "$POSTGRES_SVC")
[[ -z "$PGPORT" ]] && PGPORT="5432"

PGDATABASE=$(get_var PGDATABASE "$POSTGRES_SVC")
[[ -z "$PGDATABASE" ]] && PGDATABASE=$(get_var POSTGRES_DB "$POSTGRES_SVC")
[[ -z "$PGDATABASE" ]] && PGDATABASE="postgres"

PGUSER=$(get_var PGUSER "$POSTGRES_SVC")
[[ -z "$PGUSER" ]] && PGUSER=$(get_var POSTGRES_USER "$POSTGRES_SVC")
[[ -z "$PGUSER" ]] && PGUSER="postgres"

PGPASSWORD=$(get_var PGPASSWORD "$POSTGRES_SVC")
[[ -z "$PGPASSWORD" ]] && PGPASSWORD=$(get_var POSTGRES_PASSWORD "$POSTGRES_SVC")

log "Extracted credentials:"
echo "  NEO4J_PASSWORD: $([[ -n ${NEO4J_PASSWORD:-} ]] && echo "configured" || echo "(not set)")"
echo "  REDIS_PASSWORD: $([[ -n ${REDIS_PASSWORD:-} ]] && echo "configured" || echo "(not set)")"
echo "  PGHOST: ${PGHOST:-(not set)}"

# 3. Set environment variables
log "Setting environment variables..."

# Core secrets (only set if not already present)
set_var() {
    local key=$1
    local value=$2
    if railway variables get "$key" &>/dev/null; then
        warn "$key already set, skipping"
    else
        railway variables set "$key=$value" > /dev/null 2>&1
        success "Set $key"
    fi
}

# Generate strong secrets
JWT_SECRET=$(openssl rand -hex 32)

set_var JWT_SECRET "$JWT_SECRET"
set_var CORS_ORIGINS "https://askmukthiguru.lovable.app"
set_var LLM_PROVIDER "openrouter"
set_var GUARDRAILS_PROVIDER "lightweight"
set_var WEB_CONCURRENCY "1"
set_var PYTHON_MEMORY_LIMIT_MB "2048"

# Quantized Models (ONNX INT8)
set_var EMBEDDING_BACKEND "onnx_int8"
set_var RERANKER_BACKEND "onnx_int8"
set_var EMBEDDING_MODEL "BAAI/bge-m3"
set_var EMBEDDING_DIMENSION "1024"
set_var RERANKER_MODEL "cross-encoder/ms-marco-MiniLM-L-6-v2"
set_var SARVAM_CLOUD_MODEL "sarvam-30b"
set_var QDRANT_COLLECTION "spiritual_wisdom_contextual"

# Service URLs (internal Railway DNS)
if [[ -n "$MEMGRAPH_SVC" ]]; then
    set_var NEO4J_URI "bolt://${MEMGRAPH_SVC}.railway.internal:7687"
    set_var MEMGRAPH_URI "bolt://${MEMGRAPH_SVC}.railway.internal:7687"
    set_var NEO4J_USER "neo4j"
    set_var NEO4J_PASSWORD "${NEO4J_PASSWORD:-mukthiguru_neo4j_pass}"
    set_var LIGHTRAG_GRAPH_STORAGE "MemgraphStorage"
elif [[ -n "$NEO4J_PASSWORD" || -n "$NEO4J_SVC" ]]; then
    set_var NEO4J_URI "bolt://neo4j.railway.internal:7687"
    set_var NEO4J_USER "neo4j"
    set_var NEO4J_PASSWORD "$NEO4J_PASSWORD"
    set_var LIGHTRAG_GRAPH_STORAGE "Neo4JStorage"
fi

if [[ -n "$REDIS_PASSWORD" ]]; then
    set_var REDIS_URL "redis://:${REDIS_PASSWORD}@redis.railway.internal:6379/0"
fi

if [[ -n "$PGHOST" && -n "$PGPASSWORD" ]]; then
    set_var PGHOST "$PGHOST"
    set_var PGPORT "$PGPORT"
    set_var PGDATABASE "$PGDATABASE"
    set_var PGUSER "$PGUSER"
    set_var PGPASSWORD "$PGPASSWORD"
fi

# SUPABASE_URL must be set manually to your Supabase project URL (https://xxx.supabase.co)

# API Keys - USER MUST SET THESE MANUALLY
log "Checking API keys (must be set manually if missing)..."
for key in OPENROUTER_API_KEY SARVAM_API_KEY NIM_API_KEY SUPABASE_KEY; do
    if ! railway variables get "$key" &>/dev/null; then
        warn "$key NOT SET - set in Railway dashboard or: railway variables set $key=your_key"
    fi
done

# Auto-tune Redis memory policy to avoid OOM or expensive database tier upgrades
log "Tuning Redis memory policy (256MB maxmemory, volatile-lru eviction)..."
python3 scripts/ops/railway_cleanup.py --tune-redis 2>/dev/null || true

# 4. Deploy Backend
log "Deploying backend..."
if [[ "$DRY_RUN" == true ]]; then
    log "[DRY RUN] Would trigger: railway up --detach"
else
    railway up --detach > /dev/null 2>&1
    success "Backend deployment triggered"
fi

# 5. Celery Worker (Opt-in to protect $25 budget ceiling)
if [[ "$WITH_WORKER" == true ]]; then
    log "Deploying celery-worker service (--with-worker requested)..."
    if railway service list | grep -q "celery-worker"; then
        warn "celery-worker already exists, deploying..."
        railway up --service celery-worker --detach > /dev/null 2>&1 || warn "Could not deploy celery-worker"
        success "celery-worker updated and deployed"
    else
        # Use supported `railway add --service` flow
        if railway add --service celery-worker > /dev/null 2>&1; then
            railway variable set --service celery-worker SERVICE_TYPE=celery > /dev/null 2>&1
            railway up --service celery-worker --detach > /dev/null 2>&1
            success "celery-worker created and deployed"
        else
            error "Failed to create celery-worker service"
            exit 1
        fi
    fi
else
    log "ℹ️  Celery worker deployment skipped by default to save idle compute costs (stays under \$25 budget ceiling)."
    log "    To deploy/run the worker on demand: ./deploy_railway.sh --with-worker or make railway-worker-resume"
fi

# 6. Get URLs
log "Fetching service URLs..."
railway domain > /dev/null 2>&1

# 7. Health Check
BACKEND_URL=$(railway domain --service askmukthiguru-8119b0e8 2>/dev/null | grep -oE 'https://[^ ]+' | head -1)
HEALTHY=false
if [[ -n "$BACKEND_URL" ]]; then
    log "Testing health endpoint: $BACKEND_URL/api/health"
    for i in {1..10}; do
        if curl -sf "$BACKEND_URL/api/health" > /dev/null; then
            success "Backend healthy!"
            HEALTHY=true
            break
        else
            warn "Attempt $i/10: waiting for backend..."
            sleep 10
        fi
    done
else
    warn "Could not get backend URL automatically. Check: railway domain --service askmukthiguru-8119b0e8"
fi

if [[ "$HEALTHY" != true ]]; then
    error "Backend health verification failed after all attempts"
    exit 1
fi

# 8. Summary
log "=== Deployment Summary ==="
echo "Backend URL: $BACKEND_URL"
echo "Railway Dashboard: https://railway.com/project/$(railway status --json | jq -r .projectId 2>/dev/null || echo 'check dashboard')"
echo ""
echo "NEXT STEPS:"
echo "1. Set API keys in Railway dashboard: OPENROUTER_API_KEY, SARVAM_API_KEY, NIM_API_KEY, SUPABASE_KEY"
echo "2. In Lovable (https://askmukthiguru.lovable.app): Settings → Environment Variables → VITE_BACKEND_URL=$BACKEND_URL"
echo "3. Run data migration (see migrate_data.sh)"
echo ""
echo "Logs saved to: railway_deploy.log"

success "Deployment script completed!"