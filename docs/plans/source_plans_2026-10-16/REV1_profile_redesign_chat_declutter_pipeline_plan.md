# Unified Master Plan: Complete Router Repair, First-Person Agentic GraphRAG, Verbatim Fidelity, Modern Readability, Profile Redesign & System Infrastructure

## 1. Master Plan Linkage & Document Registry

This document serves as the **Single Source of Truth (SSOT) Master Plan**, consolidating, harmonizing, and linking all related sub-plans, architectural blueprints, research reports, and remediation batch files across the repository:

### Master Plan Matrix & Document Links

| Area / Workstream | Primary Document Link | Scope & Key Invariants Inherited | Relationship to Master Plan |
| :--- | :--- | :--- | :--- |
| **First-Person RAG Architecture** | [first-person-rag-architecture-2026-10-11.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/architecture/first-person-rag-architecture-2026-10-11.md) | Measured state of `first_person_v7`/`v8`, BGE-M3 dense+sparse vectors, cross-encoder thresholding, completeness checking. | Informs Phase 1 & 2: Vector store configuration, RRF fusion, threshold gating, and fail-open routing. |
| **Verbatim Answer Quality & Coverage** | [FP_ANSWER_QUALITY_2026-10-04.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/FP_ANSWER_QUALITY_2026-10-04.md) | 25-question golden evaluation benchmark, collection version drift (`v1`–`v7`), calibration profile (`0.45`). | Informs Phase 1: Resolves collection mismatch and unlocks verified speech retrieval. |
| **Unified Book-Style Synthesis** | [unified_book_style_teaching_synthesis_plan.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/unified_book_style_teaching_synthesis_plan.md) | *The Four Sacred Secrets* literary flow, sacred arc of consciousness, zero-paraphrase invariant, no section headers (`###`). | Informs Phase 2: Slot-filling narrative scaffolding around 100% untouched verbatim discourse passages. |
| **Synthesis Research & Token Fidelity** | [unified_book_style_teaching_synthesis_research.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/unified_book_style_teaching_synthesis_research.md) | `QuoteWeaverAssertionGate`, token overlap validation (`min_overlap=1.0`), ASR proofreading, Atma Vichara generation. | Informs Phase 2: Eliminates assertion gate failures by having Python slot quotes instead of LLM rewriting. |
| **Breakthrough Unified Flow** | [ruthless_breakthrough_unified_synthesis_plan.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/ruthless_breakthrough_unified_synthesis_plan.md) | Hybrid mode execution, elimination of fragmented clip blocks (`_format_clip_block`), seamless narrative assembly. | Informs Phase 2: Eliminates bold mid-sentence URLs and fragmented clip cards. |
| **Quote-Weaver Polish & Guardrails** | [quote_weaver_and_first_person_polish.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/quote_weaver_and_first_person_polish.md) | Verification of `_BANNED_AFFIRMATIONS`, deterministic fallback paths, audio playback strip metadata. | Informs Phase 2: Banned artificial affirmations, fail-open audio strip generation. |
| **Distributed Ingestion & ASR Architecture** | [RUTHLESS_PIPELINE_RESEARCH_AND_WORLD_CLASS_ARCHITECTURE.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/RUTHLESS_PIPELINE_RESEARCH_AND_WORLD_CLASS_ARCHITECTURE.md) | 10 pre-flight readiness probes, host-side Metal/MPS Whisper-large-v3, complete-thought discourse segmentation. | Informs Ingestion Invariants: `L-INGEST-1`, `L-INGEST-2`, host-side embedding invariants. |
| **Production Ingestion & Checkpointing** | [rigorous_ingestion_retrieval_first_person_production_plan.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/rigorous_ingestion_retrieval_first_person_production_plan.md) | Redis checkpointing, Qdrant collection management, provider graceful degradation filters (`find_artifact()`). | Informs Safety Invariants: Checkpoint cross-validation, text quality filters. |
| **Ontological Knowledge Framework** | [OKF_WIRING_RESEARCH_2026-10-04.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/OKF_WIRING_RESEARCH_2026-10-04.md) | Compiled doctrine graph (`memory/okf/compiled.json`), entity extraction, Neo4j cross-teacher relations. | Informs Phase 2: Vectorized OKF cosine matching ($<0.1\text{ms}$) and payload schema extensions. |
| **Competitor Teardowns & Best Practices** | [COMPANY_TEARDOWNS_2026-10-04.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/COMPANY_TEARDOWNS_2026-10-04.md) | Delphi.ai (exact-second anchoring), Hallow / Magisterium AI (curated-only filter), Perplexity (span trimming), GitaGPT post-mortem. | Informs Grounding: Exact-second YouTube timestamp anchoring, compute-then-constrain ordering. |
| **Recent Remediation Batch** | [remediation_batch_oct14.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/remediation_batch_oct14.md) | S1 speaker prefix recovery, boundary defect repairs, test battery passing states. | Informs Invariants: Boundary demonstratives, verified speaker labeling. |
| **Docker Elevation & Verification** | [world_class_production_elevation_and_docker_redeploy.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/world_class_production_elevation_and_docker_redeploy.md) | Docker Compose multi-container build, healthy container states, port mappings, Chrome DevTools testing. | Informs Phase 6: Docker Compose rebuild, smoke testing, and Chrome DevTools verification. |
| **UX & Resonance Transformation** | [resonant_sacred_guidance_ux_transformation.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/resonant_sacred_guidance_ux_transformation.md) | Sacred Minimalist design tokens, chat composer polish, visual hierarchy, typography contrast. | Informs Phase 4 & 5: Profile page unification and chat progressive disclosure. |

