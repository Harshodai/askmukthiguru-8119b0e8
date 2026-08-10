-- audit_grants.sql — CRIT-2 (reclassified P1 defense-in-depth)
--
-- Assert that the anonymous role has NO table grants on any PII-bearing
-- table in the public schema. Supabase's default access privileges only
-- grant anon TRIGGER / TRUNCATE / REFERENCES (schema plumbing, no data
-- access); any SELECT / INSERT / UPDATE / DELETE grant to `anon` on a
-- PII table is an exposure.
--
-- MUST return 0 rows. Any row is a finding to remediate by REVOKE.
--
-- Run with:
--   psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -f scripts/security/audit_grants.sql
-- or (CLI):
--   npx supabase db query --file scripts/security/audit_grants.sql
--
-- Covered tables: chat_*, guru_*, user_*, retrieval_*, push_*,
-- conversation*, notes, study_*, kb_chunks, router_*. Table-level grants
-- only (column-level grants are not used anywhere in this schema).
-- router_* added in CRIT-3: router_decisions holds PII (query_text).

SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'anon'
  AND table_schema = 'public'
  AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
  AND (
    table_name LIKE 'chat%'
    OR table_name LIKE 'guru%'
    OR table_name LIKE 'user%'
    OR table_name LIKE 'retrieval%'
    OR table_name LIKE 'push%'
    OR table_name LIKE 'conversation%'
    OR table_name LIKE 'notes%'
    OR table_name LIKE 'study%'
    OR table_name = 'kb_chunks'
    OR table_name LIKE 'router%'
  )
ORDER BY table_name, privilege_type;
