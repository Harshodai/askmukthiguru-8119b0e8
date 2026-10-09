-- Faculty answer labels: reviewer judgements on individual answers, kept as
-- labelled data for evals/calibration. Distinct from feedback_events (seeker
-- thumbs): a label carries faithful / safe / helpful ratings plus the trace,
-- model and policy identifiers needed to join it back to the answer served.
--
-- Access model: owner-scoped RLS (auth.uid() = user_id) for authenticated
-- users; service_role gets table GRANTs because Postgres checks grants BEFORE
-- RLS (see CLAUDE.md "Canonical memory", defect 2) and the export script
-- (backend/scripts/ops/export_faculty_labels.py) reads with service_role.
-- anon gets nothing.
--
-- ponytail: the guarded auth/role stubs below exist only so this file applies
-- in migration-revert-check.yml's empty ephemeral Postgres (L-MIGRATE-EPHEMERAL-1).
-- On Supabase they all already exist and every stub is a no-op. Do not remove.

-- Guarded by to_regclass: even with IF NOT EXISTS, Postgres checks CREATE on
-- the schema first, so an unconditional CREATE TABLE auth.users fails with
-- "permission denied for schema auth" on a real Supabase (found by the local
-- Supabase run in prelaunch-gate.yml, 2026-10-09).
DO $authstub$
BEGIN
  IF to_regclass('auth.users') IS NULL THEN
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE TABLE auth.users (id uuid PRIMARY KEY);
  END IF;
END
$authstub$;

DO $stub$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'auth' AND p.proname = 'uid'
  ) THEN
    EXECUTE $f$CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
      AS 'SELECT NULLIF(current_setting(''request.jwt.claim.sub'', true), '''')::uuid'$f$;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END
$stub$;

CREATE TABLE IF NOT EXISTS public.faculty_answer_labels (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  trace_id    text,
  request_id  text,
  -- The key an answer is labelled under; one label per (reviewer, answer).
  answer_key  text GENERATED ALWAYS AS (COALESCE(trace_id, request_id)) STORED,
  message_id  text,
  model       text,
  policy_id   text,
  release_id  text,
  faithful    text NOT NULL CHECK (faithful IN ('yes', 'partly', 'no')),
  safe        boolean NOT NULL,
  helpful     smallint NOT NULL CHECK (helpful BETWEEN 1 AND 5),
  note        text CHECK (note IS NULL OR char_length(note) <= 2000),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT faculty_answer_labels_has_answer_key
    CHECK (trace_id IS NOT NULL OR request_id IS NOT NULL),
  CONSTRAINT faculty_answer_labels_one_per_reviewer UNIQUE (user_id, answer_key)
);

CREATE INDEX IF NOT EXISTS faculty_answer_labels_created_idx
  ON public.faculty_answer_labels (created_at DESC);

ALTER TABLE public.faculty_answer_labels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS faculty_labels_select_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_select_own ON public.faculty_answer_labels
  FOR SELECT TO authenticated USING (auth.uid() = user_id);

DROP POLICY IF EXISTS faculty_labels_insert_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_insert_own ON public.faculty_answer_labels
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS faculty_labels_update_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_update_own ON public.faculty_answer_labels
  FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS faculty_labels_delete_own ON public.faculty_answer_labels;
CREATE POLICY faculty_labels_delete_own ON public.faculty_answer_labels
  FOR DELETE TO authenticated USING (auth.uid() = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.faculty_answer_labels TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.faculty_answer_labels TO service_role;

NOTIFY pgrst, 'reload schema';

-- REVERT: Drop public.faculty_answer_labels (policies, index and grants go with it)
-- DROP TABLE IF EXISTS public.faculty_answer_labels;
-- NOTIFY pgrst, 'reload schema';
