


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE TYPE "public"."app_role" AS ENUM (
    'admin',
    'user'
);


ALTER TYPE "public"."app_role" OWNER TO "postgres";


CREATE TYPE "public"."assistant_visibility" AS ENUM (
    'public',
    'link',
    'private'
);


ALTER TYPE "public"."assistant_visibility" OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."source_releases" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "corpus_id" "text" NOT NULL,
    "source_url" "text" NOT NULL,
    "source_identity" "text" NOT NULL,
    "release_version" integer NOT NULL,
    "content_checksum" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "approved_by" "text",
    "approved_at" timestamp with time zone,
    "activated_at" timestamp with time zone,
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "source_releases_approval_audit_check" CHECK (((("status" = ANY (ARRAY['approved'::"text", 'active'::"text", 'superseded'::"text"])) AND ("approved_by" IS NOT NULL) AND ("approved_at" IS NOT NULL)) OR ("status" = ANY (ARRAY['pending'::"text", 'rejected'::"text"])))),
    CONSTRAINT "source_releases_checksum_nonempty" CHECK (("length"(TRIM(BOTH FROM "content_checksum")) > 0)),
    CONSTRAINT "source_releases_corpus_nonempty" CHECK (("length"(TRIM(BOTH FROM "corpus_id")) > 0)),
    CONSTRAINT "source_releases_identity_nonempty" CHECK (("length"(TRIM(BOTH FROM "source_identity")) > 0)),
    CONSTRAINT "source_releases_notes_length" CHECK ((("notes" IS NULL) OR ("char_length"("notes") <= 1000))),
    CONSTRAINT "source_releases_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'approved'::"text", 'active'::"text", 'superseded'::"text", 'rejected'::"text"]))),
    CONSTRAINT "source_releases_version_positive" CHECK (("release_version" > 0))
);


ALTER TABLE "public"."source_releases" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."activate_source_release"("p_release_id" "uuid") RETURNS "public"."source_releases"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE candidate public.source_releases; activated_release public.source_releases;
BEGIN
    SELECT * INTO candidate FROM public.source_releases WHERE id = p_release_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'release does not exist' USING ERRCODE = 'P0001'; END IF;
    IF candidate.status <> 'approved' THEN RAISE EXCEPTION 'only approved releases may be activated' USING ERRCODE = 'P0001'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(candidate.corpus_id || '|' || candidate.source_identity, 0));
    UPDATE public.source_releases SET status = 'superseded'
      WHERE corpus_id = candidate.corpus_id AND source_identity = candidate.source_identity AND status = 'active';
    UPDATE public.source_releases SET status = 'active', activated_at = now()
      WHERE id = candidate.id RETURNING * INTO activated_release;
    RETURN activated_release;
END;
$$;


ALTER FUNCTION "public"."activate_source_release"("p_release_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."append_healing_step"("p_user_id" "uuid", "p_course_slug" "text", "p_step_id" "text", "p_total_steps" integer) RETURNS TABLE("current_step" integer, "completed_steps" "jsonb", "total_steps" integer)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    INSERT INTO public.user_healing_progress
        (user_id, course_slug, current_step, completed_steps, total_steps, last_accessed_at)
    VALUES (p_user_id, p_course_slug, 0, '[]'::jsonb, p_total_steps, now())
    ON CONFLICT (user_id, course_slug) DO NOTHING;

    UPDATE public.user_healing_progress t
    SET completed_steps = CASE
            WHEN NOT jsonb_exists(t.completed_steps, p_step_id)
                THEN jsonb_insert(t.completed_steps, '{-1}', to_jsonb(p_step_id::text), true)
            ELSE t.completed_steps
        END,
        total_steps = GREATEST(t.total_steps, p_total_steps),
        last_accessed_at = now()
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;

    UPDATE public.user_healing_progress t
    SET current_step = LEAST(jsonb_array_length(t.completed_steps), GREATEST(t.total_steps - 1, 0))
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;

    RETURN QUERY
    SELECT t.current_step, t.completed_steps, t.total_steps
    FROM public.user_healing_progress t
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;
END;
$$;


ALTER FUNCTION "public"."append_healing_step"("p_user_id" "uuid", "p_course_slug" "text", "p_step_id" "text", "p_total_steps" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."approve_source_release"("p_release_id" "uuid", "p_approved_by" "text") RETURNS "public"."source_releases"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE approved_release public.source_releases;
BEGIN
    IF length(trim(p_approved_by)) = 0 THEN
        RAISE EXCEPTION 'approved_by is required' USING ERRCODE = '22023';
    END IF;
    UPDATE public.source_releases
       SET status = 'approved', approved_by = trim(p_approved_by), approved_at = now()
     WHERE id = p_release_id AND status IN ('pending', 'superseded')
     RETURNING * INTO approved_release;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release is not pending or superseded, or does not exist' USING ERRCODE = 'P0001';
    END IF;
    RETURN approved_release;
END;
$$;


ALTER FUNCTION "public"."approve_source_release"("p_release_id" "uuid", "p_approved_by" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."brain_touch"("p_id" "text") RETURNS "void"
    LANGUAGE "sql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
    update public.user_brain_nodes
       set access_count = access_count + 1,
           updated_at   = now()
     where id = p_id
       and user_id = auth.uid()
       and auth.uid() is not null;
$$;


ALTER FUNCTION "public"."brain_touch"("p_id" "text") OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."memory_outbox" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    "session_id" "text" NOT NULL,
    "payload" "jsonb" NOT NULL,
    "consent_receipt_id" "uuid",
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "attempts" integer DEFAULT 0 NOT NULL,
    "locked_at" timestamp with time zone,
    "locked_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "processed_at" timestamp with time zone,
    "error" "text",
    "completed_steps" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    CONSTRAINT "memory_outbox_attempts_check" CHECK (("attempts" >= 0)),
    CONSTRAINT "memory_outbox_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'processing'::"text", 'done'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."memory_outbox" OWNER TO "postgres";


COMMENT ON TABLE "public"."memory_outbox" IS 'Durable, consented memory extraction intents; payloads are deleted on account-wide erasure.';



COMMENT ON COLUMN "public"."memory_outbox"."completed_steps" IS 'Enrichment sub-steps already committed for this row (AMK-C-005). A row reclaimed after a worker crash skips these instead of re-running them. Never reset on reclaim.';



CREATE OR REPLACE FUNCTION "public"."claim_memory_outbox"("p_worker_id" "text", "p_limit" integer DEFAULT 50) RETURNS SETOF "public"."memory_outbox"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
    RETURN QUERY
    WITH candidates AS (
        SELECT id
        FROM public.memory_outbox
        WHERE status = 'pending'
           OR (status = 'processing' AND locked_at < now() - interval '10 minutes')
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(p_limit, 100))
    ), claimed AS (
        UPDATE public.memory_outbox AS outbox
        SET status = 'processing',
            attempts = outbox.attempts + 1,
            locked_at = now(),
            locked_by = p_worker_id,
            error = NULL
        FROM candidates
        WHERE outbox.id = candidates.id
        RETURNING outbox.*
    )
    SELECT * FROM claimed;
END;
$$;


ALTER FUNCTION "public"."claim_memory_outbox"("p_worker_id" "text", "p_limit" integer) OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."pending_extractions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "conversation_id" "uuid",
    "message_id" "uuid",
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "attempts" integer DEFAULT 0 NOT NULL,
    "last_error" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "processed_at" timestamp with time zone,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    "consent_receipt_id" "uuid",
    "locked_at" timestamp with time zone,
    "locked_by" "text",
    CONSTRAINT "pending_extractions_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'processing'::"text", 'done'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."pending_extractions" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."claim_pending_extractions"("p_worker_id" "text", "p_limit" integer DEFAULT 50) RETURNS SETOF "public"."pending_extractions"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
BEGIN
    IF NULLIF(pg_catalog.btrim(p_worker_id), '') IS NULL THEN
        RAISE EXCEPTION 'worker_id_required' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH candidates AS (
        SELECT pending.id
        FROM public.pending_extractions AS pending
        WHERE pending.status = 'pending'
           OR (
               pending.status = 'processing'
               AND (
                   pending.locked_at IS NULL
                   OR pending.locked_at < pg_catalog.now() - interval '10 minutes'
               )
           )
        ORDER BY pending.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 50), 100))
    ), claimed AS (
        UPDATE public.pending_extractions AS pending
        SET status = 'processing',
            attempts = pending.attempts + 1,
            locked_at = pg_catalog.now(),
            locked_by = p_worker_id
        FROM candidates
        WHERE pending.id = candidates.id
        RETURNING pending.*
    )
    SELECT * FROM claimed;
END;
$$;


ALTER FUNCTION "public"."claim_pending_extractions"("p_worker_id" "text", "p_limit" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."create_compaction_snapshot"("p_user_id" "uuid", "p_tenant_id" "text", "p_memories_json" "jsonb") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
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
$$;


ALTER FUNCTION "public"."create_compaction_snapshot"("p_user_id" "uuid", "p_tenant_id" "text", "p_memories_json" "jsonb") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."create_compaction_snapshot"("p_user_id" "uuid", "p_tenant_id" "text", "p_memories_json" "jsonb") IS 'Backend-only tenant-scoped recovery snapshot; requires active memory consent.';



CREATE OR REPLACE FUNCTION "public"."demote_admin_by_id"("_user_id" "uuid") RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  IF _user_id = auth.uid() THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'cannot_demote_self');
  END IF;

  DELETE FROM public.user_roles WHERE user_id = _user_id AND role = 'admin'::public.app_role;
  RETURN jsonb_build_object('ok', true);
END;
$$;


ALTER FUNCTION "public"."demote_admin_by_id"("_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."enforce_active_memory_consent_before_write"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
DECLARE
    v_active boolean;
    v_tenant_id text;
BEGIN
    -- Some legacy personal-projection tables use UUID tenant ids, while the
    -- shared consent ledger intentionally uses text tenant ids. Read the row
    -- value through JSON to avoid casting failures on either schema.
    v_tenant_id := NULLIF(pg_catalog.btrim(to_jsonb(NEW)->>'tenant_id'), '');
    IF v_tenant_id = '00000000-0000-0000-0000-000000000000' THEN
        -- This UUID is the historical default used by the legacy personal
        -- projection tables; it represents the configured legacy tenant.
        v_tenant_id := 'oneness';
    END IF;

    -- Queue workers must be able to update status/lease metadata and scrub
    -- sensitive payloads after consent has been withdrawn. No identity, tenant,
    -- receipt, or non-empty payload mutation is allowed on this cleanup path.
    IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'memory_outbox' THEN
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id
           AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
           AND NEW.consent_receipt_id IS NOT DISTINCT FROM OLD.consent_receipt_id
           AND (NEW.payload IS NOT DISTINCT FROM OLD.payload OR NEW.payload = '{}'::jsonb) THEN
            RETURN NEW;
        END IF;
    ELSIF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'pending_extractions' THEN
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id
           AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
           AND NEW.consent_receipt_id IS NOT DISTINCT FROM OLD.consent_receipt_id
           AND (NEW.payload IS NOT DISTINCT FROM OLD.payload OR NEW.payload = '{}'::jsonb) THEN
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.user_id IS NULL OR v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'user and tenant are required for memory writes'
            USING ERRCODE = '42501';
    END IF;

    -- The matching consent-event trigger takes this same lock before inserting
    -- a grant/revocation. The two transactions therefore have a serial order.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            NEW.user_id::text || '|' || v_tenant_id || '|memory-v1',
            0
        )
    );

    SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
    INTO v_active
    FROM public.memory_consent_receipts AS receipt
    WHERE receipt.user_id = NEW.user_id
      AND receipt.tenant_id = v_tenant_id
      AND receipt.consent_version = 'memory-v1'
    ORDER BY receipt.event_sequence DESC
    LIMIT 1;

    IF NOT COALESCE(v_active, FALSE) THEN
        -- Revoking consent must stop new writes, but must not trap already
        -- stored facts forever. Permit only a status-only soft-delete of an
        -- owned canonical memory; all personal content and provenance must
        -- remain byte-for-byte identical. RLS separately permits the result
        -- status, and this trigger is the old-vs-new row integrity check.
        IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'canonical_memories' THEN
            IF NEW.status = 'deleted'
               AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
               AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
               AND (to_jsonb(NEW) - ARRAY['status', 'updated_at', 'version'])
                   = (to_jsonb(OLD) - ARRAY['status', 'updated_at', 'version']) THEN
                RETURN NEW;
            END IF;
        END IF;

        -- A soft-delete audit event is allowed only after the corresponding
        -- canonical row is already marked deleted for the same user/tenant.
        -- All other audit inserts remain consent-gated, including edits and
        -- creates; this keeps a forget action auditable after revocation.
        IF TG_OP = 'INSERT' AND TG_TABLE_NAME = 'canonical_memory_events' THEN
            IF NEW.event_type = 'DELETED'
               AND EXISTS (
                   SELECT 1
                   FROM public.canonical_memories AS memory
                   WHERE memory.id = NEW.memory_id
                     AND memory.user_id = NEW.user_id
                     AND memory.tenant_id = v_tenant_id
                     AND memory.status = 'deleted'
               ) THEN
                RETURN NEW;
            END IF;

            -- Bulk forget (DELETE /memory/canonical) hard-deletes every row for
            -- the user/tenant and then records ONE consolidated DELETED event
            -- with the all-zero memory_id sentinel. The per-row proof above can
            -- never hold for that path, so a revoked user's forget always failed
            -- the audit insert and the endpoint reported `partial_failure` even
            -- though all memory was gone. Allow the consolidated event only when
            -- no live row is left, so the trail still cannot assert a deletion
            -- that did not happen.
            IF NEW.event_type = 'DELETED'
               AND NEW.memory_id = '00000000-0000-0000-0000-000000000000'::uuid
               AND NOT EXISTS (
                   SELECT 1
                   FROM public.canonical_memories AS live
                   WHERE live.user_id = NEW.user_id
                     AND live.tenant_id = v_tenant_id
                     AND live.status <> 'deleted'
               ) THEN
                RETURN NEW;
            END IF;
        END IF;

        RAISE EXCEPTION 'active memory consent required for user and tenant'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."enforce_active_memory_consent_before_write"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."ensure_profile_and_role"() RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  uid uuid := auth.uid();
  u record;
  profile_created boolean := false;
  role_rows integer := 0;
  resolved_name text;
  resolved_avatar text;
BEGIN
  IF uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  END IF;

  SELECT id, email, raw_user_meta_data INTO u FROM auth.users WHERE id = uid;
  IF u.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'user_not_found');
  END IF;

  resolved_name := COALESCE(
    u.raw_user_meta_data->>'full_name',
    u.raw_user_meta_data->>'name',
    u.raw_user_meta_data->>'display_name',
    split_part(u.email, '@', 1)
  );
  resolved_avatar := COALESCE(
    u.raw_user_meta_data->>'avatar_url',
    u.raw_user_meta_data->>'picture'
  );

  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (uid, resolved_name, resolved_avatar)
  ON CONFLICT (id) DO UPDATE SET
    display_name = COALESCE(public.profiles.display_name, EXCLUDED.display_name),
    avatar_url   = COALESCE(public.profiles.avatar_url,   EXCLUDED.avatar_url)
  RETURNING (xmax = 0) INTO profile_created;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (uid, 'user'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;
  GET DIAGNOSTICS role_rows = ROW_COUNT;

  RETURN jsonb_build_object(
    'ok', true,
    'user_id', uid,
    'profile_created', COALESCE(profile_created, false),
    'role_created', role_rows > 0
  );
END;
$$;


ALTER FUNCTION "public"."ensure_profile_and_role"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."grant_admin_for_designated_emails"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  admin_emails text[] := ARRAY['kharshaengineer@gmail.com'];
BEGIN
  IF NEW.email_confirmed_at IS NOT NULL
     AND lower(NEW.email) = ANY(SELECT lower(unnest(admin_emails))) THEN
    -- Ensure profile exists
    INSERT INTO public.profiles (id, display_name, avatar_url)
    VALUES (
      NEW.id,
      COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
      COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture')
    )
    ON CONFLICT (id) DO NOTHING;

    -- Grant admin role
    INSERT INTO public.user_roles (user_id, role)
    VALUES (NEW.id, 'admin'::public.app_role)
    ON CONFLICT (user_id, role) DO NOTHING;

    -- Also grant base user role
    INSERT INTO public.user_roles (user_id, role)
    VALUES (NEW.id, 'user'::public.app_role)
    ON CONFLICT (user_id, role) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."grant_admin_for_designated_emails"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_new_user"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  allowed_domains text[] := ARRAY['gmail.com','googlemail.com','hotmail.com','outlook.com','live.com','msn.com'];
  email_domain text;
BEGIN
  IF NEW.email IS NOT NULL THEN
    email_domain := lower(split_part(NEW.email, '@', 2));
    IF NOT (email_domain = ANY(allowed_domains)) THEN
      RAISE EXCEPTION 'email_domain_not_allowed: %', email_domain
        USING HINT = 'Only gmail, hotmail, or outlook addresses are accepted.';
    END IF;
  END IF;

  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url')
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'user'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."handle_new_user"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
    SELECT
        p_user_id = (SELECT auth.uid())
        AND COALESCE((
            SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
            FROM public.memory_consent_receipts AS receipt
            WHERE receipt.user_id = p_user_id
              AND receipt.tenant_id = p_tenant_id
              AND receipt.consent_version = 'memory-v1'
            ORDER BY receipt.event_sequence DESC
            LIMIT 1
        ), FALSE);
$$;


ALTER FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") IS 'True only when auth.uid() owns the row and has the active memory-v1 consent receipt for that tenant; used by restrictive RLS write policies.';



CREATE OR REPLACE FUNCTION "public"."has_role"("_user_id" "uuid", "_role" "public"."app_role") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
  select exists (
    select 1 from public.user_roles
    where user_id = _user_id and role = _role
  )
$$;


ALTER FUNCTION "public"."has_role"("_user_id" "uuid", "_role" "public"."app_role") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."kb_sources_touch_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;


ALTER FUNCTION "public"."kb_sources_touch_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."list_admins"() RETURNS TABLE("id" "uuid", "email" "text", "created_at" timestamp with time zone)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RAISE EXCEPTION 'not_admin';
  END IF;

  RETURN QUERY
  SELECT u.id, u.email::text, u.created_at
  FROM public.user_roles r
  JOIN auth.users u ON u.id = r.user_id
  WHERE r.role = 'admin'::public.app_role
  ORDER BY u.created_at;
END;
$$;


ALTER FUNCTION "public"."list_admins"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_user_memories"("p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) RETURNS TABLE("id" "uuid", "content" "text", "similarity" double precision)
    LANGUAGE "plpgsql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'not_authenticated';
  END IF;

  RETURN QUERY
  SELECT
    m.id,
    m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = auth.uid()
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;


