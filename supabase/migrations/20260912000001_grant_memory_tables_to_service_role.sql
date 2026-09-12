-- Grant the memory tables to service_role.
--
-- Postgres checks table GRANTS before RLS policies, so a table with correct
-- RLS and no grant fails with 42501 regardless of policy. None of the
-- migrations that created these tables granted anything to service_role, which
-- is the role the backend's Supabase client uses. On any database built purely
-- from migrations, every read of them failed — and `user_profile_service`
-- swallows that failure as a WARNING, so personal memory silently never
-- reached an answer while the app looked healthy. Observed 2026-09-12 on a
-- local stack with all migrations applied:
--   "Supabase memory fetch failed ...: permission denied for table
--    conversation_memories (42501)"
--
-- RLS still governs row visibility for anon/authenticated; this only gives the
-- server role the table-level privileges its policies assume.

GRANT SELECT, INSERT, UPDATE, DELETE ON public.conversation_memories   TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.memory_outbox           TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.memory_compaction_snapshots TO service_role;
-- Receipts are an append-only consent/erasure record: the server may write and
-- read them, but must not rewrite or delete a receipt it already issued.
GRANT SELECT, INSERT ON public.memory_consent_receipts  TO service_role;
GRANT SELECT, INSERT ON public.memory_deletion_receipts TO service_role;
