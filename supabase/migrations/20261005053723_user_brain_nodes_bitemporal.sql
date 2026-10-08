-- Bi-temporal supersession columns for Second Brain nodes (invalidate_and_supersede).
-- Applied to prod (ozmjeuqbholoxypfxixb) 2026-10-05 as version 20261005053723;
-- this file mirrors that SQL so repo == prod. Table had 0 rows when applied.

-- ponytail: stub for migration-revert-check.yml, which applies each changed
-- migration alone against an empty ephemeral Postgres (L-MIGRATE-EPHEMERAL-1).
-- No-op on any real database where the table already exists.
create table if not exists public.user_brain_nodes (
    id           text primary key,
    user_id      uuid not null,
    kind         text not null,
    ciphertext   text not null,
    confidence   real not null default 0.8,
    decay        real not null default 1.0,
    access_count int  not null default 0,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

alter table public.user_brain_nodes
  add column if not exists valid_from    timestamptz not null default now(),
  add column if not exists valid_to      timestamptz,
  add column if not exists is_superseded boolean     not null default false,
  add column if not exists superseded_by text references public.user_brain_nodes(id) on delete set null;

create index if not exists user_brain_nodes_user_current_idx
  on public.user_brain_nodes (user_id, created_at desc)
  where is_superseded = false;

-- REVERT:
-- drop index if exists public.user_brain_nodes_user_current_idx;
-- alter table public.user_brain_nodes
--   drop column if exists superseded_by,
--   drop column if exists is_superseded,
--   drop column if exists valid_to,
--   drop column if exists valid_from;
