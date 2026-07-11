#!/usr/bin/env bash
set -euo pipefail
echo "=== Security Headers & CORS Audit ==="

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Check CORS configuration
echo "1. CORS Configuration"
if grep -q 'allow_origins=' "$ROOT_DIR/backend/app/main.py" 2>/dev/null; then
  cors_setting=$(grep 'allow_origins' "$ROOT_DIR/backend/app/main.py" | head -3)
  echo "   CORS setting found: $cors_setting"
  if echo "$cors_setting" | grep -q '"\*"'; then
    echo "   ⚠️  CORS allows ALL origins (*)"
  else
    echo "   ✅ CORS restricted to specific origins"
  fi
fi

# Check security headers
echo ""
echo "2. Security Headers (Backend)"
header_file="$ROOT_DIR/backend/app/main.py"
for header in "X-Content-Type-Options" "X-Frame-Options" "Strict-Transport-Security" "Content-Security-Policy" "Referrer-Policy" "Permissions-Policy"; do
  if grep -q "$header" "$header_file" 2>/dev/null; then
    echo "   ✅ $header"
  else
    echo "   ⚠️  $header NOT FOUND in backend"
  fi
done

# Check Nginx headers
echo ""
echo "3. Security Headers (Nginx)"
nginx_file="$ROOT_DIR/nginx.conf"
if [ -f "$nginx_file" ]; then
  for header in "X-Frame-Options" "X-Content-Type-Options" "Strict-Transport-Security" "Referrer-Policy" "Permissions-Policy"; do
    if grep -q "$header" "$nginx_file" 2>/dev/null; then
      echo "   ✅ $header in nginx.conf"
    else
      echo "   ⚠️  $header NOT FOUND in nginx.conf"
    fi
  done
fi

# Check CSP in Nginx
echo ""
echo "4. CSP Coverage"
if grep -q 'Content-Security-Policy' "$ROOT_DIR/backend/app/main.py" 2>/dev/null; then
  echo "   ✅ CSP in backend middleware"
else
  echo "   ⚠️  CSP missing in backend"
fi

echo ""
echo "Audit complete."
