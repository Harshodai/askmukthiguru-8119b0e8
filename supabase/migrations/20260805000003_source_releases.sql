-- Governed, versioned source releases for auditable corpus publication.
CREATE TABLE IF NOT EXISTS public.source_releases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    corpus_id text NOT NULL,
    source_url text NOT NULL,
    source_identity text NOT NULL,
    release_version integer NOT NULL,
    content_checksum text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    approved_by text,
    approved_at timestamptz,
    activated_at timestamptz,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_releases_status_check CHECK (status IN ('pending', 'approved', 'active', 'superseded', 'rejected')),
    CONSTRAINT source_releases_version_positive CHECK (release_version > 0),
    CONSTRAINT source_releases_corpus_nonempty CHECK (length(trim(corpus_id)) > 0),
    CONSTRAINT source_releases_identity_nonempty CHECK (length(trim(source_identity)) > 0),
    CONSTRAINT source_releases_checksum_nonempty CHECK (length(trim(content_checksum)) > 0),
    CONSTRAINT source_releases_notes_length CHECK (notes IS NULL OR char_length(notes) <= 1000),
    CONSTRAINT source_releases_approval_audit_check CHECK (
        (status IN ('approved', 'active', 'superseded') AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR status IN ('pending', 'rejected')
    ),
    CONSTRAINT source_releases_unique_version UNIQUE (corpus_id, source_identity, release_version),
    CONSTRAINT source_releases_unique_checksum UNIQUE (corpus_id, source_identity, content_checksum)
);

CREATE INDEX IF NOT EXISTS source_releases_lookup_idx
    ON public.source_releases (corpus_id, source_identity, release_version DESC);
CREATE INDEX IF NOT EXISTS source_releases_status_idx
    ON public.source_releases (corpus_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS source_releases_one_active_per_source_idx
    ON public.source_releases (corpus_id, source_identity) WHERE status = 'active';

ALTER TABLE public.source_releases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.source_releases FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.source_releases TO service_role;

CREATE OR REPLACE FUNCTION public.register_source_release(
    p_corpus_id text, p_source_url text, p_source_identity text,
    p_content_checksum text, p_notes text DEFAULT NULL
)
RETURNS public.source_releases
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
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

CREATE OR REPLACE FUNCTION public.approve_source_release(p_release_id uuid, p_approved_by text)
RETURNS public.source_releases
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE approved_release public.source_releases;
BEGIN
    IF length(trim(p_approved_by)) = 0 THEN
        RAISE EXCEPTION 'approved_by is required' USING ERRCODE = '22023';
    END IF;
    UPDATE public.source_releases SET status = 'approved', approved_by = trim(p_approved_by), approved_at = now()
      WHERE id = p_release_id AND status = 'pending' RETURNING * INTO approved_release;
    IF NOT FOUND THEN RAISE EXCEPTION 'release is not pending or does not exist' USING ERRCODE = 'P0001'; END IF;
    RETURN approved_release;
END;
$$;

CREATE OR REPLACE FUNCTION public.activate_source_release(p_release_id uuid)
RETURNS public.source_releases
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
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

CREATE OR REPLACE FUNCTION public.reject_source_release(p_release_id uuid)
RETURNS public.source_releases
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE rejected_release public.source_releases;
BEGIN
    UPDATE public.source_releases SET status = 'rejected'
      WHERE id = p_release_id AND status IN ('pending', 'approved') RETURNING * INTO rejected_release;
    IF NOT FOUND THEN RAISE EXCEPTION 'only pending or approved releases may be rejected' USING ERRCODE = 'P0001'; END IF;
    RETURN rejected_release;
END;
$$;

REVOKE ALL ON FUNCTION public.register_source_release(text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.approve_source_release(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.activate_source_release(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reject_source_release(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.register_source_release(text, text, text, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.approve_source_release(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.activate_source_release(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.reject_source_release(uuid) TO service_role;
