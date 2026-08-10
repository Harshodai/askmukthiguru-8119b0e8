-- ============================================================================
-- REVERT: Restore the pre-migration owner-only policies (any authenticated user may
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- publish public assistants again — only revert deliberately).
-- DROP POLICY IF EXISTS assistants_insert_own ON public.assistants;
-- CREATE POLICY assistants_insert_own ON public.assistants
--   FOR INSERT TO authenticated WITH CHECK (created_by = auth.uid());
-- DROP POLICY IF EXISTS assistants_update_own ON public.assistants;
-- CREATE POLICY assistants_update_own ON public.assistants
--   FOR UPDATE TO authenticated USING (created_by = auth.uid());
-- ============================================================================


-- Restrict public assistant publishing to admins only
DROP POLICY IF EXISTS assistants_insert_own ON public.assistants;
CREATE POLICY assistants_insert_own ON public.assistants
  FOR INSERT
  TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND (visibility <> 'public'::assistant_visibility OR public.has_role(auth.uid(), 'admin'::public.app_role))
  );

DROP POLICY IF EXISTS assistants_update_own ON public.assistants;
CREATE POLICY assistants_update_own ON public.assistants
  FOR UPDATE
  TO authenticated
  USING (created_by = auth.uid())
  WITH CHECK (
    created_by = auth.uid()
    AND (visibility <> 'public'::assistant_visibility OR public.has_role(auth.uid(), 'admin'::public.app_role))
  );
