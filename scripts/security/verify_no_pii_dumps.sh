#!/usr/bin/env bash
# verify_no_pii_dumps.sh — INV-6 verification gate.
#
# Thin wrapper over scripts/security/check_no_pii_dumps.sh. The plan's
# VERIFICATION GATE references INV-6: "no PII dump files in the working
# tree". This script is the canonical INV-6 caller for CI and manual ops
# verification; check_no_pii_dumps.sh is the implementation (also wired as
# the pre-commit local hook, T7).
#
# Usage:
#   bash scripts/security/verify_no_pii_dumps.sh [scan_root]
#
# Exit codes (mirrors check_no_pii_dumps.sh):
#   0 — INV-6 satisfied
#   1 — INV-6 violated (forbidden dumps present)
#   2 — usage / unexpected error

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/check_no_pii_dumps.sh" "${1:-.}"
