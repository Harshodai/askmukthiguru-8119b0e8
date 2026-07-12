-- Feature wave Task 2: retention policy + memory summary column.
-- 1. Add per-conversation retention_days (user-configurable; 0 = forever, default 90).
-- 2. Add guru_memories.summary TEXT for human-readable roll-up of the reflection
--    (the compaction job already computes a summary; this persists it as a column).
-- 3. Grant + (RLS already enabled on guru_memories via 20260711000000_enable_rls_on_all_tables.sql
--    and on conversations via 20260627130000_tenant_rls.sql) — no policy changes needed.

ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS retention_days int NOT NULL DEFAULT 90;

ALTER TABLE public.guru_memories
  ADD COLUMN IF NOT EXISTS summary text;

-- Self-heal existing rows: backfill summary = first 280 chars of claim.
UPDATE public.guru_memories
SET summary = left(claim, 280)
WHERE summary IS NULL AND claim IS NOT NULL;

-- Index for the auto-purge job: scans rows older than retention_days.
CREATE INDEX IF NOT EXISTS idx_conversations_retention_created
  ON public.conversations (created_at)
  WHERE retention_days > 0;

-- Reload PostgREST schema cache so the new columns are visible without restart.
NOTIFY pgrst, 'reload schema';
