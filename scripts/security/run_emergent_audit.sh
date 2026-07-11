#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/security"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
REPORT_FILE="$REPORT_DIR/emergent_audit_${TIMESTAMP}.md"

mkdir -p "$REPORT_DIR"

echo "# Emergent Security Audit Report" > "$REPORT_FILE"
echo "**Date:** $(date)" >> "$REPORT_FILE"
echo "**Commit:** $(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo 'N/A')" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo ""
echo "=== Emergent Security Audit ==="
echo ""

run_audit() {
  local name="$1"
  local script="$2"
  echo "Running: $name..."
  echo "## $name" >> "$REPORT_FILE"
  echo '```' >> "$REPORT_FILE"
  bash "$SCRIPT_DIR/$script" >> "$REPORT_FILE" 2>&1 || true
  echo '```' >> "$REPORT_FILE"
  echo "" >> "$REPORT_FILE"
  echo "  ✅ Done"
}

run_audit "1. Secret Leak Prevention" "audit_secrets.sh"
run_audit "2. Personal Data Flow Audit" "audit_log_pii.sh"
run_audit "3. Pre-Deploy Production Audit" "audit_endpoints.sh"
run_audit "4. Security Headers & CORS Audit" "audit_cors_headers.sh"

echo ""
echo "=== Summary ==="
echo "Report generated: $REPORT_FILE"
echo ""

# Print summary
total_issues=$(grep -o '⚠️' "$REPORT_FILE" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
total_passed=$(grep -o '✅' "$REPORT_FILE" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
echo "Report Summary: $total_passed checks passed, $total_issues issues found"
