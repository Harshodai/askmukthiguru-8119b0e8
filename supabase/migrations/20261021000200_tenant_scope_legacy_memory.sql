-- Tenant-scope the legacy guru_* memory APIs and compaction snapshots.
--
-- The backend uses the service role, so table RLS alone does not scope these
-- operations. Every SECURITY DEFINER RPC and every backend query must carry
-- the resolved tenant explicitly; user_id alone is not sufficient when one
-- account participates in more than one tenant.
--
-- Existing tenant_id values are deliberately preserved. Do not silently move
-- historical data between tenants; any legacy "default" -> "oneness" backfill
-- requires a separately reviewed data migration with environment evidence.

ALTER TABLE public.guru_core_memory
    ADD COLUMN IF NOT EXISTS tenant_id text NOT NULL DEFAULT 'oneness';
ALTER TABLE public.guru_core_memory
    ALTER COLUMN tenant_id SET DEFAULT 'oneness';

-- guru_core_memory historically had UNIQUE(user_id), which makes an upsert in
-- tenant B overwrite tenant A's row for the same user. Replace it with a
-- tenant-local uniqueness contract. IF EXISTS handles both historical schema
-- variants without deleting any existing memory rows.
ALTER TABLE public.guru_core_memory
    DROP CONSTRAINT IF EXISTS guru_core_memory_user_id_key;
DROP INDEX IF EXISTS public.guru_core_memory_user_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS guru_core_memory_user_tenant_uidx
    ON public.guru_core_memory (user_id, tenant_id);

ALTER TABLE public.guru_session_summaries
    DROP CONSTRAINT IF EXISTS guru_session_summaries_user_session_unique;
DROP INDEX IF EXISTS public.guru_session_summaries_user_session_unique;
CREATE UNIQUE INDEX IF NOT EXISTS guru_session_summaries_user_tenant_session_uidx
    ON public.guru_session_summaries (user_id, tenant_id, session_id);

ALTER TABLE public.guru_memories
    ALTER COLUMN tenant_id SET DEFAULT 'oneness';
ALTER TABLE public.guru_session_summaries
    ALTER COLUMN tenant_id SET DEFAULT 'oneness';

-- Legacy snapshots were keyed only by user. Keep existing snapshots attributed
-- to the legacy tenant by the column's deterministic default; new snapshots are
-- scoped and pruned by both tenant and user.
ALTER TABLE public.memory_compaction_snapshots
    ADD COLUMN IF NOT EXISTS tenant_id text NOT NULL DEFAULT 'oneness';
ALTER TABLE public.memory_compaction_snapshots
    ALTER COLUMN tenant_id SET DEFAULT 'oneness';
CREATE INDEX IF NOT EXISTS memory_compaction_snapshots_user_tenant_created_idx
    ON public.memory_compaction_snapshots (user_id, tenant_id, created_at DESC);

-- Remove the old signatures so there is no service-role callable, unscoped
-- variant left available for accidental future use.
DROP FUNCTION IF EXISTS public.match_user_memories_by_user(
    uuid, public.vector, integer, double precision
);
DROP FUNCTION IF EXISTS public.regenerate_summaries(uuid);
DROP FUNCTION IF EXISTS public.create_compaction_snapshot(uuid, jsonb);

CREATE FUNCTION public.match_user_memories_by_user(
    p_user_id uuid,
    p_tenant_id text,
    p_query_embedding public.vector(1024),
    p_k integer,
    p_min_sim double precision
)
RETURNS TABLE (id uuid, content text, similarity double precision)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $memory_search$
BEGIN
    IF p_user_id IS NULL OR NULLIF(pg_catalog.btrim(p_tenant_id), '') IS NULL THEN
        RAISE EXCEPTION 'user_and_tenant_required';
    END IF;
    IF p_query_embedding IS NULL THEN
        RAISE EXCEPTION 'query_embedding_required';
    END IF;
    IF p_k IS NULL OR p_k < 1 OR p_k > 100 THEN
        RAISE EXCEPTION 'invalid_result_limit';
    END IF;
    IF p_min_sim IS NULL OR p_min_sim < 0 OR p_min_sim > 1 THEN
        RAISE EXCEPTION 'invalid_min_similarity';
    END IF;

    RETURN QUERY
    SELECT
        memory.id,
        memory.content,
        (1 - (memory.embedding OPERATOR(public.<=>) p_query_embedding))::double precision
    FROM public.guru_memories AS memory
    WHERE memory.user_id = p_user_id
      AND memory.tenant_id = p_tenant_id
      AND memory.valid_to IS NULL
      AND (1 - (memory.embedding OPERATOR(public.<=>) p_query_embedding)) >= p_min_sim
    ORDER BY memory.embedding OPERATOR(public.<=>) p_query_embedding
    LIMIT p_k;
