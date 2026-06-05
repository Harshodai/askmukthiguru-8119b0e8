CREATE EXTENSION IF NOT EXISTS vector;

-- ── kb_sources ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.kb_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  url text,
  kind text NOT NULL DEFAULT 'text',
  status text NOT NULL DEFAULT 'pending',
  chunk_count int NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON public.kb_sources TO anon, authenticated;
GRANT INSERT, UPDATE, DELETE ON public.kb_sources TO authenticated;
GRANT ALL ON public.kb_sources TO service_role;

ALTER TABLE public.kb_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "kb_sources_read_all"
  ON public.kb_sources FOR SELECT
  USING (true);

CREATE POLICY "kb_sources_admin_write"
  ON public.kb_sources FOR ALL
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- ── kb_chunks ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.kb_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES public.kb_sources(id) ON DELETE CASCADE,
  ord int NOT NULL DEFAULT 0,
  text text NOT NULL,
  token_count int,
  embedding vector(768),
  created_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON public.kb_chunks TO anon, authenticated;
GRANT INSERT, UPDATE, DELETE ON public.kb_chunks TO authenticated;
GRANT ALL ON public.kb_chunks TO service_role;

ALTER TABLE public.kb_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "kb_chunks_read_all"
  ON public.kb_chunks FOR SELECT
  USING (true);

CREATE POLICY "kb_chunks_admin_write"
  ON public.kb_chunks FOR ALL
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE INDEX IF NOT EXISTS kb_chunks_source_idx ON public.kb_chunks (source_id);
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_hnsw
  ON public.kb_chunks
  USING hnsw (embedding vector_cosine_ops);

-- updated_at trigger for kb_sources (reuses existing helper if present)
CREATE OR REPLACE FUNCTION public.kb_sources_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS kb_sources_set_updated_at ON public.kb_sources;
CREATE TRIGGER kb_sources_set_updated_at
  BEFORE UPDATE ON public.kb_sources
  FOR EACH ROW EXECUTE FUNCTION public.kb_sources_touch_updated_at();

-- ── match_kb_chunks RPC (cosine similarity top-k) ────────────────
CREATE OR REPLACE FUNCTION public.match_kb_chunks(
  query_embedding vector(768),
  match_count int DEFAULT 6,
  min_similarity float DEFAULT 0.0
)
RETURNS TABLE (
  id uuid,
  source_id uuid,
  source_title text,
  source_url text,
  ord int,
  text text,
  similarity float
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT
    c.id,
    c.source_id,
    s.title AS source_title,
    s.url AS source_url,
    c.ord,
    c.text,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM public.kb_chunks c
  JOIN public.kb_sources s ON s.id = c.source_id
  WHERE c.embedding IS NOT NULL
    AND (1 - (c.embedding <=> query_embedding)) >= min_similarity
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count
$$;

GRANT EXECUTE ON FUNCTION public.match_kb_chunks(vector, int, float) TO anon, authenticated, service_role;