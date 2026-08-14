DROP POLICY IF EXISTS tenant_isolation ON public.chat_queries;
DROP POLICY IF EXISTS tenant_isolation ON public.chat_responses;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_core_memory;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_memories;
DROP POLICY IF EXISTS tenant_isolation ON public.guru_session_summaries;
DROP POLICY IF EXISTS tenant_isolation ON public.retrieval_events;

DROP POLICY IF EXISTS "read_all" ON public.app_settings;
DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
CREATE POLICY "Authenticated users can read app settings"
ON public.app_settings FOR SELECT TO authenticated USING (true);
REVOKE SELECT ON public.app_settings FROM anon;