-- ============================================================================
-- REVERT: Restore the dropped 768-dim embedding column + HNSW index (from
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- 20260605023720). kb_chunks is Qdrant-only today, so this is only needed if a
-- legacy pgvector query path is ever re-enabled. The anon REVOKE + policy drop
-- are hardening — do NOT restore the permissive kb_chunks_read_all policy.
-- ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS embedding vector(768);
-- CREATE INDEX IF NOT EXISTS kb_chunks_embedding_hnsw
--   ON public.kb_chunks USING hnsw (embedding vector_cosine_ops);
-- ============================================================================

-- P1-DB-1: kb_chunks cleanup
-- 1. Drop the dead 768-dim embedding column + HNSW index.
--    Retrieval is Qdrant-only (bge-m3, 1024-d) since 20260722090000; no backend code reads kb_chunks.
-- 2. anon exposure was already remediated by 20260615044110 (REVOKE SELECT from anon)
--    and 20260714080216 (admin-only select policy). The kb_chunks_read_all policy was
--    dropped there; we re-drop defensively and do NOT recreate a permissive policy —
--    the admin-only kb_chunks_admin_select policy from 20260714080216 is the intended state.

ALTER TABLE public.kb_chunks DROP COLUMN IF EXISTS embedding;
DROP INDEX IF EXISTS kb_chunks_embedding_hnsw;
DROP POLICY IF EXISTS kb_chunks_read_all ON public.kb_chunks;
REVOKE SELECT ON public.kb_chunks FROM anon;
NOTIFY pgrst, 'reload schema';
