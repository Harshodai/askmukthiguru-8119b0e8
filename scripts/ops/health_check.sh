#!/usr/bin/env bash
# ============================================================
# Mukthi Guru — Startup Health Check
#
# Validates all critical services before you report issues.
# Run this FIRST when something seems broken.
#
# Usage:
#   chmod +x scripts/health_check.sh
#   ./scripts/health_check.sh
# ============================================================

set -euo pipefail

export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  local expected="${3:-}"

  result=$(eval "$cmd" 2>&1) || true

  if [ -n "$expected" ]; then
    if echo "$result" | grep -q "$expected"; then
      echo -e "  ${GREEN}✅ PASS${NC}  $name"
      ((PASS++)) || true
    else
      echo -e "  ${RED}❌ FAIL${NC}  $name"
      echo -e "       Got: ${result:0:120}"
      ((FAIL++)) || true
    fi
  else
    if [ -n "$result" ] && ! echo "$result" | grep -qi "error\|fail\|refused\|not found"; then
      echo -e "  ${GREEN}✅ PASS${NC}  $name"
      ((PASS++)) || true
    else
      echo -e "  ${RED}❌ FAIL${NC}  $name"
      echo -e "       Got: ${result:0:120}"
      ((FAIL++)) || true
    fi
  fi
}

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   Mukthi Guru — Health Check v1.0     ║"
echo "╚════════════════════════════════════════╝"
echo ""

echo "── Docker Containers ───────────────────"
check "Backend container running"   "docker ps --format '{{.Names}}' | grep -q mukthiguru-backend && echo ok"  "ok"
check "Frontend container running"  "docker ps --format '{{.Names}}' | grep -q mukthiguru-frontend && echo ok" "ok"
check "Supabase Kong on :54321"     "docker ps | grep supabase_kong" "54321"
check "Redis healthy"               "docker ps | grep mukthiguru-redis" "healthy"
check "Qdrant healthy"              "docker ps | grep mukthiguru-qdrant" "healthy"

echo ""
echo "── API Endpoints ───────────────────────"
check "Backend health"              "curl -sf http://localhost/api/health" "healthy"
check "OpenAPI schema (25 paths)"   "docker exec mukthiguru-backend curl -sf localhost:8000/openapi.json | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d['paths']))\"" "25"
check "Supabase auth health"        "curl -sf http://localhost:54321/auth/v1/health" "GoTrue"
check "Frontend serves HTML"        "curl -sf http://localhost/ | grep -q 'AskMukthiGuru' && echo ok" "ok"

echo ""
echo "── Auth System ─────────────────────────"
check "Admin user in Supabase"      "docker exec mukthiguru-backend curl -sf -H 'Authorization: Bearer ${JWT_SECRET:-}' 'http://host.docker.internal:54321/rest/v1/user_roles?select=role' 2>&1" "admin"

echo ""
echo "── Known Failure Safeguards ────────────"

# Guard 1: No CallableSchema in auth.py (check real code, not comments)
if grep -v "^\s*#" backend/app/api/endpoints/auth.py 2>/dev/null | grep -q "Depends(limiter.limit"; then
  echo -e "  ${RED}❌ FAIL${NC}  [GUARD] auth.py has Depends(limiter.limit(...)) — will crash /openapi.json!"
  ((FAIL++)) || true
else
  echo -e "  ${GREEN}✅ PASS${NC}  [GUARD] auth.py has no Callable in Depends (OpenAPI safe)"
  ((PASS++)) || true
fi

# Guard 2: No new uses of current_active_user in non-auth files
STALE=$(grep -rl "Depends(current_active_user)" backend/ --include="*.py" 2>/dev/null | grep -v "auth_service.py\|__pycache__" || true)
if [ -n "$STALE" ]; then
  echo -e "  ${YELLOW}⚠️  WARN${NC}  [GUARD] current_active_user used in: $STALE"
  echo "         → These routes reject Supabase JWTs. Migrate to get_current_user_from_supabase"
else
  echo -e "  ${GREEN}✅ PASS${NC}  [GUARD] No stale current_active_user in route handlers"
fi

echo ""
echo "────────────────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}All checks passed ($PASS/$((PASS+FAIL)))${NC}"
  echo ""
  echo "  🌐  Frontend:  http://localhost"
  echo "  🔐  Auth:      http://localhost/auth"
  echo "  🛡️   Admin:     http://localhost/admin/login"
  echo "  🏥  API:       http://localhost/api/health"
  echo "  📖  Swagger:   http://localhost:8000/docs"
else
  echo -e "${RED}$FAIL check(s) FAILED (${PASS} passed)${NC}"
  echo "  → See lessons.md § Critical Incident Report for known fixes"
  exit 1
fi
echo ""
