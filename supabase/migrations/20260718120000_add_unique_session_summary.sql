-- Add unique constraint for session summary upsert
-- Required for ON CONFLICT(user_id, session_id) in memory_service.py
--
-- Preflight: a UNIQUE(user_id, session_id) constraint cannot be created if
-- duplicate rows already exist (the ALTER would abort the whole migration).
-- Deduplicate first, deterministically keeping the newest row per group
-- (max created_at, tie-broken by id), then add the constraint idempotently.

DELETE FROM public.guru_session_summaries a
USING public.guru_session_summaries b
WHERE a.user_id = b.user_id
  AND a.session_id = b.session_id
  AND (a.created_at, a.id) < (b.created_at, b.id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'guru_session_summaries_user_session_unique'
          AND conrelid = 'public.guru_session_summaries'::regclass
    ) THEN
        ALTER TABLE public.guru_session_summaries
            ADD CONSTRAINT guru_session_summaries_user_session_unique UNIQUE (user_id, session_id);
    END IF;
END $$;

-- Reload PostgREST schema cache to apply changes immediately
NOTIFY pgrst, 'reload schema';
