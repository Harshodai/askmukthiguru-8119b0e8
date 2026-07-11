#!/usr/bin/env bash
set -euo pipefail
echo "=== API Endpoint Auth Audit ==="

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "Scanning backend routes for auth dependency..."
found=0
unauth=0

# Scan a file or directory for route decorators and check auth middleware
scan_path() {
  local path="$1"
  local pattern="$2"
  # grep -rn gives us file:line:content — parse each match
  while IFS= read -r line; do
    if [ -z "$line" ]; then
      continue
    fi
    # Parse grep output: file_path:line_number:rest_of_line
    # On BSD grep, file paths with colons are rare but possible; for a reliable
    # extraction we find the LAST colon that introduces a number (the line number).
    # Simpler approach: assume standard paths and use cut.
    local file_path
    local lineno
    file_path=$(echo "$line" | cut -d: -f1)
    lineno=$(echo "$line" | cut -d: -f2)
    local content
    content=$(echo "$line" | cut -d: -f3-)

    if [ -z "$file_path" ] || [ -z "$lineno" ]; then
      continue
    fi

    # Extract route path from the decorator string
    local route
    route=$(echo "$content" | sed -n 's/.*"\([^"]*\)".*/\1/p')
    local method
    method=$(echo "$content" | sed -n "s/.*@router\.\([a-z]*\).*/\1/p")
    if [ -z "$method" ]; then
      method=$(echo "$content" | sed -n "s/.*@app\.\([a-z]*\).*/\1/p")
    fi

    # Read next 15 lines to check for auth dependency
    local has_auth=false
    local context
    context=$(sed -n "$lineno,$((lineno+15))p" "$file_path" 2>/dev/null || true)
    if echo "$context" | grep -qE 'Depends\(get_current_user|Depends\(security|Depends\(auth_bridge'; then
      has_auth=true
    fi

    found=$((found + 1))
    if [ "$has_auth" = false ]; then
      echo "  UNAUTHENTICATED: $method $route (${file_path}:${lineno})"
      unauth=$((unauth + 1))
    fi
  done < <(grep -rnE "$pattern" "$path" --include="*.py" \
    --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.venv --exclude-dir=.venv_host \
    2>/dev/null || true)
}

# Scan each file in app/api/ individually so we get proper file paths
for api_file in "$ROOT_DIR/backend/app/api"/*.py; do
  [ -f "$api_file" ] || continue
  scan_path "$api_file" '@router\.(get|post|put|delete|patch|options)'
done

# Also scan main.py for @app routes
scan_path "$ROOT_DIR/backend/app/main.py" '@app\.(get|post|put|delete)'

echo ""
echo "Total endpoints: $found"
echo "Unauthenticated: $unauth"
if [ "$unauth" -eq 0 ]; then
  echo "All endpoints have auth dependency"
fi
echo ""
echo "Audit complete."
