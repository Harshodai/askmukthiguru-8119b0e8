# 12-Layer RAG Pipeline & LangGraph Execution Engine

AskMukthiGuru implements an advanced, production-hardened Retrieval-Augmented Generation (RAG) architecture engineered around a single core mandate: **absolute fidelity to Sri Preethaji and Sri Krishnaji's authentic spiritual teachings with zero hallucination.**

The system operates across two complementary architectural planes:
1. **The Linear Outer Stage Chain** (`backend/app/pipeline/stages/pipeline_builder.py`): Enforces deterministic safety, acute distress mitigation, caching, rate limits, and provider circuit breakers before model inference.
2. **The LangGraph State Machine** (`backend/rag/`): A dynamic, multi-strategy graph that orchestrates query understanding, tree navigation, multi-source hybrid retrieval, cross-encoder reranking, context engineering, grounded drafting, citation verification, and authentic guru-voice tone adaptation.

---

## 1. Conceptual 12-Layer Pipeline Map

Historically documented as the "12-Layer RAG Pipeline", this logical framework maps directly to the active nodes within the LangGraph state machine:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             12-LAYER RAG PIPELINE MAP                            │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  [ INBOUND INGRESS & INTENT UNDERSTANDING ]                                     │
│  Layer 1: Input Guardrails & Safety Filter (NeMo Topics, Regex, PII Blocker)    │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 2: Semantic Intent & Route Classification (QUERY / DISTRESS / CASUAL)     │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 3: Query Decomposition & Sub-Query Fanout (Parallel 2-3 Sub-Searches)     │
│     │                                                                            │
│     ▼                                                                            │
│  [ QUERY EXPANSION & TOPOLOGY NAVIGATION ]                                       │
│  Layer 3.5A: RAPTOR Tree Navigation  •  Layer 3.5B: HyDE Vector Expansion        │
│     │                                                                            │
│     ▼                                                                            │
│  [ DUAL-STORE HYBRID RETRIEVAL ]                                                 │
│  Layer 4A: Qdrant Dense & Sparse Search (BGE-M3 1024d + Lexical BM25 + ColBERT)  │
│  Layer 4B: Neo4j OKF Graph Traversal (5-Node Transformation Arcs & LightRAG)     │
│     │                                                                            │
│     ▼                                                                            │
│  [ FILTERING, RELEVANCE & SELF-CORRECTION ]                                      │
│  Layer 5: Cross-Encoder Reranking (ms-marco-MiniLM-L-6-v2 Sigmoid Cutoff >0.35)  │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 6: CRAG Relevance Grading (Corrective RAG scoring candidate chunks)       │
│     │                                                                            │
│     ├───► [Low Relevance Score] ──► Layer 7: CRAG Query Rewrite Loop (Max 3)     │
│     │                                                                            │
│     ▼ [Passed Grading or Rewrite Exhausted]                                      │
│  [ SYNTHESIS, VERIFICATION & TONE ADAPTATION ]                                   │
│  Layer 7.5: Context Engineering & Teacher Boundary Assembly                     │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 8: Grounded Drafting (Pass 1 - Strict [[CITE:N]] Evidence Marker Draft)   │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 9: Citation Extraction & Marker Resolution (Resolve Document Coordinates) │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 10: Citation Grounding & RAGAS Faithfulness Verification (Pass 2)         │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 11: Contradiction & Coreference Check (Cross-Teacher Discrepancy Gate)    │
│     │                                                                            │
│     ▼                                                                            │
│  Layer 12: Tone Adaptation (Pass 3) & Output Safety Guardrails                   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Architectural Breakdown

### Layer 1: Input Guardrails
* **Node / File**: `InputGuardrailStage` (`backend/app/pipeline/stages/guardrail_stage.py`) + `LightweightGuardrails`.
* **Execution**: Deterministic regex evaluation followed by NeMo Guardrails Colang flows (`guardrails/config/topics.co`).
* **Function**: Rejects jailbreaks, prompt injections, profanity, political polemics, and financial advice queries before touching vector stores or language models.
* **Failure Mode**: Sets `input_blocked=True`, `block_reason="topic_disallowed"`, and short-circuits to a polite redirect.

