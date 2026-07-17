#!/bin/bash
# ------------------------------------------------------------------------------
# Reusable UI Regression & Production Screenshot Suite Runner
# ------------------------------------------------------------------------------
set -e

# Default settings
DEFAULT_URL="http://localhost:8080"
DEFAULT_SESSION_FILE="playwright-session.json"
TARGET_URL="${1:-$DEFAULT_URL}"
SESSION_PATH="${2:-$DEFAULT_SESSION_FILE}"

echo "====================================================================="
echo "   🚀 AskMukthiGuru UI Regression & Screenshot Runner"
echo "====================================================================="
echo "Target URL:    $TARGET_URL"
echo "Session File:  $SESSION_PATH"
echo "---------------------------------------------------------------------"

# Make sure screenshots folder exists and is clean
SCREENSHOTS_DIR="playwright-screenshots"
mkdir -p "$SCREENSHOTS_DIR"

# Check if session file exists
if [ -f "$SESSION_PATH" ]; then
    echo "✅ Authenticated browser session found at '$SESSION_PATH'"
    # Copy to default location for Playwright spec
    if [ "$SESSION_PATH" != "playwright-session.json" ]; then
        cp -f "$SESSION_PATH" "playwright-session.json"
        trap 'rm -f "playwright-session.json"' EXIT
    fi
else
    echo "⚠️  No authenticated session found at '$SESSION_PATH'."
    echo "   Running as anonymous user."
    # Remove stale default session so we run anonymously
    rm -f "$DEFAULT_SESSION_FILE"
    echo ""
    echo "   ℹ️ To run against production authenticated pages:"
    echo "     1. Log in to https://askmukthiguru.lovable.app/ in your browser"
    echo "     2. Use a Chrome extension like 'Playwright Session Export' or 'EditThisCookie'"
    echo "        to save your active cookies and localStorage state to '$DEFAULT_SESSION_FILE'."
    echo "     3. Or, execute this runner with the path to your exported JSON file."
    echo ""
fi

# Run the visual regression test suite
echo "🏃 Running Playwright E2E UI Regression Test..."
BASE_URL="$TARGET_URL" npx playwright test tests/e2e/ui-regression-screenshots.spec.ts --project=chromium

echo ""
echo "====================================================================="
echo "   🎉 Visual Regression Run Completed!"
echo "====================================================================="
echo "Screenshots saved in: $SCREENSHOTS_DIR/"
echo "Files list:"
ls -la "$SCREENSHOTS_DIR"
echo "====================================================================="
