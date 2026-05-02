# Backend Optimization Guide — AskMukthiGuru

> Comprehensive strategy for sub-second responses, high availability, and addictive user experience.

## 1. Model-as-a-Service (MaaS) Architecture

### Persona Routing

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Intent      │────▶│ Persona      │────▶│ Model Pool       │
│  Classifier  │     │ Router       │     │                  │
│  (DistilBERT)│     │              │     │ ├─ Sarvam 30B    │
└─────────────┘     └──────────────┘     │ ├─ TinyLlama 3B  │
                                          │ └─ Custom LoRA   │
                                          └──────────────────┘
```

- **Primary model**: Sarvam 30B for deep spiritual queries (QUERY intent).
- **Fast model**: TinyLlama 3B or Phi-3 Mini for casual greetings, intent routing, and CRAG rewrites.
- **LoRA adapters**: Fine-tuned layers for specific guru personas (Sri Preethaji warmth vs Sri Krishnaji directness).
- **Switching**: `ModelPool` interface with `get_model(persona, complexity)` method. Hot-swap without restart.

### Service Contract

```python
class LLMPort(Protocol):
    async def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str: ...
    async def generate_stream(self, prompt: str, **kw) -> AsyncIterator[str]: ...

class ModelPool:
    models: dict[str, LLMPort]  # "primary", "fast", "rewrite"
    def get(self, key: str) -> LLMPort: ...
```

## 2. Caching Strategy (3-Layer)

| Layer | Technology | TTL | Purpose |
|-------|-----------|-----|---------|
| L1 — Request | In-process `lru_cache` | Per-request | Deduplicate identical sub-queries within a single RAG pass |
| L2 — Session | Redis (Valkey) | 24h | Cache full responses keyed by `sha256(user_msg + last_3_msgs)` |
| L3 — Embedding | Redis + HNSW | 7d | Pre-computed embeddings for top 1000 spiritual terms |

### Cache-Aside Pattern

```python
async def get_response(key: str) -> str | None:
    # L1: in-memory
    if (hit := _mem_cache.get(key)):
        return hit
    # L2: Redis
    if (hit := await redis.get(f"resp:{key}")):
        _mem_cache[key] = hit
        return hit
    return None
```

### Cache Invalidation
- On new ingestion: flush all L2 entries whose query embeddings have cosine similarity >0.85 to any new chunk.
- Manual flush via admin `/api/admin/cache/flush` endpoint.

## 3. Background Prefetching

### Trending Topics Pre-Warm

```python
# Scheduler runs every 6 hours
async def prefetch_trending():
    topics = ["beautiful state", "soul sync meditation", "suffering",
              "consciousness", "relationship", "gratitude"]
    for topic in topics:
        embedding = await embed(topic)
        docs = await qdrant.search(embedding, limit=10)
        await redis.set(f"prefetch:{hash(topic)}", serialize(docs), ex=21600)
```

### Speculative Retrieval
- On first user message, speculatively retrieve docs for the top 3 predicted follow-up intents.
- Store in session-scoped cache; discard unused after 5 minutes.

## 4. Connection Pooling & I/O

### Current Problem
Each request creates new HTTP connections to Ollama and Qdrant.

### Solution
```python
# In ServiceContainer.__init__
self._http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    timeout=httpx.Timeout(connect=5.0, read=120.0),
)
# Reuse across all services
self.ollama = OllamaService(self._http_client)
self.qdrant = QdrantService(self._http_client)
```

### Qdrant Optimization
- Enable gRPC transport (2-3x faster than REST for search).
- Use `qdrant_client.AsyncQdrantClient` with built-in connection pooling.

## 5. RAG Pipeline Parallelism

### Current: Sequential
```
intent_router → decompose → retrieve → rerank → grade → extract → generate → verify
```

### Optimized: Parallel Where Possible
```
intent_router → decompose → [retrieve_qdrant ∥ retrieve_raptor] → merge → rerank → ...
                             [embed_sub_q1 ∥ embed_sub_q2 ∥ embed_sub_q3]
```

```python
# nodes.py — parallel retrieval
async def retrieve_documents(state: GraphState) -> GraphState:
    sub_queries = state["sub_queries"]
    tasks = [
        asyncio.gather(
            qdrant.search(q, level=0),  # leaf chunks
            qdrant.search(q, level=1),  # RAPTOR summaries
        )
        for q in sub_queries
    ]
    results = await asyncio.gather(*tasks)
    all_docs = deduplicate(flatten(results))
    return {**state, "documents": all_docs}