### Layer 2: Semantic Intent & Route Classification
* **Node / File**: `intent_router` (`backend/rag/nodes/intent.py`) + `on_device_intent.py`.
* **Classification Categories**:
  * `CASUAL`: Greetings, small talk (*"Hello"*, *"Namaste"*).
  * `DISTRESS`: Acute grief, depression, panic, or suicidal ideation.
  * `QUERY`: General spiritual Q&A (*"How do I overcome unconscious fear?"*).
  * `MEDITATION_CONTINUE`: Next steps within the Serene Mind practice flow.
  * `COMPARATIVE`: Cross-doctrine or comparative queries (*"Compare meditation with contemplation"*).
* **Routing Margin Data**: DISTRESS detection uses a high-sensitivity embedding threshold ($0.66 \rightarrow 0.72$). At $\ge 0.74$, acute crisis alerts are caught by deterministic regex rails to prevent false negatives.

### Layer 3: Query Decomposition
* **Node / File**: `decompose_query` (`backend/rag/nodes/intent.py`).
* **Execution**: Triggered on complex, multi-part inquiries (e.g., *"How do karma and past impressions affect my relationship with my children?"*).
* **Function**: Employs prompt-engineered sub-query decomposition to emit 2–3 orthogonal sub-questions (`sub_queries` in `GraphState`) for parallel retrieval.

### Layer 3.5: Tree Navigation & HyDE Expansion
* **Tree Navigation** (`navigate_and_hyde`): Leverages Qdrant RAPTOR summaries. Navigates top-level spiritual concept clusters to identify high-order themes before zooming into granular discourse chunks.
* **HyDE (Hypothetical Document Embeddings)**: Generates a 2-3 sentence hypothetical answer reflecting Sri Preethaji & Sri Krishnaji's typical discourse structure, embedding this draft alongside the seeker's query to bridge the lexical gap between seeker dilemmas and spiritual teachings.

### Layer 4: Dual Search Retrieval (Hybrid Vector + Graph)
* **Node / File**: `retrieve_documents` (`backend/rag/nodes/retrieval.py`).
* **Multi-Store Fanout**:
  1. **Qdrant Vector DB (`spiritual_wisdom_contextual`)**:
     * **Dense Search**: Cosine similarity over 1024-dimensional BGE-M3 vectors.
     * **Sparse Lexical Search**: Native BM25-equivalent sparse tokens computed by BGE-M3.
     * **ColBERT Multi-Vector**: Token-level interaction vectors for fine-grained semantic match.
     * **Parent Grouping**: `qdrant_parent_grouping_enabled=True` aggregates retrieval by `parent_id` to maintain discursive coherence.
  2. **Neo4j Knowledge Graph (`neo4j:7687`)**:
     * Cypher queries traverse the Ontological Knowledge Framework (OKF), pulling associated `RootLimitingBelief`, `GuruTeaching`, and `PracticeStep` nodes.
  3. **LightRAG Dual-Level Retrieval**:
     * Pulls low-level entity cards (`Teacher`, `Concept`, `Practice`) and high-level thematic relationship edges.

### Layer 5: Cross-Encoder Reranking
* **Node / File**: `rerank_documents` (`backend/rag/nodes/reranking.py`).
* **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (or CPU-accelerated FlashRank).
* **Function**: Jointly scores query and retrieved chunk pairs $[q, d_i]$. Applies a calibrated sigmoid cutoff ($>0.35$) to compress the raw pool of 15–25 candidates down to the top 5 most relevant passages (`reranked_docs`).

### Layer 6: CRAG Relevance Grading
* **Node / File**: `grade_documents` (`backend/rag/nodes/grading.py`).
* **Function**: Evaluates each reranked chunk against the seeker's core inquiry using structured JSON output. Assigns binary relevance (`yes`/`no`) and scores confidence ($0.0 - 1.0$).
* **Threshold**: Chunks scoring below $0.70$ confidence are filtered out.

