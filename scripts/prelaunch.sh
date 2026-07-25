#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Pre-launch gate — run before every deploy.
#
# Runs, in order:
#   1. Production build             (fails on TS / bundler errors)
#   2. Vitest unit suite            (component + lib contracts)
#   3. Playwright suites, ordered from cheapest to most interactive:
#        - page-smoke               (every route mounts)
#        - google-auth-flow         (no double-prompt, redirect contract)
#        - session-auth             (protected-route gating)
#        - prelaunch-sweep          (scroll + click every safe control)
#        - full-regression          (critical journeys)
#
# Any red step short-circuits the run with a non-zero exit — the CI gate
# and the manual "am I ready to publish?" check both use exit code.
#
# Usage:
#   scripts/prelaunch.sh                          # local vite server
#   BASE_URL=https://askmukthiguru.lovable.app scripts/prelaunch.sh   # against prod
#   SKIP_BUILD=1 scripts/prelaunch.sh             # skip vite build (fast iterate)
#   SUITES="google-auth-flow prelaunch-sweep" scripts/prelaunch.sh    # subset
#
# Optional: create a disposable test user in Supabase before the run so
# authenticated flows can be exercised. Requires SUPABASE_SERVICE_ROLE_KEY.
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

# 1) Optional: seed a disposable test user via Supabase admin API.
maybe_seed_user() {
  if [[ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" || -z "${SUPABASE_URL:-}" || -z "${TEST_USER_EMAIL:-}" ]]; then
    yellow "↷ Skipping test-user seed (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/TEST_USER_EMAIL not all set)."
    return 0
  fi
  step "Seeding test user ${TEST_USER_EMAIL}"
  local password="${TEST_USER_PASSWORD:-Preflight123!@#XY}"
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

# 2) Build (skippable for fast iteration).
run_build() {
  if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    yellow "↷ SKIP_BUILD=1 — skipping vite build"
    return 0
  fi
  npm run build
}

# 3) Vitest.
run_unit() { npm test -- --run; }

# 4) Playwright — one project per suite so failures are attributable.
run_playwright_suite() {
  local suite="$1"
  npx playwright test --project=chromium "tests/e2e/${suite}.spec.ts"
}

DEFAULT_SUITES=(
  page-smoke
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
