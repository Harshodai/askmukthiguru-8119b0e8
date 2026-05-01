# Latency Optimization Roadmap — AskMukthiGuru

> Goal: Sub-500ms first-token, <3s full response. Make the app feel instant.

## Frontend Perceived-Speed Improvements

| Technique | Impact | Effort | Status |
|---|---|---|---|
| **SSE streaming responses** | First token in <500ms vs 3-8s full wait | Medium | ✅ Wired (`sendMessageStreaming`) |
| **Skeleton guru bubble** | Instant visual feedback on send | Low | ✅ Implemented |
| **In-memory response cache** | Instant repeat queries (5-min TTL, 50 LRU) | Low | ✅ Implemented (`responseCache.ts`) |
| **Suggested starters** | Zero-friction first message | Low | ✅ Implemented |
| **Scroll-to-bottom FAB** | Never lose context in long chats | Low | ✅ Implemented |
| **React.lazy admin routes** | Cut initial bundle ~40% (admin code is heavy) | Low | TODO |
| **Prefetch /chat chunk on landing hover** | Faster navigation to chat | Low | TODO |
| **Service Worker for static assets** | Instant repeat loads | Medium | TODO |

## Backend Latency (FastAPI / RAG Pipeline)

| Technique | Impact | Effort | Priority |
|---|---|---|---|
| **SSE `StreamingResponse` from Ollama** | Token-by-token output; eliminates "wait for full generation" | Medium | P0 |
| **Parallel retrieval** | Run Qdrant vector search + RAPTOR tree navigation concurrently (`asyncio.gather` in `nodes.py`) | Low | P0 |
| **KV cache persistence** | Keep Ollama context window warm between turns for same conversation ID | Medium | P1 |
| **Lightweight intent classifier** | Replace full LLM call for intent routing with fine-tuned DistilBERT or keyword heuristic (<50ms vs 1-2s) | Medium | P1 |
| **Batch sub-query embeddings** | `decompose_query` generates multiple sub-queries; embed them in one batch call to `EmbeddingService` | Low | P1 |
| **Redis response cache** | Cache hashed frequent spiritual queries with 24h TTL | Low | P1 |
| **CRAG early-exit** | Break rewrite loop as soon as graded doc relevance exceeds 0.8 threshold | Low | P2 |
| **Speculative decoding** | Use TinyLlama as draft model with Sarvam 30B for 2-3x faster token generation (vLLM supports this) | High | P2 |
| **Connection pooling** | Use persistent `httpx.AsyncClient` for Ollama/Qdrant instead of per-request connections | Low | P1 |
| **4-bit quantization (GPTQ/AWQ)** | Lower VRAM and faster inference; Ollama supports this via Modelfile | Medium | P2 |
| **vLLM migration from Ollama** | Continuous batching, PagedAttention, tensor parallelism for multi-GPU | High | P3 |

### Backend SSE Implementation Guide

```python
# In main.py — add alongside existing /api/chat
from fastapi.responses import StreamingResponse

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        # Run guardrails + intent + retrieval (non-streaming)
        state = await run_pipeline_until_generation(req)
        # Stream the LLM generation
        async for token in ollama.astream(state["prompt"]):
            yield f"data: {json.dumps({'content': token})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Parallel Retrieval Implementation

```python
# In nodes.py — retrieve_documents
async def retrieve_documents(state: GraphState) -> dict:
    # Currently sequential; change to parallel:
    qdrant_results, raptor_results = await asyncio.gather(
        _qdrant.search(state["query"], limit=10),
        navigate_tree(state["query"], _qdrant, _embedder),
    )
    combined = deduplicate(qdrant_results + raptor_results)
    return {"documents": combined}
```

## Engagement & Addiction Loop Features

| Feature | Description | Effort |
|---|---|---|
| **Practice streak milestones** | Celebrate at 3, 7, 21, 40 days with animation + badge | Low |
| **Daily wisdom push** | Morning notification with teaching excerpt + "Ask the Guru" CTA | Medium |
| **Bookmark guru responses** | Star responses to revisit (hook `useFavorites` already exists) | Low |
| **Progress badges** | Award for: first meditation, 7-day streak, 100 messages | Medium |
| **Shareable wisdom cards** | Generate image card from guru response for social sharing | Medium |
| **Gentle re-engagement** | "We missed you" message after 3+ days absence | Low |
| **Teaching of the day** | Rotate curated excerpt on landing + chat empty state | Low |

## Architecture Recommendations

1. **WebSocket upgrade**: Replace HTTP polling with persistent WebSocket for real-time bidirectional chat
2. **Edge CDN**: Deploy static assets on Cloudflare/Vercel Edge for <50ms TTFB globally
3. **Background intent prefetch**: After 3+ chars typed, fire lightweight intent classification so backend can pre-warm retrieval
4. **Optimistic rendering**: Show user message instantly, render guru skeleton, stream tokens in
5. **Conversation-level KV cache**: Pass `conversation_id` to Ollama so it reuses context window across turns
