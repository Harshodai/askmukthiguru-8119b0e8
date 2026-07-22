-- Drop the legacy 768-dim match_kb_chunks RPC used only by the dead Supabase Edge Function.
-- The Python backend uses Qdrant directly with 1024-dim bge-m3 embeddings.
DROP FUNCTION IF EXISTS public.match_kb_chunks(vector(768), bigint, double precision);
