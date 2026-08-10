#!/usr/bin/env bash
# check_no_pii_dumps.sh — INV-6 / T7 dump-file detector.
#
# Fails (exit 1) if any of the known PII dump filenames are present in the
# working tree (tracked, untracked, or git-ignored). This is the invariant
# gate referenced by the audit plan's VERIFICATION GATE (INV-6) and the
# pre-commit hook (T7). One script, two callers:
#   - pre-commit local hook (T7) — dev-time prevention
#   - CI step / manual verification (INV-6) — enforcement gate
#
# The script NEVER deletes files. It only detects and reports. Cleanup is a
# manual ops step documented in docs/runbooks/SECRET_ROTATION.md.
#
# Forbidden filenames (literal basename matches):
#   neo4j.dump              — full Neo4j DB dump (PII: user graph)
#   supabase_dump.sql       — full Supabase SQL dump (PII: auth + profiles)
#   redis_dump.rdb          — Redis persistence snapshot (session/cache PII)
#   cookies.txt             — active YouTube OAuth session cookie
#   public_schema_dump.sql  — public schema SQL dump (may carry PII)
#
# Exit codes:
#   0 — clean tree (no forbidden dumps present)
#   1 — one or more forbidden dumps present
#   2 — usage error / unexpected failure

set -u

# Filenames that must never live in the working tree. Basenames only; the
# scan walks the whole tree (minus .git / node_modules / venv / .venv) so it
# catches nested copies too.
FORBIDDEN=(
  "neo4j.dump"
  "supabase_dump.sql"
  "redis_dump.rdb"
  "cookies.txt"
  "public_schema_dump.sql"
)

# Build a single name|name|... regex for `find -name` alternation is not
# portable across BSD/findutils; instead loop per name and dedupe hits.
SCAN_ROOT="${1:-.}"

if [ ! -d "$SCAN_ROOT/.git" ] && [ ! -f "$SCAN_ROOT/.git" ]; then
  printf 'check_no_pii_dumps: %s is not a git work tree\n' "$SCAN_ROOT" >&2
  exit 2
fi

# Prune dirs that never hold these dumps and are expensive to walk. The find
# below hardcodes the same paths (kept in sync manually — a single array
# driving the eval'd find broke -path quoting on BSD find).

hits=()
for name in "${FORBIDDEN[@]}"; do
  while IFS= read -r f; do
    [ -n "$f" ] && hits+=("$f")
  done < <(find "$SCAN_ROOT" \
    \( -path "$SCAN_ROOT/.git" -o -path "$SCAN_ROOT/node_modules" \
       -o -path "$SCAN_ROOT/backend/.venv" -o -path "$SCAN_ROOT/backend/venv" \
       -o -path "$SCAN_ROOT/.venv" \) -prune \
    -o -name "$name" -type f -print 2>/dev/null)
done

# Also check the index: a forbidden dump may be staged (not yet on disk in
# the working tree if removed but still in index). Belt-and-suspenders.
while IFS= read -r staged; do
  [ -n "$staged" ] && hits+=("STAGED: $staged")
done < <(git -C "$SCAN_ROOT" ls-files --cached -- \
  "neo4j.dump" "supabase_dump.sql" "redis_dump.rdb" "cookies.txt" \
  "public_schema_dump.sql" 2>/dev/null)

if [ "${#hits[@]}" -gt 0 ]; then
  printf 'INV-6 FAIL: forbidden PII dump file(s) present in working tree:\n' >&2
  for h in "${hits[@]}"; do
    printf '  - %s\n' "$h" >&2
  done
  printf 'Remove or move them to backups/encrypted/ per docs/runbooks/SECRET_ROTATION.md.\n' >&2
  printf 'The pre-commit hook (T7) and this script (INV-6) prevent regression.\n' >&2
  exit 1
fi

printf 'INV-6 OK: no forbidden PII dump files in working tree (%s)\n' "$SCAN_ROOT"
exit 0
