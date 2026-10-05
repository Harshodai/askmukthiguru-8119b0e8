-- Applied to prod 2026-10-05 as version 20261005053805, 42s after
-- 20261005053723_user_brain_nodes_bitemporal by a parallel session. Its
-- ADD COLUMN IF NOT EXISTS statements were no-ops there (053723 is the
-- effective column definition), so the only lasting effect is this index.
--
-- It is REDUNDANT with user_brain_nodes_user_current_idx (same predicate; that
-- index is a superset). Kept here only so repo == prod. Dropping it needs a
-- follow-up migration and owner approval.

-- ponytail: stub for migration-revert-check.yml (L-MIGRATE-EPHEMERAL-1).
create table if not exists public.user_brain_nodes (
    id            text primary key,
    user_id       uuid not null,
    is_superseded boolean not null default false
);
alter table public.user_brain_nodes
  add column if not exists is_superseded boolean not null default false;

create index if not exists brain_nodes_user_active_idx
  on public.user_brain_nodes (user_id)
  where is_superseded = false;

-- REVERT:
-- drop index if exists public.brain_nodes_user_active_idx;
