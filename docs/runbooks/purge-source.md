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

## Step 3: Qdrant Vector Deletion
Execute a filter-based deletion in Qdrant:
```bash
cd backend && .venv/bin/python -c "
from services.qdrant.client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

c = QdrantClient('http://localhost:6333')
col = 'spiritual_wisdom_contextual'
url = 'https://www.youtube.com/watch?v=TARGET_URL'

flt = Filter(must=[FieldCondition(key='source_url', match=MatchValue(value=url))])
res = c.delete(collection_name=col, points_selector=flt)
print('Qdrant delete completed:', res)
"
```

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
Flush exact cache keys that may contain excerpts from this source:
```bash
cd backend && .venv/bin/python -c "
import redis, os
r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
count = 0
for k in r.scan_iter(match='exact_cache:*'):
    r.delete(k)
    count += 1
for k in r.scan_iter(match='semantic_cache:*'):
    r.delete(k)
    count += 1
print(f'Cleared {count} cached entries.')
"
```

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
col = 'spiritual_wisdom_contextual'
url = 'https://www.youtube.com/watch?v=TARGET_URL'
flt = Filter(must=[FieldCondition(key='source_url', match=MatchValue(value=url))])
pts = c.scroll(col, scroll_filter=flt, limit=5)[0]
assert len(pts) == 0, f'Points still found: {len(pts)}'
print('Verification passed: 0 points remaining.')
"
```
