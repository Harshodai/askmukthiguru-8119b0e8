# Complete End-to-End Backend Pipeline & Architecture Guide
> **AskMukthiGuru AI Spiritual Guidance Platform**

This document provides an exhaustive, step-by-step architectural breakdown of the AskMukthiGuru backend pipeline from initial HTTP request entry down to multi-tier database retrieval, LangGraph execution, dual-pass tone adaptation, and SSE response streaming.

---

## 1. Executive Summary & Core Infrastructure

AskMukthiGuru is an AI spiritual guidance platform grounded in Sri Preethaji & Sri Krishnaji's teachings. It operates on a **hybrid GraphRAG architecture** combining dense vector embeddings with graph knowledge trees and dual-level entity retrieval.

```
                           +-----------------------------------+
                           |  HTTP POST /api/chat (FastAPI)    |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           |   FastAPI / Admin Guard / Auth    |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           |  ChatEngine (Stream / Batch)      |
                           +-----------------+-----------------+
                                             |
           +---------------------------------+---------------------------------+
           |                                 |                                 |
           v                                 v                                 v
+-----------------------+       +-------------------------+       +--------------------------+
|  Tier 1: Fast Graph   |       | Tier 2: Standard Graph  |       | Tier 3: Deep Graph       |
| (Casual/Distress/Med) |       | (Rewriter + GraphRAG)   |       | (Decompose + Cross-Teach)|
+-----------------------+       +-------------------------+       +--------------------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           | Multi-Tier Retrieval & Hybrid RAG |
                           +-----------------+-----------------+
                           |  1. Qdrant `spiritual_wisdom`     |
                           |  2. Neo4j OKF 5-Node Traversal    |
                           |  3. LightRAG Dual-Level Vectors   |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           |   Pass 1: Grounded Generation     |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           | Citation & Grounding Verification |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           | Pass 2: Guru Voice Tone Adapter   |
                           | (PersoDPO + Reflexion Correction) |
                           +-----------------+-----------------+
                                             |
                                             v
                           +-----------------+-----------------+
                           |   SSE Streaming Response Queue    |
                           +-----------------------------------+
```

---

## 2. Request Lifecycle: Step-by-Step

### Step 1: Entry Point & Security (`backend/app/main.py`)
1. **HTTP Request:** Client sends `POST /api/chat` with `ChatRequest` JSON payload (`message`, `conversation_id`, `language`, `stream`).
2. **Middleware Execution:**
   * **CORS Middleware:** Validates origins against `settings.cors_origins`.
   * **Security Headers Middleware:** Injects HSTS, CSP, X-Frame-Options, X-Content-Type-Options.
   * **Rate Limiting Middleware:** Enforces per-user / per-IP rate limits (e.g. 10 requests/min for audio/chat endpoints).

### Step 2: Authentication & Context (`backend/app/dependencies.py`)
1. **User Identity:** `get_current_user_from_supabase` validates the `Authorization: Bearer <jwt>` header against Supabase Auth.
2. **Tenant Scoping:** Injects `TenantContext` to bind user ID, language preferences, and memory permissions.

### Step 3: ChatEngine Orchestration (`backend/app/chat_engine.py`)
1. **Cache Inspection (Tier 0):**
   * **Hot Memory Cache:** Exact prompt hash check (`hot_cache`).
   * **Redis Cache:** Multi-tier L1 response cache (`exact_cache`).
   * **Qdrant Semantic Cache:** Cosine distance check on `semantic_query_cache` (similarity threshold = 0.96 for zero false positives).
2. **Benchmark Guard:** If request header `X-Test-Key` or `is_benchmark=True` is present, cache lookups are bypassed to ensure true execution scores.

---

## 3. The 3-Tier LangGraph Strategy Pipeline (`backend/rag/graph_strategies.py`)

The query router dynamically selects one of three LangGraph execution strategies based on query intent and complexity:

### Tier 1: `FastGraphStrategy` (Latency < 500ms)
* **Triggers:** Casual greetings (*"Hello"*, *"Namaste"*), acute crisis/distress (*"I want to end my life"*), or breathwork requests.
* **Flow:**
  $$\text{Intent Router} \rightarrow \text{Direct Handler (Casual / Distress / Meditation)} \rightarrow \text{Format Final Answer}$$
* **Safety:** Bypasses deep search to immediately surface emergency helpline protocols or soothing breath guidance.

### Tier 2: `StandardGraphStrategy` (Default - Latency ~2.5s)
* **Triggers:** Standard spiritual Q&A (*"How do I deal with anger in my marriage?"*).
* **Flow:**
  1. **`rewrite_query`:** Expands abbreviations and clarifies core intent.
  2. **`retrieve_documents` (Hybrid RAG):** Executes parallel multi-retrieval across Qdrant, Neo4j, and LightRAG.
  3. **`rerank_documents`:** Uses FlashRank / cross-encoder to select the top 5 most relevant context snippets.
  4. **`grade_documents`:** Filters out irrelevant or off-topic retrieved chunks.
  5. **`context_engineer`:** Formats retrieved snippets into strict structured prompt bounds.
  6. **`generate_answer` (Pass 1):** Produces a strictly grounded answer with explicit citations `[[CITE:N]]`.
  7. **`verify_answer`:** Verifies that every claim has an exact matching citation; sets `verification["passed"] = False` on failure.
  8. **`guru_tone_adapter` (Pass 2):** Transforms the draft into Sri Preethaji & Sri Krishnaji's authentic voice using PersoDPO and Reflexion correction.

