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
