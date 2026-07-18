-- Create user_brain_keys table if not exists
-- Required for second brain feature

CREATE TABLE IF NOT EXISTS public.user_brain_keys (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    kek text NOT NULL,                          -- wrapped DEK (one per user)
    dek_wrapped text,                           -- optional double-wrap for rotation
    rotated_at timestamptz,
    created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.user_brain_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "owner_brain_keys" ON public.user_brain_keys;
CREATE POLICY "owner_brain_keys" ON public.user_brain_keys
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_brain_keys TO authenticated;
GRANT ALL ON public.user_brain_keys TO service_role;

CREATE INDEX IF NOT EXISTS user_brain_keys_user_id_idx ON public.user_brain_keys (user_id);

-- Ensure the other second brain tables exist (they should from 20260717191006_second_brain_vault.sql)
-- But ensure schema cache is refreshed
NOTIFY pgrst, 'reload schema';
