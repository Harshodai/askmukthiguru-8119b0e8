#!/bin/bash
# Install git hooks into .git/hooks

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "Installing post-commit hook..."
cp -f hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
echo "Git hooks installed successfully!"
