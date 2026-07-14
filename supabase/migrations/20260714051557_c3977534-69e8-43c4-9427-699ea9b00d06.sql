
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
