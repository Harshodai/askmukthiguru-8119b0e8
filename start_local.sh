#!/bin/bash
# ==============================================================================
# AskMukthiGuru — Local Development Startup
# ==============================================================================
# Starts all services needed for local development:
#   1. Infrastructure (Qdrant, Redis, Neo4j) via Docker Compose
#   2. FastAPI Backend (port 8000)
#   3. Vite React Frontend (port 8080)
#
# Usage:
#   chmod +x start_local.sh
#   ./start_local.sh           # Start everything
#   ./start_local.sh --infra   # Only start Docker infrastructure
#   ./start_local.sh --backend # Only start backend (assumes infra is running)
#   ./start_local.sh --frontend # Only start frontend
# ==============================================================================

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${BLUE}[MukthiGuru]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# ── Check Prerequisites ──────────────────────────────────────────────────

check_prereqs() {
    log "Checking prerequisites..."
    
    local missing=0
    
    if ! command -v docker &>/dev/null; then
        err "Docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
        missing=1
    else
        ok "Docker: $(docker --version | head -1)"
    fi

    if ! command -v node &>/dev/null; then
        err "Node.js not found. Install via: brew install node"
        missing=1
    else
        ok "Node.js: $(node --version)"
    fi

    if ! command -v npm &>/dev/null; then
        err "npm not found."
        missing=1
    else
        ok "npm: $(npm --version)"
    fi

    if ! command -v python3 &>/dev/null; then
        err "Python 3 not found. Install via: brew install python@3.12"
        missing=1
    else
        ok "Python: $(python3 --version)"
    fi

    if [ $missing -eq 1 ]; then
        err "Missing prerequisites. Please install them and try again."
        exit 1
    fi
    echo ""
}

# ── Start Infrastructure ─────────────────────────────────────────────────

start_infra() {
    log "Starting infrastructure (Qdrant, Redis, Neo4j)..."
    cd "$BACKEND_DIR"
    
    # Only start the databases, not the backend/frontend Docker services
    docker compose up -d qdrant redis neo4j
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 5
    
    # Check Qdrant
    if curl -sf http://localhost:6333/healthz &>/dev/null; then
        ok "Qdrant is running on port 6333"
    else
        warn "Qdrant may still be starting up..."
    fi
    
    # Check Redis
    if docker exec mukthiguru-redis redis-cli -a mukthiguru_redis_secret_123 ping 2>/dev/null | grep -q PONG; then
        ok "Redis is running on port 6379"
    else
        warn "Redis may still be starting up..."
    fi
    
    # Check Neo4j
    if curl -sf http://localhost:7474 &>/dev/null; then
        ok "Neo4j is running on port 7474"
    else
        warn "Neo4j may still be starting up (can take 30-60s)..."
    fi
    
    echo ""
    cd "$ROOT_DIR"
}

# ── Start Backend ────────────────────────────────────────────────────────

start_backend() {
    log "Starting FastAPI backend on port 8000..."
    cd "$BACKEND_DIR"

    # Create venv if it doesn't exist
    if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
        log "Creating Python virtual environment..."
        python3 -m venv .venv
        ok "Virtual environment created at backend/.venv"
    fi

    # Activate venv
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        source venv/bin/activate
    fi

    # Install dependencies
    log "Installing Python dependencies..."
    pip install -q -r requirements.txt

    ok "Dependencies installed"
    log "Starting uvicorn..."
    echo ""
    echo "  ┌──────────────────────────────────────────────┐"
    echo "  │  Backend API:   http://localhost:8000         │"
    echo "  │  Health check:  http://localhost:8000/api/health │"
    echo "  │  Chat widget:   http://localhost:8000/chat    │"
    echo "  │  Ingest UI:     http://localhost:8000/ingest  │"
    echo "  └──────────────────────────────────────────────┘"
    echo ""

    python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

# ── Start Frontend ───────────────────────────────────────────────────────

start_frontend() {
    log "Starting Vite React frontend on port 8080..."
    cd "$ROOT_DIR"

    # Install npm dependencies if needed
    if [ ! -d "node_modules" ]; then
        log "Installing npm dependencies..."
        npm install
        ok "npm dependencies installed"
    fi

    echo ""
    echo "  ┌──────────────────────────────────────────────┐"
    echo "  │  Frontend:      http://localhost:8080         │"
    echo "  │  Admin panel:   http://localhost:8080/admin   │"
    echo "  └──────────────────────────────────────────────┘"
    echo ""

    npm run dev
}

# ── Main ─────────────────────────────────────────────────────────────────

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║     🕉️  AskMukthiGuru — Local Development    ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

case "${1:-all}" in
    --infra)
        check_prereqs
        start_infra
        ok "Infrastructure is running. Start backend and frontend separately."
        ;;
    --backend)
        start_backend
        ;;
    --frontend)
        start_frontend
        ;;
    all|"")
        check_prereqs
        start_infra
        
        log "Starting backend in background..."
        start_backend &
        BACKEND_PID=$!
        
        # Give backend a moment to start
        sleep 3
        
        log "Starting frontend..."
        start_frontend &
        FRONTEND_PID=$!
        
        # Trap to clean up on exit
        trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
        
        wait
        ;;
    *)
        echo "Usage: $0 [--infra|--backend|--frontend]"
        echo ""
        echo "  --infra     Start only Docker infrastructure (Qdrant, Redis, Neo4j)"
        echo "  --backend   Start only the FastAPI backend"
        echo "  --frontend  Start only the Vite React frontend"
        echo "  (no args)   Start everything"
        exit 1
        ;;
esac
