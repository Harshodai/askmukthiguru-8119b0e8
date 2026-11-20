-- Comment only. Guarded so it is a no-op when the table is absent. Never drops the table.
DO $$
BEGIN
  IF pg_catalog.to_regclass('public.user_brain_keys_archive_20261119') IS NOT NULL THEN
    COMMENT ON TABLE public.user_brain_keys_archive_20261119 IS 'Vault-key backup from 2026-11-19 BRAIN_KEK work; retain until owner decision; do not drop';
  END IF;
END
$$;