ALTER FUNCTION "public"."match_user_memories"("p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_user_memories_by_user"("p_user_id" "uuid", "p_tenant_id" "text", "p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) RETURNS TABLE("id" "uuid", "content" "text", "similarity" double precision)
    LANGUAGE "plpgsql" STABLE SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
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
$$;


ALTER FUNCTION "public"."match_user_memories_by_user"("p_user_id" "uuid", "p_tenant_id" "text", "p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."match_user_memories_by_user"("p_user_id" "uuid", "p_tenant_id" "text", "p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) IS 'Backend-only semantic lookup scoped to a single user and tenant.';



CREATE OR REPLACE FUNCTION "public"."promote_admin_by_email"("_email" "text") RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  uid uuid;
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  SELECT id INTO uid FROM auth.users WHERE lower(email) = lower(_email) LIMIT 1;
  IF uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'user_not_found');
  END IF;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (uid, 'admin'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN jsonb_build_object('ok', true, 'user_id', uid);
END;
$$;


ALTER FUNCTION "public"."promote_admin_by_email"("_email" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."push_devices_touch_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
begin
  new.updated_at = now();
  return new;
end;
$$;


ALTER FUNCTION "public"."push_devices_touch_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."record_practice"("p_user_id" "uuid", "p_practice_date" "date" DEFAULT CURRENT_DATE) RETURNS TABLE("current_streak" integer, "longest_streak" integer, "last_active_date" "date", "freezes_available" integer, "total_practice_days" integer, "milestone_reached" boolean)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
    rec public.user_streaks%ROWTYPE;
    prev_current INT;
    today DATE := p_practice_date;
    yesterday DATE;
    gap INT;
BEGIN
    -- Ensure row exists first (no-op if exists), then lock for update
    INSERT INTO public.user_streaks (user_id, current_streak, longest_streak, last_active_date, freezes_available, total_practice_days)
    VALUES (p_user_id, 0, 0, NULL, 1, 0)
    ON CONFLICT (user_id) DO NOTHING;

    SELECT * INTO rec FROM public.user_streaks WHERE user_id = p_user_id FOR UPDATE;

    prev_current := rec.current_streak;

    IF rec.last_active_date = today THEN
        milestone_reached := FALSE;
        RETURN QUERY SELECT rec.current_streak, rec.longest_streak, rec.last_active_date,
                            rec.freezes_available, rec.total_practice_days, FALSE;
        RETURN;
    END IF;

    yesterday := today - 1;
    IF rec.last_active_date = yesterday THEN
        rec.current_streak := rec.current_streak + 1;
    ELSIF rec.last_active_date IS NULL THEN
        rec.current_streak := 1;
    ELSE
        gap := today - rec.last_active_date;
        IF gap = 2 AND rec.freezes_available > 0 THEN
            rec.freezes_available := rec.freezes_available - 1;
            rec.current_streak := rec.current_streak + 1;
        ELSE
            rec.current_streak := 1;
        END IF;
    END IF;

    rec.last_active_date := today;
    rec.total_practice_days := rec.total_practice_days + 1;
    IF rec.current_streak > rec.longest_streak THEN
        rec.longest_streak := rec.current_streak;
    END IF;
    IF rec.total_practice_days % 14 = 0 AND rec.freezes_available < 2 THEN
        rec.freezes_available := rec.freezes_available + 1;
    END IF;

    INSERT INTO public.user_streaks (user_id, current_streak, longest_streak, last_active_date, freezes_available, total_practice_days)
    VALUES (rec.user_id, rec.current_streak, rec.longest_streak, rec.last_active_date, rec.freezes_available, rec.total_practice_days)
    ON CONFLICT (user_id) DO UPDATE SET
        current_streak = EXCLUDED.current_streak,
        longest_streak = EXCLUDED.longest_streak,
        last_active_date = EXCLUDED.last_active_date,
        freezes_available = EXCLUDED.freezes_available,
        total_practice_days = EXCLUDED.total_practice_days,
        updated_at = now();

    INSERT INTO public.retention_events (user_id, event, props)
    VALUES (p_user_id, 'practice', jsonb_build_object('streak_current', rec.current_streak));

    IF rec.current_streak IN (3, 7, 14, 21, 40, 108) AND rec.current_streak <> prev_current THEN
        INSERT INTO public.retention_events (user_id, event, props)
        VALUES (p_user_id, 'streak_milestone', jsonb_build_object('streak', rec.current_streak));
        milestone_reached := TRUE;
    ELSE
        milestone_reached := FALSE;
    END IF;

    RETURN QUERY SELECT rec.current_streak, rec.longest_streak, rec.last_active_date,
                        rec.freezes_available, rec.total_practice_days,
                        (rec.current_streak IN (3, 7, 14, 21, 40, 108) AND rec.current_streak <> prev_current);
END;
$$;


ALTER FUNCTION "public"."record_practice"("p_user_id" "uuid", "p_practice_date" "date") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."regenerate_summaries"("p_user_id" "uuid", "p_tenant_id" "text") RETURNS integer
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
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
$$;


ALTER FUNCTION "public"."regenerate_summaries"("p_user_id" "uuid", "p_tenant_id" "text") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."regenerate_summaries"("p_user_id" "uuid", "p_tenant_id" "text") IS 'Backend-only summary regeneration scoped to a single user and tenant.';



CREATE OR REPLACE FUNCTION "public"."register_source_release"("p_corpus_id" "text", "p_source_url" "text", "p_source_identity" "text", "p_content_checksum" "text", "p_notes" "text" DEFAULT NULL::"text") RETURNS "public"."source_releases"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE existing_release public.source_releases; next_version integer; created_release public.source_releases;
BEGIN
    IF length(trim(p_corpus_id)) = 0 OR length(trim(p_source_url)) = 0
       OR length(trim(p_source_identity)) = 0 OR length(trim(p_content_checksum)) = 0 THEN
        RAISE EXCEPTION 'corpus_id, source_url, source_identity, and content_checksum are required' USING ERRCODE = '22023';
    END IF;
    IF p_notes IS NOT NULL AND char_length(p_notes) > 1000 THEN
        RAISE EXCEPTION 'notes exceed 1000 characters' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(trim(p_corpus_id) || '|' || trim(p_source_identity), 0));
    SELECT * INTO existing_release FROM public.source_releases
      WHERE corpus_id = trim(p_corpus_id) AND source_identity = trim(p_source_identity)
        AND content_checksum = trim(p_content_checksum) LIMIT 1;
    IF FOUND THEN RETURN existing_release; END IF;
    SELECT COALESCE(MAX(release_version), 0) + 1 INTO next_version FROM public.source_releases
      WHERE corpus_id = trim(p_corpus_id) AND source_identity = trim(p_source_identity);
    INSERT INTO public.source_releases (corpus_id, source_url, source_identity, release_version, content_checksum, notes)
      VALUES (trim(p_corpus_id), trim(p_source_url), trim(p_source_identity), next_version,
              trim(p_content_checksum), NULLIF(trim(p_notes), ''))
      RETURNING * INTO created_release;
    RETURN created_release;
END;
$$;


ALTER FUNCTION "public"."register_source_release"("p_corpus_id" "text", "p_source_url" "text", "p_source_identity" "text", "p_content_checksum" "text", "p_notes" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."reject_source_release"("p_release_id" "uuid") RETURNS "public"."source_releases"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE rejected_release public.source_releases;
BEGIN
    UPDATE public.source_releases SET status = 'rejected'
      WHERE id = p_release_id AND status IN ('pending', 'approved') RETURNING * INTO rejected_release;
    IF NOT FOUND THEN RAISE EXCEPTION 'only pending or approved releases may be rejected' USING ERRCODE = 'P0001'; END IF;
    RETURN rejected_release;
END;
$$;


ALTER FUNCTION "public"."reject_source_release"("p_release_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."seed_admin_demo"() RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  q_full UUID := gen_random_uuid();
  q_no_response UUID := gen_random_uuid();
  q_no_retrieval UUID := gen_random_uuid();
  pv1 UUID := gen_random_uuid();
  pv2 UUID := gen_random_uuid();
  rule1 UUID := gen_random_uuid();
  run1 UUID := gen_random_uuid();
  req_id TEXT := encode(gen_random_bytes(6), 'hex');
  i INT;
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  -- Prompt versions
  INSERT INTO public.prompt_versions (id, name, version, body, active)
  VALUES (pv1, 'guru_default', 1, 'You are Sri Preethaji...', false)
  ON CONFLICT DO NOTHING;
  INSERT INTO public.prompt_versions (id, name, version, body, active)
  VALUES (pv2, 'guru_default', 2, 'You are Sri Preethaji & Sri Krishnaji...', true)
  ON CONFLICT DO NOTHING;

  -- Full trace tied to v2
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, prompt_tokens, completion_tokens, cost_estimate, prompt_version_id)
  VALUES (q_full, 'What is the Beautiful State?', 'sarvam-30b', 'ok', 1850, 420, 180, 0.0012, pv2);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_full, 'The Beautiful State is a state of inner calm, joy, and connection.',
          '[{"source":"YT:abc123","title":"Intro to Beautiful State"}]'::jsonb,
          0.94, 0.91, 0.88, 0.85, false, 0.92, 'Faithfully grounded.');
  INSERT INTO public.retrieval_events (query_id, source_docs, scores)
  VALUES (q_full, ARRAY['YT:abc123#1','YT:abc123#2','YT:def456#1'], ARRAY[0.92, 0.88, 0.81]);
  INSERT INTO public.trace_spans (query_id, span_name, start_ms, duration_ms) VALUES
    (q_full, 'safety_check', 0, 40),
    (q_full, 'retrieve_documents', 40, 620),
    (q_full, 'rerank_documents', 660, 180),
    (q_full, 'generate_answer', 840, 900),
    (q_full, 'verify_answer', 1740, 110);
  INSERT INTO public.trigger_events (query_id, trigger_type, trigger_name) VALUES (q_full, 'retrieval', 'high_confidence');

  -- Partial: no response
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, prompt_version_id)
  VALUES (q_no_response, 'How do I begin meditation?', 'sarvam-30b', 'error', 320, pv2);

  -- Partial: no retrieval, low confidence
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, cost_estimate, prompt_version_id)
  VALUES (q_no_retrieval, 'Tell me about Sri Krishnaji.', 'sarvam-30b', 'ok', 1100, 0.0006, pv1);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_no_retrieval, 'Sri Krishnaji is a co-founder of the O&O Academy.', '[]'::jsonb, 0.40, 0.55, 0.50, 0.45, true, 0.45, 'Low retrieval — likely hallucinated.');

  -- 7-day trigger trend (one per day)
  FOR i IN 0..6 LOOP
    INSERT INTO public.trigger_events (query_id, trigger_type, trigger_name, created_at)
    VALUES (q_full, 'meditation', CASE WHEN i % 2 = 0 THEN 'serene_mind' ELSE 'fallback' END, now() - (i || ' days')::interval);
  END LOOP;

  -- Alert rule + fired event
  INSERT INTO public.alert_rules (id, name, metric, comparator, threshold, enabled, active, window_minutes, channel, target)
  VALUES (rule1, 'High hallucination rate', 'hallucination_rate', '>', 0.15, true, true, 60, 'email', 'admin@example.com')
  ON CONFLICT DO NOTHING;
  INSERT INTO public.alert_events (rule_id, rule_name, value, message, fired_at)
  VALUES (rule1, 'High hallucination rate', 0.22, 'Hallucination rate above 15% in last hour', now() - interval '2 hours');

  -- Eval run + golden question
  INSERT INTO public.eval_runs (id, name, status, summary, triggered_by, prompt_version_id, started_at, finished_at)
  VALUES (run1, 'Nightly RAGAS', 'ok',
    jsonb_build_object('total', 25, 'passed', 22, 'avg_faithfulness', 0.89, 'avg_answer_relevancy', 0.86, 'avg_context_precision', 0.83, 'avg_context_recall', 0.81),
    'scheduled', pv2, now() - interval '1 day', now() - interval '23 hours');

  INSERT INTO public.golden_questions (question, expected_answer, tags, active, expected_sources)
  VALUES ('What is the Beautiful State?', 'A state of inner calm, joy, connection.', ARRAY['core','teaching'], true, ARRAY['YT:abc123']);

  -- Ingestion run
  INSERT INTO public.ingestion_runs (source, status, chunks_added, duration_ms)
  VALUES ('https://youtu.be/sample123', 'ok', 42, 18500);

  -- Annotation
  INSERT INTO public.annotations (query_id, body, label, notes, promoted_to_golden)
  VALUES (q_full, 'Reviewer notes', 'good', 'Clear and grounded answer.', true);

  -- Safety event
  INSERT INTO public.safety_events (query_id, rule, severity, action, type, excerpt)
  VALUES (q_no_retrieval, 'low_confidence_output', 'medium', 'flagged', 'pii_output', 'Sri Krishnaji is a co-founder...');

  -- App logs sharing a request_id
  INSERT INTO public.app_logs (level, message, context, request_id) VALUES
    ('info', 'chat request received', jsonb_build_object('user', 'demo'), req_id),
    ('info', 'retrieval ok', jsonb_build_object('k', 3), req_id),
    ('warn', 'low confidence answer', jsonb_build_object('confidence', 0.45), req_id);

  -- Topic cluster
  INSERT INTO public.query_clusters (label, size, centroid)
  VALUES ('Beautiful State teachings', 12, '{"x":0.1,"y":0.2}'::jsonb);

  RETURN jsonb_build_object(
    'ok', true,
    'full_trace_id', q_full,
    'missing_response_id', q_no_response,
    'missing_retrieval_id', q_no_retrieval,
    'request_id', req_id
  );
END;
$$;


ALTER FUNCTION "public"."seed_admin_demo"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."serialize_memory_consent_receipt_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO ''
    AS $$
DECLARE
    v_user_id uuid;
    v_tenant_id text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_user_id := OLD.user_id;
        v_tenant_id := OLD.tenant_id;
    ELSE
        v_user_id := NEW.user_id;
        v_tenant_id := NEW.tenant_id;
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            v_user_id::text || '|' || v_tenant_id || '|memory-v1',
            0
        )
    );

    -- The BIGSERIAL default fires before BEFORE INSERT triggers. Reassign while
    -- holding the lock so sequence order also reflects serialized event order.
    IF TG_OP = 'INSERT' THEN
        NEW.event_sequence := pg_catalog.nextval(
            pg_catalog.pg_get_serial_sequence(
                'public.memory_consent_receipts', 'event_sequence'
            )::regclass
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    -- Consent history is append-only: change state by appending a new event.
    RAISE EXCEPTION 'consent receipts are immutable; append a new consent event'
        USING ERRCODE = '42501';
END;
$$;


ALTER FUNCTION "public"."serialize_memory_consent_receipt_mutation"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."set_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
begin
    new.updated_at = now();
    return new;
end;
$$;


ALTER FUNCTION "public"."set_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."touch_canonical_memories_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."touch_canonical_memories_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."touch_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;


ALTER FUNCTION "public"."touch_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."touch_user_last_message"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  owner_id uuid;
BEGIN
  SELECT c.user_id
    INTO owner_id
    FROM public.conversations AS c
   WHERE c.id = NEW.conversation_id;

  UPDATE public.profiles
     SET last_conversation_id = NEW.conversation_id,
         last_message_id = NEW.id,
         last_active_at = now()
   WHERE id = owner_id;

  RETURN NEW;
END
$$;


ALTER FUNCTION "public"."touch_user_last_message"() OWNER TO "postgres";


COMMENT ON FUNCTION "public"."touch_user_last_message"() IS 'Updates profile continuity metadata using the conversation owner for a new chat message.';



CREATE OR REPLACE FUNCTION "public"."update_conversation_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_conversation_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."upsert_canonical_memory"("p_user_id" "uuid", "p_tenant_id" "text", "p_memory_type" "text", "p_statement" "text", "p_normalized_statement" "text", "p_fact_key" "text", "p_confidence" real, "p_importance" real, "p_sensitivity" "text", "p_source_conversation_id" "text", "p_source_turn_index" integer, "p_extraction_method" "text", "p_metadata" "jsonb" DEFAULT '{}'::"jsonb") RETURNS "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    v_existing_id UUID;
    v_new_id      UUID;
    v_old_row     RECORD;
BEGIN
    IF p_fact_key IS NOT NULL THEN
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(
                p_user_id::text || '|' || p_tenant_id || '|' || p_fact_key, 0
            )
        );
        SELECT id INTO v_existing_id
        FROM public.canonical_memories
        WHERE user_id = p_user_id
          AND tenant_id = p_tenant_id
          AND fact_key = p_fact_key
          AND status = 'active'
        LIMIT 1;

        IF v_existing_id IS NOT NULL THEN
            SELECT * INTO v_old_row
            FROM public.canonical_memories
            WHERE id = v_existing_id
              AND user_id = p_user_id
              AND tenant_id = p_tenant_id;

            UPDATE public.canonical_memories
            SET status = 'superseded',
                valid_to = now(),
                version = version + 1
            WHERE id = v_existing_id
              AND user_id = p_user_id
              AND tenant_id = p_tenant_id;

            INSERT INTO public.memory_audit_events
                (user_id, tenant_id, memory_id, action, old_state, new_state)
            VALUES (p_user_id, p_tenant_id, v_existing_id, 'superseded', to_jsonb(v_old_row), NULL);
        END IF;
    END IF;

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

    INSERT INTO public.memory_audit_events (user_id, tenant_id, memory_id, action, new_state)
    VALUES (
        p_user_id, p_tenant_id, v_new_id, 'created',
        (SELECT to_jsonb(cm) FROM public.canonical_memories cm WHERE cm.id = v_new_id)
    );
    RETURN v_new_id;
