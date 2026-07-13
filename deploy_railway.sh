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

# 1. Add Services (use Railway's supported template deployment command)
services=("neo4j" "qdrant" "postgresql" "redis")
for svc in "${services[@]}"; do
    log "Adding service: $svc"
    if railway service list | grep -q "$svc"; then
        warn "$svc already exists, skipping"
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
NEO4J_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("neo4j|Neo4j")) | .name' | head -1)
POSTGRES_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Postgres|postgres|postgresql")) | .name' | head -1)
REDIS_SVC=$(railway service list --json 2>/dev/null | jq -r '.[] | select(.name | test("Redis|redis")) | .name' | head -1)

# Helper to fetch a variable from a specific service
get_var() {
    local var=$1 service=$2
    railway variables get "$var" --service "$service" 2>/dev/null || echo ""
}

# Extract key variables from the services that own them
NEO4J_PASSWORD=$(get_var NEO4J_PASSWORD "$NEO4J_SVC")
[[ -z "$NEO4J_PASSWORD" ]] && NEO4J_PASSWORD=$(get_var NEO4J_PASSWORD "neo4j")
[[ -z "$NEO4J_PASSWORD" ]] && NEO4J_PASSWORD=$(get_var NEO4J_AUTH "$NEO4J_SVC" | cut -d'/' -f2)

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

# Models
set_var SARVAM_CLOUD_MODEL "sarvam-30b"
set_var EMBEDDING_MODEL "sentence-transformers/all-MiniLM-L6-v2"
set_var RERANKER_MODEL "BAAI/bge-reranker-v2-m3"

# Service URLs (internal Railway DNS)
if [[ -n "$NEO4J_PASSWORD" ]]; then
    set_var NEO4J_URI "bolt://neo4j.railway.internal:7687"
    set_var NEO4J_USER "neo4j"
    set_var NEO4J_PASSWORD "$NEO4J_PASSWORD"
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

# 4. Deploy Backend
log "Deploying backend..."
railway up --detach > /dev/null 2>&1
success "Backend deployment triggered"

# 5. Add Celery Worker
log "Creating celery-worker service..."
if railway service list | grep -q "celery-worker"; then
    warn "celery-worker already exists"
else
    # Use the supported `railway add --service` flow, then deploy with the
    # checked-in railway.json configuration. start_railway.py reads SERVICE_TYPE
    # and switches to the Celery worker entrypoint.
    if railway add --service celery-worker > /dev/null 2>&1; then
        railway variable set --service celery-worker SERVICE_TYPE=celery > /dev/null 2>&1
        railway up --service celery-worker --detach > /dev/null 2>&1
        success "celery-worker created and deployed"
    else
        error "Failed to create celery-worker service"
        exit 1
    fi
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