-- ============================================================================
-- Mukthi Vault — Second Brain schema (Supabase/Postgres)
-- Apply via the Supabase CLI (this project is CLI-linked, see supabase/config.toml):
--   supabase db push
-- or paste into the Supabase SQL editor.
--
-- Design guarantees enforced HERE (not just in app code):
--   * RLS on every table — the service role may write, the anon/auth role
--     can only ever touch rows where user_id = auth.uid().
--   * No plaintext columns for user content — only ciphertext blobs.
--   * Blind indexes are HMAC outputs — not reversible.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Vault keys: one wrapped DEK per user
-- ---------------------------------------------------------------------------
create table if not exists public.user_brain_keys (
    user_id      uuid primary key references auth.users(id) on delete cascade,
    wrapped_dek  text not null,              -- versioned b64 blob, KEK-wrapped
    wrap_mode    text not null default 'server_wrapped'
                 check (wrap_mode in ('server_wrapped', 'session_unlock')),
    kdf          jsonb,                      -- argon2 params for session_unlock
    version      int  not null default 1,
    created_at   timestamptz not null default now(),
    rotated_at   timestamptz
);

-- ---------------------------------------------------------------------------
-- Brain nodes: encrypted artifacts (reflections, entities, preferences...)
-- ---------------------------------------------------------------------------
create table if not exists public.user_brain_nodes (
    id           text primary key,           -- app-generated uuid hex
    user_id      uuid not null references auth.users(id) on delete cascade,
    kind         text not null
                 check (kind in ('reflection','entity','preference','relationship','journal')),
    ciphertext   text not null,              -- AES-256-GCM blob, AAD=user:kind:id
    blind        text,                       -- HMAC blind index (exact-match dedupe)
    confidence   real not null default 0.8,
    decay        real not null default 1.0,
    access_count int  not null default 0,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index if not exists brain_nodes_user_idx  on public.user_brain_nodes (user_id, created_at desc);
create index if not exists brain_nodes_kind_idx  on public.user_brain_nodes (user_id, kind);
create unique index if not exists brain_nodes_blind_uidx on public.user_brain_nodes (user_id, blind)
    where blind is not null;

-- ---------------------------------------------------------------------------
-- Brain edges: encrypted relationships between the user's own nodes
-- ---------------------------------------------------------------------------
create table if not exists public.user_brain_edges (
    id          text primary key,
    user_id     uuid not null references auth.users(id) on delete cascade,
    src         text not null references public.user_brain_nodes(id) on delete cascade,
    dst         text not null references public.user_brain_nodes(id) on delete cascade,
    rel_cipher  text not null,               -- encrypted relation label
    weight      real not null default 1.0,
    created_at  timestamptz not null default now()
);
create index if not exists brain_edges_user_idx on public.user_brain_edges (user_id);
create index if not exists brain_edges_src_idx  on public.user_brain_edges (src);
create index if not exists brain_edges_dst_idx  on public.user_brain_edges (dst);

-- ---------------------------------------------------------------------------
-- touch helper (access_count bump) — security definer, minimal surface
-- ---------------------------------------------------------------------------
create or replace function public.brain_touch(p_id text)
returns void language sql security definer set search_path = public as $$
    update public.user_brain_nodes
       set access_count = access_count + 1,
           updated_at   = now()
     where id = p_id;
$$;

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------
alter table public.user_brain_keys  enable row level security;
alter table public.user_brain_nodes enable row level security;
alter table public.user_brain_edges enable row level security;

-- Owners see ONLY their own rows (and even then, only ciphertext).
drop policy if exists brain_keys_owner  on public.user_brain_keys;
create policy brain_keys_owner on public.user_brain_keys
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists brain_nodes_owner on public.user_brain_nodes;
create policy brain_nodes_owner on public.user_brain_nodes
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists brain_edges_owner on public.user_brain_edges;
create policy brain_edges_owner on public.user_brain_edges
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- NOTE: there is intentionally NO policy granting any admin/operator role
-- read access. The backend uses the service role (bypasses RLS) but the
-- service layer (backend/services/second_brain/second_brain_service.py)
-- only ever queries scoped by the caller's user_id AND only decrypts with
-- the caller's unlocked vault. Operators reading these tables directly see
-- wrapped keys + ciphertext only.

commit;

-- Revoke public access, grant only to service_role
revoke execute on function public.brain_touch from public;
grant execute on function public.brain_touch to service_role;

-- Ensure composite index before FK references
create unique index if not exists brain_nodes_id_user_uidx
    on public.user_brain_nodes (id, user_id);

-- Fix FK to reference composite (user_id, id)
alter table public.user_brain_edges
  drop constraint if exists user_brain_edges_src_fkey,
  add constraint user_brain_edges_src_fkey
    foreign key (src, user_id) references public.user_brain_nodes(id, user_id)
    on delete cascade deferrable initially deferred;

alter table public.user_brain_edges
  drop constraint if exists user_brain_edges_dst_fkey,
  add constraint user_brain_edges_dst_fkey
    foreign key (dst, user_id) references public.user_brain_nodes(id, user_id)
    on delete cascade deferrable initially deferred;

notify pgrst, 'reload schema';