END;
$$;


ALTER FUNCTION "public"."upsert_canonical_memory"("p_user_id" "uuid", "p_tenant_id" "text", "p_memory_type" "text", "p_statement" "text", "p_normalized_statement" "text", "p_fact_key" "text", "p_confidence" real, "p_importance" real, "p_sensitivity" "text", "p_source_conversation_id" "text", "p_source_turn_index" integer, "p_extraction_method" "text", "p_metadata" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."whoami_diagnostics"() RETURNS "jsonb"
    LANGUAGE "plpgsql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  uid uuid := auth.uid();
  profile_row public.profiles%ROWTYPE;
  role_list text[];
  is_admin boolean;
BEGIN
  IF uid IS NULL THEN
    RETURN jsonb_build_object('authenticated', false);
  END IF;

  SELECT * INTO profile_row FROM public.profiles WHERE id = uid;
  SELECT array_agg(role::text) INTO role_list FROM public.user_roles WHERE user_id = uid;
  SELECT public.has_role(uid, 'admin'::public.app_role) INTO is_admin;

  RETURN jsonb_build_object(
    'authenticated', true,
    'user_id', uid,
    'profile_present', profile_row.id IS NOT NULL,
    'display_name', profile_row.display_name,
    'roles', COALESCE(role_list, ARRAY[]::text[]),
    'is_admin', COALESCE(is_admin, false)
  );
END;
$$;


ALTER FUNCTION "public"."whoami_diagnostics"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."alert_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "rule_id" "uuid",
    "value" numeric,
    "fired_at" timestamp with time zone DEFAULT "now"(),
    "resolved_at" timestamp with time zone,
    "rule_name" "text"
);


ALTER TABLE "public"."alert_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."alert_rules" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text",
    "metric" "text",
    "comparator" "text",
    "threshold" numeric,
    "window_minutes" integer,
    "channel" "text",
    "target" "text",
    "active" boolean DEFAULT true
);


ALTER TABLE "public"."alert_rules" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."annotations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "response_id" "uuid",
    "reviewer_id" "uuid",
    "label" "text",
    "notes" "text",
    "promoted_to_golden" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."annotations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."app_logs" (
    "id" bigint NOT NULL,
    "level" "text",
    "message" "text",
    "context" "jsonb",
    "request_id" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."app_logs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."app_logs_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."app_logs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."app_logs_id_seq" OWNED BY "public"."app_logs"."id";



CREATE TABLE IF NOT EXISTS "public"."app_settings" (
    "key" "text" NOT NULL,
    "value" "jsonb" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."app_settings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."assistant_access" (
    "user_id" "uuid" NOT NULL,
    "assistant_id" "uuid" NOT NULL,
    "granted_via" "text" DEFAULT 'invite'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."assistant_access" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."assistant_configurations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "guru_id" "uuid",
    "slug" "text" NOT NULL,
    "name" "text" NOT NULL,
    "system_prompt" "text",
    "knowledge_tags" "text"[] DEFAULT '{}'::"text"[],
    "is_default" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."assistant_configurations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."assistant_doctrines" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "assistant_slug" "text" NOT NULL,
    "synonyms_json" "jsonb" DEFAULT '{}'::"jsonb",
    "canonical_terms" "text"[] DEFAULT '{}'::"text"[],
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."assistant_doctrines" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."assistant_scope_metadata" (
    "assistant_id" "uuid" NOT NULL,
    "corpus_id" "text" DEFAULT 'askmukthiguru'::"text" NOT NULL,
    "teacher_id" "text",
    "graph_namespace" "text",
    "source_release_id" "text",
    "assistant_scope_version" "text" DEFAULT 'v1'::"text" NOT NULL,
    "rights_status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "rollout_enabled" boolean DEFAULT false NOT NULL,
    "ingestion_source_filter" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "knowledge_tags" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "assistant_scope_metadata_rights_status_check" CHECK (("rights_status" = ANY (ARRAY['approved'::"text", 'pending'::"text", 'revoked'::"text"])))
);


ALTER TABLE "public"."assistant_scope_metadata" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."assistants" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "slug" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" DEFAULT ''::"text" NOT NULL,
    "avatar_url" "text",
    "system_prompt" "text" DEFAULT ''::"text" NOT NULL,
    "starter_questions" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "knowledge_tags" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "visibility" "public"."assistant_visibility" DEFAULT 'public'::"public"."assistant_visibility" NOT NULL,
    "invite_code" "text",
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."assistants" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cancellations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "status" character varying(20) NOT NULL,
    "reason" character varying(50),
    "data_retention" character varying(20),
    "scheduled_deletion" timestamp with time zone,
    "completed_deletion" timestamp with time zone,
    "reactivated_at" timestamp with time zone,
    "win_back_emails_sent" "jsonb" DEFAULT '[]'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cancellations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."canonical_memories" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    "memory_type" "text" NOT NULL,
    "statement" "text" NOT NULL,
    "normalized_statement" "text",
    "fact_key" "text",
    "confidence" real DEFAULT 0.75,
    "importance" real DEFAULT 0.5,
    "sensitivity" "text" DEFAULT 'normal'::"text",
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "source_conversation_id" "text",
    "source_message_id" "text",
    "source_turn_index" integer,
    "extraction_method" "text" DEFAULT 'llm'::"text" NOT NULL,
    "evidence_count" integer DEFAULT 1,
    "embedding_id" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "last_used_at" timestamp with time zone,
    "last_confirmed_at" timestamp with time zone,
    "valid_from" timestamp with time zone,
    "valid_to" timestamp with time zone,
    "expires_at" timestamp with time zone,
    "version" integer DEFAULT 1,
    CONSTRAINT "canonical_memories_confidence_check" CHECK ((("confidence" >= (0)::double precision) AND ("confidence" <= (1)::double precision))),
    CONSTRAINT "canonical_memories_importance_check" CHECK ((("importance" >= (0)::double precision) AND ("importance" <= (1)::double precision))),
    CONSTRAINT "canonical_memories_memory_type_check" CHECK (("memory_type" = ANY (ARRAY['PROFILE'::"text", 'PREFERENCE'::"text", 'COMMUNICATION_STYLE'::"text", 'GOAL'::"text", 'PROJECT'::"text", 'INTEREST'::"text", 'RELATIONSHIP'::"text", 'USER_EXPLICIT'::"text", 'TEMPORARY_CONTEXT'::"text", 'REFLECTION'::"text"]))),
    CONSTRAINT "canonical_memories_sensitivity_check" CHECK (("sensitivity" = ANY (ARRAY['normal'::"text", 'sensitive'::"text", 'highly_sensitive'::"text"]))),
    CONSTRAINT "canonical_memories_status_check" CHECK (("status" = ANY (ARRAY['active'::"text", 'superseded'::"text", 'expired'::"text", 'deleted'::"text"])))
);


ALTER TABLE "public"."canonical_memories" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."canonical_memory_compaction_snapshots" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    "memories_json" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."canonical_memory_compaction_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."canonical_memory_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "memory_id" "uuid",
    "event_type" "text" NOT NULL,
    "actor" "text" DEFAULT 'system'::"text" NOT NULL,
    "old_version" integer,
    "new_version" integer,
    "reason" "text",
    "metadata" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text",
    CONSTRAINT "canonical_memory_events_actor_check" CHECK (("actor" = ANY (ARRAY['user'::"text", 'system'::"text", 'admin'::"text", 'resolver'::"text", 'consolidator'::"text"]))),
    CONSTRAINT "canonical_memory_events_event_type_check" CHECK (("event_type" = ANY (ARRAY['CREATED'::"text", 'UPDATED'::"text", 'DELETED'::"text", 'SUPERSEDED'::"text", 'EXPIRED'::"text", 'RESTORED'::"text", 'MERGED'::"text"])))
);


ALTER TABLE "public"."canonical_memory_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chat_messages" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "content" "text" NOT NULL,
    "citations" "text"[],
    "confidence_score" double precision,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "chat_messages_role_check" CHECK (("role" = ANY (ARRAY['user'::"text", 'guru'::"text", 'assistant'::"text"])))
);


ALTER TABLE "public"."chat_messages" OWNER TO "postgres";


COMMENT ON TABLE "public"."chat_messages" IS 'Conversation messages. Access is controlled by own_messages_* RLS policies.';



CREATE TABLE IF NOT EXISTS "public"."chat_queries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "uuid",
    "anon_user_id" "text",
    "query_text" "text" NOT NULL,
    "prompt_version_id" "uuid",
    "model" "text",
    "prompt_tokens" integer,
    "completion_tokens" integer,
    "cost_estimate" numeric,
    "latency_ms" integer,
    "status" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "user_id" "uuid",
    "provider" "text",
    "route_decision" "text",
    "cache_hit" boolean,
    "ttft_ms" integer,
    "tokens_per_second" numeric,
    "assistant_slug" "text",
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL
);


ALTER TABLE "public"."chat_queries" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chat_responses" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "response_text" "text",
    "citations" "jsonb",
    "faithfulness" numeric,
    "answer_relevancy" numeric,
    "context_precision" numeric,
    "context_recall" numeric,
    "hallucination_flag" boolean,
    "judge_reasoning" "text",
    "confidence" numeric,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "evaluation_trace" "jsonb" DEFAULT '{}'::"jsonb",
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL,
    "citations_verified" boolean,
    "orphan_citations_stripped" boolean
);


ALTER TABLE "public"."chat_responses" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chat_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "anon_user_id" "text",
    "channel" "text",
    "started_at" timestamp with time zone DEFAULT "now"(),
    "user_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."chat_sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."conversation_memories" (
    "session_id" "uuid" NOT NULL,
    "user_id" "uuid",
    "started_at" double precision NOT NULL,
    "messages" "jsonb" DEFAULT '[]'::"jsonb",
    "key_insights" "text"[] DEFAULT '{}'::"text"[],
    "emotional_arc" "jsonb" DEFAULT '[]'::"jsonb",
    "follow_up_suggestions" "text"[] DEFAULT '{}'::"text"[],
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL
);


ALTER TABLE "public"."conversation_memories" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."conversations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text",
    "preview" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "assistant_id" "uuid",
    "retention_days" integer DEFAULT 90 NOT NULL,
    "summary" "text",
    CONSTRAINT "retention_days_nonneg" CHECK (("retention_days" >= 0))
);


ALTER TABLE "public"."conversations" OWNER TO "postgres";


COMMENT ON TABLE "public"."conversations" IS 'User-owned conversations. Access is controlled by own_conversations_* RLS policies.';



CREATE TABLE IF NOT EXISTS "public"."corpus_gate_rejections" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_url" "text" NOT NULL,
    "chunk_index" integer,
    "gate_layer" "text" NOT NULL,
    "reason" "text" NOT NULL,
    "matched_span" "text",
    "point_id" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "gate_verdict" "text",
    "gate_reason" "text"
);


ALTER TABLE "public"."corpus_gate_rejections" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."corpus_sources" (
    "source_identity" "text" NOT NULL,
    "source_url" "text" NOT NULL,
    "corpus_id" "text" NOT NULL,
    "last_ingested_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_checksum" "text",
    "active_release_id" "uuid",
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."corpus_sources" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."daily_teachings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "image_url" "text" NOT NULL,
    "caption" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone DEFAULT ("now"() + '24:00:00'::interval),
    "created_by" "uuid"
);

ALTER TABLE ONLY "public"."daily_teachings" REPLICA IDENTITY FULL;


ALTER TABLE "public"."daily_teachings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."doctrine_faqs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "question" "text" NOT NULL,
    "answer" "text" NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "sort_order" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "citations" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL
);


ALTER TABLE "public"."doctrine_faqs" OWNER TO "postgres";


COMMENT ON COLUMN "public"."doctrine_faqs"."citations" IS 'Optional JSON-encoded citation URLs for the doctrine FAQ answer. NULL if no citations.';



CREATE TABLE IF NOT EXISTS "public"."eval_results" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "eval_run_id" "uuid",
    "golden_id" "uuid",
    "faithfulness" numeric,
    "answer_relevancy" numeric,
    "context_precision" numeric,
    "context_recall" numeric,
    "passed" boolean,
    "response_text" "text"
);


ALTER TABLE "public"."eval_results" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."eval_runs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "triggered_by" "text",
    "prompt_version_id" "uuid",
    "started_at" timestamp with time zone DEFAULT "now"(),
    "finished_at" timestamp with time zone,
    "summary" "jsonb"
);


ALTER TABLE "public"."eval_runs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."exit_surveys" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "reason" character varying(50) NOT NULL,
    "details" "text",
    "responded_to" boolean DEFAULT false,
    "response_type" character varying(20),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."exit_surveys" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."faculty_answer_labels" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "trace_id" "text",
    "request_id" "text",
    "answer_key" "text" GENERATED ALWAYS AS (COALESCE("trace_id", "request_id")) STORED,
    "message_id" "text",
    "model" "text",
    "policy_id" "text",
    "release_id" "text",
    "faithful" "text" NOT NULL,
    "safe" boolean NOT NULL,
    "helpful" smallint NOT NULL,
    "note" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "faculty_answer_labels_faithful_check" CHECK (("faithful" = ANY (ARRAY['yes'::"text", 'partly'::"text", 'no'::"text"]))),
    CONSTRAINT "faculty_answer_labels_has_answer_key" CHECK ((("trace_id" IS NOT NULL) OR ("request_id" IS NOT NULL))),
    CONSTRAINT "faculty_answer_labels_helpful_check" CHECK ((("helpful" >= 1) AND ("helpful" <= 5))),
    CONSTRAINT "faculty_answer_labels_note_check" CHECK ((("note" IS NULL) OR ("char_length"("note") <= 2000)))
);


ALTER TABLE "public"."faculty_answer_labels" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."feedback_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "user_id" "uuid",
    "rating" integer DEFAULT 0 NOT NULL,
    "comment" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "query_text" "text" DEFAULT ''::"text",
    "answer_text" "text" DEFAULT ''::"text",
    "feedback_text" "text" DEFAULT ''::"text",
    "metadata_json" "jsonb" DEFAULT '{}'::"jsonb"
);


ALTER TABLE "public"."feedback_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."golden_questions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "question" "text",
    "expected_answer" "text",
    "expected_sources" "text"[],
    "tags" "text"[],
    "active" boolean DEFAULT true
);


ALTER TABLE "public"."golden_questions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."guru_core_memory" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" DEFAULT "auth"."uid"() NOT NULL,
    "content" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    CONSTRAINT "core_memory_length_check" CHECK (("char_length"("content") <= 2048))
);


ALTER TABLE "public"."guru_core_memory" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."guru_memories" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" DEFAULT "auth"."uid"() NOT NULL,
    "content" "text" NOT NULL,
    "source" "text" DEFAULT 'extracted'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "embedding" "public"."vector"(1024) NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    "claim" "text",
    "confidence" double precision,
    "decay_score" double precision DEFAULT 1.0,
    "summary" "text",
    "fact_key" "text",
    "valid_from" timestamp with time zone,
    "valid_to" timestamp with time zone,
    "source_conversation_id" "text",
    CONSTRAINT "guru_memories_source_conversation_id_len" CHECK ((("source_conversation_id" IS NULL) OR ("char_length"("source_conversation_id") <= 200)))
);


ALTER TABLE "public"."guru_memories" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."guru_session_summaries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" DEFAULT "auth"."uid"(),
    "session_id" "uuid" NOT NULL,
    "summary" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL
);


ALTER TABLE "public"."guru_session_summaries" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."gurus" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "slug" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "avatar_url" "text",
    "collection_name" "text" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."gurus" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ingest_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_url" "text" NOT NULL,
    "source_type" character varying(20) DEFAULT 'video'::character varying,
    "status" character varying(20) DEFAULT 'pending'::character varying,
    "progress_pct" integer DEFAULT 0,
    "chunks_indexed" integer DEFAULT 0,
    "error_message" "text",
    "worker_id" character varying(50),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "idempotency_key" "text",
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "heartbeat_at" timestamp with time zone,
    "attempt" integer DEFAULT 0,
    "source_identity" "text",
    CONSTRAINT "ingest_jobs_progress_pct_check" CHECK ((("progress_pct" >= 0) AND ("progress_pct" <= 100))),
    CONSTRAINT "ingest_jobs_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying])::"text"[])))
);


