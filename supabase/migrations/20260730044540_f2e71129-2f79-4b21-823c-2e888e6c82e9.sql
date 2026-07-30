CREATE TABLE public.user_course_progress (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL,
  course_slug text NOT NULL,
  assigned_reason text,
  trigger_signal text,
  completed_lessons text[] NOT NULL DEFAULT '{}',
  current_lesson_index integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'active',
  started_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  UNIQUE (user_id, course_slug)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_course_progress TO authenticated;
GRANT ALL ON public.user_course_progress TO service_role;

ALTER TABLE public.user_course_progress ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own course progress"
  ON public.user_course_progress FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users insert own course progress"
  ON public.user_course_progress FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own course progress"
  ON public.user_course_progress FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own course progress"
  ON public.user_course_progress FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

CREATE INDEX idx_user_course_progress_user ON public.user_course_progress (user_id, status);

CREATE TRIGGER trg_user_course_progress_updated_at
  BEFORE UPDATE ON public.user_course_progress
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();