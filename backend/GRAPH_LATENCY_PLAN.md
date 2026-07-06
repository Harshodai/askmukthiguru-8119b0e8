# Graph-Based Latency Optimization Plan

## Current State
- LightRAG queries: **30s timeout** (can exceed on complex graphs)
- Neo4j cross-teacher queries: **unbounded** (syncs on every comparison question)
- Graph result caching: **none**
- Concurrent retrieval: **exists** but not fully leveraged
- Index status: **unknown**

## Optimization Phases (Est. 15–40s reduction)

### Phase 1: Query Result Caching (5–10s savings)
**Goal:** Memoize LightRAG and Neo4j query results within a request + across similar queries

**Files to modify:**
- `backend/services/lightrag_service.py` — add LRU cache to `aquery()`
- `backend/rag/nodes/cross_teacher_reasoning.py` — cache Neo4j results (key: teacher set)

**Approach:**
```python
# LightRAG caching: 5min TTL per query
from functools import lru_cache
_lightrag_query_cache = {}  # {query_hash: (results, timestamp)}

async def cached_lightrag_query(query: str, mode: str):
    cache_key = f"{hash(query)}:{mode}"
    if cache_key in _lightrag_query_cache:
        results, ts = _lightrag_query_cache[cache_key]
        if time.time() - ts < 300:  # 5min TTL
            return results
    results = await lightrag.aquery(query, mode=mode, ...)
    _lightrag_query_cache[cache_key] = (results, time.time())
    return results
```

**Expected wins:**
- 80% of queries are variations on common topics (beautiful state, deeksha, etc.)
- Cache hit rate: 3–5 queries per user session
- **Savings: 5–10s per cached query**

---

### Phase 2: Neo4j Index Audit + Optimization (2–5s savings)
**Goal:** Ensure Neo4j has indexes on high-cardinality query patterns

**Audit:** Run in docker exec
```bash
docker exec mukthiguru-neo4j cypher-shell -u neo4j -p <PASSWORD> "SHOW INDEXES"
```

**Expected missing indexes:**
- Teacher name lookups: `(t:Teacher {name: $name})`
- Relationship traversal: `(t1:Teacher)-[:EXPOUNDS]->(c:Concept)<-[:EXPOUNDS]-(t2:Teacher)`

**Fix:** Add indexes in `backend/app/main.py` lifespan
```python
async def ensure_neo4j_indexes():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password)
    )
    async with driver.session() as session:
        await session.run("""
            CREATE INDEX teacher_name IF NOT EXISTS 
            FOR (t:Teacher) ON (t.name)
        """)
        await session.run("""
            CREATE INDEX concept_expounds IF NOT EXISTS 
            FOR (c:Concept) ON (c.name)
        """)
    driver.close()
```

**Expected wins:**
- Index range scans: **0.5–2s per teacher comparison**
- **Savings: 2–5s for tier3_complex multi-teacher questions**

---

### Phase 3: Adaptive Graph Depth by Query Tier (3–8s savings)
**Goal:** Use graph query complexity based on `query_tier`

**Files:**
- `backend/rag/nodes/retrieval.py` — pass `query_tier` to LightRAG
- `backend/services/lightrag_service.py` — tier-aware retrieval mode

**Approach:**
```python
# In retrieve_for_single_query(), line 520:
if lightrag and intent in ["RELATIONAL", "FACTUAL", "QUERY"]:
    # Adaptive depth: fast tier → skip graph entirely
    if query_tier in ("fast", "tier2_simple"):
        mode = "local"  # Entity extraction only
    else:
        mode = "hybrid"  # Full graph + vectors
    
    tasks.append(
        asyncio.wait_for(
            lightrag.aquery(query, mode=mode, only_need_context=True),
            timeout=float(settings.lightrag_retrieval_timeout),
        )
    )
```

**Expected wins:**
- Fast queries: skip graph extraction (~5s saved)
- Simple queries: shallow graph traversal (~3s saved)
- **Savings: 3–8s per fast/simple query**

---

### Phase 4: Parallel Cross-Teacher Reasoning (2–4s savings)
**Goal:** Run Neo4j teacher comparison in parallel with document grading

**Current flow:** retrieve → rerank → grade → cross_teacher → sufficiency (serial)
**Optimized:** retrieve → rerank → {grade + cross_teacher} → sufficiency (parallel)

**Files:**
- `backend/rag/graph_strategies.py` — StandardGraphStrategy.build()

**Approach:**
```python
# Lines 289–291: Change from serial to parallel
graph.add_edge("rerank_documents", "grade_documents")
graph.add_edge("rerank_documents", "cross_teacher_reasoning")
# Both run in parallel; check_context_sufficiency waits for both
graph.add_conditional_edges(
    "grade_documents",
    lambda state: "next",  # No-op routing
    {"next": "check_context_sufficiency"}
)
graph.add_edge("cross_teacher_reasoning", "check_context_sufficiency")
```

**Expected wins:**
- **Savings: 2–4s by eliminating sequential wait**

---

### Phase 5: Graph Extraction Batching at Ingestion (Background)
**Goal:** Pre-compute entity graphs during ingestion (not on query)

**Current:** LightRAG extracts entities on first query (~10–20s latency)
**Optimized:** Extract during ingestion via background Celery task

**Files:**
- `backend/ingest/pipeline.py` — trigger extraction after Qdrant upsert
- `backend/tasks/ingest_tasks.py` — async extraction task

**Approach:**
```python
# In IngestionPipeline.ingest_url(), after upsert:
from app.tasks.ingest_tasks import extract_graph_entities

extract_graph_entities.delay(
    source_url=url,
    text=cleaned_text,
    max_depth=2,
    entity_types=["CONCEPT", "PERSON", "PRACTICE"]
)

# In ingest_tasks.py:
@celery_app.task(bind=True, max_retries=2)
def extract_graph_entities(self, source_url, text, max_depth=2, entity_types=None):
    try:
        lightrag = get_lightrag_service()
        lightrag.ainsert(text, source_url=source_url)
    except Exception as e:
        logger.warning(f"Graph extraction failed: {e}")
```

**Expected wins:**
- Moves 10–20s of extraction to background (invisible to user)
- **Savings: 10–20s per ingestion (background work)**

---

## Implementation Priority
1. **Phase 1 (Caching)** — 2 hrs, **highest ROI** (5–10s immediate)
2. **Phase 2 (Indexes)** — 1 hr, quick win (2–5s)
3. **Phase 3 (Adaptive Depth)** — 3 hrs, broad (3–8s)
4. **Phase 4 (Parallel)** — 2 hrs, architectural (2–4s)
5. **Phase 5 (Batch Extraction)** — 4 hrs, background only

## Expected Cumulative Impact
- **Baseline:** 9–98s (fast to complex with confidence gate)
- **After Phase 1+2:** 5–15s (fast) + 40–80s (complex)
- **After Phase 3:** 3–10s (fast) + 25–60s (complex)
- **After Phase 4:** 3–10s (fast) + 20–55s (complex)

## Risk Mitigation
- **Cache invalidation:** 5min TTL (configurable via env)
- **Graph depth limits:** Max depth = 3 (circuit breaker)
- **Timeout safety:** 30s LightRAG + 5s Neo4j max per query
- **Fallback:** If graph fails, vector retrieval continues

---

## Quick Wins (Start Today)
1. Add `@lru_cache` to `lightrag_service.aquery()` (30 min)
2. Add Neo4j indexes in `main.py` lifespan (20 min)
3. Tier-aware mode selection in retrieval.py (20 min)
4. **Total: 70 min → 7–12s savings on most queries**
