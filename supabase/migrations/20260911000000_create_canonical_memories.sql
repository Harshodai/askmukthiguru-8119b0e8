-- Canonical memory table — source of truth for all personal memory.
-- Phase 2 of Adaptive Memory System Upgrade.
-- Design: docs/architecture/memory-target-architecture.md

-- ---------- main table ----------
CREATE TABLE IF NOT EXISTS public.canonical_memories (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id             TEXT NOT NULL DEFAULT 'default',
    memory_type           TEXT NOT NULL CHECK (memory_type IN (
                            'PROFILE', 'PREFERENCE', 'COMMUNICATION_STYLE', 'GOAL',
                            'PROJECT', 'INTEREST', 'RELATIONSHIP', 'USER_EXPLICIT',
                            'TEMPORARY_CONTEXT', 'REFLECTION'
                          )),
    statement             TEXT NOT NULL,
    normalized_statement  TEXT,
    fact_key              TEXT,
    confidence            REAL DEFAULT 0.75 CHECK (confidence >= 0 AND confidence <= 1),
    importance            REAL DEFAULT 0.5  CHECK (importance >= 0 AND importance <= 1),
    sensitivity           TEXT DEFAULT 'normal'
                            CHECK (sensitivity IN ('normal', 'sensitive', 'highly_sensitive')),
    status                TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'superseded', 'expired', 'deleted')),
    source_conversation_id TEXT,
    source_message_id     TEXT,
    source_turn_index     INTEGER,
    extraction_method     TEXT NOT NULL DEFAULT 'llm',
    evidence_count        INTEGER DEFAULT 1,
    embedding_id          TEXT,
    metadata              JSONB DEFAULT '{}',
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    last_used_at          TIMESTAMPTZ,
    last_confirmed_at     TIMESTAMPTZ,
    valid_from            TIMESTAMPTZ,
    valid_to              TIMESTAMPTZ,
    expires_at            TIMESTAMPTZ,
    version               INTEGER DEFAULT 1
);

-- Partial unique index: only one active memory per fact_key per user.
CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_memories_active_fact_key
    ON public.canonical_memories (user_id, fact_key)
    WHERE fact_key IS NOT NULL AND status = 'active';

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_canonical_memories_user_id
    ON public.canonical_memories (user_id);
CREATE INDEX IF NOT EXISTS idx_canonical_memories_user_status
    ON public.canonical_memories (user_id, status);
CREATE INDEX IF NOT EXISTS idx_canonical_memories_type
    ON public.canonical_memories (memory_type);
CREATE INDEX IF NOT EXISTS idx_canonical_memories_updated
    ON public.canonical_memories (updated_at);
CREATE INDEX IF NOT EXISTS idx_canonical_memories_expires
    ON public.canonical_memories (expires_at)
    WHERE expires_at IS NOT NULL AND status = 'active';
CREATE INDEX IF NOT EXISTS idx_canonical_memories_user_type_status
    ON public.canonical_memories (user_id, memory_type, status);

-- ---------- RLS ----------
ALTER TABLE public.canonical_memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_canonical_memories_select ON public.canonical_memories
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY own_canonical_memories_insert ON public.canonical_memories
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY own_canonical_memories_update ON public.canonical_memories
    FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY own_canonical_memories_delete ON public.canonical_memories
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- service_role bypasses RLS automatically; explicit grant for clarity
GRANT SELECT, INSERT, UPDATE, DELETE ON public.canonical_memories TO service_role;

-- ---------- touch updated_at trigger ----------
CREATE OR REPLACE FUNCTION public.touch_canonical_memories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_canonical_memories_touch ON public.canonical_memories;
CREATE TRIGGER trg_canonical_memories_touch
    BEFORE UPDATE ON public.canonical_memories
    FOR EACH ROW EXECUTE FUNCTION public.touch_canonical_memories_updated_at();

-- ---------- audit events ----------
CREATE TABLE IF NOT EXISTS public.memory_audit_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    memory_id   UUID,
    action      TEXT NOT NULL CHECK (action IN (
                    'created', 'updated', 'superseded',
                    'expired', 'deleted', 'retrieved'
                )),
    old_state   JSONB,
    new_state   JSONB,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_audit_events_user
    ON public.memory_audit_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_audit_events_memory
    ON public.memory_audit_events (memory_id);

ALTER TABLE public.memory_audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_audit_events_select ON public.memory_audit_events
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

GRANT SELECT, INSERT ON public.memory_audit_events TO service_role;

-- ---------- idempotent upsert function ----------
CREATE OR REPLACE FUNCTION public.upsert_canonical_memory(
    p_user_id                UUID,
    p_tenant_id              TEXT,
    p_memory_type            TEXT,
    p_statement              TEXT,
    p_normalized_statement   TEXT,
    p_fact_key               TEXT,
    p_confidence             REAL,
    p_importance             REAL,
    p_sensitivity            TEXT,
    p_source_conversation_id TEXT,
    p_source_turn_index      INTEGER,
    p_extraction_method      TEXT,
    p_metadata               JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_existing_id UUID;
    v_new_id      UUID;
    v_old_row     RECORD;
BEGIN
    -- If fact_key provided, check for existing active memory
    IF p_fact_key IS NOT NULL THEN
        SELECT id INTO v_existing_id
        FROM public.canonical_memories
        WHERE user_id = p_user_id
          AND fact_key = p_fact_key
          AND status = 'active'
        LIMIT 1;

        -- Supersede existing
        IF v_existing_id IS NOT NULL THEN
            SELECT * INTO v_old_row
            FROM public.canonical_memories
            WHERE id = v_existing_id;

            UPDATE public.canonical_memories
            SET status  = 'superseded',
                valid_to = now(),
                version  = version + 1
            WHERE id = v_existing_id;

            INSERT INTO public.memory_audit_events (user_id, memory_id, action, old_state, new_state)
            VALUES (
                p_user_id,
                v_existing_id,
                'superseded',
                to_jsonb(v_old_row),
                NULL
            );
        END IF;
    END IF;

    -- Insert new memory
    INSERT INTO public.canonical_memories (
        user_id, tenant_id, memory_type, statement, normalized_statement,
        fact_key, confidence, importance, sensitivity, status,
        source_conversation_id, source_turn_index, extraction_method,
        evidence_count, valid_from, metadata
    ) VALUES (
        p_user_id, p_tenant_id, p_memory_type, p_statement, p_normalized_statement,
        p_fact_key, p_confidence, p_importance, p_sensitivity, 'active',
        p_source_conversation_id, p_source_turn_index, p_extraction_method,
        1, now(), p_metadata
    ) RETURNING id INTO v_new_id;

    INSERT INTO public.memory_audit_events (user_id, memory_id, action, new_state)
    VALUES (
        p_user_id,
        v_new_id,
        'created',
        (SELECT to_jsonb(cm) FROM public.canonical_memories cm WHERE cm.id = v_new_id)
    );

    RETURN v_new_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute only to service_role (backend calls this, not browsers)
REVOKE EXECUTE ON FUNCTION public.upsert_canonical_memory(
    UUID, TEXT, TEXT, TEXT, TEXT, TEXT, REAL, REAL, TEXT, TEXT, INTEGER, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.upsert_canonical_memory(
    UUID, TEXT, TEXT, TEXT, TEXT, TEXT, REAL, REAL, TEXT, TEXT, INTEGER, TEXT, JSONB
) TO service_role;

NOTIFY pgrst, 'reload schema';
