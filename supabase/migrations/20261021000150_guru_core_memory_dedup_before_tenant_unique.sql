-- Prepares public.guru_core_memory for UNIQUE (user_id, tenant_id), which
-- 20261021000200_tenant_scope_legacy_memory.sql creates.
-- Production held three rows for one user/tenant (inserted 0.3 s apart, 11-13
-- characters each: fixture rows), so that unique index could not be built.
-- Keep the newest row per (user_id, tenant_id); archive the others first.
-- REVERT: MANUAL ONLY. Restore from public.guru_core_memory_dedup_archive_20261119
--   (INSERT INTO public.guru_core_memory SELECT * FROM <archive>) after dropping
--   guru_core_memory_user_tenant_uidx.
CREATE TABLE IF NOT EXISTS public.guru_core_memory_dedup_archive_20261119
    (LIKE public.guru_core_memory INCLUDING DEFAULTS);
ALTER TABLE public.guru_core_memory_dedup_archive_20261119 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.guru_core_memory_dedup_archive_20261119 FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.guru_core_memory_dedup_archive_20261119 TO service_role;
DROP POLICY IF EXISTS guru_core_memory_dedup_archive_service_role
    ON public.guru_core_memory_dedup_archive_20261119;
CREATE POLICY guru_core_memory_dedup_archive_service_role
    ON public.guru_core_memory_dedup_archive_20261119
    FOR ALL TO service_role USING (true) WITH CHECK (true);

WITH ranked AS (
  SELECT id, row_number() OVER (PARTITION BY user_id, tenant_id ORDER BY created_at DESC, id DESC) AS rn
  FROM public.guru_core_memory
), archived AS (
  INSERT INTO public.guru_core_memory_dedup_archive_20261119
  SELECT g.* FROM public.guru_core_memory g JOIN ranked r ON r.id = g.id WHERE r.rn > 1
  RETURNING id
)
DELETE FROM public.guru_core_memory g USING ranked r WHERE r.id = g.id AND r.rn > 1;