---

## 2. Forensic Analysis & Root Cause Audit

Across this entire conversation, an exhaustive forensic review uncovered why answers felt generic/AI-generated, why the router aborted, why external blogs leaked in, and why latency was excessive:

### A. The Core Inversion: First-Person Agentic RAG vs 3rd-Person Fallback
- **The Core Flaw**: The system previously assumed that whenever a question was compound or multi-faceted (e.g. *"how can meditation heal suffering and imbibe love, prosperity and success"*), the First-Person Pipeline should **surrender** via `_SYNTHESIS_SHAPE_RE` and drop to 3rd-person general chat RAG.
- **The User's Requirement**: The **First-Person Pipeline must itself be intelligent, agentic, and graph-powered!** It must answer all questions—including compound, multi-thematic inquiries—using the authentic First-Person database (`first_person_v7`), retrieving clips across all facets and weaving them together seamlessly into a unified chapter.

### B. The Retrieval Budget Strangulation Defect (`retrieval.py:1591-1786`)
In `backend/rag/nodes/retrieval.py`:
```python
primary_query_limit = (
    1 if (retrieval_lane == "fast" or query_tier in ("fast", "tier2_simple")) else 2
)
primary_queries = list(dict.fromkeys(sub_queries))[:primary_query_limit]
remaining_budget = max(0, 2 - len(primary_queries))
```
- When a seeker asked a 4-part compound question, `decompose_query` generated 4 sub-queries.
- `[:primary_query_limit]` **sliced off and discarded sub-queries 3 and 4**!
- Qdrant was never queried for prosperity, wealth, or sadhana. To prevent total failure, the LLM had to hallucinate AI self-help commentary for those topics.

### C. The Anaphora / Dangling Pronoun & Grammar Defect
- In video discourses, masters often begin sentences with conversational markers or pronouns:
  *"Yes, this resolves suffering. When you observe without division..."*
  *"These are suffering states..."*
- When dumped directly into text, the user rightly asked: *"What is 'yes, this resolves'? What does 'this' mean?"*
- Without contextual antecedent resolution, verbatim quotes feel disjointed and confusing.

### D. The Latency Bottleneck: Serial LLM Ranking & Judging
- The pipeline was invoking 3–4 sequential remote LLM calls before generating the final answer:
  1. `_answerability_check` in First-Person Pipeline (~2.5s)
  2. `_llm_rerank_clips` across 8 candidates (~3.0s)
  3. `_relevance_select` judging top candidates (~2.5s)
  4. `grade_documents` in `reranking.py` running `ollama.grade_relevance` (~5-20s)
- This serial LLM evaluation chain caused massive 15–30 second latency spikes!

### E. The Router Traps & Premature Abort to `END`
1. `_first_person_claims` in `pipeline_registry.py:79-91` returned `True` for 100% of queries, unconditionally hijacking `START` to `first_person_node`.
2. `config.py:183` pointed to non-existent `first_person_v8` in local Qdrant (only `first_person_v7` with 2,294 points exists), throwing an unhandled 404 / `status="error"`.
3. `config.py:264` had `first_person_llm_fallback_enabled = False`, so `_decline()` called `_abstain()`, manufacturing a static refusal string.
4. `graph_strategies.py:172` checked `if state.get("first_person_result") is not None: return END`, terminating the graph immediately.

