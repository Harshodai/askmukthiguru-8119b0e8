-- Editorial persistence additions (2026-11-26). The 20261126000000 migration has no place for the
-- full project snapshot (brief/outline/script) or an audit trail, so add them here.
ALTER TABLE public.editorial_projects ADD COLUMN IF NOT EXISTS snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS public.editorial_audit_log (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES public.editorial_projects(id) ON DELETE CASCADE,
    actor_id TEXT,
    event TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_editorial_audit_log_project ON public.editorial_audit_log (project_id, created_at);
ALTER TABLE public.editorial_audit_log ENABLE ROW LEVEL SECURITY;

-- Only the backend (service_role, which bypasses RLS) may touch the editorial tables. RLS is enabled
-- with no policies, so anon/authenticated are already denied row access; TRUNCATE, however, ignores RLS
-- and Supabase grants it by default, and a TRUNCATE of the audit log cascades into dossiers, scripts and
-- approvals. Revoke every privilege from PUBLIC/anon/authenticated (no functional change for them).
-- service_role and superusers bypass these grants and can still UPDATE/DELETE: the audit log is
-- append-only for the public roles, not tamper-proof against the backend itself.
REVOKE ALL ON public.editorial_audit_log FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.editorial_audit_log_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.editorial_projects, public.editorial_dossiers, public.editorial_scripts,
    public.editorial_approvals FROM PUBLIC, anon, authenticated;
