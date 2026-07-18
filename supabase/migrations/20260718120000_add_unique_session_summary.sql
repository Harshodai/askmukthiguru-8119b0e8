-- Add unique constraint for session summary upsert
-- Required for ON CONFLICT(user_id, session_id) in memory_service.py

ALTER TABLE public.guru_session_summaries
ADD CONSTRAINT guru_session_summaries_user_session_unique UNIQUE (user_id, session_id);