ALTER TABLE "public"."ingest_jobs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ingestion_checkpoints" (
    "chunk_id" "text" NOT NULL,
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."ingestion_checkpoints" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ingestion_runs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source" "text",
    "chunks_added" integer,
    "embedding_model" "text",
    "duration_ms" integer,
    "status" "text",
    "error_log" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."ingestion_runs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."kb_chunks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_id" "uuid" NOT NULL,
    "ord" integer DEFAULT 0 NOT NULL,
    "text" "text" NOT NULL,
    "token_count" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."kb_chunks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."kb_sources" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "title" "text" NOT NULL,
    "url" "text",
    "kind" "text" DEFAULT 'text'::"text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "chunk_count" integer DEFAULT 0 NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."kb_sources" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."meditation_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "started_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "completed_at" timestamp with time zone,
    "duration_seconds" integer DEFAULT 0,
    "breath_cycles" integer DEFAULT 0,
    "completed" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."meditation_sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."memory_audit_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "memory_id" "uuid",
    "action" "text" NOT NULL,
    "old_state" "jsonb",
    "new_state" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL,
    CONSTRAINT "memory_audit_events_action_check" CHECK (("action" = ANY (ARRAY['created'::"text", 'updated'::"text", 'superseded'::"text", 'expired'::"text", 'deleted'::"text", 'retrieved'::"text"])))
);


ALTER TABLE "public"."memory_audit_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."memory_compaction_snapshots" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "memories_json" "jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL
);


ALTER TABLE "public"."memory_compaction_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."memory_consent_receipts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL,
    "consent_version" "text" NOT NULL,
    "granted" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "revoked_at" timestamp with time zone,
    "source" "text" DEFAULT 'user_explicit'::"text" NOT NULL,
    "event_sequence" bigint NOT NULL,
    CONSTRAINT "memory_consent_receipts_source_check" CHECK (("source" = ANY (ARRAY['user_explicit'::"text", 'auto_default'::"text"])))
);


ALTER TABLE "public"."memory_consent_receipts" OWNER TO "postgres";


COMMENT ON TABLE "public"."memory_consent_receipts" IS 'Append-only memory consent events. The most recent event per user, tenant, and policy version determines active consent.';



CREATE SEQUENCE IF NOT EXISTS "public"."memory_consent_receipts_event_sequence_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."memory_consent_receipts_event_sequence_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."memory_consent_receipts_event_sequence_seq" OWNED BY "public"."memory_consent_receipts"."event_sequence";



CREATE TABLE IF NOT EXISTS "public"."memory_deletion_receipts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL,
    "deleted_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "store_counts" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" "text" DEFAULT 'completed'::"text" NOT NULL,
    "error" "text",
    CONSTRAINT "memory_deletion_receipts_status_check" CHECK (("status" = ANY (ARRAY['completed'::"text", 'partial_failure'::"text"])))
);


ALTER TABLE "public"."memory_deletion_receipts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."model_pricing" (
    "model" "text" NOT NULL,
    "input_per_1k" numeric,
    "output_per_1k" numeric,
    "currency" "text" DEFAULT 'USD'::"text"
);


ALTER TABLE "public"."model_pricing" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."notes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text" DEFAULT 'Untitled'::"text" NOT NULL,
    "body" "text" DEFAULT ''::"text" NOT NULL,
    "tags" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "source_message_id" "text",
    "source_conversation_id" "uuid",
    "is_favorite" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."notes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."okf_review_queue" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "entry_json" "jsonb" NOT NULL,
    "source_video_id" "text",
    "source_video_title" "text",
    "guru_slug" "text" DEFAULT 'default'::"text",
    "status" "text" DEFAULT 'pending'::"text",
    "reviewer_notes" "text",
    "submitted_at" timestamp with time zone DEFAULT "now"(),
    "reviewed_at" timestamp with time zone,
    "reviewed_by" "uuid"
);


ALTER TABLE "public"."okf_review_queue" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."profiles" (
    "id" "uuid" NOT NULL,
    "display_name" "text",
    "avatar_url" "text",
    "preferred_language" "text" DEFAULT 'en'::"text",
    "tts_enabled" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "last_conversation_id" "uuid",
    "last_message_id" "uuid",
    "last_active_at" timestamp with time zone,
    "last_device_id" "text"
);


ALTER TABLE "public"."profiles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."prompt_versions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "version" "text" NOT NULL,
    "content" "text" NOT NULL,
    "active" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "description" "text" DEFAULT ''::"text",
    "author" "text" DEFAULT 'system'::"text"
);


ALTER TABLE "public"."prompt_versions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."push_devices" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "platform" "text" NOT NULL,
    "token" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    CONSTRAINT "push_devices_platform_check" CHECK (("platform" = ANY (ARRAY['android'::"text", 'ios'::"text"])))
);


ALTER TABLE "public"."push_devices" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."push_subscriptions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "endpoint" "text" NOT NULL,
    "p256dh" "text" NOT NULL,
    "auth" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."push_subscriptions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."query_clusters" (
    "query_id" "uuid" NOT NULL,
    "cluster_id" integer,
    "cluster_label" "text",
    "embedding" "jsonb"
);


ALTER TABLE "public"."query_clusters" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."retention_events" (
    "id" bigint NOT NULL,
    "user_id" "uuid" NOT NULL,
    "event" "text" NOT NULL,
    "props" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."retention_events" OWNER TO "postgres";


ALTER TABLE "public"."retention_events" ALTER COLUMN "id" ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME "public"."retention_events_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



CREATE TABLE IF NOT EXISTS "public"."retrieval_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "chunk_ids" "text"[],
    "source_docs" "text"[],
    "scores" numeric[],
    "top_k" integer,
    "retrieval_hit" boolean,
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL
);


ALTER TABLE "public"."retrieval_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."retrieval_feedback_signals" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_hash" "text" NOT NULL,
    "source_url" "text" NOT NULL,
    "point_id" "text",
    "signal" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."retrieval_feedback_signals" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."router_decisions" (
    "id" "uuid" NOT NULL,
    "query_text" "text" NOT NULL,
    "tier" "text" NOT NULL,
    "confidence" double precision NOT NULL,
    "method" "text" NOT NULL,
    "shadow_tier" "text",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."router_decisions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."safety_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "type" "text",
    "severity" "text",
    "excerpt" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."safety_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."save_offers" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "offer_type" character varying(50) NOT NULL,
    "accepted" boolean NOT NULL,
    "applied_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone
);


ALTER TABLE "public"."save_offers" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."staging_quality_queue" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_url" "text" NOT NULL,
    "content_preview" "text" NOT NULL,
    "quality_score" integer NOT NULL,
    "fail_reasons" "text"[] NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "reviewer_notes" "text" DEFAULT ''::"text" NOT NULL,
    "content_hash" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reviewed_at" timestamp with time zone,
    "reviewed_by" "uuid"
);


ALTER TABLE "public"."staging_quality_queue" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."study_notebook_items" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "notebook_id" "uuid" NOT NULL,
    "query" "text" NOT NULL,
    "answer" "text" NOT NULL,
    "citations" "jsonb" DEFAULT '[]'::"jsonb",
    "source_episode_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."study_notebook_items" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."study_notebooks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."study_notebooks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."telemetry_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "session_id" "text",
    "user_message_id" "text" NOT NULL,
    "last_message_id" "text",
    "metric_type" "text" NOT NULL,
    "metric_value" numeric NOT NULL,
    "tags" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."telemetry_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."token_usage" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "text" DEFAULT 'default'::"text" NOT NULL,
    "user_id" "text" DEFAULT ''::"text" NOT NULL,
    "session_id" "text" DEFAULT ''::"text" NOT NULL,
    "model" "text" DEFAULT ''::"text" NOT NULL,
    "provider" "text" DEFAULT 'ollama'::"text" NOT NULL,
    "tokens_in" integer DEFAULT 0 NOT NULL,
    "tokens_out" integer DEFAULT 0 NOT NULL,
    "cost_usd" numeric DEFAULT 0.0 NOT NULL,
    "endpoint" "text" DEFAULT '/api/chat'::"text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."token_usage" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."trace_spans" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "parent_span_id" "uuid",
    "name" "text" NOT NULL,
    "start_ms" bigint,
    "duration_ms" integer,
    "attributes" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "span_name" "text"
);


ALTER TABLE "public"."trace_spans" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."trigger_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "query_id" "uuid",
    "trigger_name" "text" NOT NULL,
    "metadata" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."trigger_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_brain_edges" (
    "id" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "src" "text" NOT NULL,
    "dst" "text" NOT NULL,
    "rel_cipher" "text" NOT NULL,
    "weight" real DEFAULT 1.0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_brain_edges" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_brain_keys" (
    "user_id" "uuid" NOT NULL,
    "wrapped_dek" "text" NOT NULL,
    "wrap_mode" "text" DEFAULT 'server_wrapped'::"text" NOT NULL,
    "kdf" "jsonb",
    "version" integer DEFAULT 1 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "rotated_at" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "kek" "text",
    "dek_wrapped" "text",
    CONSTRAINT "user_brain_keys_wrap_mode_check" CHECK (("wrap_mode" = ANY (ARRAY['server_wrapped'::"text", 'session_unlock'::"text"])))
);


ALTER TABLE "public"."user_brain_keys" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_brain_nodes" (
    "id" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "kind" "text" NOT NULL,
    "ciphertext" "text" NOT NULL,
    "blind" "text",
    "confidence" real DEFAULT 0.8 NOT NULL,
    "decay" real DEFAULT 1.0 NOT NULL,
    "access_count" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "valid_from" timestamp with time zone DEFAULT "now"() NOT NULL,
    "valid_to" timestamp with time zone,
    "is_superseded" boolean DEFAULT false NOT NULL,
    "superseded_by" "text",
    CONSTRAINT "user_brain_nodes_kind_check" CHECK (("kind" = ANY (ARRAY['reflection'::"text", 'entity'::"text", 'preference'::"text", 'relationship'::"text", 'journal'::"text"])))
);


ALTER TABLE "public"."user_brain_nodes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_course_progress" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "course_slug" "text" NOT NULL,
    "assigned_reason" "text",
    "trigger_signal" "text",
    "completed_lessons" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "current_lesson_index" integer DEFAULT 0 NOT NULL,
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "started_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_course_progress" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_episodes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "query" "text" NOT NULL,
    "answer" "text" NOT NULL,
    "citations" "jsonb",
    "intent" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL
);


ALTER TABLE "public"."user_episodes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_feedback" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "response_id" "uuid",
    "rating" smallint,
    "accuracy" smallint,
    "comment" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."user_feedback" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_healing_progress" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "course_slug" "text" NOT NULL,
    "current_step" integer DEFAULT 0 NOT NULL,
    "completed_steps" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "last_accessed_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "total_steps" integer DEFAULT 0 NOT NULL,
    CONSTRAINT "user_healing_progress_current_step_check" CHECK (("current_step" >= 0)),
    CONSTRAINT "user_healing_progress_total_steps_check" CHECK (("total_steps" >= 0))
);


ALTER TABLE "public"."user_healing_progress" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_personas" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "uuid" DEFAULT '00000000-0000-0000-0000-000000000000'::"uuid" NOT NULL,
    "content" "text" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_personas" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_profiles" (
    "user_id" "uuid" NOT NULL,
    "preferred_language" "text" DEFAULT 'en'::"text",
    "spiritual_level" "text" DEFAULT 'beginner'::"text",
    "topics_of_interest" "text"[] DEFAULT '{}'::"text"[],
    "last_distress_assessment" "jsonb" DEFAULT '{}'::"jsonb",
    "total_conversations" integer DEFAULT 0,
    "total_meditations_completed" integer DEFAULT 0,
    "favorite_teachings" "text"[] DEFAULT '{}'::"text"[],
    "codemix_preference" boolean DEFAULT false,
    "created_at" double precision NOT NULL,
    "updated_at" double precision NOT NULL,
    "tenant_id" "text" DEFAULT 'oneness'::"text" NOT NULL
);


ALTER TABLE "public"."user_profiles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_retention_cards" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "question" "text" NOT NULL,
    "answer" "text" NOT NULL,
    "source_type" "text" NOT NULL,
    "source_id" "text",
    "easiness_factor" double precision DEFAULT 2.5 NOT NULL,
    "interval_days" integer DEFAULT 0 NOT NULL,
    "repetitions" integer DEFAULT 0 NOT NULL,
    "next_review_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_retention_cards" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_roles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "role" "public"."app_role" NOT NULL
);


ALTER TABLE "public"."user_roles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_scene_blocks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "uuid" DEFAULT '00000000-0000-0000-0000-000000000000'::"uuid" NOT NULL,
    "session_id" "uuid",
    "scene_type" "text" DEFAULT 'general'::"text" NOT NULL,
    "compressed_blocks" "text" NOT NULL,
    "turn_count" integer DEFAULT 1 NOT NULL,
    "turn_range" "int4range",
    "started_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "ended_at" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_scene_blocks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_skills" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "tenant_id" "uuid" DEFAULT '00000000-0000-0000-0000-000000000000'::"uuid" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" DEFAULT ''::"text" NOT NULL,
    "source_atom_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    "proficiency" double precision DEFAULT 0.0 NOT NULL,
    "practice_count" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_skills" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_streaks" (
    "user_id" "uuid" NOT NULL,
    "current_streak" integer DEFAULT 0 NOT NULL,
    "longest_streak" integer DEFAULT 0 NOT NULL,
    "last_active_date" "date",
    "freezes_available" integer DEFAULT 1 NOT NULL,
    "total_practice_days" integer DEFAULT 0 NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."user_streaks" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_chat_queries_by_assistant" WITH ("security_invoker"='true') AS
 SELECT "assistant_slug",
    "count"(*) AS "query_count",
    "avg"("latency_ms") AS "avg_latency_ms",
    "avg"("prompt_tokens") AS "avg_prompt_tokens",
    "avg"("completion_tokens") AS "avg_completion_tokens",
    "max"("created_at") AS "last_query_at"
   FROM "public"."chat_queries"
  WHERE ("assistant_slug" IS NOT NULL)
  GROUP BY "assistant_slug";


ALTER VIEW "public"."v_chat_queries_by_assistant" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_meditation_heatmap" WITH ("security_invoker"='true') AS
 SELECT "user_id",
    ("date_trunc"('day'::"text", "started_at"))::"date" AS "day",
    "count"(*) AS "sessions",
    COALESCE("sum"("duration_seconds"), (0)::bigint) AS "seconds"
   FROM "public"."meditation_sessions"
  GROUP BY "user_id", (("date_trunc"('day'::"text", "started_at"))::"date");


ALTER VIEW "public"."v_meditation_heatmap" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."waitlist_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" "text" NOT NULL,
    "email_key" "text" GENERATED ALWAYS AS ("lower"("email")) STORED,
    "name" "text",
    "source" "text",
    "consented_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "waitlist_email_nonempty" CHECK (("length"(TRIM(BOTH FROM "email")) > 3)),
    CONSTRAINT "waitlist_name_length" CHECK ((("name" IS NULL) OR ("char_length"("name") <= 100))),
    CONSTRAINT "waitlist_source_length" CHECK (("char_length"("source") <= 80))
);


ALTER TABLE "public"."waitlist_entries" OWNER TO "postgres";


ALTER TABLE ONLY "public"."app_logs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."app_logs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."memory_consent_receipts" ALTER COLUMN "event_sequence" SET DEFAULT "nextval"('"public"."memory_consent_receipts_event_sequence_seq"'::"regclass");



ALTER TABLE ONLY "public"."alert_events"
    ADD CONSTRAINT "alert_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."alert_rules"
    ADD CONSTRAINT "alert_rules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."annotations"
    ADD CONSTRAINT "annotations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."app_logs"
    ADD CONSTRAINT "app_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."app_settings"
    ADD CONSTRAINT "app_settings_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."assistant_access"
    ADD CONSTRAINT "assistant_access_pkey" PRIMARY KEY ("user_id", "assistant_id");



ALTER TABLE ONLY "public"."assistant_configurations"
    ADD CONSTRAINT "assistant_configurations_guru_id_slug_key" UNIQUE ("guru_id", "slug");



ALTER TABLE ONLY "public"."assistant_configurations"
    ADD CONSTRAINT "assistant_configurations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."assistant_doctrines"
    ADD CONSTRAINT "assistant_doctrines_assistant_slug_key" UNIQUE ("assistant_slug");



ALTER TABLE ONLY "public"."assistant_doctrines"
    ADD CONSTRAINT "assistant_doctrines_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."assistant_scope_metadata"
    ADD CONSTRAINT "assistant_scope_metadata_pkey" PRIMARY KEY ("assistant_id");



ALTER TABLE ONLY "public"."assistants"
    ADD CONSTRAINT "assistants_invite_code_key" UNIQUE ("invite_code");



ALTER TABLE ONLY "public"."assistants"
    ADD CONSTRAINT "assistants_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."assistants"
    ADD CONSTRAINT "assistants_slug_key" UNIQUE ("slug");



ALTER TABLE ONLY "public"."cancellations"
    ADD CONSTRAINT "cancellations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."canonical_memories"
    ADD CONSTRAINT "canonical_memories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."canonical_memory_compaction_snapshots"
    ADD CONSTRAINT "canonical_memory_compaction_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."canonical_memory_events"
    ADD CONSTRAINT "canonical_memory_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_messages"
    ADD CONSTRAINT "chat_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_queries"
    ADD CONSTRAINT "chat_queries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_responses"
    ADD CONSTRAINT "chat_responses_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."conversation_memories"
    ADD CONSTRAINT "conversation_memories_pkey" PRIMARY KEY ("session_id");



ALTER TABLE ONLY "public"."conversations"
    ADD CONSTRAINT "conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."corpus_gate_rejections"
    ADD CONSTRAINT "corpus_gate_rejections_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."corpus_sources"
    ADD CONSTRAINT "corpus_sources_pkey" PRIMARY KEY ("source_identity");



ALTER TABLE ONLY "public"."daily_teachings"
    ADD CONSTRAINT "daily_teachings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctrine_faqs"
    ADD CONSTRAINT "doctrine_faqs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."doctrine_faqs"
    ADD CONSTRAINT "doctrine_faqs_question_unique" UNIQUE ("question");