```

## 6. Streaming Architecture

### Token-by-Token SSE

```python
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    async def event_generator():
        async for token in model.generate_stream(prompt):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### KV Cache Persistence
- Maintain Ollama's KV cache between turns using `keep_alive` parameter.
- Set `keep_alive=300` (5 minutes) for active conversations.
- For vLLM: use prefix caching with `--enable-prefix-caching`.

## 7. Inference Acceleration

| Technique | Speedup | Effort |
|-----------|---------|--------|
| 4-bit GPTQ quantization | 1.5-2x, 60% less VRAM | Low (Modelfile change) |
| Speculative decoding (TinyLlama draft) | 2-3x | Medium |
| vLLM continuous batching | 3-5x throughput | High (migration) |
| Flash Attention 2 | 1.3-1.5x | Low (flag) |
| Tensor parallelism (multi-GPU) | Near-linear scaling | Medium |

### Recommended Progression
1. **Now**: Enable 4-bit quant + Flash Attention in Ollama Modelfile
2. **Next**: Add speculative decoding with TinyLlama draft
3. **Later**: Migrate to vLLM for production multi-user

## 8. Observability & Monitoring

### Key Metrics
- `response_time_p50`, `response_time_p95`, `response_time_p99`
- `tokens_per_second` (generation speed)
- `cache_hit_rate` (L1, L2, L3 separately)
- `rag_retrieval_ms`, `rag_rerank_ms`, `rag_generation_ms`
- `crag_retry_count` (tracks query rewrite loops)
- `faithfulness_score` (Self-RAG output)

### Stack
- **Metrics**: Prometheus + Grafana (already wired via `/metrics`)
- **Tracing**: OpenTelemetry spans on each RAG node
- **Logging**: Structured JSON logs with correlation IDs

## 9. Integration Checklist

### Pre-Production
- [ ] Health endpoint returns model load status, Qdrant connectivity, cache status
- [ ] Circuit breaker on Ollama calls (3 failures → 30s open → half-open)
- [ ] Graceful degradation: if Ollama down, serve cached responses + "Guru is meditating" message
- [ ] Rate limiting: 10 req/min per IP, 60 req/min per authenticated user
- [ ] Request timeout: 30s hard limit on `/api/chat`, streaming keeps alive via heartbeat

### Deployment
- [ ] Docker health checks for all services
- [ ] Qdrant snapshot backup every 6 hours
- [ ] Rolling restart strategy (drain connections before shutdown)
- [ ] Environment-specific configs (dev/staging/prod) via `.env` files

### Security
- [ ] Input sanitization before LLM prompt injection
- [ ] NeMo guardrails on both input and output
- [ ] CORS configured for production domain only
- [ ] API key rotation mechanism for any external services

## 10. Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                     NGINX / Caddy                        │
│                   (TLS + Rate Limit)                     │
└────────────┬─────────────────────────────┬───────────────┘
             │                             │
      ┌──────▼──────┐             ┌────────▼────────┐
      │  FastAPI     │             │  React SPA      │
      │  (Backend)   │             │  (Vite Build)   │
      │  Port 8000   │             │  Static Files   │
      └──────┬───────┘             └─────────────────┘
             │
    ┌────────┼────────────────┐
    │        │                │
┌───▼───┐ ┌──▼──────┐  ┌─────▼─────┐
│Ollama │ │ Qdrant  │  │  Redis    │
│(LLM)  │ │(Vector) │  │ (Cache)   │
│GPU    │ │Port 6333│  │ Port 6379 │
└───────┘ └─────────┘  └───────────┘
```

## Summary

The biggest wins, in priority order:
1. **SSE streaming** — eliminates perceived 3-8s wait (P0, medium effort)
2. **Parallel retrieval** — cuts RAG latency 40-60% (P0, low effort)
3. **Redis response cache** — instant repeat queries (P1, low effort)
4. **Connection pooling** — reduces per-request overhead 100-200ms (P1, low effort)
5. **4-bit quantization** — doubles inference speed (P1, low effort)
6. **Speculative decoding** — 2-3x token generation speed (P2, medium effort)
7. **vLLM migration** — production-grade multi-user serving (P3, high effort)
