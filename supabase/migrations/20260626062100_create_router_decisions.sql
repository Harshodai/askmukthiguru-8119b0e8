-- ============================================================================
-- REVERT: Drop router_decisions (policies drop with the table). DESTRUCTIVE: all router
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- telemetry is lost. NOTE: the anon/authenticated GRANT ALL was revoked by
-- 20260804000002; nothing to re-grant on rollback.
-- DROP TABLE IF EXISTS public.router_decisions;
-- ============================================================================

-- Create public.router_decisions table for telemetry log
CREATE TABLE IF NOT EXISTS public.router_decisions (
    id UUID PRIMARY KEY,
    query_text TEXT NOT NULL,
    tier TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    method TEXT NOT NULL,
    shadow_tier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.router_decisions ENABLE ROW LEVEL SECURITY;

-- Create permissive policies for insert and select
CREATE POLICY "Allow insert for all users" ON public.router_decisions FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow select for all users" ON public.router_decisions FOR SELECT USING (true);

-- Grant all privileges to anon, authenticated and service_role
GRANT ALL ON public.router_decisions TO anon, authenticated, service_role;

-- Force reload of PostgREST schema cache
NOTIFY pgrst, 'reload schema';
