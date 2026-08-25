#!/usr/bin/env bash
# Verify migration behavior inside one transaction and roll it back.
# This proves the migration SQL is transaction-safe without leaving staging changes.
# Required: STAGING_ENVIRONMENT=staging, ALLOW_NONDESTRUCTIVE_DB_VERIFY=1,
#           STAGING_DB_URL=postgresql://...
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT/supabase/migrations"
DB_URL="${STAGING_DB_URL:?Set STAGING_DB_URL to the staging Postgres connection string}"

if [ "${STAGING_ENVIRONMENT:-}" != "staging" ]; then
  echo "Refusing migration verification unless STAGING_ENVIRONMENT=staging" >&2
  exit 2
fi
if [ "${ALLOW_NONDESTRUCTIVE_DB_VERIFY:-}" != "1" ]; then
  echo "Set ALLOW_NONDESTRUCTIVE_DB_VERIFY=1 to authorize transaction-only verification" >&2
  exit 2
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required for migration verification" >&2
  exit 2
fi

MIGRATION_GRANTS="$MIGRATIONS_DIR/20260825000000_restore_conversation_table_grants.sql"
MIGRATION_TRIGGER="$MIGRATIONS_DIR/20260825000001_fix_chat_message_profile_trigger.sql"
MIGRATION_ACTIVITY="$MIGRATIONS_DIR/20260825000002_restore_user_activity_table_grants.sql"
[ -f "$MIGRATION_GRANTS" ] || { echo "Missing grants migration" >&2; exit 2; }
[ -f "$MIGRATION_TRIGGER" ] || { echo "Missing trigger migration" >&2; exit 2; }
[ -f "$MIGRATION_ACTIVITY" ] || { echo "Missing user-activity grants migration" >&2; exit 2; }

EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/.staging-evidence}"
mkdir -p "$EVIDENCE_DIR"

state_sql="SELECT jsonb_build_object(
  'authenticated_conversations', has_table_privilege('authenticated', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE'),
  'authenticated_messages', has_table_privilege('authenticated', 'public.chat_messages', 'SELECT,INSERT,UPDATE,DELETE'),
  'service_role_conversations', has_table_privilege('service_role', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE'),
  'service_role_messages', has_table_privilege('service_role', 'public.chat_messages', 'SELECT,INSERT,UPDATE,DELETE'),
  'authenticated_sessions', has_table_privilege('authenticated', 'public.meditation_sessions', 'SELECT,INSERT,UPDATE,DELETE'),
  'authenticated_profiles', has_table_privilege('authenticated', 'public.user_profiles', 'SELECT,INSERT,UPDATE,DELETE'),
  'service_role_sessions', has_table_privilege('service_role', 'public.meditation_sessions', 'SELECT,INSERT,UPDATE,DELETE'),
  'service_role_profiles', has_table_privilege('service_role', 'public.user_profiles', 'SELECT,INSERT,UPDATE,DELETE'),
  'trigger_function_md5', COALESCE((SELECT md5(pg_get_functiondef(p.oid)) FROM pg_proc AS p WHERE p.oid = 'public.touch_user_last_message()'::regprocedure), 'missing')
)::text;"

psql_args=(-X -v ON_ERROR_STOP=1 -A -t "$DB_URL")

before="$(psql "${psql_args[@]}" -c "$state_sql")"
printf '%s\n' "$before" > "$EVIDENCE_DIR/migration-state-before.json"

transaction_sql="$EVIDENCE_DIR/migration-transaction.sql"
{
  printf '%s\n' 'BEGIN;'
  cat "$MIGRATION_GRANTS"
  cat "$MIGRATION_TRIGGER"
  cat "$MIGRATION_ACTIVITY"
  printf '%s\n' "SELECT CASE WHEN"
  printf '%s\n' "  has_table_privilege('authenticated', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('authenticated', 'public.chat_messages', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('service_role', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('service_role', 'public.chat_messages', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('authenticated', 'public.meditation_sessions', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('authenticated', 'public.user_profiles', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('service_role', 'public.meditation_sessions', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND has_table_privilege('service_role', 'public.user_profiles', 'SELECT,INSERT,UPDATE,DELETE')"
  printf '%s\n' "  AND pg_get_functiondef('public.touch_user_last_message()'::regprocedure) LIKE '%SELECT c.user_id%'"
  printf '%s\n' "  AND pg_get_functiondef('public.touch_user_last_message()'::regprocedure) LIKE '%NEW.conversation_id%'"
  printf '%s\n' "  AND pg_get_functiondef('public.touch_user_last_message()'::regprocedure) NOT LIKE '%NEW.user_id%'"
  printf '%s\n' "THEN 'FORWARD_OK' ELSE 'FORWARD_FAILED' END;"
  printf '%s\n' 'ROLLBACK;'
} > "$transaction_sql"

forward_result="$(psql "${psql_args[@]}" -f "$transaction_sql")"
printf '%s\n' "$forward_result" > "$EVIDENCE_DIR/migration-transaction.result"
if ! printf '%s\n' "$forward_result" | grep -qx 'FORWARD_OK'; then
  echo "Migration forward-apply assertions failed inside transaction" >&2
  exit 1
fi

after="$(psql "${psql_args[@]}" -c "$state_sql")"
printf '%s\n' "$after" > "$EVIDENCE_DIR/migration-state-after.json"
if [ "$before" != "$after" ]; then
  echo "Rollback verification failed: database state changed after ROLLBACK" >&2
  exit 1
fi

printf '%s\n' '{"ok":true,"forward_apply":"passed_inside_transaction","rollback":"state_unchanged","mutated_rows":0}' \
  | tee "$EVIDENCE_DIR/migration-rollback.result.json"
