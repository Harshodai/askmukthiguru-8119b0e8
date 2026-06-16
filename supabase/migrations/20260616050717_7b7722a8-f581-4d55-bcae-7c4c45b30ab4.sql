
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS last_conversation_id uuid;

CREATE TABLE IF NOT EXISTS public.pending_extractions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempts int NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.pending_extractions TO authenticated;
GRANT ALL ON public.pending_extractions TO service_role;

ALTER TABLE public.pending_extractions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_extractions_insert" ON public.pending_extractions
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "own_extractions_select" ON public.pending_extractions
  FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS pending_extractions_status_idx
  ON public.pending_extractions(status, created_at)
  WHERE status = 'pending';
