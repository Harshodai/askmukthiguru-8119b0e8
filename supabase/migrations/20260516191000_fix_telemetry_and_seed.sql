-- Migration to fix telemetry schema gaps and seed benchmark user
-- 1. Add user_id to chat_sessions and chat_queries
-- 2. Seed the benchmark admin user to auth.users to satisfy foreign key constraints

-- Add user_id columns
ALTER TABLE public.chat_sessions ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.chat_queries ADD COLUMN IF NOT EXISTS user_id uuid;

-- Seed the benchmark admin user into auth.users (idempotent)
-- We use a DO block to handle the insert safely
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = '00000000-0000-0000-0000-000000000000') THEN
        INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at, role, confirmation_token, email_change, email_change_token_new, recovery_token)
        VALUES (
            '00000000-0000-0000-0000-000000000000',
            'benchmark-admin@mukthi.guru',
            '', -- No password needed for test bypass
            now(),
            '{"provider":"local","providers":["local"]}',
            '{"full_name":"Benchmark Admin"}',
            now(),
            now(),
            'authenticated',
            '', '', '', ''
        );
    END IF;
END $$;

-- Ensure the benchmark user has the admin role in our app schema
INSERT INTO public.user_roles (user_id, role)
VALUES ('00000000-0000-0000-0000-000000000000', 'admin'::public.app_role)
ON CONFLICT (user_id, role) DO NOTHING;

-- Also ensure a profile exists
INSERT INTO public.profiles (id, display_name)
VALUES ('00000000-0000-0000-0000-000000000000', 'Benchmark Admin')
ON CONFLICT (id) DO NOTHING;

-- Create user_profiles entry if missing
INSERT INTO public.user_profiles (user_id, preferred_language, spiritual_level, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000000', 'en', 'seeker', extract(epoch from now()), extract(epoch from now()))
ON CONFLICT (user_id) DO NOTHING;

-- Force reload of PostgREST schema cache
NOTIFY pgrst, 'reload schema';
