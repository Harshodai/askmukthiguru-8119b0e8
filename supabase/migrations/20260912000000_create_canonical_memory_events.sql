-- canonical_memory_events: the append-only audit trail for canonical memories.
--
-- app/api/canonical_memory.py has always written to this table on every
-- create/update/delete and reads it for the GDPR export, but no migration ever
-- created it. The effect in a fresh database: the memory row inserts, the audit
-- insert raises PGRST205, and the endpoint returns 500 — so a seeker is told
-- "Failed to save memory" about a memory that WAS saved, and a retry writes a
-- duplicate. Found 2026-09-12 against a local stack with the migrations applied.

CREATE TABLE IF NOT EXISTS public.canonical_memory_events (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    -- No FK to canonical_memories: the trail must outlive the row it describes,
    -- otherwise deleting a memory erases the evidence that it was deleted.
    memory_id    uuid,
    event_type   text NOT NULL CHECK (
        event_type = ANY (ARRAY['CREATED', 'UPDATED', 'DELETED', 'SUPERSEDED', 'EXPIRED', 'RESTORED'])
    ),
    actor        text NOT NULL DEFAULT 'system' CHECK (actor = ANY (ARRAY['user', 'system', 'admin'])),
    old_version  integer,
    new_version  integer,
    reason       text,
    metadata     jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS canonical_memory_events_user_created_idx
    ON public.canonical_memory_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS canonical_memory_events_memory_idx
    ON public.canonical_memory_events (memory_id);

ALTER TABLE public.canonical_memory_events ENABLE ROW LEVEL SECURITY;

-- Read-only to the owner. There is deliberately no UPDATE or DELETE policy:
-- an audit trail a user can edit is not an audit trail. Writes come from the
-- service role, which bypasses RLS.
DROP POLICY IF EXISTS own_canonical_memory_events_select ON public.canonical_memory_events;
CREATE POLICY own_canonical_memory_events_select
    ON public.canonical_memory_events
    FOR SELECT
    USING (auth.uid() = user_id);

-- The API writes these rows through the service-role client; without the
-- INSERT grant the write fails with 42501 even though RLS would have allowed
-- it, because grants are checked before policies.
GRANT SELECT, INSERT ON public.canonical_memory_events TO service_role;
GRANT SELECT ON public.canonical_memory_events TO authenticated;

-- NOTE: this is NOT the same thing as public.memory_audit_events from
-- 20260911000000. That table records state snapshots (action/old_state/
-- new_state); this one records the canonical-memory version trail
-- (event_type/actor/old_version/new_version/reason) that
-- app/api/canonical_memory.py actually writes and exports. Two different
-- shapes, deliberately kept separate rather than forced into one.