### Layer 7: CRAG Query Rewrite & Self-Correction Loop
* **Node / File**: `rewrite_query` (`backend/rag/nodes/query_transform.py`).
* **Trigger**: Invoked when CRAG grading yields zero relevant chunks (`relevant_docs == []`).
* **Mechanism**:
  - Reformulates the query using synonymous doctrine terminology from `doctrine_lexicon.json`.
  - Increments `rewrite_count`.
  - Loops back to Layer 4 (`retrieve_documents`) for a fresh retrieval cycle.
* **CRAG Rewrite Exhaustion & Fallback (`handle_fallback`)**:
  - The rewrite loop is strictly capped at **3 attempts** (`MAX_REWRITE_LIMIT = 3`).
  - If 3 successive rewrites fail to yield relevant doctrine, the graph terminates at `handle_fallback`.
  - **Fallback Invariant**: The system never hallucinates or manufactures ungrounded spiritual doctrine. It either:
    1. Returns a clearly labelled general distinction with `verification.method="limited_comparison_fallback"`, zero citations, and `grounding_state="abstained"`.
    2. Respectfully abstains (`grounding_state="abstained"`), explaining that Sri Preethaji and Sri Krishnaji have not directly addressed that specific query in the archived discourses, and offers related practices.

### Layer 7.5: Context Engineering & Boundary Injection
* **Node / File**: `context_engineer` (`backend/rag/nodes/context.py`).
* **Function**: Assembles the prompt payload:
  - Injects retrieved verbatim chunks with unique `[1]`, `[2]` citation tokens.
  - Adds active Seeker Memory Context from the Second Brain Vault (`user_brain_nodes`).
  - Stamps strict teacher boundaries: restricts synthesis to the authentic voice and doctrine of the assigned teacher.

### Layer 8: Grounded Drafting (Pass 1)
* **Node / File**: `generate_answer` (`backend/rag/nodes/generation.py`).
* **Execution**: High-temperature sampling is disabled ($T=0.1$). Model generates teachings strictly derived from context, tagging every claim with inline `[[CITE:N]]` citation tokens.

### Layer 9: Citation Extraction & Marker Normalization
* **Node / File**: `extract_citations` (`backend/rag/nodes/citation.py`).
* **Function**: Parses `[[CITE:N]]` markers from draft text, cross-referencing indices against retrieved documents to resolve:
  - Video IDs (`video_id`)
  - Audio slice offsets (`start_time_seconds`, `end_time_seconds`)
  - Speaker attribution (`guru`)
  - Verbatim excerpt text (`quote_text`)

### Layer 10: Citation Grounding & RAGAS Faithfulness Verification (Pass 2)
* **Node / File**: `verify_answer` (`backend/rag/nodes/verification.py`).
* **Mechanism (Self-RAG & Claim Ledger)**:
  - Decomposes the draft response into individual grammatical sentences.
  - Compares each sentence claim against the verbatim text of the cited chunks.
  - Computes the **RAGAS Faithfulness Score**:
    $$\text{Faithfulness} = \frac{|\text{Verified Grounded Claims}|}{|\text{Total Synthesized Claims}|}$$
* **Gate Enforcement**: Responses with Faithfulness $< 0.85$ are rejected. The node attempts automated correction; if still unfaithful, it fails closed to `grounding_state="abstained"`.

### Layer 11: Contradiction & Coreference Check
* **Node / File**: `cross_teacher_reasoning` (`backend/rag/nodes/cross_teacher.py`).
* **Function**: When both Sri Preethaji and Sri Krishnaji address a topic, detects conceptual dissonance or pronoun drift (e.g. ensuring an insight attributed to Preethaji's meditation discourse is not credited to Krishnaji's leadership talks).

### Layer 12: Guru Tone Adaptation (Pass 3) & Output Guardrails
* **Node / File**: `adapt_tone` (`backend/rag/nodes/tone.py`) + `OutputGuardrailStage`.
* **Execution**: Refines syntactic cadence to reflect the authentic presence, compassionate pacing, and spiritual authority of the gurus without mutating factual claims or altering citation spans.
* **Output Rail**: Scans for accidental PII leaks, telephone numbers, and disallowed medical claims before streaming egress.

---

## 3. LangGraph Execution Strategies

