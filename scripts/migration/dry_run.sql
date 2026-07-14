-- ============================================================================
-- Migration dry-run — read-only assertions against the target Lovable Cloud
-- project. Safe to run on production. Fails loudly if the schema drifted.
--
-- Usage: psql "$SUPABASE_DB_URL" -f scripts/migration/dry_run.sql
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- 1) All 37 expected tables must exist ----------------------------------------
DO $$
DECLARE
  expected text[] := ARRAY[
    'alert_events','alert_rules','annotations','app_logs','assistant_access',
    'assistants','chat_messages','chat_queries','chat_responses','chat_sessions',
    'conversations','daily_teachings','eval_results','eval_runs','feedback_events',
    'golden_questions','guru_core_memory','guru_memories','guru_session_summaries',
    'ingestion_runs','kb_chunks','kb_sources','meditation_sessions','model_pricing',
    'notes','pending_extractions','profiles','prompt_versions','push_subscriptions',
    'query_clusters','retrieval_events','safety_events','telemetry_events',
    'trace_spans','trigger_events','user_profiles','user_roles'
  ];
  missing text[];
BEGIN
  SELECT array_agg(t) INTO missing
  FROM unnest(expected) t
  WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = t
  );
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: missing tables: %', missing;
  END IF;
  RAISE NOTICE '✓ all 37 expected tables present';
END $$;

-- 2) Every public table must have RLS enabled --------------------------------
DO $$
DECLARE
  bad text[];
BEGIN
  SELECT array_agg(c.relname) INTO bad
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: RLS disabled on: %', bad;
  END IF;
  RAISE NOTICE '✓ RLS enabled on every public table';
END $$;

-- 3) Every public table must GRANT to `authenticated` OR `service_role` ------
DO $$
DECLARE
  bad text[];
BEGIN
  SELECT array_agg(t.table_name) INTO bad
  FROM information_schema.tables t
  WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
    AND NOT EXISTS (
      SELECT 1 FROM information_schema.role_table_grants g
      WHERE g.table_schema = 'public'
        AND g.table_name = t.table_name
        AND g.grantee IN ('authenticated','service_role')
    );
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: no GRANT to authenticated/service_role on: %', bad;
  END IF;
  RAISE NOTICE '✓ GRANTs present on every public table';
END $$;

-- 4) Critical functions must exist -------------------------------------------
DO $$
DECLARE
  required text[] := ARRAY[
    'has_role','handle_new_user','ensure_profile_and_role',
    'whoami_diagnostics','grant_admin_for_designated_emails',
    'promote_admin_by_email','demote_admin_by_id','list_admins',
    'match_kb_chunks','match_user_memories'
  ];
  missing text[];
BEGIN
  SELECT array_agg(f) INTO missing
  FROM unnest(required) f
  WHERE NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = f
  );
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: missing functions: %', missing;
  END IF;
  RAISE NOTICE '✓ all critical functions present';
END $$;

-- 5) Admin auto-grant trigger wired ------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname LIKE '%grant_admin%'
  ) THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: grant_admin_for_designated_emails triggers not installed';
  END IF;
  RAISE NOTICE '✓ admin auto-grant triggers installed';
END $$;

-- 6) app_role enum has expected values ---------------------------------------
DO $$
DECLARE
  vals text[];
BEGIN
  SELECT array_agg(enumlabel::text ORDER BY enumsortorder) INTO vals
  FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
  WHERE t.typname = 'app_role';
  IF NOT (vals @> ARRAY['admin','user']) THEN
    RAISE EXCEPTION 'DRY-RUN FAIL: app_role enum missing admin/user, got %', vals;
  END IF;
  RAISE NOTICE '✓ app_role enum = %', vals;
END $$;

COMMIT;

\echo ''
\echo '================================================================'
\echo '  DRY-RUN PASSED — target schema matches expectations.'
\echo '  Safe to flip Railway env vars to Lovable Cloud.'
\echo '================================================================'
