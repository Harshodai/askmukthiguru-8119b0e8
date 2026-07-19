-- Create user_brain_keys table if not exists
-- Required for second brain feature

CREATE TABLE IF NOT EXISTS public.user_brain_keys (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    kek text NOT NULL,                          -- wrapped DEK (one per user)
    dek_wrapped text,                           -- optional double-wrap for rotation
    rotated_at timestamptz,
    created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL
);

ALTER TABLE public.user_brain_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "owner_brain_keys" ON public.user_brain_keys;
CREATE POLICY "owner_brain_keys" ON public.user_brain_keys
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_brain_keys TO authenticated;
GRANT ALL ON public.user_brain_keys TO service_role;

CREATE INDEX IF NOT EXISTS user_brain_keys_user_id_idx ON public.user_brain_keys (user_id);

-- updated_at auto-refresh.
-- NOTE: 20260717191006_second_brain_vault.sql runs earlier and creates
-- user_brain_keys WITHOUT an updated_at column, so the CREATE TABLE above is a
-- no-op when that migration already applied. Force-add the column (idempotent)
-- so the trigger below has something to write regardless of apply order.
ALTER TABLE public.user_brain_keys
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- Refresh updated_at on every UPDATE (key rotations, re-wraps) so it can never
-- go stale; INSERTs keep the column default.
DROP TRIGGER IF EXISTS user_brain_keys_set_updated_at ON public.user_brain_keys;
CREATE TRIGGER user_brain_keys_set_updated_at
    BEFORE UPDATE ON public.user_brain_keys
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Ensure the other second brain tables exist (they should from 20260717191006_second_brain_vault.sql)
-- But ensure schema cache is refreshed
NOTIFY pgrst, 'reload schema';
