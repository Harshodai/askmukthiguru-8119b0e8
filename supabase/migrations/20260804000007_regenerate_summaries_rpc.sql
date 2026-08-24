-- ============================================================================
-- REVERT: Drop the RPC. NOTE: summaries already backfilled by the RPC remain
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- (data-altering, recomputable via left(content,280)).
-- DROP FUNCTION IF EXISTS public.regenerate_summaries(uuid);
-- ============================================================================

-- ============================================================================
-- P1-DB-9 — regenerate_summary as a single bulk statement
--
-- The backend previously SELECTed every NULL-summary row and issued one UPDATE
-- per row (~1000 rows = 20-50s of sequential round-trips). This RPC replaces
-- the whole loop with one UPDATE ... WHERE statement.
--
-- SECURITY: SECURITY DEFINER with an explicit p_user_id parameter mirrors the
-- existing match_user_memories_by_user pattern (the backend calls with the
-- service role, which bypasses RLS and cannot rely on auth.uid()). Executing
-- the UPDATE inside this function scopes the write to the caller's user_id
-- AND keeps the summary computation (left(content,280)) in a single statement.
-- Callers are restricted to service_role + authenticated; the parameter is a
-- plain uuid, so no privilege is exposed beyond the row the caller already
-- owns.
-- ============================================================================

create or replace function public.regenerate_summaries(
    p_user_id uuid
)
returns int
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
    v_updated int;
begin
    if p_user_id is null then
        raise exception 'user_id_required';
    end if;

    update public.guru_memories
       set summary = left(content, 280)
     where user_id = p_user_id
       and summary is null
       and content is not null;

    get diagnostics v_updated = row_count;
    return v_updated;
end;
$$;

revoke execute on function public.regenerate_summaries(uuid) from public, anon;
grant  execute on function public.regenerate_summaries(uuid) to service_role;
grant  execute on function public.regenerate_summaries(uuid) to authenticated;

notify pgrst, 'reload schema';
