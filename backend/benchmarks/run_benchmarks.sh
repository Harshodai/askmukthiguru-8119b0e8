#!/usr/bin/env bash
# run_benchmarks.sh — Convenience wrapper to run all benchmark suites.
# Usage: cd backend && bash benchmarks/run_benchmarks.sh
set -eo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMEOUT="${TIMEOUT:-120}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}/.."

echo "══════════════════════════════════════════════════════════════"
echo "  Mukthi Guru Benchmark Runner"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "  Target : $BASE_URL"
echo "  Timeout: ${TIMEOUT}s"
echo ""

# ── 1. Health check ──────────────────────────────────────────
echo "⏳ Checking backend health..."
if ! curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
    echo "⚠️  Backend not reachable at $BASE_URL"
    echo "   Restart with: docker compose restart backend"
    exit 1
fi
echo "   Backend is up ✅"
echo ""

# ── 2. Focused Fix Test (smoke test) ───────────────────────
echo "══════════════════════════════════════════════════════════════"
echo "🔬 Step 1: Focused Fix Test (smoke test for known bugs)"
echo "══════════════════════════════════════════════════════════════"
python3 benchmarks/focused_fix_test.py \
    --base-url "$BASE_URL" \
    --timeout "$TIMEOUT" \
    --output "reports/focused_fix_test.json" \
    ${@}

FOCUSED_EXIT=$?
echo ""

# ── 3. Comprehensive SDLC Benchmark ──────────────────────────
echo "══════════════════════════════════════════════════════════════"
echo "📊 Step 2: SDLC RAG Benchmark (full suite, dry-run: 5 per cat)"
echo "══════════════════════════════════════════════════════════════"
python3 benchmarks/sdlc_rag_benchmark.py \
    --base-url "$BASE_URL" \
    --timeout "$TIMEOUT" \
    --limit 5 \
    --output-dir "reports" \
    ${@}

FULL_EXIT=$?
echo ""

# ── 4. Summary ───────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════"
echo "  Benchmark Complete"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "  Reports generated in backend/reports/ :"
echo "    - focused_fix_test.json"
echo "    - benchmark_report.json"
echo "    - benchmark_report.md"
echo "    - benchmark_report.xml"
echo ""

if [ $FOCUSED_EXIT -ne 0 ] || [ $FULL_EXIT -ne 0 ]; then
    echo "  ⚠️  Some tests FAILED. Review reports above."
    exit 1
else
    echo "  ✅ All tests passed."
    exit 0
fi
