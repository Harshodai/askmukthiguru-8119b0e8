-- Canonical-memory consolidation rollback snapshots.
-- The consolidator already writes to canonical_memory_compaction_snapshots,
-- but this table had no migration. Without it, snapshot creation silently
-- fails and consolidation could proceed without a recovery point.
--
-- REVERT: Manual only. Dropping this table destroys consolidation rollback
-- history; review users/retention needs before running the statements below.
-- DROP TRIGGER IF EXISTS trg_canonical_memory_compaction_snapshots_active_consent
--   ON public.canonical_memory_compaction_snapshots;
-- DROP POLICY IF EXISTS canonical_memory_compaction_snapshots_service_role
--   ON public.canonical_memory_compaction_snapshots;
-- DROP TABLE IF EXISTS public.canonical_memory_compaction_snapshots;

CREATE TABLE IF NOT EXISTS public.canonical_memory_compaction_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    memories_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS canonical_memory_compaction_snapshots_owner_created_idx
    ON public.canonical_memory_compaction_snapshots (user_id, tenant_id, created_at DESC);

ALTER TABLE public.canonical_memory_compaction_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS canonical_memory_compaction_snapshots_service_role
    ON public.canonical_memory_compaction_snapshots;
CREATE POLICY canonical_memory_compaction_snapshots_service_role
    ON public.canonical_memory_compaction_snapshots
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL ON TABLE public.canonical_memory_compaction_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.canonical_memory_compaction_snapshots TO service_role;

-- This migration runs after the consent guard is installed. Snapshots contain
-- plaintext memory, so creating/updating one is also a consent-gated write.
DROP TRIGGER IF EXISTS trg_canonical_memory_compaction_snapshots_active_consent
    ON public.canonical_memory_compaction_snapshots;
CREATE TRIGGER trg_canonical_memory_compaction_snapshots_active_consent
    BEFORE INSERT OR UPDATE ON public.canonical_memory_compaction_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_active_memory_consent_before_write();

NOTIFY pgrst, 'reload schema';
