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

run_build() {
  if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    yellow "↷ SKIP_BUILD=1 — skipping vite build"
    return 0
  fi
  npm run build
}

run_unit() { npm test -- --run; }

run_playwright_suite() {
  local suite="$1"
  npx playwright test --project=chromium "tests/e2e/${suite}.spec.ts"
}

DEFAULT_SUITES=(
  page-smoke
  a11y-smoke
  google-auth-flow
  session-auth
  prelaunch-sweep
  full-regression
)

IFS=' ' read -r -a SUITES <<< "${SUITES:-${DEFAULT_SUITES[*]}}"

bold "═══════════════════════════════════════════════════════════════"
bold "  AskMukthiGuru — Pre-launch gate"
bold "═══════════════════════════════════════════════════════════════"
echo "BASE_URL      = ${BASE_URL:-http://localhost:8080 (local dev server via playwright.config.ts)}"
echo "Suites        = ${SUITES[*]}"
echo "Skip build    = ${SKIP_BUILD:-0}"

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