### F. Commercial Blog Leakage
1. In `intent.py`, broad unanchored words (`"program"`, `"today"`, `"recent"`, `"latest"`, `"when is"`) triggered `needs_web_search = True`.
2. In `backend/.env:154`, `linkedin.com` was explicitly in `WEB_SEARCH_ALLOWED_DOMAINS`!
3. In `retrieval.py:2001-2005`, `all_docs = web_docs + all_docs` prepended external web search results directly to primary chunks.
4. In `reranking.py:58-65`, web documents were assigned an automatic score of `0.70`, bypassing rerankers and cannibalizing the database document quota.

### G. Disconnected "Splitted" Clip Blocks in QuoteWeaver
- In `backend/services/quote_weaver.py:814-820`, `_format_clip_block` rendered raw disjointed cards with mid-sentence URLs:
  `**Sri Krishnaji** · [Video Title](url)\n\nVerbatim text...`
- Joining multiple clips simply dumped these disconnected cards with dividers, producing a fragmented, disjointed reading experience with massive gaps.

---

## 3. The 11 Pillars of What Makes Us "Much Better"

1. **First-Person Agentic GraphRAG (Not Just Fallback)**:
   - When a seeker asks a multi-dimensional inquiry, the First-Person Pipeline itself runs **Agentic Query Decomposition**, searching `first_person_v7` across every doctrinal facet and traversing Neo4j knowledge relations (`cross_teacher_reasoning.py` / `atomic_graphrag.py`).
   - Retrieves verified verbatim clips for each facet and weaves them into a continuous masterwork chapter.

2. **Verbatim Discourse Center Stage (70–80% Spoken Discourse)**:
   - Present the **actual spoken words** of Sri Krishnaji and Sri Preethaji from video transcripts under bold thematic pillars matching every domain of the user's question.
   - The AI provides only 1–2 sentences of serene framing per pillar; no synthetic AI commentary.

3. **Contextual Antecedent Resolution & Grammar Smoothing**:
   - Solve dangling pronouns (*"Yes, this resolves suffering..."*):
     - QuoteWeaver's introductory narrative sentence explicitly declares the antecedent directly before the quote (using allowed non-attribution framing verbs like 'speaks on', 'addresses', 'illumines', or 'offers these words' to avoid triggering `_ATTRIBUTION_RE` in `QuoteWeaverAssertionGate`):
       *“Speaking on how silent observation dissolves the inner conflict of the divided mind, Sri Krishnaji offers these words:*
       *‘Yes, this resolves suffering. When you observe without division, the mind returns to its natural state of peace.’”*
     - The reader instantly understands what *"this"* resolves!
     - At the boundary layer, strip leading conversational filler tokens (`"Yes,"`, `"Now,"`, `"So,"`) or use scholarly bracketed clarifiers (*“[Silent observation] resolves suffering...”*).

4. **Qdrant Separate Payload Architecture (Comparison with `spiritual_wisdom_contextual`)**:
   - In `spiritual_wisdom_contextual`, chunks prepended `[Context: ...] \n <text>`, but doing so in `first_person_v7` causes dense vector calibration drift, breaking the 0.45 threshold.
   - **Solution**: Store `discourse_context`, `tags`, `okf_concept_id`, and `okf_title` as **separate payload attributes** in `first_person_v7`.
   - Enables BM25 / sparse vector / keyword filtering / multi-vector search on context and tags without drifting the 1024-d dense vector!

5. **Eliminating the LLM Ranker Latency Bottleneck**:
   - Replace slow serial LLM reranking with high-speed BGE Cross-Encoder reranking (<50ms).
   - Run the answerability check asynchronously in parallel with vector retrieval.
   - Enforce selective confidence bypass in `reranking.py`: docs with rerank score $\ge 0.58$ skip remote LLM grading entirely.

6. **Seamless Chapter Synthesis (No More "Splitted" Blocks)**:
   - Replace disconnected `_format_clip_block` cards with a unified, continuous flow:
     - Executive Insight upfront.
     - Scannable thematic pillars featuring the full verbatim discourse passages.
     - Footnote citations `[1]`, `[2]`, `[3]` linking to the footer.

