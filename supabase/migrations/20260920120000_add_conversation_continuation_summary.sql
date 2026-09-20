-- Persist only the compact continuation summary; never replace the durable transcript.
ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS summary text;

NOTIFY pgrst, 'reload schema';
