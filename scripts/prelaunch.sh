#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Pre-launch gate — run before every deploy.
#
# Runs, in order:
#   1. Production build             (fails on TS / bundler errors)
#   2. Vitest unit suite            (component + lib contracts)
#   3. Playwright suites, ordered from cheapest to most interactive:
#        - page-smoke               (every route mounts)
#        - a11y-smoke               (axe: no serious/critical WCAG violations)

#        - google-auth-flow         (no double-prompt, redirect contract)
#        - session-auth             (protected-route gating)
#        - prelaunch-sweep          (scroll + click every safe control)
#        - full-regression          (critical journeys)
#
# Any red step short-circuits with a non-zero exit — CI gate and manual
# "am I ready to publish?" check both use exit code.
#
# Usage:
#   scripts/prelaunch.sh
#   BASE_URL=https://askmukthiguru.lovable.app scripts/prelaunch.sh
#   SKIP_BUILD=1 scripts/prelaunch.sh
#   SUITES="google-auth-flow prelaunch-sweep" scripts/prelaunch.sh
#
# Local Docker: this gate runs against the compose stack on your machine (no
# hosted-platform assumptions). Before building anything it runs a named
# preflight; every failure prints "PRELAUNCH-Exxx", what is wrong, and the fix:
#   E001 tool missing (node/npm/npx/curl)      E002 node_modules missing
#   E003 compose-required env var unset        E004 backend unreachable
#   E005 backend up but not ready              E006 caches not empty
# Preflight knobs:
#   BACKEND_URL=http://localhost:8000          where /api/health is probed
#   PRELAUNCH_SKIP_BACKEND=1                   skip E004/E005 (frontend-only gate)
#   PRELAUNCH_SKIP_ENV=1                       skip E003 (no compose stack, e.g. the CI gate)
#   PRELAUNCH_VERIFY_CACHE=1                   also run `make verify-cache-empty` (E006)
#   PRELAUNCH_SKIP_PREFLIGHT=1                 skip the whole preflight
#
# Optional: seed a disposable test user via Supabase admin API before the run.
#   TEST_USER_EMAIL=preflight+$(date +%s)@example.com \
#   TEST_USER_PASSWORD='Preflight123!@#XY' \
#   SUPABASE_URL=https://<project>.supabase.co \
#   SUPABASE_SERVICE_ROLE_KEY=... \
#   scripts/prelaunch.sh
# ------------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

step() {
  bold ""
  bold "▶ $1"
  bold "────────────────────────────────────────────────────────────"
}

FAILED=()
run_step() {
  local name="$1"; shift
  step "$name"
  if "$@"; then
    green "✓ $name"
  else
    red "✗ $name"
    FAILED+=("$name")
  fi
}

