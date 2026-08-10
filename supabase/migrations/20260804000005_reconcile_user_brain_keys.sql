-- ============================================================================
-- REVERT: Column additions only — nothing dropped. To restore a single-migration
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- column set: drop the columns NOT present in the migration you want to keep.
-- Vault shape (20260717191006): keep wrapped_dek/wrap_mode/kdf/version/rotated_at
-- -- ALTER TABLE public.user_brain_keys
-- --   DROP COLUMN IF EXISTS kek, DROP COLUMN IF EXISTS dek_wrapped, DROP COLUMN IF EXISTS updated_at;
-- Keys shape (20260718120001): keep kek/dek_wrapped/rotated_at/updated_at
-- -- ALTER TABLE public.user_brain_keys
-- --   DROP COLUMN IF EXISTS wrapped_dek, DROP COLUMN IF EXISTS wrap_mode,
-- --   DROP COLUMN IF EXISTS kdf, DROP COLUMN IF EXISTS version;
-- NOTE: the wrap_mode CHECK constraint + set_updated_at() trigger are shared
-- with 20260718120001 — leave both unless rolling back the whole keys migration.
-- DESTRUCTIVE for the dropped column's data. Service compatibility: the vault
-- service reads wrapped_dek/wrap_mode/kdf/version — keep the vault shape unless
-- the service is also rolled back.
-- ============================================================================

-- ============================================================================
-- P1-DB-7 — Reconcile user_brain_keys schema drift
--
-- Two CREATE TABLE IF NOT EXISTS migrations shipped with incompatible column
-- sets for public.user_brain_keys:
--   20260717191006_second_brain_vault.sql:
--     user_id, wrapped_dek, wrap_mode, kdf, version, created_at, rotated_at
--   20260718120001_second_brain_keys_table.sql:
--     user_id, kek, dek_wrapped, rotated_at, created_at, updated_at
--
-- Whichever ran first wins; the other's columns are silently lost. The vault
-- service (backend/services/second_brain/second_brain_service.py) reads and
-- writes wrapped_dek / wrap_mode / kdf / version — Mode B (session-unlock)
-- breaks if wrap_mode / kdf / version are missing.
--
-- This migration unions both column sets idempotently. Nothing is dropped.
-- NOT NULL without a DEFAULT is relaxed to nullable for the ADD path so the
-- statement cannot fail on a non-empty table created by the other migration;
-- the service always writes these columns on upsert.
-- ============================================================================

alter table public.user_brain_keys
    add column if not exists wrapped_dek text,
    add column if not exists wrap_mode   text not null default 'server_wrapped',
    add column if not exists kdf         jsonb,
    add column if not exists version     int  not null default 1,
    add column if not exists kek         text,
    add column if not exists dek_wrapped text,
    add column if not exists rotated_at  timestamptz,
    add column if not exists created_at  timestamptz not null default now(),
    add column if not exists updated_at  timestamptz not null default now();

-- wrap_mode values are a closed set (see vault migration); enforce it even if
-- the vault migration never applied.
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'user_brain_keys_wrap_mode_check'
    ) then
        alter table public.user_brain_keys
            add constraint user_brain_keys_wrap_mode_check
            check (wrap_mode in ('server_wrapped', 'session_unlock'));
    end if;
end $$;

-- updated_at auto-refresh (keys migration ships the trigger; vault migration
-- does not — make it apply-order independent).
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists user_brain_keys_set_updated_at on public.user_brain_keys;
create trigger user_brain_keys_set_updated_at
    before update on public.user_brain_keys
    for each row execute function public.set_updated_at();

notify pgrst, 'reload schema';
