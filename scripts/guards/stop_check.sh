#!/usr/bin/env bash
# Claude Code Stop hook: block ONCE if work would be lost (uncommitted or unpushed). Repeated lesson:
# a fix sat un-pushed on a laptop/container while the session reported it done.
in=$(cat); echo "$in" | grep -q '"stop_hook_active": *true' && exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
dirty=$(git status --porcelain | grep -v '^??' | head -5)
ahead=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
if [ -n "$dirty" ] || [ "$ahead" != "0" ]; then
  echo "Unsaved work: ${ahead} unpushed commit(s); uncommitted:" >&2; echo "$dirty" >&2
  echo "Commit/push (by path, never git add -A) or state explicitly that it is intentionally local." >&2
  exit 2
fi