END;
$memory_search$;

REVOKE ALL ON FUNCTION public.match_user_memories_by_user(
    uuid, text, public.vector, integer, double precision
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user(
    uuid, text, public.vector, integer, double precision
) TO service_role;

CREATE FUNCTION public.regenerate_summaries(
    p_user_id uuid,
    p_tenant_id text
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
AS $regenerate_summaries$
DECLARE
    updated_count integer;
BEGIN
    IF p_user_id IS NULL OR NULLIF(pg_catalog.btrim(p_tenant_id), '') IS NULL THEN
        RAISE EXCEPTION 'user_and_tenant_required';
    END IF;

    UPDATE public.guru_memories
       SET summary = pg_catalog.left(content, 280)
     WHERE user_id = p_user_id
       AND tenant_id = p_tenant_id
       AND summary IS NULL
       AND content IS NOT NULL;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$regenerate_summaries$;

REVOKE ALL ON FUNCTION public.regenerate_summaries(uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.regenerate_summaries(uuid, text) TO service_role;

CREATE FUNCTION public.create_compaction_snapshot(
    p_user_id uuid,
    p_tenant_id text,
    p_memories_json jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $compaction_snapshot$
BEGIN
    IF p_user_id IS NULL OR NULLIF(pg_catalog.btrim(p_tenant_id), '') IS NULL THEN
        RAISE EXCEPTION 'user_and_tenant_required';
    END IF;
    IF p_memories_json IS NULL OR pg_catalog.jsonb_typeof(p_memories_json) <> 'array' THEN
        RAISE EXCEPTION 'memories_snapshot_must_be_array';
    END IF;

    -- Serialize against consent revocation and all durable-memory writes.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            p_user_id::text || '|' || p_tenant_id || '|memory-v1',
            0
        )
    );
    IF NOT COALESCE((
        SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
        FROM public.memory_consent_receipts AS receipt
        WHERE receipt.user_id = p_user_id
          AND receipt.tenant_id = p_tenant_id
          AND receipt.consent_version = 'memory-v1'
        ORDER BY receipt.event_sequence DESC
        LIMIT 1
    ), FALSE) THEN
        RAISE EXCEPTION 'active_memory_consent_required';
    END IF;

    INSERT INTO public.memory_compaction_snapshots (user_id, tenant_id, memories_json)
    VALUES (p_user_id, p_tenant_id, p_memories_json);

    DELETE FROM public.memory_compaction_snapshots AS snapshot
    WHERE snapshot.user_id = p_user_id
      AND snapshot.tenant_id = p_tenant_id
      AND snapshot.id NOT IN (
          SELECT recent.id
          FROM public.memory_compaction_snapshots AS recent
          WHERE recent.user_id = p_user_id
            AND recent.tenant_id = p_tenant_id
          ORDER BY recent.created_at DESC, recent.id DESC
          LIMIT 3
      );
END;
$compaction_snapshot$;

REVOKE ALL ON FUNCTION public.create_compaction_snapshot(uuid, text, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_compaction_snapshot(uuid, text, jsonb)
    TO service_role;

-- Snapshots are also personal data and must not race past consent revocation.
DROP TRIGGER IF EXISTS enforce_memory_consent_before_write
    ON public.memory_compaction_snapshots;
CREATE TRIGGER enforce_memory_consent_before_write
    BEFORE INSERT OR UPDATE ON public.memory_compaction_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.enforce_active_memory_consent_before_write();

COMMENT ON FUNCTION public.match_user_memories_by_user(uuid, text, public.vector, integer, double precision) IS
    'Backend-only semantic lookup scoped to a single user and tenant.';
COMMENT ON FUNCTION public.regenerate_summaries(uuid, text) IS
    'Backend-only summary regeneration scoped to a single user and tenant.';
COMMENT ON FUNCTION public.create_compaction_snapshot(uuid, text, jsonb) IS
    'Backend-only tenant-scoped recovery snapshot; requires active memory consent.';
NOTIFY pgrst, 'reload schema';
