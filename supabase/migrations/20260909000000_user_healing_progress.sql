-- user_healing_progress: tracks step-level progress through healing courses.
-- Separate from user_course_progress (lesson-level) for granular tracking.

CREATE TABLE IF NOT EXISTS public.user_healing_progress (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    course_slug TEXT NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0 CHECK (current_step >= 0),
    completed_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- One active progress row per user per course.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_healing_progress_user_course
  ON public.user_healing_progress (user_id, course_slug);

-- RLS: users can only see/modify their own progress.
ALTER TABLE public.user_healing_progress ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own healing progress"
  ON public.user_healing_progress FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own healing progress"
  ON public.user_healing_progress FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own healing progress"
  ON public.user_healing_progress FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
