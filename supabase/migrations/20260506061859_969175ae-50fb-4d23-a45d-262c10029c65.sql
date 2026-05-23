-- User roles (type, table, and function are already defined in 20240430000000_schema.sql)

-- RLS: users can read their own roles, admins can read all
CREATE POLICY "users_read_own_roles" ON public.user_roles
  FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.has_role(auth.uid(), 'admin'));

-- Profiles
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  preferred_language TEXT DEFAULT 'en',
  tts_enabled BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_profile_select" ON public.profiles
  FOR SELECT TO authenticated USING (id = auth.uid());
CREATE POLICY "own_profile_update" ON public.profiles
  FOR UPDATE TO authenticated USING (id = auth.uid()) WITH CHECK (id = auth.uid());
CREATE POLICY "own_profile_insert" ON public.profiles
  FOR INSERT TO authenticated WITH CHECK (id = auth.uid());

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url');
  RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Daily teachings with 24h TTL
CREATE TABLE public.daily_teachings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  image_url TEXT NOT NULL,
  caption TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '24 hours'),
  created_by UUID REFERENCES auth.users(id)
);
ALTER TABLE public.daily_teachings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone_reads_active" ON public.daily_teachings
  FOR SELECT TO authenticated USING (expires_at > now());
CREATE POLICY "admin_insert" ON public.daily_teachings
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admin_delete" ON public.daily_teachings
  FOR DELETE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

-- Meditation sessions
CREATE TABLE public.meditation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_seconds INT DEFAULT 0,
  breath_cycles INT DEFAULT 0,
  completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.meditation_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_sessions_select" ON public.meditation_sessions
  FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "own_sessions_insert" ON public.meditation_sessions
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "own_sessions_update" ON public.meditation_sessions
  FOR UPDATE TO authenticated USING (user_id = auth.uid());

-- Storage bucket for daily teaching images
INSERT INTO storage.buckets (id, name, public) VALUES ('daily-teachings', 'daily-teachings', true);

CREATE POLICY "admin_upload_teaching_images" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'daily-teachings' AND public.has_role(auth.uid(), 'admin'));

CREATE POLICY "public_read_teaching_images" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'daily-teachings');
