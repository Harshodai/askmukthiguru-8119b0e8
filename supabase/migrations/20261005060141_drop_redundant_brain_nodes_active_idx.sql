-- Recorded in production history 2026-10-05 (version 20261005060141).
drop index if exists public.brain_nodes_user_active_idx;

-- REVERT:
-- create index if not exists brain_nodes_user_active_idx
--   on public.user_brain_nodes (user_id)
--   where is_superseded = false;
