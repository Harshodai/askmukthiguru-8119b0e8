-- Owner decision 2026-11-28: do not over-engineer faculty roles.  An authorised
-- admin (the repo's existing mechanism: a 'admin' row in public.user_roles,
-- checked through public.has_role) may use the faculty labelling panel without
-- the owner hand-editing app_metadata for every reviewer.  A reviewer holding
-- the signed app_metadata.role = 'faculty_reviewer' claim still passes.
-- Row scoping is unchanged: auth.uid() = user_id on every command, so nobody
-- (admin included) reads or writes another reviewer's labels, and an ordinary
-- signed-in user or anon still fails.  user_metadata is never consulted.
-- Supersedes the policies in 20261122000000_faculty_labels_reviewer_role.sql.

DROP POLICY IF EXISTS faculty_labels_select_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_select_own ON public.faculty_answer_labels
  FOR SELECT TO authenticated
  USING (
    auth.uid() = user_id
    AND (
      COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
      OR public.has_role(auth.uid(), 'admin'::public.app_role)
    )
  );

DROP POLICY IF EXISTS faculty_labels_insert_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_insert_own ON public.faculty_answer_labels
  FOR INSERT TO authenticated
  WITH CHECK (
    auth.uid() = user_id
    AND (
      COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
      OR public.has_role(auth.uid(), 'admin'::public.app_role)
    )
  );

DROP POLICY IF EXISTS faculty_labels_update_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_update_own ON public.faculty_answer_labels
  FOR UPDATE TO authenticated
  USING (
    auth.uid() = user_id
    AND (
      COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
      OR public.has_role(auth.uid(), 'admin'::public.app_role)
    )
  )
  WITH CHECK (
    auth.uid() = user_id
    AND (
      COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
      OR public.has_role(auth.uid(), 'admin'::public.app_role)
    )
  );

DROP POLICY IF EXISTS faculty_labels_delete_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_delete_own ON public.faculty_answer_labels
  FOR DELETE TO authenticated
  USING (
    auth.uid() = user_id
    AND (
      COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer'
      OR public.has_role(auth.uid(), 'admin'::public.app_role)
    )
  );

NOTIFY pgrst, 'reload schema';

-- REVERT: re-run the policies from 20261122000000_faculty_labels_reviewer_role.sql,
-- then reload the PostgREST schema.
