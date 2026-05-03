# RAG & System Design Improvement Recommendations

> Based on analysis of "RAG Made Simple" (Nir Diamant, 2026) and "System Design for the LLM Era" (Sampriti Mitra, 2026), mapped to the Mukthi Guru 12-layer pipeline.

---

## Executive Summary

The current Mukthi Guru pipeline implements a strong foundation with CRAG, Self-RAG, CoVe, RAPTOR, and NeMo guardrails. Based on techniques from both reference books, there are **12 high-impact improvements** spanning retrieval quality, latency, grounding, and user feedback loops.

**Current Confidence Score: 6.5/10** — solid anti-hallucination pipeline, but retrieval precision, chunking strategy, and feedback loops need work for production excellence.

**Target Confidence Score: 9/10** — achievable with the improvements below.

---

## Priority 1: High Impact, Low Effort

### 1. Proposition Chunking (RAG Made Simple, Ch. 4)
- **Current**: `RecursiveCharacterTextSplitter(500 chars, 50 overlap)` — splits on character boundaries.
- **Recommended**: Break each chunk into atomic, self-contained propositions (single facts). Each proposition gets its own embedding.
- **Impact**: Eliminates retrieval of irrelevant co-located text. Improves relevance grading accuracy.
- **Effort**: Medium — requires LLM call during ingestion to decompose chunks.
- **Priority**: P0

### 2. Contextual Chunk Headers (RAG Made Simple, Ch. 7)
- **Current**: Chunks lose their source context (video title, speaker, topic).
- **Recommended**: Prepend each chunk with "Source: {video_title} | Speaker: {speaker} | Topic: {topic}" before embedding.
- **Impact**: 15-25% retrieval accuracy improvement. Chunks become self-documenting.
- **Effort**: Low — modify `ingest/pipeline.py` chunking step.
- **Priority**: P0

### 3. Fusion Retrieval (RAG Made Simple, Ch. 12)
- **Current**: Pure semantic search via Qdrant embeddings.
- **Recommended**: Combine semantic search with BM25 keyword search using Reciprocal Rank Fusion (RRF). Qdrant supports hybrid search natively.
- **Impact**: Catches exact keyword matches that embedding search misses (e.g., specific Sanskrit terms, guru names).
- **Effort**: Low — Qdrant payload indexing + RRF scoring in `qdrant_service.py`.
- **Priority**: P0

### 4. User Feedback Loops (RAG Made Simple, Ch. 17)
- **Current**: No feedback mechanism (being added in this sprint).
- **Recommended**: Use thumbs-up/down signals to:
  - Re-rank document relevance scores (boost docs cited in upvoted answers).
  - Fine-tune reranker weights.
  - Build a "golden question" dataset for offline evaluation.
- **Impact**: Continuous quality improvement without manual curation.
- **Effort**: Medium — requires feedback storage + periodic batch processing.
- **Priority**: P0

---

## Priority 2: High Impact, Medium Effort

### 5. HyDE — Hypothetical Document Embedding (RAG Made Simple, Ch. 6)
- **Current**: Direct query embedding for retrieval.
- **Recommended**: Generate a hypothetical answer first, embed that, then search. The hypothetical answer is closer in embedding space to real answers than the question is.
- **Impact**: 20-30% retrieval improvement for vague or philosophical questions (common in spiritual domain).
- **Effort**: Medium — one additional LLM call before retrieval.
- **Priority**: P1

### 6. Semantic Chunking (RAG Made Simple, Ch. 9)
- **Current**: Fixed 500-char splits.
- **Recommended**: Split text at semantic boundaries by computing embedding similarity between adjacent sentences. Split where similarity drops below threshold.
- **Impact**: Each chunk becomes a coherent thought unit. Reduces "split mid-concept" retrieval noise.
- **Effort**: Medium — requires sentence-level embedding during ingestion.
- **Priority**: P1

### 7. Context Engineering (System Design for LLM Era, Ch. 1.27)
- **Current**: System prompt + retrieved docs + chat history in a flat context.
- **Recommended**: Structured context layers:
  1. **Persona layer**: Guru personality, teaching style
  2. **Knowledge layer**: Retrieved docs with relevance scores
  3. **User state layer**: Meditation history, emotional state, preferences
  4. **Conversation layer**: Summarized history (not raw)
  5. **Instruction layer**: Output format, safety constraints
