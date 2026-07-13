-- Enable Row Level Security on all public tables that lack it.
-- These tables had RLS disabled, making them fully exposed to anon
-- and authenticated roles via the Supabase REST API.
--
-- Policies added:
--   gurus:                  SELECT for everyone (public reference data)
--   assistant_configurations: admin-only (has_role check)
--   assistant_doctrines:     admin-only (has_role check)
--   communications:          user-own SELECT + INSERT, admin full access
--   digital_employees:       user-own SELECT + INSERT + UPDATE, admin full access
--
-- The service_role key (used by backend) bypasses RLS entirely.

-- ============ gurus (public reference data) ============
ALTER TABLE IF EXISTS public.gurus ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Everyone can view gurus" ON public.gurus;
CREATE POLICY "Everyone can view gurus" ON public.gurus
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Admins can manage gurus" ON public.gurus;
CREATE POLICY "Admins can manage gurus" ON public.gurus
  FOR ALL USING (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ============ assistant_configurations (admin only) ============
ALTER TABLE IF EXISTS public.assistant_configurations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins can manage assistant_configurations" ON public.assistant_configurations;
CREATE POLICY "Admins can manage assistant_configurations" ON public.assistant_configurations
  FOR ALL USING (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ============ assistant_doctrines (admin only) ============
ALTER TABLE IF EXISTS public.assistant_doctrines ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins can manage assistant_doctrines" ON public.assistant_doctrines;
CREATE POLICY "Admins can manage assistant_doctrines" ON public.assistant_doctrines
  FOR ALL USING (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ============ communications (user-owned) ============
DO $$ 
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'communications') THEN
    ALTER TABLE public.communications ENABLE ROW LEVEL SECURITY;
    
    DROP POLICY IF EXISTS "Users can view own communications" ON public.communications;
    CREATE POLICY "Users can view own communications" ON public.communications
      FOR SELECT USING (auth.uid() = user_id);
    
    DROP POLICY IF EXISTS "Users can insert own communications" ON public.communications;
    CREATE POLICY "Users can insert own communications" ON public.communications
      FOR INSERT WITH CHECK (auth.uid() = user_id);
    
    DROP POLICY IF EXISTS "Admins can manage communications" ON public.communications;
    CREATE POLICY "Admins can manage communications" ON public.communications
      FOR ALL USING (public.has_role(auth.uid(), 'admin'::public.app_role));
  END IF;
END $$;

-- ============ digital_employees (user-owned) ============
DO $$ 
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'digital_employees') THEN
    ALTER TABLE public.digital_employees ENABLE ROW LEVEL SECURITY;
    
    DROP POLICY IF EXISTS "Users can view own digital_employees" ON public.digital_employees;
    CREATE POLICY "Users can view own digital_employees" ON public.digital_employees
      FOR SELECT USING (auth.uid() = user_id);
    
    DROP POLICY IF EXISTS "Users can insert own digital_employees" ON public.digital_employees;
    CREATE POLICY "Users can insert own digital_employees" ON public.digital_employees
      FOR INSERT WITH CHECK (auth.uid() = user_id);
    
    DROP POLICY IF EXISTS "Users can update own digital_employees" ON public.digital_employees;
    CREATE POLICY "Users can update own digital_employees" ON public.digital_employees
      FOR UPDATE USING (auth.uid() = user_id);
    
    DROP POLICY IF EXISTS "Admins can manage digital_employees" ON public.digital_employees;
    CREATE POLICY "Admins can manage digital_employees" ON public.digital_employees
      FOR ALL USING (public.has_role(auth.uid(), 'admin'::public.app_role));
  END IF;
END $$;

-- Reload PostgREST schema cache to pick up the new policies and function changes
NOTIFY pgrst, 'reload schema';
