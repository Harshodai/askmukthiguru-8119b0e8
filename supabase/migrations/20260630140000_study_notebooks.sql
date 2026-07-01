-- Phase 4: Persistent study notebooks

CREATE TABLE IF NOT EXISTS public.study_notebooks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.study_notebook_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id uuid NOT NULL REFERENCES public.study_notebooks(id) ON DELETE CASCADE,
  query text NOT NULL,
  answer text NOT NULL,
  citations jsonb DEFAULT '[]'::jsonb,
  source_episode_id uuid REFERENCES public.user_episodes(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.study_notebooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.study_notebook_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users select own notebooks" ON public.study_notebooks;
CREATE POLICY "users select own notebooks" ON public.study_notebooks
  FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users insert own notebooks" ON public.study_notebooks;
CREATE POLICY "users insert own notebooks" ON public.study_notebooks
  FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "users delete own notebooks" ON public.study_notebooks;
CREATE POLICY "users delete own notebooks" ON public.study_notebooks
  FOR DELETE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "users select own items" ON public.study_notebook_items;
CREATE POLICY "users select own items" ON public.study_notebook_items
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.study_notebooks nb
    WHERE nb.id = notebook_id AND nb.user_id = auth.uid()
  ));
DROP POLICY IF EXISTS "users insert own items" ON public.study_notebook_items;
CREATE POLICY "users insert own items" ON public.study_notebook_items
  FOR INSERT WITH CHECK (EXISTS (
    SELECT 1 FROM public.study_notebooks nb
    WHERE nb.id = notebook_id AND nb.user_id = auth.uid()
  ));

CREATE INDEX IF NOT EXISTS study_notebooks_user_created_idx
  ON public.study_notebooks (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS study_notebook_items_notebook_created_idx
  ON public.study_notebook_items (notebook_id, created_at DESC);
