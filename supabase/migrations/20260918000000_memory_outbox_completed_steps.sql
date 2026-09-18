-- AMK-C-005: memory-outbox enrichment side effects were not idempotent.
--
-- tasks/memory_outbox_tasks.py::_drain_once performs five independent writes
-- per claimed row (profile conversation memory, extract_and_write, episodic
-- log_episode, L1 add_atoms, L2 save_scene_block) and only calls
-- mark_processed() once all five succeed. Each write is individually
-- try/excepted, so the code was written for the case where a write RAISES.
--
-- It was not written for the case where the PROCESS DIES mid-loop, which
-- skips both the exception handler and mark_processed(). claim_memory_outbox()
-- then reclaims the row after its 10-minute staleness window and re-runs all
-- five writes from scratch — duplicating a user's episodic memory, L1 atoms
-- and L2 scene block. That crash mode is not hypothetical: it was reproduced
-- live on 2026-09-18 (AMK-C-001, backend SIGKILLed under a 6-request burst).
--
-- completed_steps records which sub-steps already committed so a reclaimed row
-- RESUMES instead of RESTARTING. claim_memory_outbox() returns `outbox.*`, so
-- the column flows to the worker with no change to the function, and the claim
-- deliberately does NOT reset it — that is the whole point.
--
-- This narrows, but does not mathematically close, the at-least-once window:
-- a crash between a side effect and its marker still replays that ONE step.
-- The window shrinks from "several seconds of LLM enrichment calls" to "one
-- small UPDATE", and each step becomes individually resumable. Closing it
-- fully requires the side-effect stores themselves to accept an idempotency
-- key, which they do not today.

ALTER TABLE public.memory_outbox
    ADD COLUMN IF NOT EXISTS completed_steps text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN public.memory_outbox.completed_steps IS
    'Enrichment sub-steps already committed for this row (AMK-C-005). A row '
    'reclaimed after a worker crash skips these instead of re-running them. '
    'Never reset on reclaim.';
