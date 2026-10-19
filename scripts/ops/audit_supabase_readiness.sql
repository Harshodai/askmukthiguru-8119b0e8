-- ============================================================================
-- Mukthi Guru — production Supabase readiness audit  (READ-ONLY)
-- ============================================================================
-- Paste this whole file into the Supabase SQL Editor and Run.
-- It performs SELECTs against catalog views only. It creates nothing, alters
-- nothing, and deletes nothing. Safe to run against production at any time.
--
-- Read the STATUS column. Any FAIL is a real, currently-silent defect:
--
--   grant:*            Postgres checks table GRANTS *before* RLS, so correct
--                      policies do not help a role with no privilege. With
--                      `user_roles` unreadable every admin check logs a warning
--                      and falls through to NON-ADMIN. With
--                      `conversation_memories` unreadable, personal memory
--                      never reaches an answer. 27 such tables were found on a
--                      database built purely from this repo's migrations.
--
--   table:canonical_memory_events
--                      The API writes this on every memory mutation and the
--                      GDPR export reads it. If it is missing, the memory row
--                      commits and the audit insert raises: the seeker is told
--                      "Failed to save memory" about a memory that SAVED, and
--                      a retry duplicates it.
--
--   constraint:actor_check
--                      resolver.py and consolidator.py write actor='resolver' /
--                      'consolidator'. If the CHECK rejects them the audit
--                      insert raises 23514 *inside a swallowing except*, so
--                      memories accumulate with no audit trail at all.
--
--   rls:*              These tables carry one seeker's private content.
--
--   grant_write:*:*    service_role can read a table and still lack INSERT /
--                      UPDATE / DELETE on it — Postgres grants each privilege
--                      separately, so passing grant:* proves nothing about
--                      writes. Each check name is the table and the verb the
--                      backend actually issues against it (grep'd from
--                      backend/, 2026-09-14), e.g. grant_write:memory_outbox:
--                      delete FAILing means the outbox worker's cleanup silently
--                      42501s and rows never get reaped.
--
-- Remedies live in supabase/migrations/2026091200000{1,2} and
-- 20260913120000. Apply those, then re-run this until everything is PASS.
-- ============================================================================

