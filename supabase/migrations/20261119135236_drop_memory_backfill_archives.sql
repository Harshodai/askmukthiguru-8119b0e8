-- DPDP Art. 17: the 2026-11-19 tenant backfill archive tables copied user memory
-- rows without a foreign key to auth.users, so account erasure left copies behind.
-- The backfill only changed tenant_id ('default' -> 'oneness'); every archived row
-- still exists on the live table, so the archives hold no data the live rows lack.
-- No guard on purpose: an archived row whose live row was erased (DPDP Art. 17) is exactly
-- the copy that must go, so a guard that aborts on it would defeat this migration.
-- (Applied to prod 2026-11-19 after verifying 24/24 archived rows had live copies.)


DROP TABLE IF EXISTS public.guru_memories_tenant_backfill_archive_20261119;
DROP TABLE IF EXISTS public.guru_core_memory_tenant_backfill_archive_20261119;
DROP TABLE IF EXISTS public.guru_session_summaries_tenant_backfill_archive_20261119;
