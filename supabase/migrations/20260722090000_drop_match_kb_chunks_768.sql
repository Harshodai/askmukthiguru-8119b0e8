-- ============================================================================
-- REVERT: RPCs were DROPPED here (dead edge function). Restore only if the legacy
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- Supabase Edge Function returns — definitions live in git history (see
-- 20260605023720 era). Nothing else changed; no other revert SQL needed.
-- ============================================================================

-- Drop the legacy 768-dim match_kb_chunks RPC used only by the dead Supabase Edge Function.
-- The Python backend uses services/embedding_service.py with all-MiniLM-L6-v2 via Qdrant directly.
DROP FUNCTION IF EXISTS public.match_kb_chunks(vector(768), bigint, double precision);
DROP FUNCTION IF EXISTS public.match_kb_chunks(vector(768), integer, double precision);