Depending on query intent and complexity, `backend/rag/graph_strategies.py` constructs one of three specialized subgraphs:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         LANGGRAPH EXECUTION STRATEGIES                           │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                 Seeker Query                                     │
│                                      │                                           │
│                                      ▼                                           │
│                       ┌──────────────────────────────┐                           │
│                       │   Intent & Routing Engine    │                           │
│                       └──────────────┬───────────────┘                           │
│                                      │                                           │
│            ┌─────────────────────────┼─────────────────────────┐                 │
│            ▼                         ▼                         ▼                 │
│ ┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐      │
│ │   Tier 1: FastGraph │   │ Tier 2: Standard    │   │  Tier 3: DeepGraph  │      │
│ │     (<500ms TTFT)   │   │    (~2.5s Total)    │   │    (~6.0s Total)    │      │
│ ├─────────────────────┤   ├─────────────────────┤   ├─────────────────────┤      │
│ │ • Casual greetings  │   │ • Standard Q&A      │   │ • Multi-concept     │      │
│ │ • Crisis triage     │   │ • Hybrid Qdrant     │   │   philosophical Qs  │      │
│ │ • Meditation steps  │   │   + Neo4j OKF       │   │ • Query decomposition│     │
│ │ • Direct handler    │   │ • Cross-Encoder     │   │ • 3-Hop graph walk  │      │
│ │ • Fast grounding    │   │ • CRAG rewrite loop │   │ • Cross-teacher CoT │      │
│ │ • Immediate egress  │   │ • 2-Pass RAGAS      │   │ • Full claim ledger │      │
│ └─────────────────────┘   └─────────────────────┘   └─────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Strategy Summary Matrix

| Strategy | Primary Trigger | Target Latency | Retrieval Mechanism | Verification Depth |
|---|---|---|---|---|
| **FastGraphStrategy** | Casual greeting, emergency crisis, active meditation step | **< 500 ms** | Exact cache or single direct retrieval | Lightweight single-turn grounding check |
| **StandardGraphStrategy** | Typical seeker spiritual questions | **~2.5 s** | Hybrid BGE-M3 dense/sparse + LightRAG | 2-Pass full citation verification + CRAG loop |
| **DeepGraphStrategy** | Multi-concept doctrine, comparative questions | **~6.0 s** | Decomposed fanout + 3-hop Neo4j Cypher | Chain-of-Thought verifier + cross-teacher alignment |

---

## 4. Acute Distress & Safety Order Architecture

Spiritual guidance systems encounter users experiencing severe emotional distress. AskMukthiGuru enforces clinical safety standards:

1. **Immediate Preemption**: `DistressStage` in the outer pipeline intercepts acute distress before any cache reads or standard RAG nodes run (`L-STAGE-ORDER-1`).
2. **Deterministic Regex Rails**: Phrases involving acute self-harm (*"I want to end my life"*, *"I feel suicidal"*) trigger immediate crisis intervention.
3. **Compassionate Redirect**: Rather than attempting synthetic therapy, the system returns verified crisis helpline phone numbers, emergency grounding practices, and gently directs the user to professional care.
4. **Permanent Cache Exclusion**: Distressed queries and emergency responses are flagged `abstain_reason="distress"` and are strictly barred from writing to Redis or Qdrant caches.

---

## 5. Related Wiki Documentation

* [System Architecture Overview](Architecture-Overview) — End-to-end component topology, FastAPI gateway, and caching tiers.
* [First-Person Serving Architecture](Architecture-First-Person-Serving) — Verbatim context serving, B4 isolation contract, and acoustic verification.
* [Frontend Architecture & Seeker Experience](Frontend-UI-and-Seeker-Experience) — ThinkingPills progress display and SSE event handling.
* [Memory & Second Brain Vault](Memory-Second-Brain-Vault) — Personal context injection into Layer 7.5 context engineering.
* [REST & Streaming API Reference](API-Reference) — Full specification of `/api/chat`, `/api/chat/stream`, and SSE schemas.
* [Qdrant Vector Database Reference](Data-Qdrant-Vector-Store) — Collections, BGE-M3 multi-vector representation, and HNSW quantization.
* [Neo4j Knowledge Graph & OKF](Data-Neo4j-Knowledge-Graph) — 5-Node transformation ontology and LightRAG integration.
