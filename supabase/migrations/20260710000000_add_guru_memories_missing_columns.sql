-- Add missing columns to guru_memories that were defined in 20260618044620 but
-- never applied because CREATE TABLE IF NOT EXISTS skipped the existing table.
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS claim TEXT;
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS decay_score DOUBLE PRECISION DEFAULT 1.0;
