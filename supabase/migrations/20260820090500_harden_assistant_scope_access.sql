-- Harden and accelerate server-only assistant authorization lookups.
CREATE INDEX IF NOT EXISTS assistant_access_user_assistant_idx
  ON public.assistant_access (user_id, assistant_id);
CREATE INDEX IF NOT EXISTS assistant_access_assistant_idx
  ON public.assistant_access (assistant_id);
CREATE INDEX IF NOT EXISTS assistants_slug_visibility_idx
  ON public.assistants (slug, visibility);

DROP POLICY IF EXISTS assistant_scope_metadata_service_role_only ON public.assistant_scope_metadata;
CREATE POLICY assistant_scope_metadata_service_role_only
  ON public.assistant_scope_metadata
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
