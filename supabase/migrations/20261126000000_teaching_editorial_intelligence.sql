-- Teaching Intelligence & Editorial Intelligence Platform Schema
-- Additive, idempotent migration (2026-11-26)

-- 1. Canonical Evidence Registry (immutable original_text + versioned corrections)
CREATE TABLE IF NOT EXISTS public.canonical_evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('video','interview','podcast','book','audio','website','course_event','document')),
    source_title TEXT NOT NULL DEFAULT '',
    canonical_uri TEXT NOT NULL DEFAULT '',
    teacher_id TEXT,
    speaker_verified BOOLEAN NOT NULL DEFAULT false,
    original_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL DEFAULT '',
    start_time_ms BIGINT,
    end_time_ms BIGINT,
    page_number INTEGER,
    chapter TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    transcription_confidence REAL,
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified','automated_candidate','human_verified','quarantined','revoked')),
    rights_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (rights_status IN ('unverified','licensed','cleared','revoked','quarantined')),
    source_version TEXT NOT NULL DEFAULT '1',
    transcript_version TEXT NOT NULL DEFAULT '1',
    segment_version TEXT NOT NULL DEFAULT '1',
    chunker_version TEXT NOT NULL DEFAULT 'unknown_legacy',
    content_hash TEXT NOT NULL,
    ingestion_model_version TEXT NOT NULL DEFAULT '',
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_canonical_evidence_source_id ON public.canonical_evidence (source_id);
CREATE INDEX IF NOT EXISTS idx_canonical_evidence_teacher_rights ON public.canonical_evidence (teacher_id, rights_status, verification_status);

CREATE TABLE IF NOT EXISTS public.evidence_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id TEXT NOT NULL REFERENCES public.canonical_evidence(evidence_id) ON DELETE CASCADE,
    corrected_text TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    corrected_by UUID,
    correction_version INTEGER NOT NULL DEFAULT 1,
    approved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Event-driven store synchronization outbox (Qdrant, Memgraph, OKF reconciliation)
CREATE TABLE IF NOT EXISTS public.corpus_sync_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN ('upsert_evidence','revoke_source','update_rights','resegment')),
    source_id TEXT NOT NULL,
    evidence_id TEXT,
    target_store TEXT NOT NULL CHECK (target_store IN ('qdrant','memgraph','okf','all')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','dead_letter')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_corpus_sync_outbox_status ON public.corpus_sync_outbox (status, created_at);

-- 3. Editorial Intelligence Workflow & Claim Ledger
CREATE TABLE IF NOT EXISTS public.editorial_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    target_format TEXT NOT NULL DEFAULT 'youtube_video',
    status TEXT NOT NULL DEFAULT 'idea'
        CHECK (status IN ('idea','research','evidence_collection','brief','outline','script','review','approved','published','archived')),
    assigned_editor_id UUID,
    approved_by UUID,
    approved_at TIMESTAMPTZ,
    published_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.editorial_dossiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.editorial_projects(id) ON DELETE CASCADE,
    research_query TEXT NOT NULL,
    corpus_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    underexplored_angles JSONB NOT NULL DEFAULT '[]'::jsonb,
    provenance_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.editorial_scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.editorial_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    sections JSONB NOT NULL DEFAULT '[]'::jsonb,
    validator_passed BOOLEAN NOT NULL DEFAULT false,
    validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.editorial_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.editorial_projects(id) ON DELETE CASCADE,
    script_id UUID REFERENCES public.editorial_scripts(id) ON DELETE SET NULL,
    reviewer_id UUID NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve','request_changes','reject')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Seeker Comprehension Signals (strictly isolated by user_id & tenant_id)
CREATE TABLE IF NOT EXISTS public.seeker_comprehension_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL DEFAULT 'oneness',
    concept_name TEXT NOT NULL,
    evidence_id TEXT,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('confused','needs_example','understood','explored')),
    strategy_used TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seeker_comp_user_tenant ON public.seeker_comprehension_signals (user_id, tenant_id, created_at DESC);

-- RLS Policies
ALTER TABLE public.canonical_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence_corrections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.corpus_sync_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.editorial_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.editorial_dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.editorial_scripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.editorial_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seeker_comprehension_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS seeker_comprehension_owner_only ON public.seeker_comprehension_signals;
CREATE POLICY seeker_comprehension_owner_only ON public.seeker_comprehension_signals
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
