#!/usr/bin/env bash
# Run the strict retrieval-quality gate against an explicitly configured staging corpus.
# This script never updates the repository baseline unless UPDATE_QDRANT_BASELINE=1
# is deliberately supplied for a separately authorized benchmark job.
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/.staging-evidence}"
mkdir -p "$EVIDENCE_DIR"

: "${QDRANT_URL:?Set QDRANT_URL to the staging Qdrant endpoint}"
: "${QDRANT_COLLECTION:?Set QDRANT_COLLECTION to the approved staging collection}"
: "${QDRANT_API_KEY:?Set QDRANT_API_KEY in the CI secret store}"
export REQUIRE_QDRANT_EVAL=1
export UPDATE_QDRANT_BASELINE="${UPDATE_QDRANT_BASELINE:-0}"

case "$QDRANT_URL" in
  https://*|http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ;;
  *) echo "Refusing non-HTTP(S) Qdrant URL" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-$ROOT/backend/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="${ROOT}/backend/venv/bin/python"
fi
if [ ! -x "$PYTHON" ]; then
  PYTHON="${PYTHON_FALLBACK:-python3}"
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "No usable Python environment found" >&2
  exit 2
fi

printf 'QDRANT_URL=%s\nQDRANT_COLLECTION=%s\nREQUIRE_QDRANT_EVAL=%s\nUPDATE_QDRANT_BASELINE=%s\n' \
  "${QDRANT_URL%%/}" "$QDRANT_COLLECTION" "$REQUIRE_QDRANT_EVAL" "$UPDATE_QDRANT_BASELINE" \
  > "$EVIDENCE_DIR/retrieval-config.txt"

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

before_sha=""
if [ -f "$ROOT/memory/qdrant_quality_baseline.json" ]; then
  before_sha="$(hash_file "$ROOT/memory/qdrant_quality_baseline.json")"
fi

"$PYTHON" -m pytest "$ROOT/backend/tests/test_qdrant_search_quality.py" -q -m integration \
  > "$EVIDENCE_DIR/retrieval-gate.log" 2>&1

if [ "$UPDATE_QDRANT_BASELINE" != "1" ] && [ -n "$before_sha" ] && [ -f "$ROOT/memory/qdrant_quality_baseline.json" ]; then
  after_sha="$(hash_file "$ROOT/memory/qdrant_quality_baseline.json")"
  if [ "$before_sha" != "$after_sha" ]; then
    echo "Retrieval gate changed the baseline in read-only mode" >&2
    exit 1
  fi
fi

cat "$EVIDENCE_DIR/retrieval-gate.log"
echo "Strict retrieval gate passed"
