-- ============================================================================
-- REVERT: Regression-hardening only: PostgreSQL already defaults WITH CHECK to USING,
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- so behavior is identical before/after. To restore the pre-migration catalog
-- state, recreate each affected policy WITHOUT the explicit WITH CHECK clause —
-- the USING predicates are unchanged (pattern below for one policy; the rest
-- follow the same drop+create). Guarded blocks (digital_employees,
-- communications) were no-ops.
-- DROP POLICY IF EXISTS tenant_isolation ON public.chat_queries;
-- CREATE POLICY tenant_isolation ON public.chat_queries
--   FOR ALL TO authenticated
--   USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');
-- ============================================================================

-- CRIT-2 (reclassified P1 defense-in-depth): explicit WITH CHECK on FOR ALL policies.
--
-- Empirically verified 2026-08-04 that PostgreSQL defaults WITH CHECK to the
-- USING expression when WITH CHECK is omitted, so cross-user INSERT / owner-
-- transfer UPDATE are ALREADY blocked. This migration is therefore
-- regression-hardening, not a live-vulnerability fix: it makes the intended
-- predicate explicit in the catalog (pg_policy.polwithcheck) so future
-- policy edits cannot silently widen the write surface.
--
-- Pattern per table: DROP POLICY IF EXISTS + CREATE POLICY with the SAME name
-- and predicate, adding an explicit WITH CHECK mirroring USING. Idempotent —
-- safe to run on a fresh DB and to re-apply.
--
-- Tables that may not exist in a given environment (digital_employees,
-- communications) are guarded. Tables whose FOR ALL policy was already given
-- an explicit WITH CHECK by migration 20260730000000 (conversations,
-- chat_messages, meditation_sessions, user_profiles) are NOT touched here.

-- ============ Tenant tables (20260627130000_tenant_rls.sql) ============
-- Policy: tenant_isolation, FOR ALL TO authenticated, no WITH CHECK.
-- Predicate: tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id'
DROP POLICY IF EXISTS tenant_isolation ON public.chat_queries;
CREATE POLICY tenant_isolation ON public.chat_queries
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

DROP POLICY IF EXISTS tenant_isolation ON public.chat_responses;
CREATE POLICY tenant_isolation ON public.chat_responses
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

DROP POLICY IF EXISTS tenant_isolation ON public.retrieval_events;
CREATE POLICY tenant_isolation ON public.retrieval_events
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

DROP POLICY IF EXISTS tenant_isolation ON public.guru_core_memory;
CREATE POLICY tenant_isolation ON public.guru_core_memory
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- guru_memories has separate own_* INSERT/UPDATE policies WITH CHECK from
-- 20260618044620; only the tenant_isolation FOR ALL policy is hardened here.
DROP POLICY IF EXISTS tenant_isolation ON public.guru_memories;
CREATE POLICY tenant_isolation ON public.guru_memories
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

DROP POLICY IF EXISTS tenant_isolation ON public.guru_session_summaries;
CREATE POLICY tenant_isolation ON public.guru_session_summaries
  FOR ALL TO authenticated
  USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
  WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');

-- ============ conversation_memories (20260516190000_user_memory.sql) ============
-- Policy: "Users can insert their own memories", FOR ALL, USING (auth.uid() = user_id).
DROP POLICY IF EXISTS "Users can insert their own memories" ON public.conversation_memories;
CREATE POLICY "Users can insert their own memories" ON public.conversation_memories
  FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ============ user_personas (20260728000000_create_user_personas.sql) ============
DROP POLICY IF EXISTS user_personas_owner_policy ON public.user_personas;
CREATE POLICY user_personas_owner_policy ON public.user_personas
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============ user_scene_blocks / user_skills (20260729000000) ============
DROP POLICY IF EXISTS user_scene_blocks_owner_policy ON public.user_scene_blocks;
CREATE POLICY user_scene_blocks_owner_policy ON public.user_scene_blocks
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS user_skills_owner_policy ON public.user_skills;
CREATE POLICY user_skills_owner_policy ON public.user_skills
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============ push_devices UPDATE (20260713000000_create_push_devices.sql) ============
DROP POLICY IF EXISTS users_update_own ON public.push_devices;
CREATE POLICY users_update_own ON public.push_devices
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ============ 4 admin FOR ALL policies (20260711000000_enable_rls_on_all_tables.sql) ============
-- Predicate: public.has_role(auth.uid(), 'admin'::public.app_role). There is
-- no admin_users table; has_role is the single admin gate.
DROP POLICY IF EXISTS "Admins can manage gurus" ON public.gurus;
CREATE POLICY "Admins can manage gurus" ON public.gurus
  FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

DROP POLICY IF EXISTS "Admins can manage assistant_configurations" ON public.assistant_configurations;
CREATE POLICY "Admins can manage assistant_configurations" ON public.assistant_configurations
  FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

DROP POLICY IF EXISTS "Admins can manage assistant_doctrines" ON public.assistant_doctrines;
CREATE POLICY "Admins can manage assistant_doctrines" ON public.assistant_doctrines
  FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ============ digital_employees UPDATE (guarded — table created conditionally) ============
-- digital_employees has no CREATE migration in this repo; RLS is enabled
-- conditionally by 20260711000000. Guard so a fresh DB (where the table is
-- absent) applies cleanly.
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'digital_employees') THEN
    DROP POLICY IF EXISTS "Users can update own digital_employees" ON public.digital_employees;
    CREATE POLICY "Users can update own digital_employees" ON public.digital_employees
      FOR UPDATE TO authenticated
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

-- ============ communications admin FOR ALL (guarded — table created conditionally) ============
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'communications') THEN
    DROP POLICY IF EXISTS "Admins can manage communications" ON public.communications;
    CREATE POLICY "Admins can manage communications" ON public.communications
      FOR ALL TO authenticated
      USING (public.has_role(auth.uid(), 'admin'::public.app_role))
      WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));
  END IF;
END $$;

-- Reload PostgREST schema cache (PGRST204 pattern) so new policy predicates
-- take effect immediately.
NOTIFY pgrst, 'reload schema';
