-- ============================================================================
-- REVERT: Drop push_devices + touch trigger/function. DESTRUCTIVE: all registered push
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- tokens are lost — users must re-grant notification permission. NOTE:
-- users_update_own policy recreated with WITH CHECK by 20260804000001 — drops
-- with the table.
-- DROP TRIGGER IF EXISTS push_devices_touch ON public.push_devices;
-- DROP FUNCTION IF EXISTS public.push_devices_touch_updated_at();
-- DROP TABLE IF EXISTS public.push_devices;
-- ============================================================================

-- push_devices: stores FCM (Android) / APNs (iOS) tokens for push notifications.
-- Created for AskMukthiGuru mobile app launch (Task 7).
create table if not exists push_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  platform text not null check (platform in ('android', 'ios')),
  token text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  active boolean not null default true
);

-- One token per (platform, token) — re-registration upserts (re-activates).
-- Plain unique index (no partial `where active`) so ON CONFLICT upsert works.
create unique index if not exists push_devices_uq_token
  on push_devices(platform, token);

alter table push_devices enable row level security;

-- Users can read/update/delete only their own devices.
create policy users_select_own on push_devices for select
  using (auth.uid() = user_id);
create policy users_insert_own on push_devices for insert
  with check (auth.uid() = user_id);
create policy users_update_own on push_devices for update
  using (auth.uid() = user_id);
create policy users_delete_own on push_devices for delete
  using (auth.uid() = user_id);

-- Service role bypasses RLS (used by backend to send pushes).
-- updated_at auto-touch.
create or replace function push_devices_touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists push_devices_touch on push_devices;
create trigger push_devices_touch before update on push_devices
  for each row execute function push_devices_touch_updated_at();

-- Notify PostgREST to reload schema cache (PGRST204 fix pattern).
notify pgrst, 'reload schema';