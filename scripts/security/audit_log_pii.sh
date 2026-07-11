#!/usr/bin/env bash
set -euo pipefail
echo "=== Personal Data Flow Audit ==="

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Check for PII in log statements
echo "Checking for PII in log statements..."
pii_patterns=(
  'email'
  'password'
  'phone'
  'ssn'
  'credit.?card'
  'token.*='
  'secret.*='
)

found=0
for pattern in "${pii_patterns[@]}"; do
  while IFS= read -r line; do
    if [[ "$line" == *".venv"* ]] || [[ "$line" == *"node_modules"* ]] || [[ "$line" == *".git"* ]]; then
      continue
    fi
    # Only match if the line contains both a logging function AND PII pattern
    if echo "$line" | grep -qiE '(logger\.|console\.log|print\()'; then
      # Skip known safe patterns
      if echo "$line" | grep -qiE '(email.*template|email.*service|phone.*number.*format)'; then
        continue
      fi
      echo "  $line"
      found=$((found + 1))
    fi
  done < <(grep -rn "$pattern" "$ROOT_DIR/backend" --include="*.py" --exclude-dir=venv --exclude-dir=.venv --exclude-dir=__pycache__ 2>/dev/null || true)
done

if [ "$found" -eq 0 ]; then
  echo "✅ No obvious PII in log statements found."
else
  echo "⚠️  Found $found potential PII-in-log(s) — review each above."
fi

# Check frontend console.log for PII
echo ""
echo "=== Frontend Console Log Check ==="
if [ -d "$ROOT_DIR/src" ]; then
  frontend_found=0
  for pattern in "${pii_patterns[@]}"; do
    while IFS= read -r line; do
      if echo "$line" | grep -qiE 'console\.(log|error|warn|debug)'; then
        echo "  $line"
        frontend_found=$((frontend_found + 1))
      fi
    done < <(grep -rn "$pattern" "$ROOT_DIR/src" --include="*.ts" --include="*.tsx" 2>/dev/null || true)
  done
  if [ "$frontend_found" -eq 0 ]; then
    echo "  ✅ No PII in frontend console.log"
  else
    echo "  ⚠️  Found $frontend_found potential PII in frontend console.log"
  fi
fi

echo ""
echo "Audit complete."
