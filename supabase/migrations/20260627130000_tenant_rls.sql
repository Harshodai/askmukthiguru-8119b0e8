-- Tenant-aware RLS: add tenant_id to core tables, create isolation policies
-- Each table gets a tenant_id column defaulting to 'default' for legacy data.

-- 1. chat_queries
ALTER TABLE public.chat_queries ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.chat_queries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.chat_queries;
CREATE POLICY tenant_isolation ON public.chat_queries
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- 2. chat_responses
ALTER TABLE public.chat_responses ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.chat_responses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.chat_responses;
CREATE POLICY tenant_isolation ON public.chat_responses
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- 3. retrieval_events
ALTER TABLE public.retrieval_events ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.retrieval_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.retrieval_events;
CREATE POLICY tenant_isolation ON public.retrieval_events
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- 4. guru_core_memory
ALTER TABLE public.guru_core_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.guru_core_memory ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_core_memory;
CREATE POLICY tenant_isolation ON public.guru_core_memory
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- 5. guru_memories
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.guru_memories ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_memories;
CREATE POLICY tenant_isolation ON public.guru_memories
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- 6. guru_session_summaries
ALTER TABLE public.guru_session_summaries ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.guru_session_summaries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_session_summaries;
CREATE POLICY tenant_isolation ON public.guru_session_summaries
    FOR ALL TO authenticated
    USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');