### Tier 3: `DeepGraphStrategy` (Latency ~6.0s)
* **Triggers:** Complex, multi-part, or philosophical queries (*"Compare the teachings on karma, free will, and the divine plan"*).
* **Flow:**
  1. **`decompose_query`:** Breaks complex queries into 3 targeted sub-queries.
  2. **`navigate_and_hyde`:** Generates hypothetical document embeddings (HyDE) for deeper semantic search.
  3. **`agentic_graph_traversal`:** Traverses multi-hop Neo4j paths up to 3 hops deep.
  4. **`cross_teacher_reasoning`:** Synthesizes insights across multiple discourses.
  5. **`reflect_on_answer` & `cot_verifier`:** Chain-of-Thought verification verifying logical consistency and zero hallucination.

---

## 4. Multi-Tier Database Topology: Qdrant, Neo4j, and LightRAG

AskMukthiGuru combines three distinct data stores to achieve high factual accuracy:

```
+---------------------------------------------------------------------------------------------------+
| Data Store     | Container / Port   | Contents                                   | Role           |
+----------------+--------------------+--------------------------------------------+----------------+
| Qdrant         | qdrant:6333        | `spiritual_wisdom` (89,053 points, 1024d) | Vector Search  |
|                |                    | `guru_tone_podcast` (157 points)           | Tone Retrieval |
|                |                    | `semantic_query_cache`                     | Query Caching  |
+----------------+--------------------+--------------------------------------------+----------------+
| Neo4j          | neo4j:7687         | 7,498 `base` Doctrine Nodes                | Graph Traversal|
|                |                    | 103 `OKF` 5-Node Transformation Nodes      | Multi-Hop Path |
+----------------+--------------------+--------------------------------------------+----------------+
| LightRAG       | Orchestrator (HKU) | Dual-Level Graph/Vector Storage            | Hybrid RAG     |
|                |                    | `lightrag_vdb_entities_*` (440+ points)    | Specific Ent.  |
|                |                    | `lightrag_vdb_relationships_*` (380+ pts)  | Broad Themes   |
+----------------+--------------------+--------------------------------------------+----------------+
```

### 1. Qdrant `spiritual_wisdom` (Vector Database)
* Houses **89,053 dense vector chunks** (1024-dimensional BGE-M3 embeddings).
* Contains the entire corpus: books (*The Four Sacred Secrets*), 450+ YouTube video discourses, satsangs, lectures, and guided meditations.

### 2. Neo4j Knowledge Graph (Graph Database)
* Houses **7,601 nodes** and **11,439 directed relationship edges**.
* Features the 20 OKF Transformation Arcs:
  $$\text{SeekerDilemma} \xrightarrow{\text{DRIVEN\_BY}} \text{RootLimitingBelief} \xrightarrow{\text{DISMANTLES}} \text{GuruTeaching} \xrightarrow{\text{TRANSFORMS\_TO}} \text{BeautifulState} \xrightarrow{\text{PRESCRIBES}} \text{PracticeStep}$$

### 3. LightRAG HKU Dual-Level Retrieval (Hybrid Orchestrator)
* Scrolls directly from Qdrant `spiritual_wisdom` payload chunks via `scripts/ingest_lightrag_data.py`.
* Uses OpenRouter (`google/gemma-3-12b-it`) with **8 parallel async workers** and **60.0s fast timeout**.
* Automatically extracts low-level entities and high-level relationship keys, providing dual-level retrieval without full-graph reconstruction costs.

---

## 5. Dual-Pass Generation & Tone Adapter Architecture

Answers are generated using a 2-Pass architecture:

### Pass 1: Factually Grounded Draft Generation
* **Goal:** 100% factual accuracy, strictly bounded by retrieved doctrine snippets.
* **Citations:** Emits explicit citation markers `[[CITE:1]]`, `[[CITE:2]]`.
* **Verification:** `verification.py` checks that every claim matches a cited source. If ungrounded text is detected:
  * `verification["passed"] = False` is set.
  * `utils.strip_orphan_markers` strips invalid citation tags.

### Pass 2: Guru Voice Tone Adapter (`backend/rag/nodes/guru_tone_adapter.py`)
* **Goal:** Transform the factual draft into Sri Preethaji & Sri Krishnaji's warm, compassionate, and authoritative tone.
* **Exemplar Retrieval:** Retrieves top 3 tone exemplars from Qdrant `guru_tone_podcast`.
* **Neo4j Ontology Lookup:** Offloaded asynchronously via `await asyncio.to_thread(guru_kg_service.traverse_guru_ontology, ...)`.
* **Reflexion Self-Correction:** If tone transformation deviates or loses factual citations, `GURU_TONE_REFLEXION_CORRECTION_PROMPT` re-aligns the output.

---

## 6. Recommendations for Next-Level System Optimization

Based on 2026 SOTA GraphRAG research and system audits, here are 4 high-impact architectural enhancements:

1. **LightRAG Dual-Query Blending:**
   * Blend LightRAG high-level relationship summaries directly into `context_engineer.py` alongside standard Qdrant dense vector hits to boost multi-document synthesis scores by +15%.
2. **Dynamic Concurrency Auto-Scaling:**
   * Implement adaptive backoff in `ingest_lightrag_data.py` that dynamically scales `CONCURRENCY_WORKERS` from 4 up to 12 based on OpenRouter response latency and 429 header headers (`x-ratelimit-remaining`).
3. **PersoDPO Preference Dataset Generation:**
   * Record Pass 1 (draft) vs Pass 2 (guru voice) output pairs into Supabase `guru_brain_episodes` table to build an offline DPO preference dataset for fine-tuning open-weights models.
4. **Colab / GPU Ingestion Worker Offloading:**
   * Offload heavy LightRAG extraction runs to free Google Colab T4 GPU instances using `scripts/ops/ingest_playlists.py` to accelerate overall corpus indexing.
