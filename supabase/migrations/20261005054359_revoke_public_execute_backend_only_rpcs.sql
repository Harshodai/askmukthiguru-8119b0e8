-- Backend-only SECURITY DEFINER RPCs: EXECUTE for service_role only.
--
-- These eight functions bypass RLS by design and are called only by the
-- backend with the service-role key (corpus_release_registry.py,
-- memory_outbox.py, memory_service.py). No frontend code calls them via
-- supabase.rpc (grep of src/ and supabase/functions/, 2026-10-05; generated
-- types excluded).
--
-- Earlier migrations revoke from PUBLIC (and anon for some), but never from
-- `authenticated` explicitly. Supabase's default privileges grant EXECUTE on
-- new public-schema functions to anon and authenticated DIRECTLY, not via
-- PUBLIC, so a fresh `supabase db reset` can leave a signed-in user able to
-- call e.g. claim_memory_outbox or activate_source_release.
--
-- Prod (ozmjeuqbholoxypfxixb) already matches this end state as of
-- 2026-10-05: has_function_privilege() is false for anon and authenticated and
-- true for service_role on all eight. This file makes the repo reproduce it.
-- Idempotent. NOT APPLIED -- owner decides.
--
-- Guarded with to_regprocedure / pg_roles so migration-revert-check.yml's empty
-- ephemeral Postgres (no functions, no Supabase roles) runs it as a no-op.

DO $$
DECLARE
    sig text;
    sigs text[] := ARRAY[
        'public.register_source_release(text,text,text,text,text)',
        'public.approve_source_release(uuid,text)',
        'public.activate_source_release(uuid)',
        'public.reject_source_release(uuid)',
        'public.claim_memory_outbox(text,integer)',
        'public.match_user_memories_by_user(uuid,vector,integer,double precision)',
        'public.regenerate_summaries(uuid)',
        'public.create_compaction_snapshot(uuid,jsonb)'
    ];
BEGIN
    FOREACH sig IN ARRAY sigs LOOP
        -- to_regprocedure raises (not NULL) when an argument TYPE is unknown,
        -- e.g. `vector` without pgvector on the ephemeral DB.
        BEGIN
            IF to_regprocedure(sig) IS NULL THEN
                CONTINUE;
            END IF;
        EXCEPTION WHEN undefined_object THEN
            CONTINUE;
        END;
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', sig);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM anon', sig);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM authenticated', sig);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', sig);
        END IF;
    END LOOP;
END
$$;

-- REVERT:
-- -- Intentionally a no-op. The pre-migration state in prod is already this
-- -- state, and re-granting EXECUTE to anon/authenticated would reopen an RLS
-- -- bypass on SECURITY DEFINER functions.
-- SELECT 1;