maybe_seed_user() {
  if [[ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" || -z "${SUPABASE_URL:-}" || -z "${TEST_USER_EMAIL:-}" ]]; then
    yellow "↷ Skipping test-user seed (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/TEST_USER_EMAIL not all set)."
    return 0
  fi
  step "Seeding test user ${TEST_USER_EMAIL}"
  # The hardcoded fallback password below is a disposable LOCAL-DEV credential.
  # It may only be used against the local Supabase CLI instance — loopback hosts,
  # non-HTTPS scheme, Supabase API port 54321:
  #   http://127.0.0.1:54321  — PUBLIC_SUPABASE_URL in backend/.env (npx supabase status)
  #   http://localhost:54321  — VITE_SUPABASE_URL default in backend/docker-compose.yml
  # (http://host.docker.internal:54321 is a Docker-only alias that does not resolve
  # from the host shell where this script runs, so it is intentionally not allowlisted.)
  # The test account is created via the Supabase Admin API and is disposable — it is
  # NOT a real user credential. Always override via TEST_USER_PASSWORD in CI to use a
  # secret injected from your secret store.
  local -r LOCAL_SUPABASE_URLS=(
    "http://127.0.0.1:54321"
    "http://localhost:54321"
  )
  local url="${SUPABASE_URL%/}"
  local allowlisted=0
  local allowed
  for allowed in "${LOCAL_SUPABASE_URLS[@]}"; do
    if [[ "$url" == "$allowed" ]]; then
      allowlisted=1
      break
    fi
  done
  local password
  if [[ "$allowlisted" -eq 1 ]]; then
    password="${TEST_USER_PASSWORD:-Preflight123!@#XY}" # gitleaks:allow
  else
    if [[ -z "${TEST_USER_PASSWORD:-}" ]]; then
      red "✗ TEST_USER_PASSWORD is required for SUPABASE_URL=${url} (hardcoded fallback is local-dev only)"
      return 1
    fi
    password="$TEST_USER_PASSWORD"
  fi
  local code
  code=$(curl -sS -o /tmp/prelaunch-user.json -w "%{http_code}" \
    -X POST "${SUPABASE_URL}/auth/v1/admin/users" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_USER_EMAIL}\",\"password\":\"${password}\",\"email_confirm\":true}")
  if [[ "$code" == "200" || "$code" == "201" ]]; then
    green "✓ test user created"
    export PLAYWRIGHT_TEST_USER_EMAIL="$TEST_USER_EMAIL"
    export PLAYWRIGHT_TEST_USER_PASSWORD="$password"
  else
    red "✗ failed to create test user (HTTP $code) — continuing without it"
    cat /tmp/prelaunch-user.json || true
  fi
}

# ----------------------------- local-Docker preflight -------------------------
# Env vars backend/docker-compose.yml marks `${VAR:?...}`: compose refuses to
# start without them. SUPABASE_ANON_KEY is baked into the frontend image at build
# time (empty = silently broken auth), so it is checked here too.
COMPOSE_REQUIRED_VARS=(NEO4J_PASSWORD REDIS_PASSWORD JWT_SECRET CORS_ORIGINS SUPABASE_ANON_KEY)

preflight_fail() { # code, problem, fix
  red "PRELAUNCH-$1: $2"
  red "  fix: $3"
  return 1
}

# True if NAME is set non-empty in the environment or in backend/.env.
# Never prints the value.
env_var_set() {
  local name="$1"
  [[ -n "${!name:-}" ]] && return 0
  [[ -f "$ROOT/backend/.env" ]] && grep -Eq "^${name}=.+" "$ROOT/backend/.env"
}

preflight_tools() {
  local rc=0 t
  for t in node npm npx curl; do
    command -v "$t" >/dev/null 2>&1 || { preflight_fail E001 "'$t' not found on PATH" "install it (Node 22 LTS for node/npm/npx)"; rc=1; }
  done
  [[ -d "$ROOT/node_modules" ]] || { preflight_fail E002 "node_modules is missing" "run: npm ci"; rc=1; }
  return $rc
}

preflight_env() {
  if [[ "${PRELAUNCH_SKIP_ENV:-0}" == "1" ]]; then
    yellow "↷ PRELAUNCH_SKIP_ENV=1 — not checking compose env vars"
    return 0
  fi
  local rc=0 v
  for v in "${COMPOSE_REQUIRED_VARS[@]}"; do
    env_var_set "$v" || { preflight_fail E003 "$v is not set (environment or backend/.env)" "cp backend/.env.example backend/.env and set $v (see README Quickstart)"; rc=1; }
  done
  return $rc
}

preflight_backend() {
  if [[ "${PRELAUNCH_SKIP_BACKEND:-0}" == "1" ]]; then
    yellow "↷ PRELAUNCH_SKIP_BACKEND=1 — not probing the backend"
    return 0
  fi
  local url="${BACKEND_URL:-http://localhost:8000}" body
  if ! body="$(curl -sS -m 10 "${url%/}/api/health" 2>&1)"; then
    preflight_fail E004 "backend not reachable at ${url%/}/api/health (${body:0:120})" "cd backend && docker compose up -d qdrant memgraph redis backend, then wait for ready:true"
    return 1
  fi
  if ! grep -Eq '"ready"[[:space:]]*:[[:space:]]*true' <<<"$body"; then
    preflight_fail E005 "backend answered but is not ready (${body:0:160})" "wait for startup to finish (docker compose logs -f backend), then re-run"
    return 1
  fi
}

preflight_caches() {
  [[ "${PRELAUNCH_VERIFY_CACHE:-0}" == "1" ]] || return 0
  local py="${PYTHON:-python3}"
  "$py" "$ROOT/scripts/ops/verify_cache_empty.py" || {
    preflight_fail E006 "query caches are not verified empty (see output above)" "make flush-cache, then make verify-cache-empty"
    return 1
  }
}

run_preflight() {
  if [[ "${PRELAUNCH_SKIP_PREFLIGHT:-0}" == "1" ]]; then
    yellow "↷ PRELAUNCH_SKIP_PREFLIGHT=1 — skipping preflight"
    return 0
  fi
  local before=${#FAILED[@]}
  run_step "Preflight: tools"   preflight_tools
  run_step "Preflight: env"     preflight_env
  run_step "Preflight: backend" preflight_backend
  run_step "Preflight: caches"  preflight_caches
  if [[ ${#FAILED[@]} -gt $before ]]; then
    bold ""
    red "  Preflight failed: ${FAILED[*]:$before}"
    red "  Build and e2e were NOT run — fix the PRELAUNCH-Exxx items above first."
    exit 1
  fi
}

run_build() {
  if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    yellow "↷ SKIP_BUILD=1 — skipping vite build"
    return 0
  fi
  npm run build
}

run_unit() { npm test -- --run; }

check_suite_env() {
  local suite="$1"
  if [[ "$suite" == "rls-cross-user" ]]; then
    if [[ -z "${SUPABASE_URL:-}" || -z "${SUPABASE_ANON_KEY:-}" || -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
      if ! curl -s -m 2 http://127.0.0.1:54321/auth/v1/health >/dev/null 2>&1 && \
         ! curl -s -m 2 http://localhost:54321/auth/v1/health >/dev/null 2>&1; then
        red "✗ Suite '${suite}' requires SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY (or local Supabase on port 54321)."
        red "  Missing required environment variables — failing loudly instead of skipping green."
        return 1
      fi
    fi
  fi
  return 0
}

run_playwright_suite() {
  local suite="$1"
  if ! check_suite_env "$suite"; then
    return 1
  fi
  # Per-suite --output keeps a failing suite's screenshot/trace/error-context
  # from being wiped by the next suite's outputDir clear (same as #57 17f73714).
  npx playwright test --project=chromium --output="test-results/${suite}" "tests/e2e/${suite}.spec.ts"
}

DEFAULT_SUITES=(
  page-smoke
  a11y-smoke
  google-auth-flow
  session-auth
  prelaunch-sweep
  full-regression
  # Tenant-isolation proof. Both specs already existed and were referenced by
  # NO gate and NO CI workflow — 17K and 14K of real cross-user attack tests
  # sitting inert while the pre-launch gate reported green. These are the only
  # executable evidence that user A cannot read user B's data, so a release
  # gate that omits them cannot speak to isolation at all.
  # Note: rls-cross-user needs `serviceWorkers: 'block'` — a service worker
  # bypasses page.route() (see the AAL2/RLS notes in the root CLAUDE.md).
  rls-cross-user
  security-aal2
)

run_prelaunch() {
  IFS=' ' read -r -a SUITES <<< "${SUITES:-${DEFAULT_SUITES[*]}}"

  bold "═══════════════════════════════════════════════════════════════"
  bold "  AskMukthiGuru — Pre-launch gate"
  bold "═══════════════════════════════════════════════════════════════"
  echo "BASE_URL      = ${BASE_URL:-http://localhost:8080 (local dev server via playwright.config.ts)}"
  echo "Suites        = ${SUITES[*]}"
  echo "Skip build    = ${SKIP_BUILD:-0}"

  run_preflight
  maybe_seed_user
  run_step "Build"        run_build
  run_step "Unit (vitest)" run_unit

  for suite in "${SUITES[@]}"; do
    run_step "e2e: $suite" run_playwright_suite "$suite"
  done

  bold ""
  bold "═══════════════════════════════════════════════════════════════"
  if [[ ${#FAILED[@]} -eq 0 ]]; then
    green "  ALL GREEN — safe to publish."
    bold "═══════════════════════════════════════════════════════════════"
    exit 0
  fi

  red   "  FAILED: ${FAILED[*]}"
  red   "  Do NOT publish. Fix reds, re-run scripts/prelaunch.sh."
  bold  "═══════════════════════════════════════════════════════════════"
  exit 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  run_prelaunch "$@"
fi
