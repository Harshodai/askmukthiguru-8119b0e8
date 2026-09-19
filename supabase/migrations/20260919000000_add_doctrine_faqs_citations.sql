-- Add citations column to doctrine_faqs (was missing, causing startup WARNING on every deploy)
-- Safe: IF NOT EXISTS prevents errors on re-run; TEXT allows null for rows without citations.
-- After this migration, doctrine_cache.py can SELECT citations without the 42703 error.

ALTER TABLE doctrine_faqs
    ADD COLUMN IF NOT EXISTS citations TEXT;

COMMENT ON COLUMN doctrine_faqs.citations IS
    'Optional JSON-encoded citation URLs for the doctrine FAQ answer. NULL if no citations.';
