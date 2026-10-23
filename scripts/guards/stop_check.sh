#!/usr/bin/env bash
# Claude Code Stop hook: block ONCE if commits would be lost (unpushed). Repeated lesson:
# a fix sat un-pushed on a laptop/container while the session reported it done.
# A dirty tree only warns (exit 0): the owner's rule is "never commit unless asked", so the tree is
# usually dirty on purpose, and blocking on it forces an extra full-context model call every turn.
in=$(cat); echo "$in" | grep -q '"stop_hook_active": *true' && exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
dirty=$(git status --porcelain | grep -v '^??' | head -5)
# With an upstream: commits not on it. Without one (a fresh branch): commits on no remote at all.
if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  ahead=$(git rev-list --count '@{u}..HEAD')
else
  ahead=$(git rev-list --count HEAD --not --remotes 2>/dev/null || echo 0)
fi
if [ "$ahead" != "0" ]; then
  echo "Unsaved work: ${ahead} unpushed commit(s); uncommitted:" >&2; echo "$dirty" >&2
  echo "Push (by path, never git add -A) or state explicitly that it is intentionally local." >&2
  exit 2
fi
if [ -n "$dirty" ]; then
  printf '{"systemMessage": "Uncommitted tracked changes (warning only, not blocking): %s"}\n' \
    "$(echo "$dirty" | tr '\n' ';' | sed 's/"/\\"/g')"
fi
exit 0