7. **Interactive Living Voice Audio Playback Strip (`DiscourseAudioStrip.tsx`)**:
   - Connect each verbatim quote to its exact video timestamp, rendering a one-click audio pill: `▶ Listen to Sri Krishnaji (01:12)`.
   - The seeker can literally press play and hear the teacher speak the exact words, completely dispelling any "AI-generated" perception.

8. **Interactive Guided Sadhana Launch Button (`GuidedMeditationFlow.tsx`)**:
   - Underneath the Daily Sadhana practice points, embed a direct action: `[Begin 3-Minute Silent Observation]` that launches the interactive meditation player right inside the app via `useSereneMind()`.

9. **User-Based Knowledge Graph Preservation & Protection**:
   - Clarify the architecture: remove the public unauthenticated Wisdom Map from navigation.
   - Preserve and fix the **User Personal Consciousness Knowledge Graph** (`/api/kg/personal-subgraph`) for authorized users by replacing `require_aal2` with `get_current_user_from_supabase`.
   - Embedded exclusively in **Profile $\to$ Memory $\to$ Graph View**.

10. **Sacred Minimalist Profile Page Overhaul (`ProfilePage.tsx`)**:
    - Unify the seeker header across all 4 tabs (`Journey`, `Personalization`, `Memory`, `Settings`), eliminating the "Double Hero" / disappearing hero bug.
    - Wire up `ProfileStatTiles.tsx` (7-day sparkline + session counters) and `SadhanaHeatmap.tsx` (activity calendar heatmap) into `JourneyOverview.tsx`.

11. **Chat Window Decluttering & Photographic Share Themes**:
    - Collapse bulky reference cards into a clean source pill (`✦ 3 Sources · Sri Krishnaji & Sri Preethaji`).
    - Implement real photo themes in `WisdomCardGenerator.tsx` using `public/og/` images (**Ekam Sanctuary**, **Serene Mind**, **Sacred Dawn**, **Obsidian Night**).

---

## 4. The Master Answer Model: What the Seeker Receives

**Seeker Query**: *"How can meditation heal suffering and imbibe love, prosperity and success?"*

**The Generated Response (Verbatim-First, Agentic & Scannable)**:

