-- Faculty labels are evaluation data, not a seeker feedback channel.  The
-- original owner-only policies prevented cross-reviewer reads but allowed any
-- authenticated account to create a row for itself.  Require a role minted in
-- the signed JWT's app_metadata as well.  user_metadata is deliberately not
-- consulted: users can edit it themselves.
--
-- Provisioning: set app_metadata.role = "faculty_reviewer" through the
-- Supabase admin API for a named, consented reviewer. Teachers and volunteers
-- do not receive this role by default. RLS remains the authority; the frontend
-- check is only an early visibility guard.

DROP POLICY IF EXISTS faculty_labels_select_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_select_own ON public.faculty_answer_labels
  FOR SELECT TO authenticated
  USING (
    auth.uid() = user_id
    AND COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
  );

DROP POLICY IF EXISTS faculty_labels_insert_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_insert_own ON public.faculty_answer_labels
  FOR INSERT TO authenticated
  WITH CHECK (
    auth.uid() = user_id
    AND COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
  );

DROP POLICY IF EXISTS faculty_labels_update_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_update_own ON public.faculty_answer_labels
  FOR UPDATE TO authenticated
  USING (
    auth.uid() = user_id
    AND COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
  )
  WITH CHECK (
    auth.uid() = user_id
    AND COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
  );

DROP POLICY IF EXISTS faculty_labels_delete_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_delete_own ON public.faculty_answer_labels
  FOR DELETE TO authenticated
  USING (
    auth.uid() = user_id
    AND COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
  );

NOTIFY pgrst, 'reload schema';

-- REVERT: restore the owner-only policies from
-- 20261007000000_faculty_answer_labels.sql, then reload PostgREST schema.
