# Forensic Architectural Audit & Ruthless Challenge: First-Person Verbatim Pipeline vs. Normal Enterprise RAG Stack

**Date:** 2026-09-26  
**Auditor:** Multi-Agent Deep Codebase Inspection Fleet (16 Audited Dimensions)  
**Target:** Claude Code / Engineering Team  
**Governing Invariant:** *An answer in First-Person mode is strictly a validated pointer to authentic recorded discourse with exact seconds and verified speaker identity — never LLM-fabricated teaching prose.*

---

## Executive Summary: The Architectural Disparity Matrix

A forensic audit of the repository reveals a profound architectural chasm between the **Normal Conversational RAG Route** (`/api/chat` / `backend/rag/` / `backend/app/pipeline/`) and the **First-Person Verbatim Route** (`/api/first-person/query` / `backend/services/first_person_pipeline.py` / `src/pages/TeacherWords.tsx`).

While `/api/chat` was engineered as an enterprise-grade, multi-stage, self-correcting cognitive engine with graph traversal, multilingual routing, distributed rate limiting, and dense telemetry, `/api/first-person/query` was constructed as an isolated, single-pass vector lookup that ignores virtually every supporting system in the repository.

| Architectural Dimension | Normal Conversational RAG (`/api/chat`) | First-Person Verbatim Route (`/api/first-person/query`) |
| :--- | :--- | :--- |
| **Retrieval Strategy** | Multi-hop Hybrid (Dense BGE-M3 + Sparse BM25 + Qdrant MMR + ColBERT Cross-Encoder) | Bare bi-encoder dense cosine lookup (`first_person_v2`) |
| **Corrective RAG (CRAG)** | Relevance grading (`BATCH_GRADE_PROMPT`), adaptive score floors, query rewriting loop | None; immediate exit or abstention on low cosine similarity |
| **Hypothetical Doc Embeddings** | Concurrent HyDE (`HYDE_PROMPT` in `navigate_and_hyde`) across 4 LLM providers | None; queries embedded strictly verbatim |
| **Knowledge Graph (GraphRAG)** | 6,430 Memgraph nodes, 4,194 relationships, LightRAG dual-level vectors (12,882 points) | Completely disconnected; zero graph awareness |
| **Ontological Framework (OKF)** | 672 markdown files, 17.6 MB `compiled.json` with 1.10x curation boost | None; doctrine terms unmapped |
| **Hierarchical Summaries** | RAPTOR tree navigation (`raptor_level == 1` clusters) | Single flat clip points only |
| **Multilingual & Indic Script** | Dynamic 3-tier translation (Gemini $\to$ Sarvam $\to$ Ollama) preserving citation markers | Raw query passed to BGE-M3; zero translation, severe Indic recall penalty |
| **Input Guardrails & Safety** | Multilingual text detection, `_BLOCKED_TOPICS`, persona allowlist, crisis diversion | Only checks `DistressLevel.SEVERE` (suicide); toxic/abusive inputs search vector DB |
| **Rate Limiting & Abuse** | Redis-backed distributed Lua script token bucket (`TokenBucketMiddleware`) | Skipped (`if not path.startswith('/api/chat')`); in-process SlowAPI fallback only |
| **Observability & Tracing** | Jaeger OpenTelemetry spans, Prometheus metrics across all stages | Explicitly excluded in `DEFAULT_FASTAPI_EXCLUDED_URLS`; Jaeger is blind to First-Person |
| **Audio Ingestion & Quality** | Dual ASR voting (Whisper Large-v3 + Parakeet), ECAPA-TDNN diarization, CTC alignment | Word timestamps, word confidence, voiceprint scores, and ROVER disputed flags **dropped** |
| **Caching Architecture** | Multi-tier: exact cache + semantic vector cache (0.92 cosine threshold) | Redis SHA-256 exact match only; **fails to invalidate on video quarantine** |
| **Concurrency & Workers** | Celery background task queue, async Redis broker, non-blocking async pipeline | Blocks global `ThreadPoolExecutor` threads via `asyncio.to_thread` on sync I/O |
| **Persistence & Multi-Tenancy** | 82 Supabase tables, cross-user RLS verified with synthetic Alice/Bob, `tenant_id` filters | Zero Postgres tables, no bookmarks, no ratings, zero `tenant_id` scoping |
| **Frontend UI/UX** | 14 languages, STT speech input, Obsidian-style Knowledge Graph, waveform audio player | English only, no STT, no teacher filter UI, deep-link jumps to 0:00, Zod strips pre-roll |

