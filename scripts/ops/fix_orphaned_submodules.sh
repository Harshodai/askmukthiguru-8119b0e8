#!/usr/bin/env bash
# fix_orphaned_submodules.sh — run once in your local clone before applying the tarball.
#
# WHY:
#   Upstream Harshodai/askmukthiguru-8119b0e8 has TWO gitlink entries in its index
#   without a corresponding .gitmodules file:
#     - backend/repos/LightRAG        (mode 160000, commit 186beb6565495cb7cfcc9e144b4e69af59a5015d)
#     - backend/repos/RAG-Anything    (mode 160000, commit 8395634289f68445001219fd7f725965cf46a394)
#
#   This is the SAME class of bug that caused your "Save to GitHub" 403 with
#   external/askmukthiguru — git treats them as submodules and tries to push
#   to their (non-existent in your account) upstream remotes. Future `git add`
#   operations will re-stage them as gitlinks.
#
# WHAT THIS DOES:
#   Removes the orphaned gitlinks from the index (working-tree contents untouched
#   if present, otherwise it just removes the stale entries). After this runs
#   once, future pushes will not encounter the submodule landmine.
#
# RUN ONCE:
#   chmod +x fix_orphaned_submodules.sh
#   ./fix_orphaned_submodules.sh
#   git commit -m "fix: remove orphaned gitlinks (backend/repos/LightRAG, RAG-Anything)"

set -euo pipefail

if [ ! -d ".git" ]; then
  echo "ERROR: not in a git repository root. cd into your askmukthiguru clone first." >&2
  exit 1
fi

removed=0
for path in "backend/repos/LightRAG" "backend/repos/RAG-Anything"; do
  if git ls-files --stage "$path" 2>/dev/null | grep -q "^160000"; then
    echo "Removing gitlink: $path"
    git rm --cached "$path" 2>/dev/null || true
    # If a real submodule .git/modules entry exists, prune it
    if [ -d ".git/modules/$path" ]; then
      rm -rf ".git/modules/$path"
      echo "  pruned .git/modules/$path"
    fi
    removed=$((removed + 1))
  else
    echo "OK: $path not staged as gitlink (already clean)"
  fi
done

# Also remove any empty directory left behind
for path in "backend/repos/LightRAG" "backend/repos/RAG-Anything"; do
  if [ -d "$path" ] && [ -z "$(ls -A "$path" 2>/dev/null)" ]; then
    rmdir "$path" 2>/dev/null && echo "Removed empty dir: $path"
  fi
done

if [ "$removed" -gt 0 ]; then
  echo ""
  echo "Removed $removed gitlink(s). Now commit:"
  echo "  git commit -m 'fix: remove orphaned gitlinks (LightRAG, RAG-Anything)'"
else
  echo ""
  echo "Nothing to fix — already clean."
fi
