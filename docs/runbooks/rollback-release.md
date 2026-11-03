# Runbook: Rollback or Supersede a Source Release (DE-6.3)

## Objective
Safely revoke, supersede, or restore a content source release in the `source_releases` registry, ensuring unverified or defective content is immediately excluded from serving without mutating Qdrant vectors.

---

## Background
Mukthi Guru uses a dual-layer publication model:
1. **Physical Layer:** Vector points in Qdrant carry immutable payloads with `source_release_version` and `source_url`.
2. **Logical Serving Gate:** the release filter is `RELEASE_FILTER_MODE` (`off` | `shadow` | `enforce`, default `off`; `settings.release_filter_mode`). `CORPUS_PUBLICATION_ENFORCEMENT_ENABLED` is a different, manifest-presence gate and does **not** apply this filter. Under `enforce`, a point is served only if:
   - `domain_rights_status = "licensed"` (`require_licensed_domain_reads`), and
   - its `source_release_version` equals the source's `active` release in `source_releases`.
   Points with no (or a non-numeric) `source_release_version` are dropped, and if the release registry cannot be read retrieval abstains rather than guessing a version.
   Revoking or superseding a release cuts points instantly **only in `enforce`**. In `off` nothing is filtered; in `shadow` exclusions are only logged/metered (`would_filter_inactive_release`). Confirm the mode before relying on this runbook.

---

## Step 1: Identify Defective Source Release
Query active releases for the source URL:
```sql
SELECT id, source_url, version, status, content_checksum, created_at
FROM public.source_releases
WHERE source_url = 'https://www.youtube.com/watch?v=EXAMPLE_ID'
ORDER BY version DESC;
```

---

## Step 2: Revoke / Quarantining a Release
To instantly withhold an active release:
```sql
-- Mark active release as revoked or quarantined
UPDATE public.source_releases
SET status = 'revoked', updated_at = now()
WHERE source_url = 'https://www.youtube.com/watch?v=EXAMPLE_ID'
  AND version = 3;
```
If rolling back to a previous valid version (e.g. version 2):
```sql
-- Restore previous release to active status
UPDATE public.source_releases
SET status = 'active', updated_at = now()
WHERE source_url = 'https://www.youtube.com/watch?v=EXAMPLE_ID'
  AND version = 2;
```

---

## Step 3: Flush Exact & Semantic Caches
Responses may be cached for up to 24 hours in Redis:
```bash
make flush-cache          # Redis mukthiguru:cache, mukthiguru:semcache, cache:first_person_exact + Qdrant semantic cache
make verify-cache-empty   # exit 0 = empty; 1 = still cached; 2 = unreachable (NOT empty)
```
Never use `FLUSHALL`. Do not hand-roll `scan_iter` patterns: the real namespaces
are `mukthiguru:cache`, `mukthiguru:semcache` and `cache:first_person_exact`
(`backend/app/constants.py`, `scripts/ops/flush_cache.py`); patterns such as
`exact_cache:*` match zero keys, so revoked content would keep serving from cache
for the 24 h TTL.

---

## Step 4: Verification
1. Run admin provenance lookup to confirm status:
   ```bash
   curl -s -X GET http://localhost:8000/api/admin/corpus/provenance/POINT_ID \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
   ```
2. Confirm `RELEASE_FILTER_MODE=enforce` is live (`settings.release_filter_mode`), then run a test retrieval query mentioning the source topic and assert points from version 3 are absent from `chunks` and `citations`. A pass under `off` or `shadow` proves nothing.
3. Check Prometheus metrics:
   Monitor `retrieval_release_shadow_exclusions_total` if running in shadow mode.
