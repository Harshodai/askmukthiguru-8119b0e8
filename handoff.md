# Session Handoff — Jul 16, 2026 (Deep Investigation: "Who is Sri Preethaji?" Connection Issue)

## 1. Goal
Investigate the "connection issue" response for query "Who is Sri Preethaji?" on Railway production. User claimed documents exist in Qdrant but response indicated content gap. Need to trace END-TO-END pipeline: intent → routing → retrieval → generation → response.

## 2. Current State of Code
- **Backend**: Deployed on Railway (project: `resilient-embrace`, service: `askmukthiguru-8119b0e8`, env: `production`)
- **Deployment**: `32c9c228` (healthy, `/api/health` returns `ready: true`)
- **Embedding Model Config**: `BAAI/bge-m3` (1024-dim) in `app/config.py:174-175`
- **Qdrant Collection**: Created at startup with 1024-dim vectors
- **LLM Provider**: OpenRouter (primary), nim (fallback)

## 3. Files Actively Examined (Not Edited)
- `backend/services/embedding_service.py` — **root cause location** (lines 218-263)
- `backend/services/openrouter_service.py` — graceful degradation logic
- `backend/rag/nodes/retrieval.py` — retrieve_documents, Qdrant search calls
- `backend/app/config.py` — embedding_model, embedding_dimension settings
- `backend/services/qdrant/client.py` — Qdrant collection creation with dimension
- Railway CLI logs — production error evidence

## 4. Everything Tried & Failed (Root Cause Analysis)

### Initial Hypotheses (ALL WRONG)
| Hypothesis | Test | Result |
|------------|------|--------|
| Content gap: no Sri Preethaji docs in Qdrant | Check compiled.json, OKF files | ✅ 6 sri-preethaji + 15 "both" entries exist |
| OKF injection not working | Check `rag_okf_injection_enabled` (True), teacher routing | ✅ Would work if Qdrant returned docs |
| Retrieval pipeline bug | Trace `retrieve_documents` → `retrieve_for_single_query` | ✅ Pipeline logic correct |
| Intent classification wrong | Check intent_router for "Who is Sri Preethaji?" | ✅ Would classify as QUERY/FACTUAL |

### ACTUAL ROOT CAUSE (Found in Railway Logs)
```
2026-07-16 07:22:47,708 [ERROR] Qdrant dense search failed (non-fatal): 
  httpx.HTTPStatusError: 400 Bad Request
  Response: {"detail":{"error":"Wrong input: Vector dimension error: expected dim: 1024, got 384"}}
```

**The embedding service silently fell back from `BAAI/bge-m3` (1024-dim) to `intfloat/multilingual-e5-small` (384-dim) on Railway startup, but Qdrant collection remained 1024-dim.**

