#!/usr/bin/env bash
# Staging-only red-team smoke. It must never run against production.
# Required: STAGING_ENVIRONMENT=staging, STAGING_BASE_URL, SUPABASE_URL,
#           SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY,
#           ALLOW_STAGING_SYNTHETIC_USERS=1
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
BASE_URL="${STAGING_BASE_URL:?Set STAGING_BASE_URL to the staging origin}"
BASE_URL="${BASE_URL%/}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/.staging-evidence}"
mkdir -p "$EVIDENCE_DIR"

if [ "${STAGING_ENVIRONMENT:-}" != "staging" ]; then
  echo "Refusing red-team run unless STAGING_ENVIRONMENT=staging" >&2
  exit 2
fi
if [ "${ALLOW_STAGING_SYNTHETIC_USERS:-}" != "1" ]; then
  echo "Set ALLOW_STAGING_SYNTHETIC_USERS=1 to authorize synthetic-user tests" >&2
  exit 2
fi
case "$BASE_URL" in
  https://*|http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ;;
  *) echo "Refusing non-HTTP(S) staging URL" >&2; exit 2 ;;
esac

: "${SUPABASE_URL:?Set SUPABASE_URL to staging Supabase}"
: "${SUPABASE_SERVICE_ROLE_KEY:?Set SUPABASE_SERVICE_ROLE_KEY in the staging secret store}"
: "${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY in the staging secret store}"

SUPABASE_URL="$SUPABASE_URL" \
SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" \
  python3 "$ROOT/backend/scripts/verify_rls_policies.py" \
  > "$EVIDENCE_DIR/rls-verifier.json"

python3 - "$EVIDENCE_DIR/rls-verifier.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    print("RLS verifier failed", file=sys.stderr)
    raise SystemExit(1)
print("Synthetic-user RLS gate passed")
PY

STAGING_BASE_URL="$BASE_URL" EVIDENCE_DIR="$EVIDENCE_DIR/runtime" \
  "$ROOT/scripts/ops/verify_runtime_gate.sh"

method_status="$EVIDENCE_DIR/http-methods.txt"
: > "$method_status"
for method in PUT PATCH DELETE; do
  code="$(curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -o /dev/null -w '%{http_code}' -X "$method" "$BASE_URL/api/chat/stream" || true)"
  printf '%s %s\n' "$method" "$code" >> "$method_status"
  case "$code" in
    405|401|403|404|422) ;;
    *) echo "Unexpected $method status on chat route: $code" >&2; exit 1 ;;
  esac
done

echo "Staging red-team gate passed"
