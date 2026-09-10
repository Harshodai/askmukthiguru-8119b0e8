-- Lock down create_compaction_snapshot: it is SECURITY DEFINER (runs with the
-- function owner's privileges, bypassing the caller's RLS), but the original
-- migration never restricted EXECUTE, so any authenticated/anon role could
-- call it with an arbitrary p_user_id and insert/delete another user's
-- compaction snapshot rows. Also pin search_path so a session-level path
-- override can't redirect the unqualified table references to a hostile
-- schema (the standard SECURITY DEFINER hardening).

REVOKE ALL ON FUNCTION create_compaction_snapshot(UUID, JSONB) FROM PUBLIC;
REVOKE ALL ON FUNCTION create_compaction_snapshot(UUID, JSONB) FROM anon;
GRANT EXECUTE ON FUNCTION create_compaction_snapshot(UUID, JSONB) TO service_role;

ALTER FUNCTION create_compaction_snapshot(UUID, JSONB) SET search_path = public, pg_temp;