### Failure Chain
1. **Railway container starts** → `ContainerBuilder.build()` loads embedding service
2. **Primary model `BAAI/bge-m3` fails to load** (likely: OOM, network timeout, or HF cache corruption on Railway's limited resources)
3. **Fallback chain triggers** → loads `intfloat/multilingual-e5-small` (384-dim) 
4. **Config mutated in-place** (lines 238-245): `settings.embedding_model = "intfloat/multilingual-e5-small"`, `settings.embedding_dimension = 384`
5. **Qdrant collection already exists** with 1024-dim (created earlier or by different replica)
6. **Every dense search fails** with dimension mismatch: "expected 1024, got 384"
7. **All retrievals return empty** → `all_docs = []`
8. **OKF injection skipped** (gated on `all_docs` being truthy at line 1113)
9. **Generation called with empty context** → OpenRouter returns 429 (rate limited from retries)
10. **Graceful degradation triggers** → "I'm experiencing a temporary connection issue"

### Why This Was Missed
- Logs showed "Batches: 100%..." progress bars (HF model download) but no clear "fallback to 384-dim" warning
- Config mutation happens silently in `_ensure_encoder()` 
- No validation that Qdrant dimension matches current embedding dimension
- Tests mock embedding service, never catch dimension drift

## 5. Key Learnings

### Architecture Flaw: Silent Config Mutation
```python
# embedding_service.py:238-245 — DANGEROUS
if model_name != settings.embedding_model:
    settings.embedding_model = model_name
    if model_name in FALLBACK_DIMS:
        settings.embedding_dimension = FALLBACK_DIMS[model_name]
```
**This mutates global config at runtime** — any code reading `settings.embedding_dimension` AFTER this gets the WRONG value for Qdrant operations that already happened.

### Qdrant Collection Dimension Drift
- Collection created once at first startup with whatever dimension was active
- No migration/recreation on dimension change
- No startup assertion that `collection.dim == settings.embedding_dimension`

### Railway Resource Constraints
- `BAAI/bge-m3` (560MB) likely OOMs or times out on Railway's limited memory
- Fallback models are smaller (384-dim models ~90MB) but WRONG dimension
- Need: pre-warm model, or pin dimension, or fail fast instead of silent fallback

### Retrieval-Only-Fallback Is Insufficient
- BM25 text search still works (doesn't need embeddings) — returned some results
- But dense vector search (primary retrieval) completely broken
- RRF fusion had BM25 results but they were low quality for "Who is Sri Preethaji?"

## 6. Next Steps (Priority Order)

### P0: Fix Dimension Mismatch (Deploy Required)
**Option A — Fail Fast (Recommended)**:
```python
# In _ensure_encoder(): remove dimension mutation, only allow primary model
FALLBACK_CHAIN = [settings.embedding_model]  # Only primary
# If primary fails → raise, don't silently downgrade dimension
```

**Option B — Recreate Collection on Dimension Change**:
```python
# In QdrantService.__init__ or ContainerBuilder.build():
# Check existing collection dim vs settings.embedding_dimension
# If mismatch: delete + recreate collection (lose vectors, but correct)
```

**Option C — Pre-load Model in Docker Build**:
```dockerfile
# In Dockerfile: RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
# Caches model in image, avoids runtime download/OOM
```

### P1: Add Startup Validation
```python
# In ContainerBuilder.build() after all services init:
assert qdrant_collection_dim == settings.embedding_dimension, \
    f"Qdrant dim {qdrant_collection_dim} != embedding dim {settings.embedding_dimension}"
```

### P2: Make OKF Injection Work Even with Empty Qdrant Results
```python
# In retrieval.py:1111 — remove `all_docs` requirement for OKF injection
if (
    getattr(settings, "rag_okf_injection_enabled", False)
    and intent not in ("CASUAL", "GREETING")
):
    # OKF can provide curated doctrine even when vector search fails
```

### P3: Improve Graceful Degradation Message
- Current: "connection issue" — misleading when root cause is retrieval failure
- Better: "I couldn't find relevant teachings in my knowledge base. Please try rephrasing."

## 7. Commands to Verify Fix Locally
```bash
# 1. Check current embedding dimension
cd backend && python -c "from app.config import settings; print(settings.embedding_model, settings.embedding_dimension)"

# 2. Check Qdrant collection dimension
cd backend && python -c "
from services.qdrant_service import QdrantService
from app.config import settings
qs = QdrantService(settings.qdrant_url, settings.qdrant_api_key)
# qs.client.get_collection('mukthi_guru_docs')  # check .config.params.vectors.size
"

# 3. Test retrieval for "Who is Sri Preethaji?"
cd backend && python -c "
import asyncio
from app.dependencies import get_container
async def test():
    c = get_container()
    from rag.nodes.retrieval import retrieve_documents
    from rag.states import GraphState
    state = GraphState(question='Who is Sri Preethaji?', chat_history=[], intent='FACTUAL', query_tier='standard')
    result = await retrieve_documents(state)
    print(f'Docs: {len(result.get(\"documents\", []))}')
asyncio.run(test())
"
```

## 8. What Was Confirmed Working
- ✅ OKF data exists (23 compiled entries, 6 sri-preethaji specific)
- ✅ OKF injection logic correct (teacher routing, synonym expansion)
- ✅ Pipeline stages execute in order
- ✅ OpenRouter generation works when given context
- ✅ BM25 text search returns results (doesn't need embeddings)
- ✅ Health endpoint, container startup, graph compilation all healthy

## 9. Summary
**The "connection issue" was a red herring.** The true failure was a **silent embedding dimension drift** from 1024→384 caused by model fallback on Railway's constrained environment, leaving Qdrant with mismatched collection dimension. Every dense vector search failed, retrieval returned empty, OKF injection was gated off, and OpenRouter's rate limit on retry triggered the misleading "connection issue" fallback.

**Fix**: Prevent silent dimension change (Option A) or validate/recreate Qdrant collection at startup (Option B). Deploy and verify with the test commands above.