ALTER TABLE ONLY "public"."eval_results"
    ADD CONSTRAINT "eval_results_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."eval_runs"
    ADD CONSTRAINT "eval_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."exit_surveys"
    ADD CONSTRAINT "exit_surveys_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."faculty_answer_labels"
    ADD CONSTRAINT "faculty_answer_labels_one_per_reviewer" UNIQUE ("user_id", "answer_key");



ALTER TABLE ONLY "public"."faculty_answer_labels"
    ADD CONSTRAINT "faculty_answer_labels_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."feedback_events"
    ADD CONSTRAINT "feedback_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."golden_questions"
    ADD CONSTRAINT "golden_questions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."guru_core_memory"
    ADD CONSTRAINT "guru_core_memory_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."guru_memories"
    ADD CONSTRAINT "guru_memories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."guru_session_summaries"
    ADD CONSTRAINT "guru_session_summaries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."gurus"
    ADD CONSTRAINT "gurus_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."gurus"
    ADD CONSTRAINT "gurus_slug_key" UNIQUE ("slug");



ALTER TABLE ONLY "public"."ingest_jobs"
    ADD CONSTRAINT "ingest_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ingestion_checkpoints"
    ADD CONSTRAINT "ingestion_checkpoints_pkey" PRIMARY KEY ("chunk_id");



ALTER TABLE ONLY "public"."ingestion_runs"
    ADD CONSTRAINT "ingestion_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."kb_chunks"
    ADD CONSTRAINT "kb_chunks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."kb_sources"
    ADD CONSTRAINT "kb_sources_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."meditation_sessions"
    ADD CONSTRAINT "meditation_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."memory_audit_events"
    ADD CONSTRAINT "memory_audit_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."memory_compaction_snapshots"
    ADD CONSTRAINT "memory_compaction_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."memory_consent_receipts"
    ADD CONSTRAINT "memory_consent_receipts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."memory_deletion_receipts"
    ADD CONSTRAINT "memory_deletion_receipts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."memory_outbox"
    ADD CONSTRAINT "memory_outbox_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."model_pricing"
    ADD CONSTRAINT "model_pricing_pkey" PRIMARY KEY ("model");



ALTER TABLE ONLY "public"."notes"
    ADD CONSTRAINT "notes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."okf_review_queue"
    ADD CONSTRAINT "okf_review_queue_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pending_extractions"
    ADD CONSTRAINT "pending_extractions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."prompt_versions"
    ADD CONSTRAINT "prompt_versions_name_version_key" UNIQUE ("name", "version");



ALTER TABLE ONLY "public"."prompt_versions"
    ADD CONSTRAINT "prompt_versions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."push_devices"
    ADD CONSTRAINT "push_devices_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."push_subscriptions"
    ADD CONSTRAINT "push_subscriptions_endpoint_key" UNIQUE ("endpoint");



ALTER TABLE ONLY "public"."push_subscriptions"
    ADD CONSTRAINT "push_subscriptions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."query_clusters"
    ADD CONSTRAINT "query_clusters_pkey" PRIMARY KEY ("query_id");



ALTER TABLE ONLY "public"."retention_events"
    ADD CONSTRAINT "retention_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."retrieval_events"
    ADD CONSTRAINT "retrieval_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."retrieval_feedback_signals"
    ADD CONSTRAINT "retrieval_feedback_signals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."router_decisions"
    ADD CONSTRAINT "router_decisions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."safety_events"
    ADD CONSTRAINT "safety_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."save_offers"
    ADD CONSTRAINT "save_offers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."source_releases"
    ADD CONSTRAINT "source_releases_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."source_releases"
    ADD CONSTRAINT "source_releases_unique_checksum" UNIQUE ("corpus_id", "source_identity", "content_checksum");



ALTER TABLE ONLY "public"."source_releases"
    ADD CONSTRAINT "source_releases_unique_version" UNIQUE ("corpus_id", "source_identity", "release_version");



ALTER TABLE ONLY "public"."staging_quality_queue"
    ADD CONSTRAINT "staging_quality_queue_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."study_notebook_items"
    ADD CONSTRAINT "study_notebook_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."study_notebooks"
    ADD CONSTRAINT "study_notebooks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."telemetry_events"
    ADD CONSTRAINT "telemetry_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."token_usage"
    ADD CONSTRAINT "token_usage_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."trace_spans"
    ADD CONSTRAINT "trace_spans_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."trigger_events"
    ADD CONSTRAINT "trigger_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_brain_edges"
    ADD CONSTRAINT "user_brain_edges_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_brain_keys"
    ADD CONSTRAINT "user_brain_keys_pkey" PRIMARY KEY ("user_id");



ALTER TABLE ONLY "public"."user_brain_nodes"
    ADD CONSTRAINT "user_brain_nodes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_course_progress"
    ADD CONSTRAINT "user_course_progress_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_course_progress"
    ADD CONSTRAINT "user_course_progress_user_id_course_slug_key" UNIQUE ("user_id", "course_slug");



ALTER TABLE ONLY "public"."user_episodes"
    ADD CONSTRAINT "user_episodes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_feedback"
    ADD CONSTRAINT "user_feedback_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_healing_progress"
    ADD CONSTRAINT "user_healing_progress_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_personas"
    ADD CONSTRAINT "user_personas_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_personas"
    ADD CONSTRAINT "user_personas_user_id_tenant_id_key" UNIQUE ("user_id", "tenant_id");



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_pkey" PRIMARY KEY ("user_id");



ALTER TABLE ONLY "public"."user_retention_cards"
    ADD CONSTRAINT "user_retention_cards_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_roles"
    ADD CONSTRAINT "user_roles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_roles"
    ADD CONSTRAINT "user_roles_user_id_role_key" UNIQUE ("user_id", "role");



ALTER TABLE ONLY "public"."user_scene_blocks"
    ADD CONSTRAINT "user_scene_blocks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_scene_blocks"
    ADD CONSTRAINT "user_scene_blocks_user_id_tenant_id_session_id_id_key" UNIQUE ("user_id", "tenant_id", "session_id", "id");



ALTER TABLE ONLY "public"."user_skills"
    ADD CONSTRAINT "user_skills_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_skills"
    ADD CONSTRAINT "user_skills_user_id_tenant_id_name_key" UNIQUE ("user_id", "tenant_id", "name");



ALTER TABLE ONLY "public"."user_streaks"
    ADD CONSTRAINT "user_streaks_pkey" PRIMARY KEY ("user_id");



ALTER TABLE ONLY "public"."waitlist_entries"
    ADD CONSTRAINT "waitlist_entries_email_key_key" UNIQUE ("email_key");



ALTER TABLE ONLY "public"."waitlist_entries"
    ADD CONSTRAINT "waitlist_entries_pkey" PRIMARY KEY ("id");



CREATE INDEX "app_logs_created_at_idx" ON "public"."app_logs" USING "btree" ("created_at" DESC);



CREATE INDEX "assistant_access_assistant_idx" ON "public"."assistant_access" USING "btree" ("assistant_id");



CREATE INDEX "assistant_access_user_assistant_idx" ON "public"."assistant_access" USING "btree" ("user_id", "assistant_id");



CREATE INDEX "assistants_slug_visibility_idx" ON "public"."assistants" USING "btree" ("slug", "visibility");



CREATE INDEX "brain_edges_dst_idx" ON "public"."user_brain_edges" USING "btree" ("dst");



CREATE INDEX "brain_edges_src_idx" ON "public"."user_brain_edges" USING "btree" ("src");



CREATE INDEX "brain_edges_user_idx" ON "public"."user_brain_edges" USING "btree" ("user_id");



CREATE UNIQUE INDEX "brain_nodes_blind_uidx" ON "public"."user_brain_nodes" USING "btree" ("user_id", "blind") WHERE ("blind" IS NOT NULL);



CREATE UNIQUE INDEX "brain_nodes_id_user_uidx" ON "public"."user_brain_nodes" USING "btree" ("id", "user_id");



CREATE INDEX "brain_nodes_kind_idx" ON "public"."user_brain_nodes" USING "btree" ("user_id", "kind");



CREATE INDEX "brain_nodes_user_idx" ON "public"."user_brain_nodes" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "canonical_memory_compaction_snapshots_owner_created_idx" ON "public"."canonical_memory_compaction_snapshots" USING "btree" ("user_id", "tenant_id", "created_at" DESC);



CREATE INDEX "canonical_memory_compaction_snapshots_user_tenant_created_idx" ON "public"."canonical_memory_compaction_snapshots" USING "btree" ("user_id", "tenant_id", "created_at" DESC);



CREATE INDEX "canonical_memory_events_memory_idx" ON "public"."canonical_memory_events" USING "btree" ("memory_id");



CREATE INDEX "canonical_memory_events_user_created_idx" ON "public"."canonical_memory_events" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "canonical_memory_events_user_tenant_created_idx" ON "public"."canonical_memory_events" USING "btree" ("user_id", "tenant_id", "created_at" DESC);



CREATE INDEX "chat_queries_created_at_idx" ON "public"."chat_queries" USING "btree" ("created_at" DESC);



CREATE INDEX "chat_responses_hallucination_flag_created_at_idx" ON "public"."chat_responses" USING "btree" ("hallucination_flag", "created_at" DESC);



CREATE INDEX "chat_sessions_user_created_idx" ON "public"."chat_sessions" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "faculty_answer_labels_created_idx" ON "public"."faculty_answer_labels" USING "btree" ("created_at" DESC);



CREATE UNIQUE INDEX "guru_core_memory_user_tenant_uidx" ON "public"."guru_core_memory" USING "btree" ("user_id", "tenant_id");



CREATE INDEX "guru_memories_active_fact_key_idx" ON "public"."guru_memories" USING "btree" ("user_id", "fact_key") WHERE (("valid_to" IS NULL) AND ("fact_key" IS NOT NULL));



CREATE INDEX "guru_memories_embedding_idx" ON "public"."guru_memories" USING "hnsw" ("embedding" "public"."vector_cosine_ops") WITH ("m"='32', "ef_construction"='200');



CREATE INDEX "guru_memories_hnsw_idx" ON "public"."guru_memories" USING "hnsw" ("embedding" "public"."vector_cosine_ops") WITH ("m"='16', "ef_construction"='64');



CREATE INDEX "guru_memories_user_created_idx" ON "public"."guru_memories" USING "btree" ("user_id", "created_at" DESC);



CREATE UNIQUE INDEX "guru_session_summaries_user_tenant_session_uidx" ON "public"."guru_session_summaries" USING "btree" ("user_id", "tenant_id", "session_id");



CREATE INDEX "guru_summaries_user_created_idx" ON "public"."guru_session_summaries" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_app_logs_level_created" ON "public"."app_logs" USING "btree" ("level", "created_at" DESC);



CREATE INDEX "idx_app_logs_request_id" ON "public"."app_logs" USING "btree" ("request_id");



CREATE INDEX "idx_cancellations_scheduled" ON "public"."cancellations" USING "btree" ("scheduled_deletion");



CREATE INDEX "idx_cancellations_status" ON "public"."cancellations" USING "btree" ("status");



CREATE INDEX "idx_cancellations_user" ON "public"."cancellations" USING "btree" ("user_id");



CREATE UNIQUE INDEX "idx_canonical_memories_active_fact_key" ON "public"."canonical_memories" USING "btree" ("user_id", "tenant_id", "fact_key") WHERE (("fact_key" IS NOT NULL) AND ("status" = 'active'::"text"));



CREATE INDEX "idx_canonical_memories_expires" ON "public"."canonical_memories" USING "btree" ("expires_at") WHERE (("expires_at" IS NOT NULL) AND ("status" = 'active'::"text"));



CREATE INDEX "idx_canonical_memories_type" ON "public"."canonical_memories" USING "btree" ("memory_type");



CREATE INDEX "idx_canonical_memories_updated" ON "public"."canonical_memories" USING "btree" ("updated_at");



CREATE INDEX "idx_canonical_memories_user_id" ON "public"."canonical_memories" USING "btree" ("user_id");



CREATE INDEX "idx_canonical_memories_user_status" ON "public"."canonical_memories" USING "btree" ("user_id", "status");



CREATE INDEX "idx_canonical_memories_user_type_status" ON "public"."canonical_memories" USING "btree" ("user_id", "memory_type", "status");



CREATE INDEX "idx_chat_messages_conv_created" ON "public"."chat_messages" USING "btree" ("conversation_id", "created_at" DESC);



CREATE INDEX "idx_chat_messages_conversation" ON "public"."chat_messages" USING "btree" ("conversation_id");



CREATE INDEX "idx_chat_queries_assistant_slug" ON "public"."chat_queries" USING "btree" ("assistant_slug") WHERE ("assistant_slug" IS NOT NULL);



CREATE INDEX "idx_chat_queries_created_at" ON "public"."chat_queries" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_chat_queries_model_created_at" ON "public"."chat_queries" USING "btree" ("model", "created_at" DESC);



CREATE INDEX "idx_chat_queries_route_created_at" ON "public"."chat_queries" USING "btree" ("route_decision", "created_at" DESC);



CREATE INDEX "idx_chat_queries_session_created" ON "public"."chat_queries" USING "btree" ("session_id", "created_at" DESC);



CREATE INDEX "idx_chat_queries_status_created" ON "public"."chat_queries" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "idx_chat_queries_user_created" ON "public"."chat_queries" USING "btree" ("anon_user_id", "created_at" DESC);



CREATE INDEX "idx_chat_responses_created_at" ON "public"."chat_responses" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_chat_responses_query_created" ON "public"."chat_responses" USING "btree" ("query_id", "created_at" DESC);



CREATE INDEX "idx_chat_responses_query_id" ON "public"."chat_responses" USING "btree" ("query_id");



CREATE INDEX "idx_compaction_snapshots_user_created" ON "public"."memory_compaction_snapshots" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_conversations_retention_created" ON "public"."conversations" USING "btree" ("created_at") WHERE ("retention_days" > 0);



CREATE INDEX "idx_conversations_user" ON "public"."conversations" USING "btree" ("user_id");



CREATE INDEX "idx_corpus_gate_rejections_reason" ON "public"."corpus_gate_rejections" USING "btree" ("reason");



CREATE INDEX "idx_corpus_gate_rejections_source_url_created_at" ON "public"."corpus_gate_rejections" USING "btree" ("source_url", "created_at" DESC);



CREATE INDEX "idx_corpus_sources_corpus_id" ON "public"."corpus_sources" USING "btree" ("corpus_id");



CREATE INDEX "idx_corpus_sources_status_last_ingested_at" ON "public"."corpus_sources" USING "btree" ("status", "last_ingested_at");



CREATE INDEX "idx_exit_surveys_reason" ON "public"."exit_surveys" USING "btree" ("reason");



CREATE INDEX "idx_exit_surveys_user" ON "public"."exit_surveys" USING "btree" ("user_id");



CREATE INDEX "idx_feedback_events_created_at" ON "public"."feedback_events" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_ingest_jobs_created_at" ON "public"."ingest_jobs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_ingest_jobs_idempotency_key" ON "public"."ingest_jobs" USING "btree" ("idempotency_key") WHERE ("idempotency_key" IS NOT NULL);



CREATE INDEX "idx_ingest_jobs_status" ON "public"."ingest_jobs" USING "btree" ("status");



CREATE INDEX "idx_ingest_jobs_status_heartbeat_at" ON "public"."ingest_jobs" USING "btree" ("status", "heartbeat_at");



CREATE INDEX "idx_ingestion_checkpoints_tenant" ON "public"."ingestion_checkpoints" USING "btree" ("tenant_id");



CREATE INDEX "idx_memory_audit_events_memory" ON "public"."memory_audit_events" USING "btree" ("memory_id");



CREATE INDEX "idx_memory_audit_events_user" ON "public"."memory_audit_events" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_memory_consent_receipts_latest" ON "public"."memory_consent_receipts" USING "btree" ("user_id", "tenant_id", "consent_version", "event_sequence" DESC);



CREATE INDEX "idx_memory_consent_receipts_user_tenant" ON "public"."memory_consent_receipts" USING "btree" ("user_id", "tenant_id", "consent_version");



CREATE INDEX "idx_memory_deletion_receipts_user_tenant" ON "public"."memory_deletion_receipts" USING "btree" ("user_id", "tenant_id", "deleted_at" DESC);



CREATE INDEX "idx_memory_outbox_status_created" ON "public"."memory_outbox" USING "btree" ("status", "created_at");



CREATE INDEX "idx_memory_outbox_user_tenant" ON "public"."memory_outbox" USING "btree" ("user_id", "tenant_id", "created_at" DESC);



CREATE INDEX "idx_pending_extractions_status_created" ON "public"."pending_extractions" USING "btree" ("status", "created_at");



CREATE INDEX "idx_push_devices_user_id_active" ON "public"."push_devices" USING "btree" ("user_id", "active");



CREATE INDEX "idx_retrieval_events_query_id" ON "public"."retrieval_events" USING "btree" ("query_id");



CREATE INDEX "idx_retrieval_feedback_signals_query_hash" ON "public"."retrieval_feedback_signals" USING "btree" ("query_hash");



CREATE INDEX "idx_retrieval_feedback_signals_source_url_expires_at" ON "public"."retrieval_feedback_signals" USING "btree" ("source_url", "expires_at");



CREATE INDEX "idx_safety_events_created_at" ON "public"."safety_events" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_safety_events_query_id" ON "public"."safety_events" USING "btree" ("query_id");



CREATE INDEX "idx_save_offers_user" ON "public"."save_offers" USING "btree" ("user_id");



