-- ponytail: this CREATE TABLE IF NOT EXISTS stub is intentional, not
-- redundant — migration-revert-check.yml applies each changed migration
-- alone against a fresh, empty ephemeral Postgres (no baseline replay), so
-- without it the ADD COLUMN below fails CI with "relation does not exist".
-- Confirmed against lessons.md L-MIGRATE-EPHEMERAL-1 (2026-09-20) and
-- .github/workflows/migration-revert-check.yml before touching this. Do not
-- remove without also changing how that workflow seeds the ephemeral DB.
CREATE TABLE IF NOT EXISTS public.conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  created_at timestamptz DEFAULT now()
);

-- Persist only the compact continuation summary; never replace the durable transcript.
ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS summary text;

NOTIFY pgrst, 'reload schema';

-- REVERT: Drop summary column from public.conversations
-- ALTER TABLE public.conversations DROP COLUMN IF EXISTS summary;
-- NOTIFY pgrst, 'reload schema';
