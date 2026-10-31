# Runbook: Cross-Store Source Purge Procedure (DE-6.3)

## Objective
Permanently and completely purge a content source across all persistent stores and caches in response to:
- DMCA or copyright take-down notices.
- Content rights withdrawal or licensing changes.
- Teacher attribution corrections or requested removals.

---

## Scope & Target Stores
A complete purge must touch 5 systems:
1. **Supabase:** Mark source status as `purged` / revoke releases; delete quality staging rows.
2. **Qdrant:** Delete all points with matching `source_url`.
3. **Neo4j / Memgraph:** Delete source document nodes and orphan entity edges.
4. **Redis:** Invalidate exact response caches and semantic vector query caches.
5. **Compliance Logger:** Write an immutable audit log receipt.

---

## Step 1: Pre-Purge Impact Assessment
Query the number of points and relations that will be impacted:
```bash
python -m scripts.ops.cross_store_audit --source-url "https://www.youtube.com/watch?v=TARGET_URL"
```

---

## Step 2: Supabase Rights & Release Revocation
Revoke all releases for the source URL in Supabase:
```sql
UPDATE public.source_releases
SET status = 'revoked', updated_at = now()
WHERE source_url = 'https://www.youtube.com/watch?v=TARGET_URL';
```
Delete pending items in staging:
```sql
DELETE FROM public.staging_quality_queue
WHERE source_url = 'https://www.youtube.com/watch?v=TARGET_URL';
```

---

## Step 3: Qdrant Vector Deletion (snapshot, manifest, then delete)
Follow `SOURCE_QUARANTINE.md`: enumerate, export a manifest, verify counts, delete only those IDs, scoped to tenant and corpus. Never delete before the snapshot and manifest exist.

1. Snapshot the collection (restore point):

```bash
cd backend && .venv/bin/python -m scripts.ops.snapshot_qdrant --create
```

2. Dry run: enumerate the IDs, write the manifest, stop. Re-run with `APPLY=1` only after the printed count matches Step 1's impact assessment.

```bash
cd backend && SOURCE_URL='https://www.youtube.com/watch?v=TARGET_URL' .venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, time
from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

url = os.environ["SOURCE_URL"]
col = settings.qdrant_collection
c = QdrantClient(settings.qdrant_url)
flt = Filter(must=[
    FieldCondition(key="source_url", match=MatchValue(value=url)),
    FieldCondition(key="tenant_id", match=MatchValue(value=settings.default_tenant_id)),
    FieldCondition(key="corpus_id", match=MatchValue(value=settings.default_corpus_id)),
])
ids, off = [], None
while True:
    pts, off = c.scroll(col, scroll_filter=flt, limit=256, offset=off, with_payload=False)
    ids += [str(p.id) for p in pts]
    if off is None:
        break
manifest = pathlib.Path(f"purge_manifest_{int(time.time())}.json")
manifest.write_text(json.dumps({"collection": col, "source_url": url, "ids": sorted(ids),
                                "sha256": hashlib.sha256("".join(sorted(ids)).encode()).hexdigest()}))
print(f"{len(ids)} point(s) in {col}; manifest {manifest}")
if os.environ.get("APPLY") == "1" and ids:
    c.delete(col, points_selector=flt)
    print("deleted")
else:
    print("DRY RUN: nothing deleted (set APPLY=1 to delete)")
PY
```
3. Hold the maintenance lock and keep the manifest with the compliance receipt (Step 6).

---

## Step 4: Knowledge Graph Node Pruning
Delete the source node and cascade prune orphan relations in Neo4j/Memgraph:
```cypher
MATCH (d:Document {url: $source_url})
OPTIONAL MATCH (d)-[r]-()
DELETE r, d;
```

---

## Step 5: Redis Cache Invalidation
Cached answers may still quote this source:
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

## Step 6: Log Compliance Receipt
Write audit record to the local compliance log:
```bash
cd backend && .venv/bin/python -c "
from services.compliance_logger import get_compliance_logger
cl = get_compliance_logger()
cl.write_record({
    'action': 'source_purge',
    'source_url': 'https://www.youtube.com/watch?v=TARGET_URL',
    'reason': 'rights_revocation',
    'status': 'completed'
})
print('Compliance receipt recorded.')
"
```

---

## Step 7: Post-Purge Verification
Confirm zero points remain in Qdrant:
```bash
cd backend && .venv/bin/python -c "
from services.qdrant.client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

c = QdrantClient('http://localhost:6333')
from app.config import settings
col = settings.qdrant_collection
url = 'https://www.youtube.com/watch?v=TARGET_URL'
flt = Filter(must=[FieldCondition(key='source_url', match=MatchValue(value=url))])
pts = c.scroll(col, scroll_filter=flt, limit=5)[0]
assert len(pts) == 0, f'Points still found: {len(pts)}'
print('Verification passed: 0 points remaining.')
"
```
