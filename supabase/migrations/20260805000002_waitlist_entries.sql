-- Consent-required, service-role-only early-access intake.
CREATE TABLE IF NOT EXISTS public.waitlist_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    email_key text GENERATED ALWAYS AS (lower(email)) STORED UNIQUE,
    name text,
    source text,
    consented_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT waitlist_email_nonempty CHECK (length(trim(email)) > 3),
    CONSTRAINT waitlist_name_length CHECK (name IS NULL OR char_length(name) <= 100),
    CONSTRAINT waitlist_source_length CHECK (char_length(source) <= 80)
);

ALTER TABLE public.waitlist_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.waitlist_entries FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.waitlist_entries TO service_role;
