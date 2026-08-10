-- ============================================================================
-- REVERT: Drop the span_name alias column + index. NOTE: backfilled span_name values
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- are dropped with the column (local-env data loss only). The attributes column
-- is shared with 20260601090000 — leave it unless that migration also reverts.
-- DROP INDEX IF EXISTS idx_trace_spans_span_name;
-- ALTER TABLE public.trace_spans DROP COLUMN IF EXISTS span_name;
-- ============================================================================

-- Fix: Add span_name column as alias to trace_spans for Lovable cloud compatibility.
-- Context: Local DB (original schema 20240430) uses `name` column.
-- Lovable cloud DB (migration 20260527060500 applied to fresh DB) uses `span_name`.
-- This migration makes both environments consistent by ensuring both columns exist.
-- The telemetry_sink.py always writes to `name` (the original column); this migration
-- adds `span_name` as a generated/computed alias for compatibility with any direct queries.

-- Step 1: Add span_name if missing (Lovable cloud already has it, local doesn't)
ALTER TABLE public.trace_spans
  ADD COLUMN IF NOT EXISTS span_name TEXT;

-- Step 2: Backfill span_name from name for all existing rows (local only effect)
UPDATE public.trace_spans
  SET span_name = name
  WHERE span_name IS NULL AND name IS NOT NULL;

-- Step 3: Ensure attributes column exists (added by 20260601090000 but guard here too)
ALTER TABLE public.trace_spans
  ADD COLUMN IF NOT EXISTS attributes jsonb DEFAULT '{}'::jsonb;

-- Step 4: Index for span name lookups in admin trace detail view
CREATE INDEX IF NOT EXISTS idx_trace_spans_span_name
  ON public.trace_spans(span_name);
