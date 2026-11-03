#!/usr/bin/env bash
# ==============================================================================
# sync_github_wiki.sh — Synchronize AskMukthiGuru documentation to GitHub Wiki
# ==============================================================================
# Usage:
#   ./scripts/ops/sync_github_wiki.sh
#
# Prerequisite:
#   GitHub requires at least ONE page to be initially created via the GitHub web UI
#   (https://github.com/Harshodai/askmukthiguru-8119b0e8/wiki) before the .wiki.git
#   repository is provisioned.
# ==============================================================================

set -euo pipefail

REPO_OWNER="Harshodai"
REPO_NAME="askmukthiguru-8119b0e8"
WIKI_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}.wiki.git"
WORK_DIR="/tmp/askmukthiguru-wiki-repo"
STAGING_DIR="/tmp/wiki-staging"

echo "=== AskMukthiGuru GitHub Wiki Sync ==="

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh CLI is required." >&2
    exit 1
fi

TOKEN=$(gh auth token)
AUTH_WIKI_URL="https://x-access-token:${TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.wiki.git"

echo "Checking if GitHub Wiki git repository is initialized..."
if ! git ls-remote "$AUTH_WIKI_URL" >/dev/null 2>&1; then
    echo ""
    echo "⚠️  GitHub Wiki repository is not yet initialized on GitHub servers."
    echo "GitHub requires you to create the very first page via web UI:"
    echo "  👉 Visit: https://github.com/${REPO_OWNER}/${REPO_NAME}/wiki"
    echo "  👉 Click 'Create the first page' (or save the default 'Home' page)."
    echo ""
    echo "Once that is done, run this script again: ./scripts/ops/sync_github_wiki.sh"
    exit 2
fi

echo "Cloning GitHub Wiki repository..."
rm -rf "$WORK_DIR"
git clone "$AUTH_WIKI_URL" "$WORK_DIR"

echo "Copying staged wiki documents from ${STAGING_DIR}..."
cp -R "${STAGING_DIR}/"* "$WORK_DIR/"

cd "$WORK_DIR"
git config user.name "Harshodai"
git config user.email "harshodai@gmail.com"

git add .
if git diff --cached --quiet; then
    echo "No changes to commit. GitHub Wiki is already up-to-date."
else
    git commit -m "docs(wiki): update comprehensive documentation from AskMukthiGuru repo"
    git push origin master
    echo "✅ Successfully synced all Wiki pages to https://github.com/${REPO_OWNER}/${REPO_NAME}/wiki!"
fi
