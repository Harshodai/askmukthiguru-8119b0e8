-- Migration to create memory layer tables for seekers
-- Supports core memory, episodic memories, and session summaries

-- Enable pgvector extension if not already present
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Core Memory Table (capped at 2KB content)
CREATE TABLE IF NOT EXISTS public.guru_core_memory (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content text NOT NULL CONSTRAINT core_memory_length_check CHECK (char_length(content) <= 2048),
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Episodic memories with 1024-dimensional dense embeddings
CREATE TABLE IF NOT EXISTS public.guru_memories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  source text NOT NULL DEFAULT 'extracted',
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- HNSW index for fast vector similarity search using Cosine Distance
CREATE INDEX IF NOT EXISTS guru_memories_hnsw_idx 
ON public.guru_memories 
USING hnsw (embedding vector_cosine_ops);

-- 3. Rolling session summaries
CREATE TABLE IF NOT EXISTS public.guru_session_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id uuid NOT NULL,
  summary text NOT NULL,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS on all tables
ALTER TABLE public.guru_core_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guru_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guru_session_summaries ENABLE ROW LEVEL SECURITY;

-- RLS policies for guru_core_memory
DROP POLICY IF EXISTS "Users can see their own core memory" ON public.guru_core_memory;
CREATE POLICY "Users can see their own core memory" ON public.guru_core_memory
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own core memory" ON public.guru_core_memory;
CREATE POLICY "Users can insert their own core memory" ON public.guru_core_memory
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own core memory" ON public.guru_core_memory;
CREATE POLICY "Users can update their own core memory" ON public.guru_core_memory
  FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own core memory" ON public.guru_core_memory;
CREATE POLICY "Users can delete their own core memory" ON public.guru_core_memory
  FOR DELETE USING (auth.uid() = user_id);

-- RLS policies for guru_memories
DROP POLICY IF EXISTS "Users can see their own memories" ON public.guru_memories;
CREATE POLICY "Users can see their own memories" ON public.guru_memories
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own memories" ON public.guru_memories;
CREATE POLICY "Users can insert their own memories" ON public.guru_memories
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own memories" ON public.guru_memories;
CREATE POLICY "Users can update their own memories" ON public.guru_memories
  FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own memories" ON public.guru_memories;
CREATE POLICY "Users can delete their own memories" ON public.guru_memories
  FOR DELETE USING (auth.uid() = user_id);

-- RLS policies for guru_session_summaries
DROP POLICY IF EXISTS "Users can see their own session summaries" ON public.guru_session_summaries;
CREATE POLICY "Users can see their own session summaries" ON public.guru_session_summaries
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own session summaries" ON public.guru_session_summaries;
CREATE POLICY "Users can insert their own session summaries" ON public.guru_session_summaries
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own session summaries" ON public.guru_session_summaries;
CREATE POLICY "Users can update their own session summaries" ON public.guru_session_summaries
  FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own session summaries" ON public.guru_session_summaries;
CREATE POLICY "Users can delete their own session summaries" ON public.guru_session_summaries
  FOR DELETE USING (auth.uid() = user_id);

-- RPC for semantic memory search (Cosine Similarity)
CREATE OR REPLACE FUNCTION public.match_user_memories(
  p_user_id uuid,
  p_query_embedding vector(1024),
  p_k int,
  p_min_sim float
)
RETURNS TABLE (
  id uuid,
  content text,
  similarity float
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  RETURN QUERY
  SELECT
    m.id,
    m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = p_user_id
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;
