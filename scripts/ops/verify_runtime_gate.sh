#!/usr/bin/env bash
# Verify a deployed staging runtime without mutating application data.
# Required: STAGING_BASE_URL=https://staging.example
# Optional: EVIDENCE_DIR=/tmp/askmukthi-staging-evidence
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
BASE_URL="${STAGING_BASE_URL:?Set STAGING_BASE_URL to the staging origin}"
BASE_URL="${BASE_URL%/}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/.staging-evidence}"
mkdir -p "$EVIDENCE_DIR"

case "$BASE_URL" in
  http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ;;
  https://*) ;;
  *) echo "Refusing non-HTTP(S) staging URL" >&2; exit 2 ;;
esac

curl_common=(--silent --show-error --fail-with-body --max-time "${CURL_MAX_TIME_SECONDS:-20}" --retry 1)

fetch_json() {
  local path="$1"
  local output="$2"
  curl "${curl_common[@]}" "$BASE_URL$path" -o "$output"
}

fetch_headers() {
  local path="$1"
  local output="$2"
  curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" --retry 1 -D "$output" -o /dev/null "$BASE_URL$path"
}

fetch_json /api/health "$EVIDENCE_DIR/health.json"
fetch_headers /api/health "$EVIDENCE_DIR/health.headers"

python3 - "$EVIDENCE_DIR/health.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
failures = []
if payload.get("ready") is not True:
    failures.append(f"ready={payload.get('ready')!r}")
if payload.get("status") not in {"healthy", "ready"}:
    failures.append(f"status={payload.get('status')!r}")
artifacts = payload.get("runtime_artifacts") or {}
if artifacts.get("readiness_ok") is not True:
    failures.append(f"runtime_artifacts.readiness_ok={artifacts.get('readiness_ok')!r}")
missing = artifacts.get("missing_required") or []
if missing:
    failures.append(f"missing_required={missing!r}")
if failures:
    print("Runtime readiness gate failed: " + "; ".join(failures), file=sys.stderr)
    raise SystemExit(1)
print("Runtime readiness gate passed")
PY

python3 - "$EVIDENCE_DIR/health.headers" <<'PY'
import pathlib
import sys

headers = {}
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines():
    if ":" in line and not line.startswith("HTTP/"):
        key, value = line.split(":", 1)
        headers[key.lower().strip()] = value.strip()
required = {
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
    "content-security-policy",
}
missing = sorted(required - headers.keys())
if missing:
    print(f"Missing security headers: {missing}", file=sys.stderr)
    raise SystemExit(1)
print("Security-header gate passed")
PY

metrics_code="$(curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -o "$EVIDENCE_DIR/metrics.body" -w '%{http_code}' "$BASE_URL/api/metrics" || true)"
printf '%s\n' "$metrics_code" > "$EVIDENCE_DIR/metrics.status"
case "$metrics_code" in
  401|403) echo "Unauthenticated metrics gate passed ($metrics_code)" ;;
  *) echo "Expected unauthenticated metrics denial, got HTTP $metrics_code" >&2; exit 1 ;;
esac

cors_headers="$EVIDENCE_DIR/cors.headers"
curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -D "$cors_headers" -o /dev/null -H 'Origin: https://evil.example' "$BASE_URL/api/health"
if grep -Eiq '^access-control-allow-origin:[[:space:]]*(\*|https://evil\.example)[[:space:]]*$' "$cors_headers"; then
  echo "CORS gate failed: wildcard or evil origin was allowed" >&2
  exit 1
fi
echo "CORS gate passed"

missing_asset_code="$(curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -o "$EVIDENCE_DIR/missing-asset.body" -w '%{http_code}' "$BASE_URL/assets/__staging_missing_asset__.js" || true)"
printf '%s\n' "$missing_asset_code" > "$EVIDENCE_DIR/missing-asset.status"
if [ "$missing_asset_code" != "404" ]; then
  echo "Missing-asset gate failed: expected 404, got HTTP $missing_asset_code" >&2
  exit 1
fi
echo "Missing-asset gate passed"

admin_code="$(curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -o "$EVIDENCE_DIR/admin.body" -w '%{http_code}' "$BASE_URL/api/admin/kpis" || true)"
printf '%s\n' "$admin_code" > "$EVIDENCE_DIR/admin.status"
case "$admin_code" in
  401|403) echo "Unauthenticated admin gate passed ($admin_code)" ;;
  *) echo "Expected unauthenticated admin denial, got HTTP $admin_code" >&2; exit 1 ;;
esac

chat_code="$(curl --silent --show-error --max-time "${CURL_MAX_TIME_SECONDS:-20}" -o "$EVIDENCE_DIR/chat-malformed.body" -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{}' "$BASE_URL/api/chat/stream" || true)"
printf '%s\n' "$chat_code" > "$EVIDENCE_DIR/chat-malformed.status"
case "$chat_code" in
  400|401|403|422) echo "Malformed-chat fail-closed gate passed ($chat_code)" ;;
  *) echo "Unexpected malformed-chat response HTTP $chat_code" >&2; exit 1 ;;
esac

echo "Runtime staging gate passed"
