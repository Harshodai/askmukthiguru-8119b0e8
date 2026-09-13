-- Widen canonical_memory_events.actor to the values the code actually writes.
--
-- 20260912000000 created this table with
--   CHECK (actor = ANY (ARRAY['user','system','admin']))
-- which was written from assumption, not from the writers. The real writers are
-- `user` (app/api/canonical_memory.py), `resolver`
-- (services/canonical_memory/resolver.py) and `consolidator`
-- (services/canonical_memory/consolidator.py).
--
-- Effect of the gap: the memory row committed, then the audit insert raised
-- 23514 and was swallowed by resolver.py's try/except — so automatic writes
-- landed with NO audit trail at all, and the GDPR export under-reported them.
-- Measured 2026-09-13: 1 memory written, 0 audit rows.
--
-- 'system' and 'admin' are retained; they are legitimate future actors and
-- dropping them would be a second guess in the same place.

ALTER TABLE public.canonical_memory_events
    DROP CONSTRAINT IF EXISTS canonical_memory_events_actor_check;

ALTER TABLE public.canonical_memory_events
    ADD CONSTRAINT canonical_memory_events_actor_check
    CHECK (actor = ANY (ARRAY['user', 'system', 'admin', 'resolver', 'consolidator']));
