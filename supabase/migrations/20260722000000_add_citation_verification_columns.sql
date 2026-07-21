-- Task 2: persist citation post-verification flags per response.
ALTER TABLE public.chat_responses
    ADD COLUMN IF NOT EXISTS citations_verified boolean DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS orphan_citations_stripped boolean DEFAULT NULL;

-- Notify PostgREST to reload its schema cache so the new columns are visible immediately.
NOTIFY pgrst, 'reload schema';