CREATE INDEX "idx_token_usage_created_at" ON "public"."token_usage" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_token_usage_tenant_created" ON "public"."token_usage" USING "btree" ("tenant_id", "created_at" DESC);



CREATE INDEX "idx_token_usage_user_created" ON "public"."token_usage" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_trace_spans_query_id" ON "public"."trace_spans" USING "btree" ("query_id");



CREATE INDEX "idx_trace_spans_span_name" ON "public"."trace_spans" USING "btree" ("span_name");



CREATE INDEX "idx_trigger_events_created" ON "public"."trigger_events" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_trigger_events_name_created_at" ON "public"."trigger_events" USING "btree" ("trigger_name", "created_at" DESC);



CREATE INDEX "idx_trigger_events_query_id" ON "public"."trigger_events" USING "btree" ("query_id");



CREATE UNIQUE INDEX "idx_user_course_progress_one_active" ON "public"."user_course_progress" USING "btree" ("user_id") WHERE ("status" = 'active'::"text");



CREATE INDEX "idx_user_course_progress_user" ON "public"."user_course_progress" USING "btree" ("user_id", "status");



CREATE INDEX "idx_user_feedback_response_created" ON "public"."user_feedback" USING "btree" ("response_id", "created_at" DESC);



CREATE UNIQUE INDEX "idx_user_healing_progress_user_course" ON "public"."user_healing_progress" USING "btree" ("user_id", "course_slug");



CREATE INDEX "idx_user_scene_blocks_session" ON "public"."user_scene_blocks" USING "btree" ("session_id");



CREATE INDEX "idx_user_scene_blocks_user" ON "public"."user_scene_blocks" USING "btree" ("user_id", "tenant_id");



CREATE INDEX "idx_user_skills_user" ON "public"."user_skills" USING "btree" ("user_id", "tenant_id");



CREATE INDEX "kb_chunks_source_idx" ON "public"."kb_chunks" USING "btree" ("source_id");



CREATE INDEX "memory_compaction_snapshots_user_tenant_created_idx" ON "public"."memory_compaction_snapshots" USING "btree" ("user_id", "tenant_id", "created_at" DESC);



CREATE INDEX "notes_user_updated_idx" ON "public"."notes" USING "btree" ("user_id", "updated_at" DESC);



CREATE INDEX "pending_extractions_status_idx" ON "public"."pending_extractions" USING "btree" ("status", "created_at") WHERE ("status" = 'pending'::"text");



CREATE INDEX "pending_extractions_user_tenant_receipt_idx" ON "public"."pending_extractions" USING "btree" ("user_id", "tenant_id", "consent_receipt_id");



CREATE UNIQUE INDEX "push_devices_uq_token" ON "public"."push_devices" USING "btree" ("platform", "token");



CREATE INDEX "push_subscriptions_user_idx" ON "public"."push_subscriptions" USING "btree" ("user_id");



CREATE INDEX "retention_events_event_idx" ON "public"."retention_events" USING "btree" ("event", "created_at" DESC);



CREATE INDEX "retention_events_user_idx" ON "public"."retention_events" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "safety_events_type_created_at_idx" ON "public"."safety_events" USING "btree" ("type", "created_at" DESC);



CREATE INDEX "source_releases_lookup_idx" ON "public"."source_releases" USING "btree" ("corpus_id", "source_identity", "release_version" DESC);



CREATE UNIQUE INDEX "source_releases_one_active_per_source_idx" ON "public"."source_releases" USING "btree" ("corpus_id", "source_identity") WHERE ("status" = 'active'::"text");



CREATE INDEX "source_releases_status_idx" ON "public"."source_releases" USING "btree" ("corpus_id", "status", "created_at" DESC);



CREATE INDEX "study_notebook_items_notebook_created_idx" ON "public"."study_notebook_items" USING "btree" ("notebook_id", "created_at" DESC);



CREATE INDEX "study_notebooks_user_created_idx" ON "public"."study_notebooks" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "telemetry_events_metric_type_created_idx" ON "public"."telemetry_events" USING "btree" ("metric_type", "created_at" DESC);



CREATE INDEX "telemetry_events_session_created_idx" ON "public"."telemetry_events" USING "btree" ("session_id", "created_at" DESC);



CREATE INDEX "telemetry_events_user_id_created_idx" ON "public"."telemetry_events" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "telemetry_events_user_msg_idx" ON "public"."telemetry_events" USING "btree" ("user_message_id");



CREATE INDEX "telemetry_events_user_session_created_idx" ON "public"."telemetry_events" USING "btree" ("user_id", "session_id", "created_at" DESC);



CREATE INDEX "trace_spans_query_id_idx" ON "public"."trace_spans" USING "btree" ("query_id");



CREATE INDEX "trigger_events_trigger_name_created_at_idx" ON "public"."trigger_events" USING "btree" ("trigger_name", "created_at" DESC);



CREATE UNIQUE INDEX "uq_source_releases_identity_checksum" ON "public"."source_releases" USING "btree" ("corpus_id", "source_identity", "content_checksum");



COMMENT ON INDEX "public"."uq_source_releases_identity_checksum" IS 'Prevents duplicate source releases when ingestion retries the same checksum.';



CREATE UNIQUE INDEX "uq_source_releases_one_active" ON "public"."source_releases" USING "btree" ("corpus_id", "source_identity") WHERE ("status" = 'active'::"text");



COMMENT ON INDEX "public"."uq_source_releases_one_active" IS 'Guarantees one active release per corpus/source; activation remains advisory-lock serialized.';



CREATE INDEX "user_brain_keys_user_id_idx" ON "public"."user_brain_keys" USING "btree" ("user_id");



CREATE INDEX "user_brain_nodes_user_current_idx" ON "public"."user_brain_nodes" USING "btree" ("user_id", "created_at" DESC) WHERE ("is_superseded" = false);



CREATE INDEX "user_episodes_user_created_idx" ON "public"."user_episodes" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "user_retention_cards_user_review_idx" ON "public"."user_retention_cards" USING "btree" ("user_id", "next_review_at");



CREATE INDEX "user_streaks_last_active_idx" ON "public"."user_streaks" USING "btree" ("last_active_date" DESC);



CREATE OR REPLACE TRIGGER "assistant_scope_metadata_touch" BEFORE UPDATE ON "public"."assistant_scope_metadata" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "assistants_touch" BEFORE UPDATE ON "public"."assistants" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "doctrine_faqs_touch_updated_at" BEFORE UPDATE ON "public"."doctrine_faqs" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."canonical_memories" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."canonical_memory_compaction_snapshots" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."canonical_memory_events" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."conversation_memories" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."guru_core_memory" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."guru_memories" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."guru_session_summaries" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."memory_audit_events" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."memory_compaction_snapshots" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."memory_outbox" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."pending_extractions" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."user_episodes" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."user_personas" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."user_profiles" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."user_scene_blocks" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "enforce_memory_consent_before_write" BEFORE INSERT OR UPDATE ON "public"."user_skills" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "kb_sources_set_updated_at" BEFORE UPDATE ON "public"."kb_sources" FOR EACH ROW EXECUTE FUNCTION "public"."kb_sources_touch_updated_at"();



CREATE OR REPLACE TRIGGER "notes_touch_updated_at" BEFORE UPDATE ON "public"."notes" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "push_devices_touch" BEFORE UPDATE ON "public"."push_devices" FOR EACH ROW EXECUTE FUNCTION "public"."push_devices_touch_updated_at"();



CREATE OR REPLACE TRIGGER "serialize_memory_consent_receipt_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "public"."memory_consent_receipts" FOR EACH ROW EXECUTE FUNCTION "public"."serialize_memory_consent_receipt_mutation"();



CREATE OR REPLACE TRIGGER "trg_canonical_memories_touch" BEFORE UPDATE ON "public"."canonical_memories" FOR EACH ROW EXECUTE FUNCTION "public"."touch_canonical_memories_updated_at"();



CREATE OR REPLACE TRIGGER "trg_canonical_memory_compaction_snapshots_active_consent" BEFORE INSERT OR UPDATE ON "public"."canonical_memory_compaction_snapshots" FOR EACH ROW EXECUTE FUNCTION "public"."enforce_active_memory_consent_before_write"();



CREATE OR REPLACE TRIGGER "trg_guru_core_touch" BEFORE UPDATE ON "public"."guru_core_memory" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "trg_guru_memories_touch" BEFORE UPDATE ON "public"."guru_memories" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "trg_touch_last_message" AFTER INSERT ON "public"."chat_messages" FOR EACH ROW EXECUTE FUNCTION "public"."touch_user_last_message"();



CREATE OR REPLACE TRIGGER "trg_user_course_progress_updated_at" BEFORE UPDATE ON "public"."user_course_progress" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_user_retention_cards_touch" BEFORE UPDATE ON "public"."user_retention_cards" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "trg_user_streaks_touch" BEFORE UPDATE ON "public"."user_streaks" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();



CREATE OR REPLACE TRIGGER "update_conversations_updated_at" BEFORE UPDATE ON "public"."conversations" FOR EACH ROW EXECUTE FUNCTION "public"."update_conversation_updated_at"();



CREATE OR REPLACE TRIGGER "user_brain_keys_set_updated_at" BEFORE UPDATE ON "public"."user_brain_keys" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



ALTER TABLE ONLY "public"."alert_events"
    ADD CONSTRAINT "alert_events_rule_id_fkey" FOREIGN KEY ("rule_id") REFERENCES "public"."alert_rules"("id");



ALTER TABLE ONLY "public"."annotations"
    ADD CONSTRAINT "annotations_response_id_fkey" FOREIGN KEY ("response_id") REFERENCES "public"."chat_responses"("id");



ALTER TABLE ONLY "public"."assistant_access"
    ADD CONSTRAINT "assistant_access_assistant_id_fkey" FOREIGN KEY ("assistant_id") REFERENCES "public"."assistants"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."assistant_access"
    ADD CONSTRAINT "assistant_access_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."assistant_configurations"
    ADD CONSTRAINT "assistant_configurations_guru_id_fkey" FOREIGN KEY ("guru_id") REFERENCES "public"."gurus"("id");



ALTER TABLE ONLY "public"."assistant_scope_metadata"
    ADD CONSTRAINT "assistant_scope_metadata_assistant_id_fkey" FOREIGN KEY ("assistant_id") REFERENCES "public"."assistants"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."assistants"
    ADD CONSTRAINT "assistants_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cancellations"
    ADD CONSTRAINT "cancellations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."canonical_memories"
    ADD CONSTRAINT "canonical_memories_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."canonical_memory_compaction_snapshots"
    ADD CONSTRAINT "canonical_memory_compaction_snapshots_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."canonical_memory_events"
    ADD CONSTRAINT "canonical_memory_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_messages"
    ADD CONSTRAINT "chat_messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_queries"
    ADD CONSTRAINT "chat_queries_prompt_version_id_fkey" FOREIGN KEY ("prompt_version_id") REFERENCES "public"."prompt_versions"("id");



ALTER TABLE ONLY "public"."chat_queries"
    ADD CONSTRAINT "chat_queries_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."chat_sessions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_responses"
    ADD CONSTRAINT "chat_responses_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversation_memories"
    ADD CONSTRAINT "conversation_memories_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversations"
    ADD CONSTRAINT "conversations_assistant_id_fkey" FOREIGN KEY ("assistant_id") REFERENCES "public"."assistants"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."daily_teachings"
    ADD CONSTRAINT "daily_teachings_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."eval_results"
    ADD CONSTRAINT "eval_results_eval_run_id_fkey" FOREIGN KEY ("eval_run_id") REFERENCES "public"."eval_runs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."eval_results"
    ADD CONSTRAINT "eval_results_golden_id_fkey" FOREIGN KEY ("golden_id") REFERENCES "public"."golden_questions"("id");



ALTER TABLE ONLY "public"."eval_runs"
    ADD CONSTRAINT "eval_runs_prompt_version_id_fkey" FOREIGN KEY ("prompt_version_id") REFERENCES "public"."prompt_versions"("id");