- **Impact**: Better grounding, fewer hallucinations, more personalized responses.
- **Effort**: Medium — refactor `prompts.py` and `generate_answer` node.
- **Priority**: P1

### 8. Adaptive Retrieval (RAG Made Simple, Ch. 18)
- **Current**: Always retrieves documents regardless of query type.
- **Recommended**: Route queries through a classifier:
  - CASUAL → No retrieval needed (direct LLM response)
  - FACTUAL → Full RAG pipeline
  - FOLLOW_UP → Use conversation context + minimal retrieval
  - MEDITATION → Direct to Serene Mind (no retrieval)
- **Impact**: 40-60% latency reduction for non-retrieval queries. Better user experience.
- **Effort**: Low — `intent_router` already exists, just needs expanded routing logic.
- **Priority**: P1

---

## Priority 3: Advanced Techniques

### 9. Explainable Retrieval (RAG Made Simple, Ch. 19)
- **Current**: Citations show source URLs but no explanation of why a source was selected.
- **Recommended**: Generate a brief explanation for each cited source: "This source was selected because it discusses [topic] in the context of [query intent]."
- **Impact**: Builds user trust. Helps admin review retrieval quality.
- **Effort**: Medium — additional LLM call or prompt modification.
- **Priority**: P2

### 10. Graph RAG Integration (RAG Made Simple, Ch. 21)
- **Current**: LightRAG service exists but is underutilized. Linear retrieval only.
- **Recommended**: Build a knowledge graph of teaching concepts, interconnections between teachings, and guru-concept relationships. Use for multi-hop reasoning.
- **Impact**: Handles complex relational queries ("How does Sri Krishnaji's teaching on X relate to Sri Preethaji's Y?").
- **Effort**: High — requires entity extraction + graph construction during ingestion.
- **Priority**: P2

### 11. Low-Latency Architecture (System Design for LLM Era, Ch. 2.2)
- **Current**: Sequential pipeline (intent → retrieve → rerank → grade → generate → verify).
- **Recommended**:
  - **Speculative execution**: Start generation while verification runs in parallel.
  - **Streaming with early flush**: Send the first sentence as soon as it's generated.
  - **Semantic cache**: Already implemented (responseCache.ts). Expand to backend with Redis.
  - **Connection pooling**: Persistent connections to Qdrant and Ollama.
  - **Batch embeddings**: Embed multiple sub-queries in a single batch call.
- **Impact**: 50-70% latency reduction (target: <1.5s for cached, <3s for fresh).
- **Effort**: Medium-High.
- **Priority**: P1

### 12. Production Observability (System Design for LLM Era, Ch. 2.5)
- **Current**: Basic logging. Admin console with trace viewer.
- **Recommended**:
  - Per-query confidence scores (already being added).
  - Token usage tracking per conversation.
  - Retrieval precision metrics (using feedback signal).
  - A/B testing framework for prompt variants.
  - Automated regression detection on RAGAS eval scores.
- **Impact**: Data-driven improvement cycle.
- **Effort**: Medium.
- **Priority**: P2

---

## Implementation Roadmap

| Phase | Techniques | Timeline | Confidence Gain |
|-------|-----------|----------|----------------|
| **Phase 1** | Contextual Headers, Fusion Retrieval, Feedback Loops | Week 1-2 | 6.5 → 7.5 |
| **Phase 2** | Proposition Chunking, Adaptive Retrieval, Context Engineering | Week 3-4 | 7.5 → 8.5 |
| **Phase 3** | HyDE, Semantic Chunking, Low-Latency | Week 5-6 | 8.5 → 9.0 |
| **Phase 4** | Graph RAG, Explainable Retrieval, Observability | Week 7-8 | 9.0 → 9.5 |

---

## Architecture Alignment

Both books emphasize that production RAG systems need:
1. **Layered retrieval** (not just vector search) — we need Fusion Retrieval
2. **Self-correcting loops** (CRAG) — already implemented ✅
3. **Verification gates** (Self-RAG + CoVe) — already implemented ✅
4. **User feedback integration** — being added now
5. **Context engineering over prompt engineering** — next priority
6. **Observability and evaluation** — admin console exists, needs expansion

The Mukthi Guru pipeline is architecturally sound. The main gaps are in **retrieval diversity** (fusion search), **chunk quality** (proposition + semantic chunking), and **continuous learning** (feedback loops).
