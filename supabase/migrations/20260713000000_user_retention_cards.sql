-- Add public.user_retention_cards table for SM-2 spaced repetition active recall cards

CREATE TABLE IF NOT EXISTS public.user_retention_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_type TEXT NOT NULL, -- 'notebook_item', 'teaching', 'concept'
    source_id TEXT, -- ID of the underlying notebook_item or core memory
    easiness_factor DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    interval_days INT NOT NULL DEFAULT 0,
    repetitions INT NOT NULL DEFAULT 0,
    next_review_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS user_retention_cards_user_review_idx 
    ON public.user_retention_cards (user_id, next_review_at ASC);

-- Enable RLS
ALTER TABLE public.user_retention_cards ENABLE ROW LEVEL SECURITY;

-- Select policy
CREATE POLICY "own_retention_cards_select" ON public.user_retention_cards 
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

-- Insert policy
CREATE POLICY "own_retention_cards_insert" ON public.user_retention_cards 
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- Update policy
CREATE POLICY "own_retention_cards_update" ON public.user_retention_cards 
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Delete policy
CREATE POLICY "own_retention_cards_delete" ON public.user_retention_cards 
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Grant privileges
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_retention_cards TO authenticated;
GRANT ALL ON public.user_retention_cards TO service_role;

-- Touch trigger for updated_at
CREATE TRIGGER trg_user_retention_cards_touch 
    BEFORE UPDATE ON public.user_retention_cards 
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