ALTER TABLE ONLY "public"."exit_surveys"
    ADD CONSTRAINT "exit_surveys_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."faculty_answer_labels"
    ADD CONSTRAINT "faculty_answer_labels_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."guru_core_memory"
    ADD CONSTRAINT "guru_core_memory_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."guru_memories"
    ADD CONSTRAINT "guru_memories_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."guru_session_summaries"
    ADD CONSTRAINT "guru_session_summaries_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."kb_chunks"
    ADD CONSTRAINT "kb_chunks_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."kb_sources"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."kb_sources"
    ADD CONSTRAINT "kb_sources_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."meditation_sessions"
    ADD CONSTRAINT "meditation_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_audit_events"
    ADD CONSTRAINT "memory_audit_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_compaction_snapshots"
    ADD CONSTRAINT "memory_compaction_snapshots_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_consent_receipts"
    ADD CONSTRAINT "memory_consent_receipts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_deletion_receipts"
    ADD CONSTRAINT "memory_deletion_receipts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_outbox"
    ADD CONSTRAINT "memory_outbox_consent_receipt_id_fkey" FOREIGN KEY ("consent_receipt_id") REFERENCES "public"."memory_consent_receipts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."memory_outbox"
    ADD CONSTRAINT "memory_outbox_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."notes"
    ADD CONSTRAINT "notes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."pending_extractions"
    ADD CONSTRAINT "pending_extractions_consent_receipt_id_fkey" FOREIGN KEY ("consent_receipt_id") REFERENCES "public"."memory_consent_receipts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."pending_extractions"
    ADD CONSTRAINT "pending_extractions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_last_conversation_id_fkey" FOREIGN KEY ("last_conversation_id") REFERENCES "public"."conversations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_last_message_id_fkey" FOREIGN KEY ("last_message_id") REFERENCES "public"."chat_messages"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."push_devices"
    ADD CONSTRAINT "push_devices_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."push_subscriptions"
    ADD CONSTRAINT "push_subscriptions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."query_clusters"
    ADD CONSTRAINT "query_clusters_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."retention_events"
    ADD CONSTRAINT "retention_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."retrieval_events"
    ADD CONSTRAINT "retrieval_events_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."safety_events"
    ADD CONSTRAINT "safety_events_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."save_offers"
    ADD CONSTRAINT "save_offers_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."staging_quality_queue"
    ADD CONSTRAINT "staging_quality_queue_reviewed_by_fkey" FOREIGN KEY ("reviewed_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."study_notebook_items"
    ADD CONSTRAINT "study_notebook_items_notebook_id_fkey" FOREIGN KEY ("notebook_id") REFERENCES "public"."study_notebooks"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."study_notebook_items"
    ADD CONSTRAINT "study_notebook_items_source_episode_id_fkey" FOREIGN KEY ("source_episode_id") REFERENCES "public"."user_episodes"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."study_notebooks"
    ADD CONSTRAINT "study_notebooks_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."telemetry_events"
    ADD CONSTRAINT "telemetry_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."trace_spans"
    ADD CONSTRAINT "trace_spans_parent_span_id_fkey" FOREIGN KEY ("parent_span_id") REFERENCES "public"."trace_spans"("id");



ALTER TABLE ONLY "public"."trace_spans"
    ADD CONSTRAINT "trace_spans_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."trigger_events"
    ADD CONSTRAINT "trigger_events_query_id_fkey" FOREIGN KEY ("query_id") REFERENCES "public"."chat_queries"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_brain_edges"
    ADD CONSTRAINT "user_brain_edges_dst_fkey" FOREIGN KEY ("dst", "user_id") REFERENCES "public"."user_brain_nodes"("id", "user_id") ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;



ALTER TABLE ONLY "public"."user_brain_edges"
    ADD CONSTRAINT "user_brain_edges_src_fkey" FOREIGN KEY ("src", "user_id") REFERENCES "public"."user_brain_nodes"("id", "user_id") ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;



ALTER TABLE ONLY "public"."user_brain_edges"
    ADD CONSTRAINT "user_brain_edges_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_brain_keys"
    ADD CONSTRAINT "user_brain_keys_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_brain_nodes"
    ADD CONSTRAINT "user_brain_nodes_superseded_by_fkey" FOREIGN KEY ("superseded_by") REFERENCES "public"."user_brain_nodes"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."user_brain_nodes"
    ADD CONSTRAINT "user_brain_nodes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_episodes"
    ADD CONSTRAINT "user_episodes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_feedback"
    ADD CONSTRAINT "user_feedback_response_id_fkey" FOREIGN KEY ("response_id") REFERENCES "public"."chat_responses"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_healing_progress"
    ADD CONSTRAINT "user_healing_progress_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_personas"
    ADD CONSTRAINT "user_personas_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_retention_cards"
    ADD CONSTRAINT "user_retention_cards_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_roles"
    ADD CONSTRAINT "user_roles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_scene_blocks"
    ADD CONSTRAINT "user_scene_blocks_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_skills"
    ADD CONSTRAINT "user_skills_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_streaks"
    ADD CONSTRAINT "user_streaks_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



CREATE POLICY "Active doctrine FAQs are publicly readable" ON "public"."doctrine_faqs" FOR SELECT USING ("is_active");



CREATE POLICY "Admins can delete app settings" ON "public"."app_settings" FOR DELETE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can insert app settings" ON "public"."app_settings" FOR INSERT TO "authenticated" WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can manage assistant_configurations" ON "public"."assistant_configurations" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can manage assistant_doctrines" ON "public"."assistant_doctrines" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can manage gurus" ON "public"."gurus" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read alert_events" ON "public"."alert_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read alert_rules" ON "public"."alert_rules" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read all memories" ON "public"."conversation_memories" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read all profiles" ON "public"."user_profiles" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read annotations" ON "public"."annotations" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read app settings" ON "public"."app_settings" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read app_logs" ON "public"."app_logs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read chat_queries" ON "public"."chat_queries" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read chat_responses" ON "public"."chat_responses" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read chat_sessions" ON "public"."chat_sessions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read eval_results" ON "public"."eval_results" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read eval_runs" ON "public"."eval_runs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read golden_questions" ON "public"."golden_questions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read ingestion_runs" ON "public"."ingestion_runs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read model_pricing" ON "public"."model_pricing" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read prompt_versions" ON "public"."prompt_versions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read query_clusters" ON "public"."query_clusters" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read retrieval_events" ON "public"."retrieval_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read safety_events" ON "public"."safety_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read trace_spans" ON "public"."trace_spans" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read trigger_events" ON "public"."trigger_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read user_feedback" ON "public"."user_feedback" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can read user_roles" ON "public"."user_roles" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins can update app settings" ON "public"."app_settings" FOR UPDATE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins have full access to okf_review_queue" ON "public"."okf_review_queue" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Admins manage doctrine FAQs" ON "public"."doctrine_faqs" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Allow insert for admins only" ON "public"."router_decisions" FOR INSERT TO "authenticated" WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Allow read access to admins only" ON "public"."staging_quality_queue" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Allow select for admins only" ON "public"."router_decisions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Allow write access to admins only" ON "public"."app_settings" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Allow write access to admins only" ON "public"."staging_quality_queue" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "Everyone can view gurus" ON "public"."gurus" FOR SELECT USING (true);



CREATE POLICY "Service role full access on ingest_jobs" ON "public"."ingest_jobs" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access on ingestion_checkpoints" ON "public"."ingestion_checkpoints" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Service role manages compaction snapshots" ON "public"."memory_compaction_snapshots" USING (("auth"."role"() = 'service_role'::"text")) WITH CHECK (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role manages telemetry" ON "public"."telemetry_events" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Users can delete own memory outbox rows" ON "public"."memory_outbox" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own core memory" ON "public"."guru_core_memory" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own memories" ON "public"."guru_memories" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own session summaries" ON "public"."guru_session_summaries" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert own healing progress" ON "public"."user_healing_progress" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own core memory" ON "public"."guru_core_memory" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own memories" ON "public"."conversation_memories" TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own memories" ON "public"."guru_memories" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own session summaries" ON "public"."guru_session_summaries" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can read own memory consent receipts" ON "public"."memory_consent_receipts" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can read own memory deletion receipts" ON "public"."memory_deletion_receipts" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can read own memory outbox rows" ON "public"."memory_outbox" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see their own core memory" ON "public"."guru_core_memory" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see their own memories" ON "public"."conversation_memories" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see their own memories" ON "public"."guru_memories" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see their own profiles" ON "public"."user_profiles" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see their own session summaries" ON "public"."guru_session_summaries" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update own healing progress" ON "public"."user_healing_progress" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own core memory" ON "public"."guru_core_memory" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own memories" ON "public"."guru_memories" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own profiles" ON "public"."user_profiles" FOR UPDATE TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "Users can update their own session summaries" ON "public"."guru_session_summaries" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view own healing progress" ON "public"."user_healing_progress" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own compaction snapshots" ON "public"."memory_compaction_snapshots" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users delete own course progress" ON "public"."user_course_progress" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users insert own course progress" ON "public"."user_course_progress" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users own feedback" ON "public"."feedback_events" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users read own course progress" ON "public"."user_course_progress" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users read their own telemetry" ON "public"."telemetry_events" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users update own course progress" ON "public"."user_course_progress" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "admin_delete" ON "public"."daily_teachings" FOR DELETE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admin_insert" ON "public"."daily_teachings" FOR INSERT TO "authenticated" WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admin_update" ON "public"."daily_teachings" FOR UPDATE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read alert_events" ON "public"."alert_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read alert_rules" ON "public"."alert_rules" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read annotations" ON "public"."annotations" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read app_logs" ON "public"."app_logs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read chat_queries" ON "public"."chat_queries" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read chat_responses" ON "public"."chat_responses" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read eval_results" ON "public"."eval_results" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read eval_runs" ON "public"."eval_runs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read feedback_events" ON "public"."feedback_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read golden_questions" ON "public"."golden_questions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read ingestion_runs" ON "public"."ingestion_runs" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read model_pricing" ON "public"."model_pricing" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read prompt_versions" ON "public"."prompt_versions" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read query_clusters" ON "public"."query_clusters" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read retrieval_events" ON "public"."retrieval_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read safety_events" ON "public"."safety_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read token_usage" ON "public"."token_usage" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read trace_spans" ON "public"."trace_spans" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read trigger_events" ON "public"."trigger_events" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins read user_profiles" ON "public"."user_profiles" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins write alert_rules" ON "public"."alert_rules" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins write annotations" ON "public"."annotations" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins write golden_questions" ON "public"."golden_questions" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins write model_pricing" ON "public"."model_pricing" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins write prompt_versions" ON "public"."prompt_versions" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins_manage_roles_delete" ON "public"."user_roles" FOR DELETE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins_manage_roles_insert" ON "public"."user_roles" FOR INSERT TO "authenticated" WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "admins_manage_roles_update" ON "public"."user_roles" FOR UPDATE TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



ALTER TABLE "public"."alert_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."alert_rules" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."annotations" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "anon_reads_active_daily_teachings" ON "public"."daily_teachings" FOR SELECT TO "anon" USING (("expires_at" > "now"()));



CREATE POLICY "anyone_reads_active" ON "public"."daily_teachings" FOR SELECT TO "authenticated" USING (("expires_at" > "now"()));



ALTER TABLE "public"."app_logs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."app_settings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."assistant_access" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "assistant_access_own_select" ON "public"."assistant_access" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



ALTER TABLE "public"."assistant_configurations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."assistant_doctrines" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."assistant_scope_metadata" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "assistant_scope_metadata_service_role_only" ON "public"."assistant_scope_metadata" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."assistants" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "assistants_delete_own" ON "public"."assistants" FOR DELETE TO "authenticated" USING (("created_by" = "auth"."uid"()));



CREATE POLICY "assistants_insert_own" ON "public"."assistants" FOR INSERT TO "authenticated" WITH CHECK ((("created_by" = "auth"."uid"()) AND (("visibility" <> 'public'::"public"."assistant_visibility") OR "public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"))));



CREATE POLICY "assistants_read_granted" ON "public"."assistants" FOR SELECT TO "authenticated" USING ((("visibility" <> 'public'::"public"."assistant_visibility") AND (EXISTS ( SELECT 1
   FROM "public"."assistant_access" "a"
  WHERE (("a"."assistant_id" = "assistants"."id") AND ("a"."user_id" = "auth"."uid"()))))));



CREATE POLICY "assistants_read_own" ON "public"."assistants" FOR SELECT TO "authenticated" USING (("created_by" = "auth"."uid"()));



CREATE POLICY "assistants_read_public" ON "public"."assistants" FOR SELECT TO "authenticated", "anon" USING (("visibility" = 'public'::"public"."assistant_visibility"));



CREATE POLICY "assistants_update_own" ON "public"."assistants" FOR UPDATE TO "authenticated" USING (("created_by" = "auth"."uid"())) WITH CHECK ((("created_by" = "auth"."uid"()) AND (("visibility" <> 'public'::"public"."assistant_visibility") OR "public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"))));



CREATE POLICY "brain_edges_owner" ON "public"."user_brain_edges" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "brain_keys_owner" ON "public"."user_brain_keys" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "brain_nodes_owner" ON "public"."user_brain_nodes" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."cancellations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."canonical_memories" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."canonical_memory_compaction_snapshots" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "canonical_memory_compaction_snapshots_service_role" ON "public"."canonical_memory_compaction_snapshots" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."canonical_memory_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_messages" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_queries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_responses" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."conversation_memories" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."conversations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."corpus_gate_rejections" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "corpus_gate_rejections_service_role_all" ON "public"."corpus_gate_rejections" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."corpus_sources" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "corpus_sources_service_role_all" ON "public"."corpus_sources" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."daily_teachings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."doctrine_faqs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."eval_results" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."eval_runs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."exit_surveys" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."faculty_answer_labels" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "faculty_labels_delete_own" ON "public"."faculty_answer_labels" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "faculty_labels_insert_own" ON "public"."faculty_answer_labels" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "faculty_labels_select_own" ON "public"."faculty_answer_labels" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "faculty_labels_update_own" ON "public"."faculty_answer_labels" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."feedback_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."golden_questions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."guru_core_memory" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."guru_memories" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."guru_session_summaries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."gurus" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ingest_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ingestion_checkpoints" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ingestion_runs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."kb_chunks" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "kb_chunks_admin_select" ON "public"."kb_chunks" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "kb_chunks_admin_write" ON "public"."kb_chunks" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



ALTER TABLE "public"."kb_sources" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "kb_sources_admin_select" ON "public"."kb_sources" FOR SELECT TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



CREATE POLICY "kb_sources_admin_write" ON "public"."kb_sources" TO "authenticated" USING ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")) WITH CHECK ("public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role"));



ALTER TABLE "public"."meditation_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."memory_audit_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."memory_compaction_snapshots" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."memory_consent_receipts" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "memory_consent_required_insert" ON "public"."canonical_memories" AS RESTRICTIVE FOR INSERT TO "authenticated" WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_insert" ON "public"."guru_core_memory" AS RESTRICTIVE FOR INSERT TO "authenticated" WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_insert" ON "public"."guru_memories" AS RESTRICTIVE FOR INSERT TO "authenticated" WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_insert" ON "public"."guru_session_summaries" AS RESTRICTIVE FOR INSERT TO "authenticated" WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_insert" ON "public"."pending_extractions" AS RESTRICTIVE FOR INSERT TO "authenticated" WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_update" ON "public"."canonical_memories" AS RESTRICTIVE FOR UPDATE TO "authenticated" USING (true) WITH CHECK (("public"."has_active_memory_consent"("user_id", "tenant_id") OR ("status" = 'deleted'::"text")));



CREATE POLICY "memory_consent_required_update" ON "public"."guru_core_memory" AS RESTRICTIVE FOR UPDATE TO "authenticated" USING (true) WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_update" ON "public"."guru_memories" AS RESTRICTIVE FOR UPDATE TO "authenticated" USING (true) WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_update" ON "public"."guru_session_summaries" AS RESTRICTIVE FOR UPDATE TO "authenticated" USING (true) WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



CREATE POLICY "memory_consent_required_update" ON "public"."pending_extractions" AS RESTRICTIVE FOR UPDATE TO "authenticated" USING (true) WITH CHECK ("public"."has_active_memory_consent"("user_id", "tenant_id"));



ALTER TABLE "public"."memory_deletion_receipts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."memory_outbox" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."model_pricing" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."notes" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "notes_own_delete" ON "public"."notes" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "notes_own_insert" ON "public"."notes" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "notes_own_select" ON "public"."notes" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "notes_own_update" ON "public"."notes" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."okf_review_queue" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "own_audit_events_select" ON "public"."memory_audit_events" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memories_delete" ON "public"."canonical_memories" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memories_insert" ON "public"."canonical_memories" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memories_select" ON "public"."canonical_memories" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memories_update" ON "public"."canonical_memories" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memory_compaction_snapshots_select" ON "public"."canonical_memory_compaction_snapshots" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_canonical_memory_events_select" ON "public"."canonical_memory_events" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_chat_sessions_delete" ON "public"."chat_sessions" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_chat_sessions_insert" ON "public"."chat_sessions" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_chat_sessions_select" ON "public"."chat_sessions" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_conversations_delete" ON "public"."conversations" FOR DELETE TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_conversations_insert" ON "public"."conversations" FOR INSERT TO "authenticated" WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_conversations_select" ON "public"."conversations" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_conversations_update" ON "public"."conversations" FOR UPDATE TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_core_memory_delete" ON "public"."guru_core_memory" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_core_memory_insert" ON "public"."guru_core_memory" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_core_memory_select" ON "public"."guru_core_memory" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_core_memory_update" ON "public"."guru_core_memory" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_extractions_insert" ON "public"."pending_extractions" FOR INSERT TO "authenticated" WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_extractions_select" ON "public"."pending_extractions" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_guru_memories_delete" ON "public"."guru_memories" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_guru_memories_insert" ON "public"."guru_memories" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_guru_memories_select" ON "public"."guru_memories" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_guru_memories_update" ON "public"."guru_memories" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_messages_delete" ON "public"."chat_messages" FOR DELETE TO "authenticated" USING (("conversation_id" IN ( SELECT "conversations"."id"
   FROM "public"."conversations"
  WHERE ("conversations"."user_id" = "auth"."uid"()))));



CREATE POLICY "own_messages_insert" ON "public"."chat_messages" FOR INSERT TO "authenticated" WITH CHECK (("conversation_id" IN ( SELECT "conversations"."id"
   FROM "public"."conversations"
  WHERE ("conversations"."user_id" = "auth"."uid"()))));



CREATE POLICY "own_messages_select" ON "public"."chat_messages" FOR SELECT TO "authenticated" USING (("conversation_id" IN ( SELECT "conversations"."id"
   FROM "public"."conversations"
  WHERE ("conversations"."user_id" = "auth"."uid"()))));



CREATE POLICY "own_messages_update" ON "public"."chat_messages" FOR UPDATE TO "authenticated" USING (("conversation_id" IN ( SELECT "c"."id"
   FROM "public"."conversations" "c"
  WHERE ("c"."user_id" = "auth"."uid"())))) WITH CHECK (("conversation_id" IN ( SELECT "c"."id"
   FROM "public"."conversations" "c"
  WHERE ("c"."user_id" = "auth"."uid"()))));



CREATE POLICY "own_profile_insert" ON "public"."profiles" FOR INSERT TO "authenticated" WITH CHECK (("id" = "auth"."uid"()));



CREATE POLICY "own_profile_select" ON "public"."profiles" FOR SELECT TO "authenticated" USING (("id" = "auth"."uid"()));



CREATE POLICY "own_profile_update" ON "public"."profiles" FOR UPDATE TO "authenticated" USING (("id" = "auth"."uid"())) WITH CHECK (("id" = "auth"."uid"()));



CREATE POLICY "own_push_subs_delete" ON "public"."push_subscriptions" FOR DELETE TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_push_subs_insert" ON "public"."push_subscriptions" FOR INSERT TO "authenticated" WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_push_subs_select" ON "public"."push_subscriptions" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_push_subs_update" ON "public"."push_subscriptions" FOR UPDATE TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_retention_cards_delete" ON "public"."user_retention_cards" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_retention_cards_insert" ON "public"."user_retention_cards" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_retention_cards_select" ON "public"."user_retention_cards" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_retention_cards_update" ON "public"."user_retention_cards" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_retention_events_insert" ON "public"."retention_events" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_retention_events_select" ON "public"."retention_events" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_sessions_insert" ON "public"."meditation_sessions" FOR INSERT TO "authenticated" WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_sessions_select" ON "public"."meditation_sessions" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "own_sessions_update" ON "public"."meditation_sessions" FOR UPDATE TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "own_streaks_select" ON "public"."user_streaks" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_summaries_delete" ON "public"."guru_session_summaries" FOR DELETE TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_summaries_insert" ON "public"."guru_session_summaries" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "own_summaries_select" ON "public"."guru_session_summaries" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "own_summaries_update" ON "public"."guru_session_summaries" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "owner_brain_keys" ON "public"."user_brain_keys" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."pending_extractions" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "pending_extractions_self" ON "public"."pending_extractions" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



ALTER TABLE "public"."profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."prompt_versions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."push_devices" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."push_subscriptions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."query_clusters" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."retention_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."retrieval_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."retrieval_feedback_signals" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "retrieval_feedback_signals_service_role_all" ON "public"."retrieval_feedback_signals" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."router_decisions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."safety_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."save_offers" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "self" ON "public"."push_subscriptions" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "service_role manage conversation_memories" ON "public"."conversation_memories" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_role manage token_usage" ON "public"."token_usage" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_role_all" ON "public"."guru_memories" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_role_all_events" ON "public"."retention_events" TO "service_role" USING (true) WITH CHECK (true);



ALTER TABLE "public"."source_releases" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."staging_quality_queue" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."study_notebook_items" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."study_notebooks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."telemetry_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."token_usage" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."trace_spans" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."trigger_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_brain_edges" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_brain_keys" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_brain_nodes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_course_progress" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_episodes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_feedback" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_healing_progress" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_personas" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user_personas_owner_policy" ON "public"."user_personas" TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



ALTER TABLE "public"."user_profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_retention_cards" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_roles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_scene_blocks" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user_scene_blocks_owner_policy" ON "public"."user_scene_blocks" TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



ALTER TABLE "public"."user_skills" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user_skills_owner_policy" ON "public"."user_skills" TO "authenticated" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



ALTER TABLE "public"."user_streaks" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "users delete own notebooks" ON "public"."study_notebooks" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users insert feedback" ON "public"."feedback_events" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users insert own conversation_memories" ON "public"."conversation_memories" FOR INSERT TO "authenticated" WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users insert own episodes" ON "public"."user_episodes" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users insert own items" ON "public"."study_notebook_items" FOR INSERT WITH CHECK ((EXISTS ( SELECT 1
   FROM "public"."study_notebooks" "nb"
  WHERE (("nb"."id" = "study_notebook_items"."notebook_id") AND ("nb"."user_id" = "auth"."uid"())))));



CREATE POLICY "users insert own notebooks" ON "public"."study_notebooks" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users read own chat_queries" ON "public"."chat_queries" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "users read own conversation_memories" ON "public"."conversation_memories" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users read own feedback" ON "public"."feedback_events" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "users select own episodes" ON "public"."user_episodes" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users select own items" ON "public"."study_notebook_items" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."study_notebooks" "nb"
  WHERE (("nb"."id" = "study_notebook_items"."notebook_id") AND ("nb"."user_id" = "auth"."uid"())))));



