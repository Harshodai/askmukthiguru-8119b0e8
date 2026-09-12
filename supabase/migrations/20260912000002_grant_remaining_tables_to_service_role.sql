-- Grant the remaining application tables to service_role.
--
-- Companion to 20260912000001. A survey of a database built purely from this
-- migration set found 22 tables the backend's own role could not read: Postgres
-- checks GRANTS before RLS, so correct policies do not help a role with no
-- table privilege. The failures are quiet — `user_roles` denied means every
-- admin check logs "Admin role check failed" and falls through to non-admin,
-- and `profiles` / `user_healing_progress` / `ingest_jobs` fail the same way.
--
-- RLS continues to govern what anon and authenticated can see. This grants only
-- the server role the table-level privileges its policies already assume.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.assistant_configurations TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.assistant_doctrines TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cancellations TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.exit_surveys TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.gurus TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_jobs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingestion_checkpoints TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.okf_review_queue TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.push_devices TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.save_offers TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.study_notebook_items TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.study_notebooks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_brain_edges TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_brain_nodes TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_episodes TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_feedback TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_healing_progress TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_personas TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_roles TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_scene_blocks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_skills TO service_role;
