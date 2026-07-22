-- Drop the legacy 768-dim match_kb_chunks RPC used only by the dead Supabase Edge Function.
-- The Python backend uses services/embedding_service.py with all-MiniLM-L6-v2 via Qdrant directly.
DROP FUNCTION IF EXISTS public.match_kb_chunks(vector(768), bigint, double precision);
DROP FUNCTION IF EXISTS public.match_kb_chunks(vector(768), integer, double precision);
