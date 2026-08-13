-- Controlled rollback: a superseded, already-audited source release may return
-- to approved status only through an explicit service-role re-approval. It must
-- then traverse the existing activate_source_release transaction, which
-- atomically supersedes the currently active peer release.
CREATE OR REPLACE FUNCTION public.approve_source_release(p_release_id uuid, p_approved_by text)
RETURNS public.source_releases
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
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
REVOKE ALL ON FUNCTION public.approve_source_release(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.approve_source_release(uuid, text) TO service_role;
