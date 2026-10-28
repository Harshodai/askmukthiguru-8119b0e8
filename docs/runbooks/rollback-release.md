# Runbook: Rollback or Supersede a Source Release (DE-6.3)

## Objective
Safely revoke, supersede, or restore a content source release in the `source_releases` registry, ensuring unverified or defective content is immediately excluded from serving without mutating Qdrant vectors.

---

## Background
Mukthi Guru uses a dual-layer publication model:
1. **Physical Layer:** Vector points in Qdrant carry immutable payloads with `source_release_version` and `source_url`.
2. **Logical Serving Gate:** When `CORPUS_PUBLICATION_ENFORCEMENT_ENABLED=true`, retrieval queries apply a filter requiring:
   - `domain_rights_status = "licensed"`
   - `source_release_version` matching an `active` release in `source_releases`.
Revoking or superseding a release in the database instantly cuts points from the retrieval candidates.

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
Because responses may be cached for up to 24 hours in Redis:
```bash
# Invalidate cache for the source URL
cd backend && .venv/bin/python -c "
import redis, os
r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
count = 0
for key in r.scan_iter(match='exact_cache:*'):
    r.delete(key)
    count += 1
print(f'Flushed {count} cache keys.')
"
```

---

## Step 4: Verification
1. Run admin provenance lookup to confirm status:
   ```bash
   curl -s -X GET http://localhost:8000/api/admin/corpus/point/POINT_ID \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
   ```
2. Run test retrieval query mentioning the source topic:
   Verify that points from version 3 are NOT returned in `chunks` or `citations`.
3. Check Prometheus metrics:
   Monitor `retrieval_release_shadow_exclusions_total` if running in shadow mode.
