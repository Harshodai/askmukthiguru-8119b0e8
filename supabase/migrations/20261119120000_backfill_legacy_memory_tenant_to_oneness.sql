-- Migration: 20261119120000_backfill_legacy_memory_tenant_to_oneness.sql
-- Description: Archive and backfill legacy 'default' tenant rows to 'oneness' for guru_* memory tables.
-- Provenance: 18 rows in guru_memories (3 users, July 2026), 1 row in guru_core_memory, 5 rows in guru_session_summaries.
-- Invariant: Zero collisions with existing 'oneness' rows (verified: 0 existing 'oneness' rows in these tables).
-- Reference: docs/handoffs/HANDOFF_2026_11_19_RAILWAY_GO_LIVE.md, 20261021000200_tenant_scope_legacy_memory.sql

BEGIN;

-- Temporarily run as replica so application write-triggers (which require active
-- modern consent-v1 receipts) do not fail the historical backfill of pre-consent legacy rows.
SET LOCAL session_replication_role = 'replica';

-- 1. Create Archive Tables to preserve immutable audit trail of historical 'default' state
CREATE TABLE IF NOT EXISTS public.guru_memories_tenant_backfill_archive_20261119 (
    archived_at timestamp with time zone NOT NULL DEFAULT now(),
    archive_reason text NOT NULL DEFAULT '20261119_railway_go_live_tenant_backfill',
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    content text NOT NULL,
    source text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    embedding public.vector(1024) NOT NULL,
    tenant_id text NOT NULL,
    claim text,
    confidence double precision,
    decay_score double precision,
    summary text,
    fact_key text,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    source_conversation_id text,
    CONSTRAINT guru_memories_backfill_archive_pkey PRIMARY KEY (id, archived_at)
);

CREATE TABLE IF NOT EXISTS public.guru_core_memory_tenant_backfill_archive_20261119 (
    archived_at timestamp with time zone NOT NULL DEFAULT now(),
    archive_reason text NOT NULL DEFAULT '20261119_railway_go_live_tenant_backfill',
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    tenant_id text NOT NULL,
    CONSTRAINT guru_core_memory_backfill_archive_pkey PRIMARY KEY (id, archived_at)
);

CREATE TABLE IF NOT EXISTS public.guru_session_summaries_tenant_backfill_archive_20261119 (
    archived_at timestamp with time zone NOT NULL DEFAULT now(),
    archive_reason text NOT NULL DEFAULT '20261119_railway_go_live_tenant_backfill',
    id uuid NOT NULL,
    user_id uuid,
    session_id uuid NOT NULL,
    summary text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    tenant_id text NOT NULL,
    CONSTRAINT guru_session_summaries_backfill_archive_pkey PRIMARY KEY (id, archived_at)
);

-- Enable RLS on archive tables and restrict access to service_role
ALTER TABLE public.guru_memories_tenant_backfill_archive_20261119 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guru_core_memory_tenant_backfill_archive_20261119 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guru_session_summaries_tenant_backfill_archive_20261119 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS archive_memories_service_only ON public.guru_memories_tenant_backfill_archive_20261119;
CREATE POLICY archive_memories_service_only ON public.guru_memories_tenant_backfill_archive_20261119
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS archive_core_service_only ON public.guru_core_memory_tenant_backfill_archive_20261119;
CREATE POLICY archive_core_service_only ON public.guru_core_memory_tenant_backfill_archive_20261119
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS archive_summaries_service_only ON public.guru_session_summaries_tenant_backfill_archive_20261119;
CREATE POLICY archive_summaries_service_only ON public.guru_session_summaries_tenant_backfill_archive_20261119
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 2. Populate Archive Tables with existing 'default' tenant rows
INSERT INTO public.guru_memories_tenant_backfill_archive_20261119 (
    id, user_id, content, source, created_at, updated_at, embedding,
    tenant_id, claim, confidence, decay_score, summary, fact_key,
    valid_from, valid_to, source_conversation_id
)
SELECT
    id, user_id, content, source, created_at, updated_at, embedding,
    tenant_id, claim, confidence, decay_score, summary, fact_key,
    valid_from, valid_to, source_conversation_id
FROM public.guru_memories
WHERE tenant_id = 'default'
ON CONFLICT (id, archived_at) DO NOTHING;

INSERT INTO public.guru_core_memory_tenant_backfill_archive_20261119 (
    id, user_id, content, created_at, updated_at, tenant_id
)
SELECT
    id, user_id, content, created_at, updated_at, tenant_id
FROM public.guru_core_memory
WHERE tenant_id = 'default'
ON CONFLICT (id, archived_at) DO NOTHING;

INSERT INTO public.guru_session_summaries_tenant_backfill_archive_20261119 (
    id, user_id, session_id, summary, created_at, updated_at, tenant_id
)
SELECT
    id, user_id, session_id, summary, created_at, updated_at, tenant_id
FROM public.guru_session_summaries
WHERE tenant_id = 'default'
ON CONFLICT (id, archived_at) DO NOTHING;

-- 3. Execute Backfill Update from 'default' to 'oneness'
UPDATE public.guru_memories
SET tenant_id = 'oneness',
    updated_at = now()
WHERE tenant_id = 'default';

UPDATE public.guru_core_memory
SET tenant_id = 'oneness',
    updated_at = now()
WHERE tenant_id = 'default';

UPDATE public.guru_session_summaries
SET tenant_id = 'oneness',
    updated_at = now()
WHERE tenant_id = 'default';

COMMIT;