---

## Part 1: Comprehensive Evidence of Existing Systems in the Codebase

### 1.1 CRAG (Corrective RAG) & Self-Correction
* **Relevance Grading**: [`backend/rag/nodes/reranking.py:239`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/reranking.py#L239) (`grade_documents`) batches retrieved passages into an LLM call using `BATCH_GRADE_PROMPT` ([`backend/rag/prompts/rag.py:165`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/prompts/rag.py#L165)). Scores $\ge 0.75$ skip LLM grading; scores $< 0.35$ are rejected; borderline candidates are graded for factual responsiveness.
* **Routing After Grading**: [`backend/rag/nodes/intent.py:1795`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/intent.py#L1795) (`route_after_grading`) inspects relevance grades. If relevance is low and `rewrite_count < max_rewrites`, it branches to query reformulation rather than giving up.
* **Query Rewriter**: [`backend/rag/nodes/short_circuit.py:162`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/short_circuit.py#L162) (`rewrite_query`) leverages `QUERY_REWRITE_PROMPT` to reframe seeker queries based on the failure rationale.
* **Self-Correction Orchestrator**: [`backend/rag/self_correction.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/self_correction.py) manages `RewriteQueryCorrection` and `FallbackCorrection` with bounded execution cycles.

### 1.2 HyDE (Hypothetical Document Embeddings)
* **Concurrent Execution**: [`backend/rag/nodes/retrieval.py:878`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/retrieval.py#L878) (`navigate_and_hyde`) runs `decompose_query`, `navigate_knowledge_tree`, and `generate_hyde` concurrently via `asyncio.gather`.
* **Domain Prompt**: [`backend/rag/prompts/rag.py:145`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/prompts/rag.py#L145) (`HYDE_PROMPT`):
  > *"Write a brief, hypothetical teaching that answers the user's question. Use the specific vocabulary of the Ekam teachings (e.g., 'Beautiful State', 'Suffering State', 'Inner Transformation', 'Connection')."*
* **Multi-Provider Implementations**: Implemented across all four LLM backends:
  - `backend/services/sarvam_service.py` (`generate_hyde`)
  - `backend/services/openrouter_service.py` (`generate_hyde`)
  - `backend/services/nim_service.py` (`generate_hyde`)
  - `backend/services/ollama_service.py` (`generate_hyde`)
* **Vector Embedding**: The generated hypothetical discourse is embedded with BGE-M3 and used in hybrid search ([`retrieval.py:1053`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/retrieval.py#L1053)), bridging the vocabulary gap between colloquial questions and spiritual doctrine.

### 1.3 Knowledge Graph, Memgraph, Neo4j & LightRAG
* **Live Graph Database**: Running on `bolt://localhost:7687` (Memgraph 2.18 / Neo4j protocol) containing **6,430 nodes and 4,194 relationships**.
* **LightRAG Service**: [`backend/services/lightrag_service.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/lightrag_service.py) (1,188 lines) orchestrates dual-level graph vectors in Qdrant:
  - `lightrag_vdb_entities_baai_bge_m3_1024d` (**6,709 entity vectors**)
  - `lightrag_vdb_relationships_baai_bge_m3_1024d` (**4,120 relationship vectors**)
  - `lightrag_vdb_chunks_baai_bge_m3_1024d` (**2,053 chunk vectors**)
* **Atomic GraphRAG**: [`backend/rag/nodes/atomic_graphrag.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/atomic_graphrag.py) runs openCypher traversals with 1-hop and 2-hop decay models (`w2 = r2.weight * r2.confidence * hop2_decay`).
* **GraphRAG Fusion**: [`backend/services/graphrag_fusion.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/graphrag_fusion.py) executes Reciprocal Rank Fusion ($k=60$) combining graph topology with vector search, adding a **+0.05 corroboration bonus** when both channels retrieve the same node.

### 1.4 OKF (Ontological Knowledge Framework)
* **Curated Doctrine Base**: [`memory/okf/`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/memory/okf/) contains **672 markdown files** systematically defining spiritual concepts, practices, analogies, and states of consciousness.
* **Precompiled Embeddings**: [`memory/okf/compiled.json`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/memory/okf/compiled.json) is a pre-indexed 17.6 MB artifact with 1024-dimensional embeddings.
* **Dynamic Injection**: [`backend/rag/nodes/retrieval.py:172`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/retrieval.py#L172) (`_okf_match`) computes cosine similarity against compiled OKF entries and injects them into the retrieval pipeline with a **1.10x curation boost**.

### 1.5 Advanced Retrieval: RAPTOR, Context Budgeting, ColBERT & MMR
* **RAPTOR Hierarchical Clusters**: Normal chat navigates tree summaries (`backend/rag/tree_navigator.py`) over `raptor_level == 1` clusters using LLM reasoning to summarize entire discourse arcs.
* **Context Budgeting**: [`backend/rag/nodes/context_engineer.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/context_engineer.py) uses `ContextBudgetManager` and `sort_docs_litm_aware` ("Lost in the Middle" awareness) to eliminate redundant tokens.
* **Cross-Encoder Reranking & MMR**: Normal chat uses a cross-encoder model (`ms-marco-MiniLM-L-6-v2`) and Qdrant Maximal Marginal Relevance ($\lambda=0.7$) to diversify results and reject lexical false friends.
* **Lexicon Expansion**: [`backend/services/doctrine_terms.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/doctrine_terms.py) expands queries with canonical doctrine synonyms (`DOCTRINE_SYNONYMS`, `expand_query_with_synonyms`).

### 1.6 Multilingual & Indic Script Translation
* **Routing Translation Provider**: [`backend/services/translation/routing_provider.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/translation/routing_provider.py) implements a 3-tier translation cascade:
  1. Gemini Translation (`settings.gemini_translation_enabled`)
  2. Sarvam Translation (`sarvam-m` / `sarvam-30b` / `sarvam-105b` with `restore_citation_markers`)
  3. Ollama Translation (`llama3.2` / `qwen2.5`) as offline fallback.
* **Citation Marker Preservation**: [`services/translation/citation_markers.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/translation/citation_markers.py) ensures timestamps and brackets (`[02:15]`) remain uncorrupted during translation.
* **Multilingual Guardrail Gate**: [`guardrail_stage.py:102-109`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/pipeline/stages/guardrail_stage.py#L102-L109) translates non-English scripts to English via `guardrail_text_for` before safety evaluation.

### 1.7 Cognitive Personalization, Quality & Verification
* **LettuceDetect & CoVe**: Normal chat verifies factual claims using ModernBERT token classification (`backend/services/lettuce_detect_service.py`) and Chain-of-Verification sub-questions (`backend/rag/nodes/verification.py`).
* **Cross-Teacher Reasoning**: [`backend/rag/nodes/reasoning.py:cross_teacher_reasoning`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/nodes/reasoning.py) balances and harmonizes the complementary perspectives of Sri Preethaji and Sri Krishnaji.
* **Second Brain Vault**: [`backend/services/second_brain/`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/second_brain/) indexes user reflections in `second_brain_vault` and classifies user familiarity (`Seeker` vs. `Practitioner` vs. `Advanced Meditator`).
* **Text Quality Filter**: [`backend/services/text_quality_filter.py:find_artifact`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/text_quality_filter.py) enforces binding repository invariants, catching CoT reasoning leaks (`<think>`), provider graceful-degradation canned strings, and ASR decoder loops.

### 1.8 Observability, Telemetry & Security Gaps
* **Tracing Blinding**: [`backend/app/observability.py:21`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/observability.py#L21) (`DEFAULT_FASTAPI_EXCLUDED_URLS`) excludes every endpoint except `/api/chat`, completely blinding Jaeger OpenTelemetry tracing to `/api/first-person/query`.
* **Rate Limiting Bypass**: [`backend/app/middleware/rate_limit.py:81`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/middleware/rate_limit.py#L81) explicitly checks:
  ```python
  if not request.url.path.startswith("/api/chat"):
      return await call_next(request)
  ```
  This allows `/api/first-person/query` to completely bypass the Redis-backed Lua distributed token bucket!
* **Guardrail Bypass**: In [`backend/app/api/first_person.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/api/first_person.py), the query runs only through `serene_mind_engine.analyze(query)` for `DistressLevel.SEVERE`. It skips `InputGuardrailStage` and `_BLOCKED_TOPICS`, allowing toxic queries to be embedded and searched against sacred discourse vectors.
* **Quarantine Invalidation Flaw**: Serve-time hash failures increment `FIRST_PERSON_QUARANTINED_TOTAL` but do not write back `first_person_eligible=False` to Qdrant, leaving corrupted points searchable. Furthermore, deleting a video from Qdrant does not invalidate Redis exact cache (`EXACT_CACHE_TTL = 86400`), serving corrupted clips for up to 24 hours.

### 1.9 Audio Ingestion, Diarization & Metadata Stripping
* **Dual ASR Voting**: Whisper Large-v3 and Parakeet TDT 0.6B vote on transcript words with ROVER alignment (`MIN_ASR_AGREEMENT = 0.80`).
* **Speaker Diarization**: SpeechBrain ECAPA-TDNN 192d embeddings model known teachers against non-teacher cohorts with pause-boundary snapping (`SNAP_RADIUS_S = 2.0s`).
* **Forced Alignment**: Wav2vec2 CTC forced aligner produces millisecond-level word timestamps and confidence scores.
* **Critical Metadata Dropping**: When writing to `FirstPersonStore` ([`backend/services/first_person_store.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/first_person_store.py)):
  - Millisecond word timestamps are **discarded** (karaoke transcript tracking impossible).
  - Word confidence scores are **discarded**.
  - ROVER `disputed` flags and alternative hypotheses are **discarded**.
  - Diarization voiceprint cosine scores and `speaker_confidence` are **set to None**.
  - `question_dense` vector is left completely unpopulated.

### 1.10 Frontend Contract Mismatches & UI Gaps
* **Acoustic Pre-Roll Stripped by Zod**: Backend produces `playback_start_seconds` (floored at 0.0), `playback_end_seconds`, and `playback_url`. However, `firstPersonCitationSchema` in [`src/lib/firstPersonService.ts`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/src/lib/firstPersonService.ts) omits these fields! Zod strips them on validation, forcing `DiscourseVideoModal` to play from unpadded `timestamp_seconds`.
* **Deep-Link Bug**: `mapFirstPersonCitationToDiscourseCitation` maps `url: citation.video_url` (0:00 video URL) instead of `source_url`. The modal's "Open YouTube" button jumps the user to 0:00 rather than the cited teaching!
* **Unhandled Proxy Crashes**: `await response.json()` in `firstPersonService.ts:124` lacks try/catch protection, crashing on proxy HTML 502/504 error pages.
* **Frontend UI Omissions in `TeacherWords.tsx`**:
  - No audio waveform player mode (`SacredVoicePlayer.tsx` remains orphaned).
  - No language selector (hardcoded to English).
  - No teacher filter controls (API accepts `teacher_id`, UI provides no toggles).
  - No parent discourse context expansion.
  - No speech-to-text (STT) mic input.
  - No retry action on error alert.

---

## Part 2: Ruthless Forensic Questions for Claude Code

### Question 1: Why Was First-Person Built as an Isolated Silo?
* **Fact**: When creating `FirstPersonPipeline` ([`backend/services/first_person_pipeline.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/first_person_pipeline.py)), why did you build a bare-bones vector lookup that completely ignores the `backend/rag/` subsystem?
* **Impact**: While `/api/chat` benefits from multi-hop reasoning, intent routing, and graph fusion, `/api/first-person/query` operates like a naive 2022-era vector search. Why didn't you reuse the mature retrieval infrastructure?

### Question 2: Why Do We Prematurely Abstain Instead of Triggering HyDE?
* **Fact**: In `first_person_pipeline.py:380`, when the bi-encoder cosine score falls below the calibration threshold, the pipeline immediately returns `"weak_match"` or `"abstained"`.
* **Ruthless Challenge**: You already implemented [`HYDE_PROMPT`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/rag/prompts/rag.py#L145) and `generate_hyde` across four LLM providers. Why didn't you build a Tier-2 fallback: when direct search confidence is weak, trigger HyDE to translate colloquial seeker language into authentic Ekam doctrine vocabulary and re-query Qdrant before giving up?

### Question 3: Why Are 6,430 Memgraph Nodes and 6,709 LightRAG Entities Ignored?
* **Fact**: In `first_person_store.py`, points in `first_person_v2` contain text, timestamps, speaker, and hash—but **zero entity or concept links**.
* **Ruthless Challenge**: When a seeker asks about *"overcoming jealousy in a marriage"*, the word "jealousy" might not appear in a clip. But our Knowledge Graph maps `Jealousy` $\to$ `Comparison` $\to$ `Separation` $\to$ `Witness State`. Why is `FirstPersonStore` completely severed from Memgraph and LightRAG, blinding the search to ontological connections already mapped in our database?

### Question 4: Why Is There No Fast CRAG Relevance Filter on Candidate Clips?
* **Fact**: The first-person pipeline retrieves top clips from Qdrant, verifies their SHA-256 hash, and computes cosine similarity. If the score clears the threshold, it serves the clip.
* **Ruthless Challenge**: Vector similarity is notoriously vulnerable to lexical distractors (e.g., a clip about "the quietness of the forest" scoring high for "how to quiet mental chatter"). In `/api/chat`, you wrote `grade_documents` with `BATCH_GRADE_PROMPT` to verify relevance. Why is there no fast LLM relevance evaluator in First-Person to verify: *"Does this spoken quote actually answer the question before we serve it?"*

### Question 5: Why Is There No Multilingual Bridge for Indic Seekers?
* **Fact**: In [`backend/app/api/first_person.py:100`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/api/first_person.py#L100), `req.query` is passed directly to the embedder without language detection or translation.
* **Ruthless Challenge**: Sri Preethaji and Sri Krishnaji discourses in this index are spoken in English. When an Indian devotee asks in Telugu (*"బాధ నుంచి విముక్తి ఎలా?"*) or Hindi (*"अहंकार से मुक्ति कैसे पाएं?"*), BM25 sparse matching yields zero hits, and dense matching is severely degraded. Why was `RoutingTranslationProvider` omitted from the First-Person query path?

### Question 6: Why Was `question_dense` Left Dead in `first_person_store.py`?
* **Fact**: `first_person_store.py:346–350` explicitly states:
  > *"question_dense is deliberately NOT prefetched here: today it is frequently a copy of the passage vector... which would double-count the same signal twice in RRF fusion."*
* **Ruthless Challenge**: Why did you define a multi-vector schema with `question_dense` and then leave it as a duplicate of `passage_dense`? Why wasn't an offline question-generation pass run to generate 3–5 representative seeker questions for each clip, enabling true question-to-question semantic search?

### Question 7: Why Does the API Hide Parent Discourse Context from the UI?
* **Fact**: In Clips V2, discourses were segmented into parent spans ($\le 180\text{ s}$) and child sub-chunks ($100$–$200$ words). The parent ID is stored in Qdrant's payload.
* **Ruthless Challenge**: The API response only emits the child's `start_ms` and `end_ms`. Why doesn't the contract expose `parent_start_seconds`, `parent_end_seconds`, and `parent_verbatim_text` so that the frontend video player can offer an *"Expand to Full Discourse"* button?

### Question 8: Why Is First-Person Blotted Out from Jaeger Tracing?
* **Fact**: In [`backend/app/observability.py:21`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/observability.py#L21), `DEFAULT_FASTAPI_EXCLUDED_URLS` excludes all paths except `/api/chat`.
* **Ruthless Challenge**: Did you intentionally blind ops and engineering from inspecting First-Person query spans, latencies, and vector search bottlenecks in Jaeger?

### Question 9: Why Does TokenBucketMiddleware Bypass `/api/first-person/query`?
* **Fact**: [`backend/app/middleware/rate_limit.py:81`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/middleware/rate_limit.py#L81) explicitly checks `if not request.url.path.startswith("/api/chat"): return await call_next(request)`.
* **Ruthless Challenge**: Why does an unauthenticated user on `/api/first-person/query` bypass the distributed Redis token bucket, leaving the route vulnerable to DoS attacks on expensive ONNX embedding routines?

### Question 10: Why Are Toxic and Explicit Prompts Not Filtered?
* **Fact**: First-Person runs only `serene_mind_engine.analyze(query)` for `DistressLevel.SEVERE`.
* **Ruthless Challenge**: Why are `InputGuardrailStage` and `_BLOCKED_TOPICS` missing? Why does the system allow explicit, abusive, or politically charged queries to query the vector database and receive "weak match" sacred discourse citations?

### Question 11: Why Does Redis Cache Continue Serving Quarantined Videos?
* **Fact**: Redis exact cache has a 24-hour TTL (`EXACT_CACHE_TTL = 86400`). When a video is quarantined or deleted from Qdrant, Redis keys are not invalidated.
* **Ruthless Challenge**: If a video fails copyright or doctrinal audit and is quarantined, why does First-Person continue serving the cached clip to users for up to 24 hours?

### Question 12: Why Are Rich ASR & Diarization Metadata Dropped?
* **Fact**: Forced alignment produces millisecond word timestamps, and ECAPA-TDNN produces voiceprint cosine scores. `FirstPersonStore` drops both.
* **Ruthless Challenge**: Why did you discard word-level timestamps, making synchronized karaoke highlighting and precise acoustic boundary trimming impossible in the frontend?

### Question 13: Why Does Zod Strip Acoustic Pre-Roll in the Frontend?
* **Fact**: The backend emits `playback_start_seconds` (floored at 0.0) and `playback_end_seconds`. `firstPersonCitationSchema` in `firstPersonService.ts` omits these fields.
* **Ruthless Challenge**: Why did you let Zod silently strip the acoustic pad, forcing `DiscourseVideoModal` to start abruptly on the first spoken syllable instead of using the padded window?

### Question 14: Why Does the Deep-Link Button Jump to 0:00?
* **Fact**: `mapFirstPersonCitationToDiscourseCitation` maps `url: citation.video_url` instead of `source_url`.
* **Ruthless Challenge**: When a seeker clicks "Open in YouTube" to watch the full discourse, why does the link send them to 0:00 of an hour-long video instead of the exact timestamp where the teacher spoke the quote?

### Question 15: Why Is First-Person Completely Stateless with Zero Memory?
* **Fact**: In normal chat, multi-turn follow-ups are resolved via `resolve_followup.py`. First-Person has zero session context.
* **Ruthless Challenge**: If a seeker asks *"What did Sri Krishnaji say about fear?"*, receives a clip, and follows up with *"What meditation did he recommend for that?"*, why does First-Person fail completely instead of resolving the follow-up against the prior discourse?

### Question 16: Why Was BenchmarkSessionPool Implemented and Never Wired Up?
* **Fact**: [`backend/evaluation/session_pool.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/evaluation/session_pool.py) contains `BenchmarkSessionPool` to pre-mint and lease anonymous tokens. Lines 12–18 state: *"Not yet wired up: this module has no caller in bench.py"*.
* **Ruthless Challenge**: Why did you build the token pool to fix the 5 req / 60s rate limit bottleneck and then abandon it, forcing benchmark runs to suffer slow execution or hit rate limits?

---

## Part 3: The Unified Two-Tier Cascading Retrieval Architecture (Post-Run 2 Blueprint)

To resolve these defects while strictly honoring the **Zero Hallucination Invariant**, we will deploy the **Two-Tier Cascading Retrieval Architecture** immediately following Benchmark Run 2.

```mermaid
flowchart TD
    UserQuery["Seeker Query (Text / Audio STT)"] --> InputSafety["1. Input Safety & Guardrails (Multilingual)"]
    InputSafety -->|Blocked / Distress| CrisisRedirect["Crisis Helplines / Moderation Notice"]
    InputSafety -->|Safe| CacheCheck{"2. Exact Cache Check (SHA-256)"}
    
    CacheCheck -->|Hit| ExactCache["Return Verified Clip (<5ms)"]
    CacheCheck -->|Miss| Tier1["TIER 1: Fast Direct Path (<64ms)"]
    
    Tier1 --> HybridSearch["Direct Hybrid Vector Search (Qdrant first_person_v2)"]
    HybridSearch --> ConfCheck{"Score >= Direct Threshold (0.78)?"}
    
    ConfCheck -->|YES (High Conf)| CryptoGate1["Cryptographic SHA-256 & Artifact Gate"]
    CryptoGate1 --> Playback1["Verified Teacher Discourse (Audio/Video Modal)"]
    
    ConfCheck -->|NO (Weak Match)| Tier2["TIER 2: Cascading Agentic Fallback (<1.5s)"]
    
    Tier2 --> StepA["A. Indic Translation (Sarvam/Gemini)"]
    StepA --> StepB["B. HyDE Ekam Vocabulary Expansion"]
    StepB --> StepC["C. Memgraph Ontological Concept Traversal"]
    StepC --> StepD["D. Multi-Vector Re-Query (Passage + Question Dense)"]
    StepD --> StepE["E. ColBERT / Cross-Encoder Reranking"]
    StepE --> StepF["F. CRAG Batch Relevance Grader (BATCH_GRADE_PROMPT)"]
    
    StepF --> FinalCheck{"Relevance Grade Passed?"}
    FinalCheck -->|YES| CryptoGate2["Cryptographic SHA-256 & Artifact Gate"]
    CryptoGate2 --> Playback2["Verified Teacher Discourse (Audio/Video Modal)"]
    FinalCheck -->|NO| HonestAbstain["Honest Abstention: 'Related, not a direct answer' (weak_match)"]
```

### Key Architectural Invariants for Implementation:
1. **Zero LLM Teaching Generation**: The LLM is restricted to the role of a **Search Lens** (translation, vocabulary projection, graph concept linking, and binary relevance grading). Every text snippet rendered to the user is 100% authentic, recorded teacher speech.
2. **Mandatory `find_artifact()` Gate**: Every LLM output (HyDE query, translation, or relevance grade) must pass `find_artifact()` to prevent `<think>` leaks or provider degradation strings from entering vector embeddings or search filters.
3. **Write-Back Quarantine**: Any clip that fails cryptographic SHA-256 verification at runtime must immediately execute a write-back setting `first_person_eligible=False` in Qdrant and purge matching Redis cache keys.
4. **Full Acoustic Window Delivery**: The API schema must expose `playback_start_seconds` and `playback_end_seconds`, and the frontend Zod schema must preserve them to eliminate abrupt speech starts.
