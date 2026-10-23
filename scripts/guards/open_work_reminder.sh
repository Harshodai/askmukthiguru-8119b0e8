#!/usr/bin/env bash
# Claude Code SessionStart hook: point at the one open-work list and warn when it has gone stale.
# The list's own header says "edit this one, do not start another plan file"; this keeps it the first thing read.
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
list="docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md"
if [ ! -f "$list" ]; then
  echo "OPEN WORK: $list is missing. CLAUDE.md points at it; find the current list before answering 'what is pending?'."
  exit 0
fi
mtime=$(stat -f %m "$list" 2>/dev/null || stat -c %Y "$list")
age=$(( ( $(date +%s) - mtime ) / 86400 ))
msg="OPEN WORK: single list is $list (read 'Ruthless order of work' and 'Start here'). Last edited ${age}d ago. When an item closes or a new one appears, edit that file, not a new plan file."
[ "$age" -ge 3 ] && msg="$msg STALE: reconcile it with git log before relying on it."
echo "$msg"
