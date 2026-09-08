-- Memory compaction snapshots: safety net before destructive compaction
-- Stores the last 3 snapshots per user so we can recover if compaction
-- produces contaminated or lossy output.

CREATE TABLE IF NOT EXISTS memory_compaction_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    memories_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS: users can only see their own snapshots
ALTER TABLE memory_compaction_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own compaction snapshots"
    ON memory_compaction_snapshots
    FOR SELECT
    USING (auth.uid() = user_id);

-- Service role (backend) needs full access
CREATE POLICY "Service role manages compaction snapshots"
    ON memory_compaction_snapshots
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Index for cleanup queries (keep only last 3 per user)
CREATE INDEX IF NOT EXISTS idx_compaction_snapshots_user_created
    ON memory_compaction_snapshots (user_id, created_at DESC);

-- RPC: create snapshot and prune old ones (atomic)
CREATE OR REPLACE FUNCTION create_compaction_snapshot(
    p_user_id UUID,
    p_memories_json JSONB
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO memory_compaction_snapshots (user_id, memories_json)
    VALUES (p_user_id, p_memories_json);

    -- Keep only the last 3 snapshots per user
    DELETE FROM memory_compaction_snapshots
    WHERE user_id = p_user_id
      AND id NOT IN (
          SELECT id FROM memory_compaction_snapshots
          WHERE user_id = p_user_id
          ORDER BY created_at DESC
          LIMIT 3
      );
END;
$$;
