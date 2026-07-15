
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'system';

DO $$ BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='guru_memories') THEN
    DROP POLICY IF EXISTS "service_role_all" ON public.guru_memories;
    CREATE POLICY "service_role_all" ON public.guru_memories
      FOR ALL TO service_role USING (true) WITH CHECK (true);
    DROP POLICY IF EXISTS "users_read_own" ON public.guru_memories;
    CREATE POLICY "users_read_own" ON public.guru_memories
      FOR SELECT TO authenticated USING (user_id = auth.uid());
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';
