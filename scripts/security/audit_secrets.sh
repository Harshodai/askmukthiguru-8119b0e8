#!/usr/bin/env bash
set -euo pipefail
echo "=== Secret Leak Prevention Audit ==="

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

patterns=(
  # API key patterns (generic and specific)
  'api[_-]?key[[:space:]]*[=:][[:space:]]*['"'"'"]?[A-Za-z0-9_\-]{20,}'
  'sk_[a-zA-Z0-9]{20,}'       # OpenAI/Sarvam style
  'AIza[0-9A-Za-z\-_]{35}'    # Google API
  'xox[baprs]-[0-9a-zA-Z\-]{10,}' # Slack tokens
  'ghp_[a-zA-Z0-9]{36}'       # GitHub PAT
  'pk_live_[a-zA-Z0-9]{24}'   # Stripe live
  'sk_live_[a-zA-Z0-9]{24}'   # Stripe secret live
  '-----BEGIN (RSA |EC )?PRIVATE KEY-----'  # Private keys
  # Password patterns (careful: avoid backslash-heavy char classes on BSD grep)
  'password[[:space:]]*[=:][[:space:]]*['"'"'"]?[A-Za-z0-9!@#%^&*()_+={}|;:,.<>?-]{8,}'
  'PASSWORD[[:space:]]*[=:][[:space:]]*['"'"'"]?[A-Za-z0-9!@#%^&*()_+={}|;:,.<>?-]{8,}'
)

EXCLUDE_DIRS="--exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=dist-ssr --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=reports --exclude-dir=playwright-report"

echo "Scanning for potential hardcoded secrets..."
found=0
for pattern in "${patterns[@]}"; do
  while IFS= read -r line; do
    echo "  POTENTIAL: $line"
    found=$((found + 1))
  done < <(grep -rn "$pattern" "$ROOT_DIR" \
    --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" \
    --include="*.yml" --include="*.yaml" --include="*.sh" \
    --include="*.conf" --include="*.json" \
    $EXCLUDE_DIRS \
    2>/dev/null || true)
done

if [ "$found" -eq 0 ]; then
  echo "  No potential secrets found in source files."
else
  echo "  Found $found potential secret(s) — review each above."
  echo "  False positives may include test fixtures with placeholder keys."
fi

# Check git history for committed secrets
echo ""
echo "=== Git History Check ==="
git -C "$ROOT_DIR" log --all --pretty=format:"  %h %s" --diff-filter=A \
  -- '*scratch*' '*secret*' '*key*' 2>/dev/null || echo "  No suspicious files in git history"

# Check .env.example exists and has no real secrets
echo ""
echo "=== .env.example Check ==="
if [ -f "$ROOT_DIR/.env.example" ]; then
  echo "  .env.example exists"
  if grep -qiE '(sk_live|pk_live|ghp_|AIza)' "$ROOT_DIR/.env.example" 2>/dev/null; then
    echo "  WARNING: .env.example contains what looks like real secrets!"
  else
    echo "  .env.example contains only placeholder values"
  fi
else
  echo "  WARNING: .env.example does not exist"
fi

# Check .env is in .gitignore
echo ""
echo "=== Env File Check ==="
if [ -f "$ROOT_DIR/.env" ]; then
  if grep -q ".env" "$ROOT_DIR/.gitignore" 2>/dev/null; then
    echo "  .env is in .gitignore"
  else
    echo "  WARNING: .env is NOT in .gitignore"
  fi
fi

echo ""
echo "Audit complete."
