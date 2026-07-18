-- Streak state + retention events for compassionate habit tracking

CREATE TABLE IF NOT EXISTS public.user_streaks (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    current_streak INT NOT NULL DEFAULT 0,
    longest_streak INT NOT NULL DEFAULT 0,
    last_active_date DATE,
    freezes_available INT NOT NULL DEFAULT 1,
    total_practice_days INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_streaks_last_active_idx
    ON public.user_streaks (last_active_date DESC);

ALTER TABLE public.user_streaks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_streaks_select" ON public.user_streaks
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

GRANT SELECT ON public.user_streaks TO authenticated;
GRANT ALL ON public.user_streaks TO service_role;

CREATE TRIGGER trg_user_streaks_touch
    BEFORE UPDATE ON public.user_streaks
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- Retention events — append-only log for cohort analysis

CREATE TABLE IF NOT EXISTS public.retention_events (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    props JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retention_events_user_idx
    ON public.retention_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS retention_events_event_idx
    ON public.retention_events (event, created_at DESC);

ALTER TABLE public.retention_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_retention_events_select" ON public.retention_events
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "own_retention_events_insert" ON public.retention_events
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "service_role_all_events" ON public.retention_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT, INSERT ON public.retention_events TO authenticated;
GRANT ALL ON public.retention_events TO service_role;

-- Atomic record_practice for RetentionService: loads, calculates, saves state
-- and logs practice/milestone events in a single transaction.
CREATE OR REPLACE FUNCTION public.record_practice(p_user_id UUID, p_practice_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE(
    current_streak INT,
    longest_streak INT,
    last_active_date DATE,
    freezes_available INT,
    total_practice_days INT,
    milestone_reached BOOLEAN
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    rec public.user_streaks%ROWTYPE;
    prev_current INT;
    today DATE := p_practice_date;
    yesterday DATE;
    gap INT;
BEGIN
    -- Ensure row exists first (no-op if exists), then lock for update
    INSERT INTO public.user_streaks (user_id, current_streak, longest_streak, last_active_date, freezes_available, total_practice_days)
    VALUES (p_user_id, 0, 0, NULL, 1, 0)
    ON CONFLICT (user_id) DO NOTHING;

    SELECT * INTO rec FROM public.user_streaks WHERE user_id = p_user_id FOR UPDATE;

    prev_current := rec.current_streak;

    IF rec.last_active_date = today THEN
        milestone_reached := FALSE;
        RETURN QUERY SELECT rec.current_streak, rec.longest_streak, rec.last_active_date,
                            rec.freezes_available, rec.total_practice_days, FALSE;
        RETURN;
    END IF;

    yesterday := today - 1;
    IF rec.last_active_date = yesterday THEN
        rec.current_streak := rec.current_streak + 1;
    ELSIF rec.last_active_date IS NULL THEN
        rec.current_streak := 1;
    ELSE
        gap := today - rec.last_active_date;
        IF gap = 2 AND rec.freezes_available > 0 THEN
            rec.freezes_available := rec.freezes_available - 1;
            rec.current_streak := rec.current_streak + 1;
        ELSE
            rec.current_streak := 1;
        END IF;
    END IF;

    rec.last_active_date := today;
    rec.total_practice_days := rec.total_practice_days + 1;
    IF rec.current_streak > rec.longest_streak THEN
        rec.longest_streak := rec.current_streak;
    END IF;
    IF rec.total_practice_days % 14 = 0 AND rec.freezes_available < 2 THEN
        rec.freezes_available := rec.freezes_available + 1;
    END IF;

    INSERT INTO public.user_streaks (user_id, current_streak, longest_streak, last_active_date, freezes_available, total_practice_days)
    VALUES (rec.user_id, rec.current_streak, rec.longest_streak, rec.last_active_date, rec.freezes_available, rec.total_practice_days)
    ON CONFLICT (user_id) DO UPDATE SET
        current_streak = EXCLUDED.current_streak,
        longest_streak = EXCLUDED.longest_streak,
        last_active_date = EXCLUDED.last_active_date,
        freezes_available = EXCLUDED.freezes_available,
        total_practice_days = EXCLUDED.total_practice_days,
        updated_at = now();

    INSERT INTO public.retention_events (user_id, event, props)
    VALUES (p_user_id, 'practice', jsonb_build_object('streak_current', rec.current_streak));

    IF rec.current_streak IN (3, 7, 14, 21, 40, 108) AND rec.current_streak <> prev_current THEN
        INSERT INTO public.retention_events (user_id, event, props)
        VALUES (p_user_id, 'streak_milestone', jsonb_build_object('streak', rec.current_streak));
        milestone_reached := TRUE;
    ELSE
        milestone_reached := FALSE;
    END IF;

    RETURN QUERY SELECT rec.current_streak, rec.longest_streak, rec.last_active_date,
                        rec.freezes_available, rec.total_practice_days,
                        (rec.current_streak IN (3, 7, 14, 21, 40, 108) AND rec.current_streak <> prev_current);
END;
$$;

-- Revoke default EXECUTE from PUBLIC and authenticated, grant only to service_role
REVOKE EXECUTE ON FUNCTION public.record_practice(UUID, DATE) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.record_practice(UUID, DATE) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.record_practice(UUID, DATE) TO service_role;
