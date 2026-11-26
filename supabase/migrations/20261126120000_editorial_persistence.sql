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

-- Append-only for PUBLIC/anon/authenticated only. service_role (used by the backend) and
-- superusers bypass these grants and can still UPDATE/DELETE; this is not tamper-proof.
REVOKE UPDATE, DELETE ON public.editorial_audit_log FROM PUBLIC, anon, authenticated;
