# Mukthi Guru — World-Class Optimization Plan

## Context

The Mukthi Guru project has a solid architectural foundation (12-layer RAG pipeline, LangGraph state machine, CRAG/Self-RAG/CoVe verification layers) but deep exploration revealed **20 critical issues** that prevent it from being world-class. The most severe: hybrid search is broken (silently falls to dense-only), the embedding model is English-only for a 10-language app, 11-13 sequential LLM calls per query make the <3s target impossible, HyDE is dead code, chat history is never used, output guardrails are inoperative, and the context window is 96% underutilized. This plan addresses all issues in priority order while keeping the $0/local-only constraint and centering on Sarvam 30B.

## Decisions (Confirmed)
- **Embedding model:** BAAI/bge-m3 (1024d, native dense+sparse+ColBERT, 100+ languages, ~2.3GB) — eliminates the need for a separate sparse/BM25 encoder
- **Scope:** Full plan — all 5 tiers (30 items, ~6 weeks)
- **Re-ingestion:** Clean re-ingestion of all content (new collection schema with 1024d vectors + sparse vectors)

---

## Tier 1: Critical Fixes (Broken Functionality)

### 1.1 Switch to bge-m3 + Fix Hybrid Search (currently broken — dense-only, English-only)
**Files:** `backend/services/embedding_service.py`, `backend/services/qdrant_service.py`, `backend/app/config.py`, `backend/.env.example`, `backend/requirements.txt`
**Problems (combined — two critical issues solved together):**
- `all-MiniLM-L6-v2` (384d) is English-only. Hindi/Telugu/Tamil queries produce garbage embeddings.
- `qdrant_client.search()` doesn't accept `query_text` — silently catches TypeError and falls back to dense-only. BM25/sparse search never runs.
**Fix — Use `BAAI/bge-m3` which natively produces dense + sparse + ColBERT vectors in one model:**
- Replace `SentenceTransformer("all-MiniLM-L6-v2")` with `FlagModel("BAAI/bge-m3", use_fp16=True)` from the `FlagEmbedding` library
- bge-m3's `encode()` returns both `dense_vecs` (1024d) and `lexical_weights` (sparse BM25-like) in one call — no separate fastembed needed
- Reconfigure Qdrant collection with **named vectors**: `dense` (1024d cosine) + `sparse` (SparseVector from lexical_weights)
- At ingestion: generate both vector types per chunk with a single `model.encode()` call, upsert as named vectors
- At query: use `qdrant_client.query_points()` with `prefetch` for both dense and sparse, fused via **Reciprocal Rank Fusion (RRF)** — this replaces the broken `search()` call
- Update `EMBEDDING_DIMENSION` from 384 to 1024 in config
- bge-m3 supports 100+ languages including all 10 target Indian languages (Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, English)
- Add `FlagEmbedding>=1.2.10` to requirements.txt (MIT license, free)
- Drop the `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker — bge-m3's ColBERT late-interaction scores can serve as the reranker, or keep the CrossEncoder but use `BAAI/bge-reranker-v2-m3` (multilingual, trained on diverse data, not just web search)
**Complexity:** L (but solves two critical issues at once + eliminates the reranker mismatch)

### 1.3 Enable HyDE (Currently Dead Code)
**Files:** `backend/app/config.py`, `backend/.env.example`
**Problem:** `rag_use_hyde` is not defined in Settings — `getattr(settings, "rag_use_hyde", False)` always returns False.
**Fix:** Add `rag_use_hyde: bool = True` to `Settings` class in config.py and `RAG_USE_HYDE=true` to .env.example.
**Complexity:** S

### 1.4 Fix Output Guardrail (Currently Inoperative)
**Files:** `backend/guardrails/rails.py`
**Problem:** Output rail sends the answer as a `user` message asking "Moderate this response for safety" — NeMo treats this as a new user query, not output moderation.
**Fix:** Restructure the output check to send the answer as a `bot` turn in the conversation history, then call `generate_async()` to let NeMo's output flows evaluate it. The Colang `check output moderation` flow expects to see a bot turn, not a user turn.
**Complexity:** M

### 1.5 Fix Metrics Bug
**Files:** `backend/app/main.py`
**Problem:** `REQUEST_COUNT.labels(status="success").inc()` is called at line 220 BEFORE the pipeline runs.
**Fix:** Move it after successful pipeline completion (line 228). Add `REQUEST_COUNT.labels(status="error").inc()` in the except block. Add `REQUEST_COUNT.labels(status="blocked").inc()` in the guardrail block path.
**Complexity:** S

### 1.6 Consolidate Prompts (Dead Code Cleanup)
**Files:** `backend/rag/prompts.py`, `backend/services/ollama_service.py`
**Problem:** `prompts.py` defines GRADE_RELEVANCE_PROMPT, FAITHFULNESS_CHECK_PROMPT, VERIFICATION_PROMPT, etc. but none are imported — real prompts are inline in `ollama_service.py`.
**Fix:** Move all inline prompts from `ollama_service.py` methods to `prompts.py` as constants, then import them. This centralizes prompt management for easier tuning.
**Complexity:** M

### 1.7 Unify Guardrail Model with Main Pipeline
**Files:** `backend/guardrails/config/config.yml`, `backend/app/config.py`
**Problem:** NeMo uses `llama3.2:latest` while the main pipeline uses `sarvam-30b:latest`.
**Fix:** Make configurable: add `guardrails_model: str = "sarvam-30b:latest"` to config.py and template the config.yml. Using the same model ensures consistent behavior; alternatively, using llama3.2 for guardrails (faster classification) is defensible if documented.
**Complexity:** S

### 1.8 Fix Meditation Negation Handling
**Files:** `backend/rag/meditation.py`
**Problem:** `should_start_meditation()` checks if ANY positive signal keyword appears. "no, please don't guide me" contains "please" and "guide" → incorrectly returns True.
**Fix:** Add a negation pre-check: if the message contains "no", "don't", "not", "nah", "nope", "stop", "cancel" → return False before checking positive signals.
**Complexity:** S

---

## Tier 2: High-Impact Accuracy Improvements

### 2.1 Increase Chunk Size and Rerank Top-K (Context Window Utilization)
**Files:** `backend/app/config.py`, `backend/.env.example`
**Problem:** 500-char chunks (~100 tokens) with top-3 reranked = ~300 tokens fed to an 8192-token window (4% utilization).
**Fix:**
- Change `rag_chunk_size` from 500 to **1500** (chars, ~300 tokens)
- Change `rag_chunk_overlap` from 50 to **200** (chars)
- Change `rag_top_k_rerank` from 3 to **5**
- This gives ~1500 tokens of context to the LLM — 5x improvement while staying safely within the 8K window (system prompt ~200 tokens + question ~50 tokens + context ~1500 tokens + answer ~512 tokens = ~2262 tokens, well within 8192)
- Also increase `num_predict` from 512 to **1024** to allow longer spiritual explanations
**Complexity:** S (config changes, but requires re-ingestion)

### 2.2 Incorporate Chat History into Generation
**Files:** `backend/rag/nodes.py`, `backend/rag/prompts.py`
**Problem:** `chat_history` exists in GraphState but is NEVER used in any prompt. No multi-turn context.
**Fix:**
- In `generate_answer` node: format last 3 turns of `chat_history` as context before the current question
- In `retrieve_documents` node: use the last user message from history to augment the current query for better retrieval on follow-up questions (e.g., "tell me more about that" → include "that" referent from history)
- Add a `MULTI_TURN_PROMPT` template to `prompts.py` that includes conversation context
- Keep history to last 3 turns max to avoid context window overflow
**Complexity:** M

### 2.3 Add Metadata Filtering by RAPTOR Level at Retrieval
**Files:** `backend/rag/nodes.py`, `backend/services/qdrant_service.py`
**Problem:** Level-0 leaf chunks and level-1 RAPTOR summaries compete equally in search — no structured retrieval.
**Fix:**
- Implement two-phase retrieval in `retrieve_documents`:
  1. Search level-1 summaries first (thematic overview) — top 2
  2. Search level-0 chunks (specific details) — top 15
  3. Merge and rerank the combined set
- Add a `raptor_level` filter parameter to `QdrantService.search()`
- Create a payload index on `raptor_level` for fast filtering
**Complexity:** M

### 2.4 Add Source Provenance to RAPTOR Summaries
**Files:** `backend/ingest/raptor.py`
**Problem:** Level-1 summary nodes have no `source_url` or `title` — cannot be traced back to source videos.
**Fix:** When building summaries, collect all unique `source_url` and `title` values from the cluster's leaf chunks. Store them as `source_urls: list[str]` and `titles: list[str]` in the summary point's metadata.
**Complexity:** S

### 2.5 Add Ingestion Deduplication
**Files:** `backend/services/qdrant_service.py`, `backend/ingest/pipeline.py`
**Problem:** Re-ingesting the same video creates duplicate chunks (UUID-based IDs, no uniqueness check).
**Fix:**
- Generate deterministic point IDs using `uuid5(NAMESPACE_URL, f"{source_url}:{chunk_index}:{raptor_level}")` instead of random `uuid4()`
- Before ingestion, check if points with this source_url already exist via a scroll query with filter
- Offer `overwrite` vs `skip` modes
**Complexity:** M

### 2.6 Improve Self-RAG with Cross-Verification
**Files:** `backend/services/ollama_service.py`, `backend/rag/nodes.py`
**Problem:** Same model checks its own output — tends to validate its own hallucinations.
**Fix:**
- Use a **two-pass verification** approach:
  - Pass 1: Generate the answer with `temperature=0.3` (creative)
  - Pass 2: Check faithfulness with `temperature=0.0` (strict) and an explicit **sentence-by-sentence** verification prompt that forces the LLM to quote the source sentence for each claim
- Add a `per_sentence_attribution` option that asks the LLM to produce `[Claim] → [Source Quote]` pairs, rejecting any claim without a direct source quote
- This is still the same model but the stricter prompt and different temperature significantly reduce self-validation bias
**Complexity:** M

### 2.7 Fix Depression Detector for Multilingual
**Files:** `backend/services/depression_detector.py`
**Problem:** `distilroberta-finetuned-depression` is English-only. Hindi/Telugu distress goes undetected.
**Fix:**
- Replace with `cardiffnlp/twitter-xlm-roberta-base-sentiment-latest` (multilingual, 100+ languages) as the base for distress detection, OR
- Use a simpler approach: add a keyword-based pre-filter for distress terms in all 10 Indian languages (e.g., Hindi: "दुखी", "उदास", "मरना"; Telugu: "బాధ", "దుఃఖం") combined with the English model
- Also fix the truncation: change `text[:512]` to proper tokenizer truncation using the model's tokenizer
**Complexity:** M

---

## Tier 3: Latency & Efficiency Optimizations

### 3.1 Reduce LLM Calls from 11-13 to 5-6 per Query
**Files:** `backend/rag/nodes.py`, `backend/services/ollama_service.py`, `backend/rag/graph.py`
**Problem:** Each LLM call to Sarvam 30B takes 1-3s. 11-13 calls = 11-39s minimum.
**Fix — Merge and eliminate calls:**
1. **Eliminate `is_complex_query`** — always decompose (decomposition of a simple query just returns the original query; costs 1 call instead of 2)
2. **Batch grade_relevance** — instead of 3 separate LLM calls grading one doc each, send all 5 reranked docs in ONE prompt asking the LLM to rate each 1-5 (one call instead of 3-5)
3. **Merge extract_hints + generate_answer** — include hint extraction instructions directly in the generation prompt ("First, identify 3-5 key evidence phrases, then write your answer using those phrases"). Saves 1 call.
4. **Merge check_faithfulness + verify_claims** — combine Self-RAG and CoVe into a single structured verification prompt: "For each sentence in the answer, quote the supporting source text. Then give a VERDICT: FAITHFUL/HALLUCINATED". Saves 1 call.
5. **Replace NeMo guardrails with lightweight classifier** — instead of 2 full LLM calls (input + output rail), use a small fine-tuned classifier or keyword-based rules for input, and a simple regex/rule-based check for output. This saves 2 LLM calls.
**Result:** From 11-13 calls down to ~5: intent_classify, decompose, generate (with hints), verify (combined), and optional rewrite on CRAG loop.
**Complexity:** L

### 3.2 Add Streaming Support
**Files:** `backend/app/main.py`, `backend/rag/nodes.py`, `backend/services/ollama_service.py`, `src/lib/aiService.ts`
**Problem:** Client sees nothing until entire 12-layer pipeline completes (5-20 seconds).
**Fix:**
- Backend: Use FastAPI `StreamingResponse` with Server-Sent Events (SSE)
- For the `generate_answer` node: use Ollama's streaming API (`ChatOllama.astream()`) and yield tokens as they arrive
- Stream structure: emit status events during pipeline stages (`{"event": "status", "data": "Searching knowledge base..."}`) then stream the actual answer tokens (`{"event": "token", "data": "The beautiful state..."}`)
- Frontend: Replace `fetch().json()` with `EventSource` or `fetch` + `ReadableStream` parsing
- This gives perceived latency of ~2-3s (time until first token) while total completion time remains the same
**Complexity:** L

### 3.3 Parallelize Independent LLM Calls
**Files:** `backend/rag/nodes.py`
**Problem:** Sub-query retrieval is sequential even though queries are independent.
**Fix:**
- In `retrieve_documents`: use `asyncio.gather()` to run embed + search for all sub-queries concurrently
- In `grade_documents`: if keeping per-doc grading, use `asyncio.gather()` for all grade calls
- In RAPTOR `_summarize_clusters`: use `asyncio.gather()` for all cluster summarizations
**Complexity:** M

### 3.4 Add Response Caching
**Files:** `backend/app/main.py` (new: `backend/services/cache_service.py`)
**Problem:** Identical or near-identical queries re-run the full 12-layer pipeline.
**Fix:**
- Add an in-memory LRU cache (stdlib `functools.lru_cache` or `cachetools.TTLCache`)
- Cache key: normalized query embedding (cosine similarity > 0.95 = cache hit)
- Cache the final answer + citations + intent for 1 hour TTL
- Invalidate cache when new content is ingested
- Zero cost — pure Python, no external service
**Complexity:** M

### 3.5 Optimize Corrector Speed
**Files:** `backend/ingest/corrector.py`
**Problem:** Naive 2000-char splits create 15 sequential LLM calls for a 1-hour video.
**Fix:**
- Increase chunk size from 2000 to 4000 chars (Sarvam 30B's 8K context can handle it)
- Use sentence-aware splitting (split on `. ` or `\n`) to avoid cutting mid-sentence
- Add overlap of 100 chars at boundaries to preserve cross-boundary names
- Parallelize correction chunks with `asyncio.gather()` (max 3 concurrent)
- Skip correction for manual captions (Tier 1 transcripts) which are already high quality
**Complexity:** M

### 3.6 Use a Smaller Model for Classification Tasks
**Files:** `backend/app/config.py`, `backend/services/ollama_service.py`
**Problem:** Sarvam 30B (~18GB VRAM) is used for binary yes/no classification (intent, grading, faithfulness) where a 3B model would suffice — massive overkill.
**Fix:**
- Add `ollama_classify_model: str = "llama3.2:3b"` to config.py
- Create two LLM instances in `OllamaService.__init__()`: `_llm` (Sarvam 30B for generation) and `_llm_fast` (llama3.2:3b for classification)
- Use `_llm_fast` for: `classify_intent()`, `grade_relevance()`, `check_faithfulness()`
- Use `_llm` (Sarvam 30B) for: `generate()`, `verify_claims()`, `summarize()`
- Classification calls drop from ~3s to ~0.3s each. Combined with T3.1 (5 total calls), this brings the pipeline closer to the <3s perceived latency target
**Complexity:** M

---

## Tier 4: Advanced AI Techniques for World-Class Quality

### 4.1 Implement Parent-Child Chunking (Contextual Retrieval)
**Files:** `backend/ingest/pipeline.py`, `backend/services/qdrant_service.py`, `backend/rag/nodes.py`
**Why:** Current 1500-char chunks may retrieve a relevant sentence but miss surrounding context.
**Fix:**
- At ingestion: create two chunk tiers — **child chunks** (500 chars, for precise retrieval) and **parent chunks** (2000 chars, for context)
- Store the parent chunk ID in each child chunk's metadata
- At retrieval: search using child chunks (precise matching) but feed the PARENT chunk to the LLM (full context)
- This gives retrieval precision of small chunks with generation context of large chunks
**Complexity:** L

### 4.2 Implement Contextual Embedding (Anthropic-style)
**Files:** `backend/ingest/pipeline.py`, `backend/services/ollama_service.py`
**Why:** Raw chunks lose document-level context. "This practice helps achieve inner peace" — which practice?
**Fix:**
- Before embedding each chunk, prepend a short LLM-generated context sentence: use Sarvam 30B to generate a 1-line summary like "This chunk discusses the Heartfulness meditation technique from Sri Preethaji's 2023 talk on inner peace."
- Embed the context-enriched chunk: `context_sentence + "\n" + chunk_text`
- This dramatically improves retrieval precision for ambiguous chunks
- Cost: 1 LLM call per chunk at ingestion time (amortized, not per-query)
**Complexity:** L

### 4.3 Implement True Recursive RAPTOR (Multi-Level)
**Files:** `backend/ingest/raptor.py`
**Why:** Current RAPTOR is single-level (leaf + 1 summary). True RAPTOR recursively clusters summaries to create a tree.
**Fix:**
- After generating level-1 summaries, cluster those summaries and generate level-2 "meta-summaries"
- Continue until cluster count drops below threshold (e.g., < 3 clusters)
- At retrieval, search across all levels with `raptor_level` filter
- Higher levels provide thematic/conceptual answers; lower levels provide specific quotes
**Complexity:** L

### 4.4 Add Maximal Marginal Relevance (MMR) for Diversity
**Files:** `backend/services/qdrant_service.py`, `backend/rag/nodes.py`
**Why:** Top-5 results can all be near-duplicates from the same video segment.
**Fix:**
- After initial top-20 retrieval, apply MMR: iteratively select docs that are relevant to the query but dissimilar to already-selected docs
- Use `lambda * sim(doc, query) - (1-lambda) * max(sim(doc, selected_docs))` with lambda=0.7
- This ensures diversity of perspective in the context fed to the LLM
**Complexity:** M

### 4.5 Add Contextual Compression (Sentence-Level Reranking)
**Files:** new `backend/rag/compressor.py`, `backend/rag/nodes.py`
**Why:** Even after reranking, a 1500-char chunk may have only 2 relevant sentences. The rest dilutes the context.
**Fix:**
- Add a compression step between reranking and generation
- Split each reranked chunk into sentences, score each sentence against the query using the CrossEncoder (already loaded), keep only sentences above a score threshold
- No extra model needed — reuses the existing CrossEncoder. Runs in ~50ms for 40-50 sentences
- This concentrates the context on exactly the relevant evidence, improving generation precision
**Complexity:** M

### 4.5 Implement Agentic Query Routing
**Files:** `backend/rag/nodes.py`, `backend/rag/graph.py`
**Why:** Not all queries need the full pipeline. A greeting doesn't need CRAG+CoVe.
**Fix:**
- Replace the current binary `is_complex_query` with a 3-tier routing:
  - **Simple factual** (e.g., "What is Ekam?"): single retrieval + generation, no CRAG loop, no CoVe
  - **Complex analytical** (e.g., "Compare meditation techniques"): full pipeline with decomposition, CRAG, CoVe
  - **Experiential/personal** (e.g., "How do I find inner peace?"): retrieval + generation with extended hints, but lighter verification
- This reduces average LLM calls per query from 5-6 to 3-4 for simple queries
**Complexity:** M

### 4.6 Add Confidence-Based Answer Gating
**Files:** `backend/rag/nodes.py`, `backend/rag/states.py`
**Why:** Current pipeline uses binary pass/fail for faithfulness. A scored approach enables graduated responses.
**Fix:**
- Add `confidence_score: float` to GraphState
- In the combined verification step, ask the LLM to output a confidence 1-10
- Score < 3: return fallback ("I don't have enough information...")
- Score 3-6: return answer with caveat ("Based on what I found, though I recommend exploring further...")
- Score 7-10: return answer confidently with citations
**Complexity:** M

---

## Tier 5: Frontend & UX Improvements

### 5.1 Wire Backend Signals to Frontend
**Files:** `src/lib/aiService.ts`, `src/components/chat/ChatInterface.tsx`
**Problem:** Frontend ignores `intent`, `citations`, `blocked`, `block_reason`, `meditation_step`.
**Fix:**
- Parse all fields from the backend ChatResponse
- Display citations as clickable YouTube links below the guru's response
- When `intent === "DISTRESS"` and `meditation_step > 0`, automatically open the SereneMindModal
- When `blocked === true`, display `block_reason` as a system message instead of the fake placeholder quote
- Track `meditation_step` in component state and send it back on subsequent requests
**Complexity:** M

### 5.2 Add SSE Streaming to Frontend
**Files:** `src/lib/aiService.ts`, `src/components/chat/ChatInterface.tsx`
**Problem:** No streaming — user sees a loading indicator for 5-20 seconds.
**Fix:**
- In `custom` provider mode: use `fetch()` with `ReadableStream` to consume SSE events
- Display status events as subtle loading text ("Searching knowledge base...", "Generating answer...")
- Stream answer tokens into the chat bubble as they arrive
- Add an AbortController to cancel requests on component unmount or new message
**Complexity:** M

### 5.3 Fix Connection Check
**Files:** `src/lib/aiService.ts`
**Problem:** `checkConnection()` sends HEAD to a POST-only endpoint → always fails.
**Fix:** Change to `GET /api/health` instead.
**Complexity:** S

### 5.4 Add Conversation History Trimming
**Files:** `src/lib/aiService.ts`
**Problem:** Full chat history sent on every request, unbounded.
**Fix:** Trim to last 10 messages before sending to the backend. Add a `max_history` config option.
**Complexity:** S

---

## Implementation Priority Order

**Phase 1 — Fix What's Broken (Week 1):**
1. 1.3 Enable HyDE (S)
2. 1.5 Fix Metrics Bug (S)
3. 1.6 Consolidate Prompts (M)
4. 1.7 Unify Guardrail Model (S)
5. 2.1 Increase Chunk Size + Rerank Top-K (S — config only, needs re-ingestion)
6. 5.3 Fix Connection Check (S)
7. 5.4 Add History Trimming (S)

**Phase 2 — Core Accuracy Upgrades (Week 2-3):**
1. 1.1 Switch to bge-m3 + Fix Hybrid Search (L — requires re-ingestion, solves multilingual + hybrid in one shot)
2. 2.2 Incorporate Chat History (M)
3. 2.3 RAPTOR Level Filtering at Retrieval (M)
4. 2.4 Source Provenance in RAPTOR Summaries (S)
5. 2.5 Ingestion Deduplication (M)
6. 1.4 Fix Output Guardrail (M)

**Phase 3 — Latency Optimization (Week 3-4):**
1. 3.1 Reduce LLM Calls from 11 to 5-6 (L) — **biggest single improvement**
2. 3.6 Use Smaller Model for Classification (M)
3. 3.3 Parallelize Independent Calls (M)
4. 3.5 Optimize Corrector Speed (M)
5. 3.4 Add Response Caching (M)
6. 5.1 Wire Backend Signals to Frontend (M)

**Phase 4 — World-Class Techniques (Week 4-6):**
1. 3.2 Add Streaming Support (L)
2. 5.2 SSE Streaming Frontend (M)
3. 4.4 MMR for Diversity (M)
4. 4.5 Contextual Compression (M)
5. 4.6 Agentic Query Routing (M)
6. 4.7 Confidence-Based Answer Gating (M)
7. 2.6 Improve Self-RAG Cross-Verification (M)
8. 2.7 Multilingual Depression Detection (M)

**Phase 5 — Polish (Week 6+):**
1. 4.1 Parent-Child Chunking (L)
2. 4.2 Contextual Embedding (L)
3. 4.3 True Recursive RAPTOR (L)

---

## Files to Modify (Summary)

| File | Changes |
|---|---|
| `backend/app/config.py` | Add `rag_use_hyde`, update defaults for chunk_size, overlap, rerank_top_k, num_predict |
| `backend/.env.example` | Mirror new config fields |
| `backend/services/embedding_service.py` | Swap to BAAI/bge-m3 (dense+sparse+ColBERT), optional bge-reranker-v2-m3 |
| `backend/services/qdrant_service.py` | Named vectors (dense+sparse), RRF fusion via query_points(), MMR, dedup IDs, level filtering |
| `backend/services/ollama_service.py` | Import prompts from prompts.py, per-task temperature, streaming |
| `backend/rag/prompts.py` | Consolidate all prompts, add multi-turn template, batch grading prompt |
| `backend/rag/nodes.py` | Merge nodes, chat history usage, parallel retrieval, confidence scoring |
| `backend/rag/graph.py` | Rewire for merged nodes, agentic routing |
| `backend/rag/states.py` | Add `confidence_score` field |
| `backend/app/main.py` | Fix metrics, add SSE streaming endpoint, fix REQUEST_COUNT placement |
| `backend/guardrails/rails.py` | Fix output rail API usage |
| `backend/guardrails/config/config.yml` | Change model to sarvam-30b |
| `backend/ingest/pipeline.py` | Dedup check, parent-child chunking, contextual embedding |
| `backend/ingest/raptor.py` | Source provenance, recursive levels, parallel summarization |
| `backend/ingest/corrector.py` | Larger chunks, sentence-aware splitting, parallel correction |
| `backend/services/depression_detector.py` | Multilingual model or keyword pre-filter |
| `backend/requirements.txt` | Add FlagEmbedding>=1.2.10, optionally BAAI/bge-reranker-v2-m3 |
| `src/lib/aiService.ts` | SSE streaming, wire backend signals, fix connection check, history trimming |
| `src/components/chat/ChatInterface.tsx` | Display citations, auto-trigger meditation, stream tokens |

---

## Verification Plan

After each phase:
1. **Ingestion test:** Ingest a test YouTube video, verify chunks are created with both dense and sparse vectors, verify RAPTOR summaries have source provenance
2. **Retrieval test:** Query in English AND Hindi, verify multilingual retrieval returns relevant chunks
3. **Quality test:** Ask 10 test questions, verify:
   - Answers cite specific teachings (not generic spiritual advice)
   - Faithfulness check catches fabricated claims
   - CRAG loop triggers when initial docs are poor
   - Fallback response triggers when no relevant docs exist
4. **Latency test:** Measure end-to-end response time, target:
   - Time to first token (with streaming): < 3s
   - Total response time: < 8s for simple queries, < 15s for complex
5. **Frontend test:** Verify citations render, meditation flow triggers on distress, blocked messages show reason
6. **Metrics test:** Hit `/metrics` and verify REQUEST_COUNT, DEPRESSION_EVENTS counters are correct
7. **Multilingual test:** Send queries in Hindi, Telugu, Tamil — verify retrieval + generation quality

---

## Expected Impact Summary

| Metric | Current State | After Phase 2 | After Phase 5 (Final) |
|--------|--------------|---------------|----------------------|
| LLM calls per query | 11-13 sequential | 5-6 | 3-5 (adaptive routing) |
| Response latency | 25-70s | 10-15s | 3-8s (streamed: <2s to first token) |
| Context window utilization | 4% (~300 tokens of 8192) | 40% (~3300 tokens) | 50-60% (with compression) |
| Embedding languages | English only (384d) | 100+ languages (1024d bge-m3) | + sparse + ColBERT |
| Hybrid search | Broken (dense-only fallback) | Working (dense + sparse RRF) | + MMR diversity |
| Chat history | In state but NEVER used | Last 3 turns in generation | Full multi-turn context |
| Hallucination prevention | Weak (same model self-validates) | Stronger (batched + merged verify) | Multi-technique (CoVe + compression + confidence gating) |
| Chunk size | 500 chars (~100 tokens) | 1500 chars (~300 tokens) | Parent-child (500 retrieval / 2000 context) |
| RAPTOR | Single-level, no provenance | Source provenance added | True recursive multi-level |
| Depression detection | English only | Multilingual keyword pre-filter | + multilingual model |
| Re-ingestion | Creates duplicates | Deduplicated (uuid5) | + overwrite/skip modes |
| Frontend integration | Only reads `response` field | All fields wired (intent, citations, blocked, meditation) | + SSE streaming + AbortController |
| Reranker | MS-MARCO web search (English) | bge-reranker-v2-m3 (multilingual) | + sentence-level compression |
| Classification model | Sarvam 30B for everything | llama3.2:3b for classification | Adaptive per task |
| Output guardrail | Broken (wrong NeMo API) | Fixed (bot turn format) | + lightweight classifier option |
| Metrics | SUCCESS counted before execution | Correct placement | + per-stage latency + CRAG iteration count |