CREATE POLICY "users select own notebooks" ON "public"."study_notebooks" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_delete_own" ON "public"."push_devices" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_insert_own" ON "public"."cancellations" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users_insert_own" ON "public"."exit_surveys" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users_insert_own" ON "public"."push_devices" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users_insert_own" ON "public"."save_offers" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users_read_own" ON "public"."guru_memories" FOR SELECT TO "authenticated" USING (("user_id" = "auth"."uid"()));



CREATE POLICY "users_read_own_roles" ON "public"."user_roles" FOR SELECT TO "authenticated" USING ((("user_id" = "auth"."uid"()) OR "public"."has_role"("auth"."uid"(), 'admin'::"public"."app_role")));



CREATE POLICY "users_select_own" ON "public"."cancellations" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_select_own" ON "public"."exit_surveys" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_select_own" ON "public"."push_devices" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_select_own" ON "public"."save_offers" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_update_own" ON "public"."cancellations" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_update_own" ON "public"."exit_surveys" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "users_update_own" ON "public"."push_devices" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "users_update_own" ON "public"."save_offers" FOR UPDATE USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."waitlist_entries" ENABLE ROW LEVEL SECURITY;


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON TABLE "public"."source_releases" TO "service_role";



REVOKE ALL ON FUNCTION "public"."activate_source_release"("p_release_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."activate_source_release"("p_release_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."append_healing_step"("p_user_id" "uuid", "p_course_slug" "text", "p_step_id" "text", "p_total_steps" integer) TO "authenticated";



REVOKE ALL ON FUNCTION "public"."approve_source_release"("p_release_id" "uuid", "p_approved_by" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."approve_source_release"("p_release_id" "uuid", "p_approved_by" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."brain_touch"("p_id" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."brain_touch"("p_id" "text") TO "service_role";
GRANT ALL ON FUNCTION "public"."brain_touch"("p_id" "text") TO "authenticated";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_outbox" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_outbox" TO "authenticated";
GRANT ALL ON TABLE "public"."memory_outbox" TO "service_role";



REVOKE ALL ON FUNCTION "public"."claim_memory_outbox"("p_worker_id" "text", "p_limit" integer) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."claim_memory_outbox"("p_worker_id" "text", "p_limit" integer) TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."pending_extractions" TO "anon";
GRANT ALL ON TABLE "public"."pending_extractions" TO "authenticated";
GRANT ALL ON TABLE "public"."pending_extractions" TO "service_role";



REVOKE ALL ON FUNCTION "public"."claim_pending_extractions"("p_worker_id" "text", "p_limit" integer) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."claim_pending_extractions"("p_worker_id" "text", "p_limit" integer) TO "service_role";



REVOKE ALL ON FUNCTION "public"."create_compaction_snapshot"("p_user_id" "uuid", "p_tenant_id" "text", "p_memories_json" "jsonb") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."create_compaction_snapshot"("p_user_id" "uuid", "p_tenant_id" "text", "p_memories_json" "jsonb") TO "service_role";



REVOKE ALL ON FUNCTION "public"."demote_admin_by_id"("_user_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."demote_admin_by_id"("_user_id" "uuid") TO "service_role";
GRANT ALL ON FUNCTION "public"."demote_admin_by_id"("_user_id" "uuid") TO "authenticated";



REVOKE ALL ON FUNCTION "public"."enforce_active_memory_consent_before_write"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."ensure_profile_and_role"() FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."ensure_profile_and_role"() TO "authenticated";



REVOKE ALL ON FUNCTION "public"."grant_admin_for_designated_emails"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."handle_new_user"() FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "service_role";



REVOKE ALL ON FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."has_active_memory_consent"("p_user_id" "uuid", "p_tenant_id" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."has_role"("_user_id" "uuid", "_role" "public"."app_role") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."has_role"("_user_id" "uuid", "_role" "public"."app_role") TO "authenticated";
GRANT ALL ON FUNCTION "public"."has_role"("_user_id" "uuid", "_role" "public"."app_role") TO "service_role";



REVOKE ALL ON FUNCTION "public"."kb_sources_touch_updated_at"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."list_admins"() FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."list_admins"() TO "service_role";
GRANT ALL ON FUNCTION "public"."list_admins"() TO "authenticated";



REVOKE ALL ON FUNCTION "public"."match_user_memories"("p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."match_user_memories"("p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) TO "authenticated";



REVOKE ALL ON FUNCTION "public"."match_user_memories_by_user"("p_user_id" "uuid", "p_tenant_id" "text", "p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."match_user_memories_by_user"("p_user_id" "uuid", "p_tenant_id" "text", "p_query_embedding" "public"."vector", "p_k" integer, "p_min_sim" double precision) TO "service_role";



REVOKE ALL ON FUNCTION "public"."promote_admin_by_email"("_email" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."promote_admin_by_email"("_email" "text") TO "service_role";
GRANT ALL ON FUNCTION "public"."promote_admin_by_email"("_email" "text") TO "authenticated";



REVOKE ALL ON FUNCTION "public"."record_practice"("p_user_id" "uuid", "p_practice_date" "date") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."record_practice"("p_user_id" "uuid", "p_practice_date" "date") TO "service_role";



REVOKE ALL ON FUNCTION "public"."regenerate_summaries"("p_user_id" "uuid", "p_tenant_id" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."regenerate_summaries"("p_user_id" "uuid", "p_tenant_id" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."register_source_release"("p_corpus_id" "text", "p_source_url" "text", "p_source_identity" "text", "p_content_checksum" "text", "p_notes" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."register_source_release"("p_corpus_id" "text", "p_source_url" "text", "p_source_identity" "text", "p_content_checksum" "text", "p_notes" "text") TO "service_role";



REVOKE ALL ON FUNCTION "public"."reject_source_release"("p_release_id" "uuid") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."reject_source_release"("p_release_id" "uuid") TO "service_role";



REVOKE ALL ON FUNCTION "public"."seed_admin_demo"() FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."seed_admin_demo"() TO "service_role";



REVOKE ALL ON FUNCTION "public"."serialize_memory_consent_receipt_mutation"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."set_updated_at"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."touch_updated_at"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."touch_user_last_message"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."update_conversation_updated_at"() FROM PUBLIC;



REVOKE ALL ON FUNCTION "public"."upsert_canonical_memory"("p_user_id" "uuid", "p_tenant_id" "text", "p_memory_type" "text", "p_statement" "text", "p_normalized_statement" "text", "p_fact_key" "text", "p_confidence" real, "p_importance" real, "p_sensitivity" "text", "p_source_conversation_id" "text", "p_source_turn_index" integer, "p_extraction_method" "text", "p_metadata" "jsonb") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."upsert_canonical_memory"("p_user_id" "uuid", "p_tenant_id" "text", "p_memory_type" "text", "p_statement" "text", "p_normalized_statement" "text", "p_fact_key" "text", "p_confidence" real, "p_importance" real, "p_sensitivity" "text", "p_source_conversation_id" "text", "p_source_turn_index" integer, "p_extraction_method" "text", "p_metadata" "jsonb") TO "service_role";



REVOKE ALL ON FUNCTION "public"."whoami_diagnostics"() FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."whoami_diagnostics"() TO "authenticated";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."alert_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."alert_events" TO "authenticated";
GRANT ALL ON TABLE "public"."alert_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."alert_rules" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."alert_rules" TO "authenticated";
GRANT ALL ON TABLE "public"."alert_rules" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."annotations" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."annotations" TO "authenticated";
GRANT ALL ON TABLE "public"."annotations" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."app_logs" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."app_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."app_logs" TO "service_role";



GRANT UPDATE ON SEQUENCE "public"."app_logs_id_seq" TO "anon";
GRANT UPDATE ON SEQUENCE "public"."app_logs_id_seq" TO "authenticated";
GRANT UPDATE ON SEQUENCE "public"."app_logs_id_seq" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."app_settings" TO "anon";
GRANT ALL ON TABLE "public"."app_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."app_settings" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_access" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_access" TO "authenticated";
GRANT ALL ON TABLE "public"."assistant_access" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_configurations" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_configurations" TO "authenticated";
GRANT ALL ON TABLE "public"."assistant_configurations" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_doctrines" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistant_doctrines" TO "authenticated";
GRANT ALL ON TABLE "public"."assistant_doctrines" TO "service_role";



GRANT ALL ON TABLE "public"."assistant_scope_metadata" TO "service_role";



GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."assistants" TO "anon";
GRANT ALL ON TABLE "public"."assistants" TO "authenticated";
GRANT ALL ON TABLE "public"."assistants" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."cancellations" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."cancellations" TO "authenticated";
GRANT ALL ON TABLE "public"."cancellations" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."canonical_memories" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."canonical_memories" TO "authenticated";
GRANT ALL ON TABLE "public"."canonical_memories" TO "service_role";



GRANT ALL ON TABLE "public"."canonical_memory_compaction_snapshots" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."canonical_memory_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."canonical_memory_events" TO "authenticated";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."canonical_memory_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_messages" TO "anon";
GRANT ALL ON TABLE "public"."chat_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_messages" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_queries" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_queries" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_queries" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_responses" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_responses" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_responses" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."chat_sessions" TO "anon";
GRANT ALL ON TABLE "public"."chat_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_sessions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."conversation_memories" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."conversation_memories" TO "authenticated";
GRANT ALL ON TABLE "public"."conversation_memories" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."conversations" TO "anon";
GRANT ALL ON TABLE "public"."conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."conversations" TO "service_role";



GRANT ALL ON TABLE "public"."corpus_gate_rejections" TO "service_role";



GRANT ALL ON TABLE "public"."corpus_sources" TO "service_role";



GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."daily_teachings" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."daily_teachings" TO "authenticated";
GRANT ALL ON TABLE "public"."daily_teachings" TO "service_role";



GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."doctrine_faqs" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."doctrine_faqs" TO "authenticated";
GRANT ALL ON TABLE "public"."doctrine_faqs" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."eval_results" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."eval_results" TO "authenticated";
GRANT ALL ON TABLE "public"."eval_results" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."eval_runs" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."eval_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."eval_runs" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."exit_surveys" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."exit_surveys" TO "authenticated";
GRANT ALL ON TABLE "public"."exit_surveys" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."faculty_answer_labels" TO "anon";
GRANT ALL ON TABLE "public"."faculty_answer_labels" TO "authenticated";
GRANT ALL ON TABLE "public"."faculty_answer_labels" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."feedback_events" TO "anon";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."feedback_events" TO "authenticated";
GRANT ALL ON TABLE "public"."feedback_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."golden_questions" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."golden_questions" TO "authenticated";
GRANT ALL ON TABLE "public"."golden_questions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."guru_core_memory" TO "anon";
GRANT ALL ON TABLE "public"."guru_core_memory" TO "authenticated";
GRANT ALL ON TABLE "public"."guru_core_memory" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."guru_memories" TO "anon";
GRANT ALL ON TABLE "public"."guru_memories" TO "authenticated";
GRANT ALL ON TABLE "public"."guru_memories" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."guru_session_summaries" TO "anon";
GRANT ALL ON TABLE "public"."guru_session_summaries" TO "authenticated";
GRANT ALL ON TABLE "public"."guru_session_summaries" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."gurus" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."gurus" TO "authenticated";
GRANT ALL ON TABLE "public"."gurus" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingest_jobs" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingest_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."ingest_jobs" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingestion_checkpoints" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingestion_checkpoints" TO "authenticated";
GRANT ALL ON TABLE "public"."ingestion_checkpoints" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingestion_runs" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."ingestion_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."ingestion_runs" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."kb_chunks" TO "anon";
GRANT ALL ON TABLE "public"."kb_chunks" TO "authenticated";
GRANT ALL ON TABLE "public"."kb_chunks" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."kb_sources" TO "anon";
GRANT ALL ON TABLE "public"."kb_sources" TO "authenticated";
GRANT ALL ON TABLE "public"."kb_sources" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."meditation_sessions" TO "anon";
GRANT ALL ON TABLE "public"."meditation_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."meditation_sessions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_audit_events" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_audit_events" TO "authenticated";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_audit_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_compaction_snapshots" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_compaction_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."memory_compaction_snapshots" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_consent_receipts" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_consent_receipts" TO "authenticated";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN,UPDATE ON TABLE "public"."memory_consent_receipts" TO "service_role";



GRANT UPDATE ON SEQUENCE "public"."memory_consent_receipts_event_sequence_seq" TO "anon";
GRANT UPDATE ON SEQUENCE "public"."memory_consent_receipts_event_sequence_seq" TO "authenticated";
GRANT UPDATE ON SEQUENCE "public"."memory_consent_receipts_event_sequence_seq" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_deletion_receipts" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_deletion_receipts" TO "authenticated";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."memory_deletion_receipts" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."model_pricing" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."model_pricing" TO "authenticated";
GRANT ALL ON TABLE "public"."model_pricing" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."notes" TO "anon";
GRANT ALL ON TABLE "public"."notes" TO "authenticated";
GRANT ALL ON TABLE "public"."notes" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."okf_review_queue" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."okf_review_queue" TO "authenticated";
GRANT ALL ON TABLE "public"."okf_review_queue" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."profiles" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."prompt_versions" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."prompt_versions" TO "authenticated";
GRANT ALL ON TABLE "public"."prompt_versions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."push_devices" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."push_devices" TO "authenticated";
GRANT ALL ON TABLE "public"."push_devices" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."push_subscriptions" TO "anon";
GRANT ALL ON TABLE "public"."push_subscriptions" TO "authenticated";
GRANT ALL ON TABLE "public"."push_subscriptions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."query_clusters" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."query_clusters" TO "authenticated";
GRANT ALL ON TABLE "public"."query_clusters" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."retention_events" TO "anon";
GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."retention_events" TO "authenticated";
GRANT ALL ON TABLE "public"."retention_events" TO "service_role";



GRANT UPDATE ON SEQUENCE "public"."retention_events_id_seq" TO "anon";
GRANT UPDATE ON SEQUENCE "public"."retention_events_id_seq" TO "authenticated";
GRANT UPDATE ON SEQUENCE "public"."retention_events_id_seq" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."retrieval_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."retrieval_events" TO "authenticated";
GRANT ALL ON TABLE "public"."retrieval_events" TO "service_role";



GRANT ALL ON TABLE "public"."retrieval_feedback_signals" TO "service_role";



GRANT ALL ON TABLE "public"."router_decisions" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."safety_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."safety_events" TO "authenticated";
GRANT ALL ON TABLE "public"."safety_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."save_offers" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."save_offers" TO "authenticated";
GRANT ALL ON TABLE "public"."save_offers" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."staging_quality_queue" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."staging_quality_queue" TO "authenticated";
GRANT ALL ON TABLE "public"."staging_quality_queue" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."study_notebook_items" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."study_notebook_items" TO "authenticated";
GRANT ALL ON TABLE "public"."study_notebook_items" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."study_notebooks" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."study_notebooks" TO "authenticated";
GRANT ALL ON TABLE "public"."study_notebooks" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."telemetry_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."telemetry_events" TO "authenticated";
GRANT ALL ON TABLE "public"."telemetry_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."token_usage" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."token_usage" TO "authenticated";
GRANT ALL ON TABLE "public"."token_usage" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."trace_spans" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."trace_spans" TO "authenticated";
GRANT ALL ON TABLE "public"."trace_spans" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."trigger_events" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."trigger_events" TO "authenticated";
GRANT ALL ON TABLE "public"."trigger_events" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_brain_edges" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_brain_edges" TO "authenticated";
GRANT ALL ON TABLE "public"."user_brain_edges" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_brain_keys" TO "anon";
GRANT ALL ON TABLE "public"."user_brain_keys" TO "authenticated";
GRANT ALL ON TABLE "public"."user_brain_keys" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_brain_nodes" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_brain_nodes" TO "authenticated";
GRANT ALL ON TABLE "public"."user_brain_nodes" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_course_progress" TO "anon";
GRANT ALL ON TABLE "public"."user_course_progress" TO "authenticated";
GRANT ALL ON TABLE "public"."user_course_progress" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_episodes" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_episodes" TO "authenticated";
GRANT ALL ON TABLE "public"."user_episodes" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_feedback" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_feedback" TO "authenticated";
GRANT ALL ON TABLE "public"."user_feedback" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_healing_progress" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_healing_progress" TO "authenticated";
GRANT ALL ON TABLE "public"."user_healing_progress" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_personas" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_personas" TO "authenticated";
GRANT ALL ON TABLE "public"."user_personas" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_profiles" TO "anon";
GRANT ALL ON TABLE "public"."user_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."user_profiles" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_retention_cards" TO "anon";
GRANT ALL ON TABLE "public"."user_retention_cards" TO "authenticated";
GRANT ALL ON TABLE "public"."user_retention_cards" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_roles" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_roles" TO "authenticated";
GRANT ALL ON TABLE "public"."user_roles" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_scene_blocks" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_scene_blocks" TO "authenticated";
GRANT ALL ON TABLE "public"."user_scene_blocks" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_skills" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_skills" TO "authenticated";
GRANT ALL ON TABLE "public"."user_skills" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_streaks" TO "anon";
GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."user_streaks" TO "authenticated";
GRANT ALL ON TABLE "public"."user_streaks" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_chat_queries_by_assistant" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_chat_queries_by_assistant" TO "authenticated";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_chat_queries_by_assistant" TO "service_role";



GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_meditation_heatmap" TO "anon";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_meditation_heatmap" TO "authenticated";
GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."v_meditation_heatmap" TO "service_role";



GRANT ALL ON TABLE "public"."waitlist_entries" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT UPDATE ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT UPDATE ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT UPDATE ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLES TO "service_role";