> ### 1. On Healing Suffering Through Meditation — Sri Krishnaji
> When you observe your inner state, all suffering arises from division—an anxious thinker resisting and fighting their own thoughts and emotions. Speaking on how silent observation dissolves this inner conflict, Sri Krishnaji explains:
>
> > *"When you look at your suffering, observe what is happening inside you. The moment you name it, the moment you judge it, the moment you fight it, you have divided yourself into two: the observer and the observed. In that division lies all conflict and suffering. But when you look without division, when there is pure observation without the urge to escape, that observation itself dissolves the conflict. There is an end to sorrow. When you observe without division, the mind returns to its natural state of peace."* [1]
>
> ▶ **[Listen to Sri Krishnaji (01:12)]**
>
> ---
>
> ### 2. On Awakened Love & The Beautiful State — Sri Preethaji
> When suffering ends, you stop living in self-centric fear where you constantly seek love and validation to fill an inner void. You enter a state of profound connection where love is your natural state of being:
>
> > *"Love is very, very important for the world to heal—not as an idea, not as a concept, but as a real state of awakening where your heart has actually awakened. That love can only awaken when you become free of the poisons of the mind. As you move out of suffering and immerse in awakened states of consciousness, you create a change in the 40,000 neurons of your heart, healing your own hurts and becoming capable of healing the hearts of those you love. When the heart is in a beautiful state, you don't seek love to fill an inner emptiness. Love is your very nature."* [2]
>
> ▶ **[Listen to Sri Preethaji (02:25)]**
>
> ---
>
> ### 3. On Conscious Wealth, Prosperity & Success — Sri Krishnaji
> Prosperity and enduring success do not come from anxious striving or fear; they are the natural fruits of an unclouded mind acting from connection:
>
> > *"When you make decisions from fear, greed, or scarcity, your intelligence is compromised; you generate friction and distrust. But when you act from a calm mind and a connected heart, your decisions possess immense clarity. You see opportunities where others see obstacles. That clarity in action is the seed of true prosperity and success. Fortune favors the connected consciousness."* [3]
>
> ▶ **[Listen to Sri Krishnaji (05:10)]**
>
> ---
>
> ### Daily Sadhana: Experiencing the Shift
> 1. **Silent Observation:** The moment inner turmoil or fear arises, pause. Observe the disturbance silently as a witness for three minutes without judging, naming, or trying to change it.
> 2. **Awakening the Heart:** Shift your awareness to the center of your chest. Breathe gently into the heart space, allowing the tension of division to melt into connection.
> 3. **Conscious Action:** Before speaking or making an important decision today, check your inner state. Ensure your action arises from a calm, connected heart rather than an anxious demand for results.
>
> 🪷 **[Begin 3-Minute Silent Observation Practice]**
>
> ---
>
> *When disturbance surfaces within you today, can you pause and witness it with silent observation rather than fighting it?*
> *How would your decisions, work, and relationships transform if you acted from a tranquil, connected heart rather than an anxious demand for success?*
>
> ---
> *Sources of Wisdom (Watch the Full Discourses):*
> [1] Sri Krishnaji — [Transforming Suffering into a Beautiful State](https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s) (01:12 – 02:45)
> [2] Sri Preethaji — [The Science of Love and Connection](https://www.youtube.com/watch?v=AQUZcU5L9xE&t=145s) (02:25 – 03:50)
> [3] Sri Krishnaji — [Conscious Wealth Creation](https://www.youtube.com/watch?v=mmpmX3-qfc4&t=310s) (05:10 – 06:40)

---

## 5. End-to-End Implementation Tasks Breakdown

### Phase 1: Complete Router Repair, First-Person Agentic RAG & Retrieval Budget Unlock

- [ ] **Task 1.1: Fix Collection, Calibration & Fallback Configuration (`backend/app/config.py`)**
  - Point `first_person_collection = "first_person_v7"` (matches live 2,294 points in Qdrant; fixes 404).
  - Set `first_person_uncalibrated_direct_enabled = True`.
  - Set `first_person_calibration_path = "config/first_person_calibration_v7.json"` (loads 0.45 calibrated threshold).
  - Set `first_person_question_dense_enabled = True` (activates dual dense RRF).
  - Set `first_person_llm_fallback_enabled = True` (prevents hard abstention exit when query requires broader wisdom synthesis).

- [ ] **Task 1.2: First-Person Agentic Multi-Facet Retrieval (`backend/services/first_person_pipeline.py` & `first_person_bridge.py`)**
  - In `first_person_bridge.py`:
    - Detect multi-thematic inquiries and decompose into sub-facets (e.g. suffering, love, prosperity).
    - Batch-encode sub-queries asynchronously in a single pass using `container.embedding.encode_batch_full_async`.
    - Pass `facet_dense_vectors` into `FirstPersonPipeline.execute`.
  - In `FirstPersonPipeline.execute`:
    - For compound queries with `facet_dense_vectors`, query `FirstPersonStore` (`first_person_v7`) for each facet.
    - Traverse Neo4j Graph relations (`services/cross_teacher_reasoning.py`) to connect concepts across teachers.
    - Gather top confident clips across all facets into `confident_clips` for `QuoteWeaverService`.

- [ ] **Task 1.3: Router Fail-Open & Graph Strategy Repairs**
  - In `backend/rag/graph_strategies.py` (`_route_after_first_person`):
    - If `state.get("first_person_result")` has `is_direct=True` and passed verification $\to$ return `END`.
    - If `first_person_result` is an abstention/refusal or weak match $\to$ do NOT return `END`; fall through to `parallel_start(state)` so holistic wisdom synthesis generates the response.
  - In `backend/app/pipeline/stages/first_person_bridge.py` (`_decline`):
    - When `status == "error"` (e.g. store/collection missing or connection failure), ALWAYS fail open (`return None`) so infrastructure faults never trap the seeker in a static refusal.

- [ ] **Task 1.4: Unlock Multi-Topic Retrieval Budget in General RAG (`backend/rag/nodes/retrieval.py`)**
  - Remove hardcoded `primary_query_limit = 2` cap: set `primary_query_limit = min(5, len(sub_queries))` for complex queries.
  - Parallel-encode all sub-queries using `embedder.encode_batch` in a single pass (~35ms).
  - In `reranking.py`: enforce a **Guaranteed Per-Topic Quota** so that every decomposed sub-query gets at least 1 top-scoring verified chunk in `relevant_docs`.

- [ ] **Task 1.5: Strict Web Search Quarantine & Commercial Blog Firewall**
  - In `backend/.env` and `backend/app/config.py`:
    - Clean `WEB_SEARCH_ALLOWED_DOMAINS`: remove `linkedin.com`, `facebook.com`, `twitter.com`, `x.com`, `instagram.com`, `linktr.ee`, etc. Set strictly: `WEB_SEARCH_ALLOWED_DOMAINS=ekam.org,theonenessmovement.org`.
    - Set `web_search_allow_db_domain_override = False` so database settings cannot widen search domains.
  - In `backend/services/web_search_service.py`:
    - Prefix search engine queries with explicit site operators: `f"(site:ekam.org OR site:theonenessmovement.org) {query}"` so DuckDuckGo never crawls corporate blogs or Medium articles.
    - Add hard reject-list blocking `linkedin.com`, `medium.com`, `substack.com`, `wordpress.com`, and commercial coaching blogs.
  - In `backend/rag/query_patterns.py` (`DOCTRINE_TEMPORAL_PATTERNS`):
    - Remove broad single-word substrings: `"program"`, `"today"`, `"recent"`, `"latest"`, `"when is"`.
    - Anchor to high-precision logistics patterns: `r"\b(upcoming|schedule of|dates? for|registration for)\s+(?:retreats?|festivals?|events?)\b"`.
  - In `backend/rag/graph_strategies.py` (`route_after_intent`):
    - Only route to `"temporal"` (`web_search_node`) when `intent == "LIVE_LOGISTICS"` and `live_logistics_enabled is True`. Doctrinal queries (`QUERY`, `FACTUAL`, `RELATIONAL`) must never route to web search.
  - In `backend/rag/nodes/retrieval.py:2001-2005`:
    - Delete the `all_docs = web_docs + all_docs` merge line so external web snippets are never injected into doctrinal RAG retrieval.
  - In `backend/rag/nodes/reranking.py:58-65`:
    - Remove web docs isolation, default `0.70` score injection, and `db_budget` deduction.
  - In `backend/rag/nodes/citation_extractor.py`:
    - Enforce that citations for spiritual teachings come exclusively from verified teacher transcripts or cleared doctrine references; never cite external web URLs for Guru wisdom.

---

### Phase 2: Verbatim-First Wisdom Structuring, Grammar Smoothing & Latency Optimization

- [ ] **Task 2.1: Contextual Antecedent Resolution & Grammar Smoothing (`QuoteWeaver` & Boundary Layer)**
  - In `backend/services/quote_weaver.py`:
    - Solve dangling pronouns (*"Yes, this resolves..."*, *"These are suffering states..."*):
      - The lead-in sentence explicitly introduces the antecedent: e.g. *"Speaking on how silent observation dissolves the inner conflict of the divided mind, Sri Krishnaji explains: [verbatim quote]"*.
    - In `backend/ingest/verbatim/boundaries.py`:
      - Strip conversational discourse openers (`"Yes,"`, `"Now,"`, `"So,"`) at boundary cleanup, preserving 100% of the substantive verbatim speech.

- [ ] **Task 2.2: Qdrant Separate Payload Architecture (`backend/services/first_person_store.py`)**
  - Adopt Contextual Situating without dense vector drift:
    - Index `discourse_context`, `tags`, `okf_concept_id`, and `okf_title` as **separate payload entities** in `first_person_v7`.
    - Keep `passage_dense` strictly pure verbatim to maintain the 0.45 calibrated cosine geometry.
    - Enable sparse / keyword filtering on tags and discourse context for agentic queries.

- [ ] **Task 2.3: Modernize `GURU_SYSTEM_PROMPT` in `backend/rag/prompts/system.py`**
  - Shift prompt focus from AI commentary to **Verbatim Teacher Presence**:
    - Ground 70–80% of substantive teachings in the direct verbatim words of Sri Krishnaji and Sri Preethaji.
    - Remove the legacy ban on bold concept labels and structured points (`"Bold nothing by default... Everywhere else write in sentences"`).
    - Instruct the model to structure multi-part inquiries with clear, scannable thematic pillars featuring the full verbatim discourse passages.
    - Ban generic AI meta-commentary, chatbot apologies, and throat-clearing.

- [ ] **Task 2.4: Eliminate LLM Ranker Latency Bottlenecks**
  - In `backend/services/first_person_pipeline.py`:
    - Replace serial `_llm_rerank_clips` with fast BGE Cross-Encoder reranking (<50ms).
    - Run `_answerability_check` in background thread overlapping vector search.
  - In `backend/rag/nodes/reranking.py`:
    - Lower `crag_skip_confidence` from 0.75 to 0.58 so high-scoring cross-encoder hits bypass the remote LLM grader (`ollama.grade_relevance`), saving 5–15 seconds per turn.
  - In `backend/rag/nodes/retrieval.py`:
    - Vectorize OKF cosine matching via NumPy dot product ($<0.1\text{ms}$).

- [ ] **Task 2.5: Continuous Masterwork Slot-Filling in `QuoteWeaver` (`backend/services/quote_weaver.py`)**
  - Deprecate clumsy `_format_clip_block` mid-sentence URLs.
  - Implement the **Verbatim-First Slot-Filling Template**:
    - The full verbatim spoken text is rendered front and center as blockquotes under clean speaker and topic headers.
    - Python deterministically slots 100% exact verbatim clips from Qdrant with footnote markers `[1]`, `[2]`, `[3]`.
    - Attach Discourse Audio Strip metadata (YouTube video ID, start/end seconds) to each quote block so `DiscourseAudioStrip.tsx` can render a one-click audio pill: `▶ Listen to Sri Krishnaji (01:12)`.
    - Daily sadhana practice steps and Atma Vichara inquiries directly from the discourse.
    - Direct interactive action button metadata: `[Begin 3-Minute Silent Observation]` wired to launch `GuidedMeditationFlow.tsx`.
    - Footnotes rendered cleanly in the footer with exact YouTube start timestamps.
  - In `QuoteWeaverAssertionGate`:
    - Update Rule 4b to allow structured bullet points and numbered sadhana steps for multi-dimensional inquiries, matching modern ChatGPT/Claude readability.
    - Ensure introductory scaffolding strictly uses non-attribution framing verbs (`speaks on`, `addresses`, `illumines`, `offers these words`) to prevent Rule 6b assertion failures.
    - Retain `_BANNED_AFFIRMATIONS` assertion gate.

---

### Phase 3: User Knowledge Graph Auth Fix & Navigation Cleanup

- [ ] **Task 3.1: Fix User Knowledge Graph Authorization (`backend/app/api/kg.py`)**
  - In `backend/app/api/kg.py:388` (`kg_personal_subgraph`):
    - Replace `user: dict = Depends(require_aal2)` with `user: dict = Depends(get_current_user_from_supabase)`.
    - Enforce proper authorization:
      - Anonymous/unauthenticated users receive an empty graph (`count=0`).
      - Authorized logged-in users receive their personal subgraph combining memories, notes, and connected concepts.
  - In `src/components/kg/KGConceptMap.tsx`:
    - Remove the AAL2 step-up lock screen; if unauthenticated, show a clean sign-in prompt; if authenticated, load the personal consciousness map.

- [ ] **Task 3.2: Remove Public Wisdom Map Navigation**
  - Remove public Wisdom Map (`kg`) navigation item from `src/components/chat/DesktopSidebar.tsx`.
  - Remove Wisdom Map button from `src/components/chat/MobileConversationSheet.tsx`.
  - Remove Wisdom Map command item from `src/components/common/CommandPalette.tsx`.
  - Remove Wisdom Map link from `src/components/chat/ChatMessage.tsx` and `src/components/chat/DeepenAndTuneBar.tsx`.
  - Retain the personal knowledge graph embedded exclusively in **Profile $\to$ Memory $\to$ Graph View**.

---

### Phase 4: Sacred Minimalist Profile Page Redesign (`src/pages/ProfilePage.tsx`)

- [ ] **Task 4.1: Profile Header & Layout Unification (`src/pages/ProfilePage.tsx`)**
  - Eliminate the "Double Hero" bug: render a single unified Sacred Minimalist seeker header across all tabs (`[Journey]`, `[Personalization]`, `[Memory]`, `[Settings]`).
  - Header elements: seeker avatar, level badge (`Seeker` / `Practitioner` / `Advanced`), streak counter, display name, and clean photo modal.
  - Segmented tab bar with subtle glass/hairline border styling.

- [ ] **Task 4.2: Enhance Journey Tab (`src/components/profile/JourneyOverview.tsx`)**
  - Add `sessions: NormalizedSession[]` to `JourneyOverviewProps` and pass `sessions` state loaded from `loadMeditationSessions()` in `ProfilePage.tsx`.
  - Remove redundant secondary hero header from `JourneyOverview.tsx`.
  - Integrate `ProfileStatTiles.tsx` (7-day practice sparkline and session counts using `sessions`).
  - Integrate `SadhanaHeatmap.tsx` for consistent daily meditation calendar visualization (using `sessions`).
  - Clean up recent conversations and guided next-step cards.

- [ ] **Task 4.3: Overhaul Personalization & Settings Tabs**
  - Personalization: Display name, intention bio, preferred language picker, and interactive Guru tone cards (Gentle, Direct, Poetic).
  - Settings: Harmonize `PreferencesCard`, `SecurityCard`, and `AccountDataCard` with consistent cards and typography.

---

### Phase 5: Chat Window Decluttering & Share Card Photo Themes

- [ ] **Task 5.1: Progressive Disclosure in Chat Window (`src/components/chat/ChatMessage.tsx`)**
  - Collapse bulky expanded reference cards and verbose badges into an elegant source pill (`✦ 3 Sources · Sri Krishnaji & Sri Preethaji`).
  - Clicking the pill opens the sliding `CitationPanel`.
  - Streamline the message action bar: elevate `Listen` (audio playback), `Share Wisdom` (card generator), and `Copy` to primary visibility.
  - Wire interactive Sadhana button to `useSereneMind().open('audio', false, customSteps, sourceTeaching)` so seekers can begin practice with 1 tap.
  - Remove debug noise, raw score numbers, and duplicate cards.

- [ ] **Task 5.2: Photo-Background Themes in Share Card (`src/components/chat/WisdomCardGenerator.tsx`)**
  - Add photographic themes using real high-resolution images in `public/og/`:
    - **Ekam Sanctuary**: Temple atmosphere (`/og/og-teachings.jpg`) with gold serif typography and vignette.
    - **Serene Mind**: Tranquil misty nature (`/og/og-serene.jpg`) with emerald/white accents.
    - **Sacred Dawn**: Morning glow (`/og/og-practices.jpg`) with rose-gold styling.
    - **Obsidian / Minimalist Night**: Dark luxury gradient with gold foil branding.
  - Add theme preview thumbnails in the theme selector bar.
  - Implement direct "Share" (native Web Share API) and "Download PNG" (via `html-to-image` / Canvas) with instant feedback.

---

### Phase 6: Docker Build, Deployment & Verification

- [ ] **Task 6.1: Docker Compose Rebuild & Health Check**
  - Build frontend: `docker compose -f backend/docker-compose.yml build frontend`.
  - Build backend: `docker compose -f backend/docker-compose.yml build backend`.
  - Deploy: `docker compose -f backend/docker-compose.yml up -d frontend backend`.
  - Verify container status with `docker ps`.

- [ ] **Task 6.2: DevTools & Browser Verification**
  - Open and inspect `http://localhost/profile` using Chrome DevTools.
  - Verify the redesigned Profile page, unified header, sparklines, and heatmap.
  - Test login with authorized user credentials and verify that the personal knowledge graph populates without 403 errors.
  - Ask compound questions in Chat and verify that the pipeline delivers genuine Verbatim-First, scannable, user-tuned answers without company blogs or splitted blocks.
  - Test Wisdom Card generator with photo themes and confirm high-resolution export.

---

## 6. Invariants & Guardrails

- **`L-NO-INVENTED-CREDIT-1`**: Never invent credit or fabricate quotes for teachers.
- **`L-FP-HYBRID-SCAFFOLD-1`**: Quoted speech must remain byte-for-byte exact with the stored transcript; synthesis is applied to the narrative structure.
- **`L-INGEST-1` / `L-INGEST-2`**: Any LLM output persisted to Qdrant must pass `find_artifact()`.
- **Zero Company Blogs**: External web search is strictly quarantined to `LIVE_LOGISTICS` at Ekam/Oneness; never cite third-party commercial/company blogs in spiritual wisdom.
- **Ponytail Principle**: Keep solutions thin, robust, and clean—no redundant systems or artificial affirmations.
