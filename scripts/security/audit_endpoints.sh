#!/usr/bin/env bash
set -euo pipefail
echo "=== API Endpoint Auth Audit ==="

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "Scanning backend routes for auth dependency..."
found=0
unauth=0

scan_file() {
  local file="$1"
  local pattern="$2"
  while IFS= read -r line; do
    if echo "$line" | grep -qE "$pattern"; then
      route=$(echo "$line" | sed -n 's/.*"\([^"]*\)".*/\1/p')
      method=$(echo "$line" | sed -n "s/.*@router\.\([a-z]*\).*/\1/p")
      if [ -z "$method" ]; then
        method=$(echo "$line" | sed -n "s/.*@app\.\([a-z]*\).*/\1/p")
      fi
      lineno=$(echo "$line" | cut -d: -f2)
      has_auth=false
      context=$(sed -n "$lineno,$((lineno+15))p" "$file" 2>/dev/null)
      if echo "$context" | grep -qE 'Depends\(get_current_user|Depends\(security|Depends\(auth_bridge'; then
        has_auth=true
      fi
      found=$((found + 1))
      if [ "$has_auth" = false ]; then
        echo "  ⚠️  UNAUTHENTICATED: $method $route (${file}:${lineno})"
        unauth=$((unauth + 1))
      fi
    fi
  done < <(grep -rnE "$pattern" "$file" --include="*.py" 2>/dev/null || true)
}

scan_file "$ROOT_DIR/backend/app/api" '@router\.(get|post|put|delete|patch|options)'
scan_file "$ROOT_DIR/backend/app/main.py" '@app\.(get|post|put|delete)'

echo ""
echo "Total endpoints: $found"
echo "Unauthenticated: $unauth"
if [ "$unauth" -eq 0 ]; then
  echo "✅ All endpoints have auth dependency"
fi
echo ""
echo "Audit complete."