WITH required_readable(tbl) AS (
    VALUES ('canonical_memories'), ('canonical_memory_events'),
           ('conversation_memories'), ('memory_consent_receipts'),
           ('memory_deletion_receipts'), ('memory_outbox'),
           ('user_roles'), ('profiles'), ('user_healing_progress'),
           ('chat_responses')
),
required_rls(tbl) AS (
    VALUES ('canonical_memories'), ('canonical_memory_events'),
           ('conversation_memories')
),
required_actors(actor) AS (
    VALUES ('user'), ('resolver'), ('consolidator')
),
-- Write verbs service_role actually issues, one row per table+verb pair
-- (grep for .insert(/.update(/.upsert(/.delete( against each table, 2026-09-14).
-- `profiles` and `user_healing_progress` are absent here on purpose: no write
-- call site exists for either in backend/ (profiles is populated by Supabase
-- auth, not app code) — do not add them without a real call site to cite.
-- canonical_memory_events carries only INSERT: it is an append-only ledger by
-- design, so a missing UPDATE/DELETE grant is correct, not a gap.
required_writes(tbl, priv) AS (
    VALUES ('canonical_memories', 'INSERT'), ('canonical_memories', 'UPDATE'),
           ('canonical_memories', 'DELETE'),
           ('canonical_memory_events', 'INSERT'),
           ('conversation_memories', 'INSERT'), ('conversation_memories', 'UPDATE'),
           ('memory_consent_receipts', 'INSERT'),
           ('memory_deletion_receipts', 'INSERT'),
           ('memory_outbox', 'INSERT'), ('memory_outbox', 'UPDATE'),
           ('memory_outbox', 'DELETE'),
           ('user_roles', 'INSERT'), ('user_roles', 'UPDATE'), ('user_roles', 'DELETE'),
           ('chat_responses', 'INSERT'), ('chat_responses', 'UPDATE')
),

-- 1. Do the tables the backend depends on exist?
check_tables AS (
    SELECT
        'table:' || r.tbl AS check_name,
        CASE WHEN t.table_name IS NULL THEN 'FAIL' ELSE 'PASS' END AS status,
        CASE WHEN t.table_name IS NULL
             THEN 'MISSING — see the header for what breaks'
             ELSE 'exists' END AS detail
    FROM required_readable r
    LEFT JOIN information_schema.tables t
           ON t.table_schema = 'public' AND t.table_name = r.tbl
),

-- 2. Can service_role (the backend's own role) read them?
check_grants AS (
    SELECT
        'grant:' || r.tbl AS check_name,
        CASE WHEN g.table_name IS NULL THEN 'FAIL' ELSE 'PASS' END AS status,
        CASE WHEN g.table_name IS NULL
             THEN 'NO service_role SELECT — every read fails with 42501'
             ELSE 'service_role SELECT' END AS detail
    FROM required_readable r
    JOIN information_schema.tables t
      ON t.table_schema = 'public' AND t.table_name = r.tbl      -- only if it exists
    -- has_table_privilege, NOT information_schema.role_table_grants: that view is
    -- filtered to grants where the CONNECTING role is grantor, grantee, or a member
    -- of the grantee. Supabase's SQL Editor connects as supabase_read_only_user,
    -- which is none of those for service_role, so the view reports every table as
    -- ungranted and the audit invents a broken production. has_table_privilege asks
    -- the catalog directly and is independent of who is connected.
    LEFT JOIN LATERAL (
        SELECT r.tbl AS table_name
        WHERE has_table_privilege('service_role', 'public.' || quote_ident(r.tbl), 'SELECT')
    ) g ON TRUE
),

-- 3. Can service_role perform the writes the code actually issues? Read
-- access proves nothing here — INSERT/UPDATE/DELETE are separate GRANTs.
check_grant_writes AS (
    SELECT
        'grant_write:' || w.tbl || ':' || lower(w.priv) AS check_name,
        CASE WHEN has_table_privilege('service_role', 'public.' || quote_ident(w.tbl), w.priv)
             THEN 'PASS' ELSE 'FAIL' END AS status,
        CASE WHEN has_table_privilege('service_role', 'public.' || quote_ident(w.tbl), w.priv)
             THEN 'service_role ' || w.priv
             ELSE 'NO service_role ' || w.priv || ' — writes fail with 42501' END AS detail
    FROM required_writes w
    JOIN information_schema.tables t
      ON t.table_schema = 'public' AND t.table_name = w.tbl      -- only if it exists
),

-- 4. Schema-wide sweep: ANY public table the server role cannot read.
ungranted AS (
    SELECT t.table_name
    FROM information_schema.tables t
    WHERE t.table_schema = 'public'
      AND t.table_type = 'BASE TABLE'
      AND NOT has_table_privilege(
              'service_role', 'public.' || quote_ident(t.table_name), 'SELECT')
),
check_sweep AS (
    SELECT
        'grant:all_public_tables' AS check_name,
        CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
        CASE WHEN count(*) = 0
             THEN 'every public table readable by service_role'
             ELSE count(*) || ' unreadable: ' ||
                  string_agg(table_name, ', ' ORDER BY table_name)
        END AS detail
    FROM ungranted
),

-- 5. Is RLS on for the tables holding private seeker content?
check_rls AS (
    SELECT
        'rls:' || r.tbl AS check_name,
        CASE WHEN c.relname IS NULL THEN 'FAIL'
             WHEN c.relrowsecurity THEN 'PASS'
             ELSE 'FAIL' END AS status,
        CASE WHEN c.relname IS NULL THEN 'table missing, cannot verify RLS'
             WHEN c.relrowsecurity THEN 'enabled'
             ELSE 'DISABLED — seeker content is not row-isolated' END AS detail
    FROM required_rls r
    LEFT JOIN pg_class c
           ON c.relname = r.tbl
          AND c.relkind = 'r'
          AND c.relnamespace = 'public'::regnamespace
),

-- 6. Does the audit CHECK admit every actor the code writes?
actor_def AS (
    SELECT pg_get_constraintdef(oid) AS def
    FROM pg_constraint
    WHERE conname = 'canonical_memory_events_actor_check'
    LIMIT 1
),
check_actor AS (
    SELECT
        'constraint:actor_check' AS check_name,
        CASE
            WHEN (SELECT def FROM actor_def) IS NULL THEN 'FAIL'
            WHEN EXISTS (
                SELECT 1 FROM required_actors a
                WHERE (SELECT def FROM actor_def) NOT LIKE '%''' || a.actor || '''%'
            ) THEN 'FAIL'
            ELSE 'PASS'
        END AS status,
        CASE
            WHEN (SELECT def FROM actor_def) IS NULL
                THEN 'constraint absent — cannot verify audit writers'
            WHEN EXISTS (
                SELECT 1 FROM required_actors a
                WHERE (SELECT def FROM actor_def) NOT LIKE '%''' || a.actor || '''%'
            ) THEN 'rejects ' || (
                SELECT string_agg(a.actor, ', ')
                FROM required_actors a
                WHERE (SELECT def FROM actor_def) NOT LIKE '%''' || a.actor || '''%'
            ) || ' — audit writes raise 23514 and are swallowed'
            ELSE 'admits all writers'
        END AS detail
),

all_checks AS (
    SELECT * FROM check_tables
    UNION ALL SELECT * FROM check_grants
    UNION ALL SELECT * FROM check_grant_writes
    UNION ALL SELECT * FROM check_sweep
    UNION ALL SELECT * FROM check_rls
    UNION ALL SELECT * FROM check_actor
)

SELECT
    status,
    check_name,
    detail
FROM all_checks
ORDER BY (status = 'PASS'), check_name;   -- FAILs first
