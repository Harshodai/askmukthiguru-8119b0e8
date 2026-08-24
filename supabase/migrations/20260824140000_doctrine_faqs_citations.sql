-- doctrine_faqs had no provenance column at all: DoctrineCacheStage could
-- only ever return citations=[] for a Supabase-backed hit, an
-- indistinguishable-from-fabricated answer bypassing the RAG pipeline's
-- normal source verification (audit finding OH-P0-01, 2026-08-24).
-- backend/services/doctrine_cache.py now refuses to serve any row whose
-- citations array is empty.
ALTER TABLE public.doctrine_faqs
  ADD COLUMN IF NOT EXISTS citations jsonb NOT NULL DEFAULT '[]'::jsonb;

NOTIFY pgrst, 'reload schema';
