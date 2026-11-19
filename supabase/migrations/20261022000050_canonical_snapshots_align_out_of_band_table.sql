-- public.canonical_memory_compaction_snapshots already existed in production
-- (created by hand, so no migration recorded it) with memories_json TEXT and an
-- index/trigger under different names than 20261022000100 creates. Align it first
-- so that migration is a clean no-op on the table and does not leave duplicates.
-- Only converts the column while the table is empty; otherwise it fails loudly.
-- REVERT: MANUAL ONLY.
DO $$
BEGIN
  IF (SELECT data_type FROM information_schema.columns
       WHERE table_schema='public' AND table_name='canonical_memory_compaction_snapshots'
         AND column_name='memories_json') = 'text' THEN
    IF (SELECT count(*) FROM public.canonical_memory_compaction_snapshots) = 0 THEN
      ALTER TABLE public.canonical_memory_compaction_snapshots
        ALTER COLUMN memories_json TYPE jsonb USING memories_json::jsonb;
    ELSE
      RAISE EXCEPTION 'canonical_memory_compaction_snapshots has rows and a text memories_json; convert it by hand';
    END IF;
  END IF;
END $$;
DROP INDEX IF EXISTS public.canonical_memory_compaction_snapshots_user_tenant_created_idx;
DROP TRIGGER IF EXISTS enforce_memory_consent_before_write ON public.canonical_memory_compaction_snapshots;
