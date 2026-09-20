-- Persist only the compact continuation summary; never replace the durable transcript.
ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS summary text;

NOTIFY pgrst, 'reload schema';

-- REVERT: Drop summary column from public.conversations
-- ALTER TABLE public.conversations DROP COLUMN IF EXISTS summary;
-- NOTIFY pgrst, 'reload schema';
