-- Fix concurrent-completion race in user_healing_progress: the API previously
-- did a SELECT then an application-side list-append then an UPSERT, which
-- loses a concurrent completion (last writer wins, dropping the other step).
-- This RPC makes the append atomic in a single UPDATE, guarded by
-- jsonb_exists so a step already recorded is never duplicated.

ALTER TABLE public.user_healing_progress
  ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 0 CHECK (total_steps >= 0);

CREATE OR REPLACE FUNCTION public.append_healing_step(
    p_user_id UUID,
    p_course_slug TEXT,
    p_step_id TEXT,
    p_total_steps INTEGER
)
RETURNS TABLE(current_step INTEGER, completed_steps JSONB, total_steps INTEGER)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    INSERT INTO public.user_healing_progress
        (user_id, course_slug, current_step, completed_steps, total_steps, last_accessed_at)
    VALUES (p_user_id, p_course_slug, 0, '[]'::jsonb, p_total_steps, now())
    ON CONFLICT (user_id, course_slug) DO NOTHING;

    UPDATE public.user_healing_progress t
    SET completed_steps = CASE
            WHEN NOT jsonb_exists(t.completed_steps, p_step_id)
                THEN jsonb_insert(t.completed_steps, '{-1}', to_jsonb(p_step_id::text), true)
            ELSE t.completed_steps
        END,
        total_steps = GREATEST(t.total_steps, p_total_steps),
        last_accessed_at = now()
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;

    UPDATE public.user_healing_progress t
    SET current_step = LEAST(jsonb_array_length(t.completed_steps), GREATEST(t.total_steps - 1, 0))
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;

    RETURN QUERY
    SELECT t.current_step, t.completed_steps, t.total_steps
    FROM public.user_healing_progress t
    WHERE t.user_id = p_user_id AND t.course_slug = p_course_slug;
END;
$$;

GRANT EXECUTE ON FUNCTION public.append_healing_step(UUID, TEXT, TEXT, INTEGER) TO authenticated;
