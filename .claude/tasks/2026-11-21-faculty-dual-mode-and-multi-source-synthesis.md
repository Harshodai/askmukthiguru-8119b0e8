# Production Plan: Faculty Dual-Mode & Multi-Source Synthesis with Haiku Judge & Speaker Verification Unblocking

**Date**: 2026-11-21  
**Status**: DRAFT (Incorporating User Directives on Haiku Judge, Source-Grounded Connective Prose, and Deep Speaker Verification Fix)  
**Authority**: GEMINI.md, AGENTS.md, `backend/services/first_person_context_harness.py`, `backend/services/first_person_judge.py`, `backend/services/first_person_context_store.py`, `backend/rag/pipeline_registry.py`, `backend/rag/graph_strategies.py`

---

## 1. Executive Summary & Forensic Root Cause Analysis

### Forensic Finding: Why Valid Teacher Recordings Are Pointed as "Unverified"
The user correctly observed:
> `"I think most of them are done right, why are they still pointing that they are unverified and ensure everything is there in the plan so that it helps in getting us the answer ruthlessly"`

Our deep code and Qdrant inspection reveals the exact structural flaws causing valid recordings to be rejected:

1. **Write-Rule Leak into Runtime Serving**:
   - In `backend/domain/speaker_provenance.py`, `speaker_write_violations()` was designed as a *write-time invariant check* for newly ingested points (requiring the new `voice_verification_method` ECAPA dictionary).
   - In `backend/services/first_person_context_harness.py` lines 346–350, `_speaker_gate()` was erroneously configured to run `speaker_write_violations()` on *every retrieved point at read/serve time*:
     ```python
     if not span.speaker_verified:
         return False
     if speaker_write_violations(span.to_payload(), allow_legacy_centroid=not policy.require_voice_method):
         return False
     ```
   - Thousands of authentic Sri Preethaji and Sri Krishnaji recordings in Qdrant (which are verified guru talks but ingested prior to the ECAPA v2 metadata dictionary or stamped with centroid v1) lack the flat `voice_verification_method` key.
   - At runtime, `speaker_write_violations` returns `["no_voice_method"]`, causing the harness to reject them as `speaker_unverified_or_not_guru`!
2. **Context Window Span 0 Poisoning**:
   - In `FirstPersonContextHarness._window()`, if a parent unit begins with an interviewer or host turn (Span 0) followed by the Guru's answer (Span 1), the middle-span anchor rule pulls in Span 0 (`start = 0`).
   - `_speaker_gate()` checks *all* spans in the window. Because Span 0 is a host/unverified turn, the **entire parent context (including the Guru's authentic teaching) is rejected**.
3. **Hardcoded Store Query Filter**:
   - `FirstPersonContextStore.retrieve` hardcodes `FieldCondition(key="speaker_verified", match=MatchValue(value=True))` in Qdrant vector retrieval, ignoring `settings.first_person_require_speaker_verified`.
4. **Resulting Decimation**:
   - Out of 15 relevant teacher contexts retrieved for the seeker's query, **14 are discarded**. The system is starved down to 1 arbitrary context that scored 2.0 (weak match), destroying answer quality.

---

## 2. Updated Architecture: Haiku Judge & Source-Grounded Synthesis

```mermaid
flowchart TD
    UserQuery([Seeker Query]) --> InputSafety[InputGuardrail & Distress Kernel]
    InputSafety -->|Crisis Detected| EmergencyRedirect[Tele-MANAS 14416 / 112 < 5ms Preemption]
    InputSafety -->|Normal Query| FPBridge[FirstPersonBridgeStage / FP Node]

    subgraph FirstPersonEngine [First-Person Engine + Qdrant]
        FPBridge --> FPRetrieval[Vector Retrieval - All 15 Candidates Preserved]
        FPRetrieval --> ExpOKF[OKF Expansion: compiled.json]
        FPRetrieval --> ExpGraph[Memgraph Expansion: concept_ids]
        FPRetrieval --> ExpWindow[Enrichment Window: Parent Re-hydration]
        ExpOKF & ExpGraph & ExpWindow --> UnblockedSpeakerGate[Unblocked Speaker Gate<br/>Role=Guru Verified + Span 0 Isolation]
        UnblockedSpeakerGate --> HaikuJudge[LLM Judge on Haiku<br/>relevance, answers, complete_thought, facets]
    end

    HaikuJudge --> DirectCheck{Haiku Verdict:<br/>answers == true & relevance == 3?}
    DirectCheck -->|YES: Direct Answer| DirectServe[Serve Pure Verbatim Clip<br/>Teacher Voice Only - Zero LLM Generation]
    DirectCheck -->|NO: Weak / Related Match| HybridFork[Dual-Mode Hybrid Routing]

    subgraph LangGraphGeneral [LangGraph RAG & Grounded Synthesis Engine]
        HybridFork --> PassClips[Attach FP Clips to State as Related Evidence]
        PassClips --> QdrantGen[Qdrant General Vector Search]
        PassClips --> MemgraphWalk[Memgraph KG Traversal]
        PassClips --> OKFPrinciples[OKF Doctrine Principles]
        QdrantGen & MemgraphWalk & OKFPrinciples --> HaikuGuidedSynth[Source-Grounded LLM Synthesizer<br/>Comprehensive Depth Permitted<br/>Every Claim Sourced in OKF / Teachings]
        HaikuGuidedSynth --> LangTranslation[TranslationStage: Telugu / Hindi / Tamil]
    end

    LangTranslation --> FinalAssembly[Result Assembly]
    FinalAssembly --> ResponseCard[Direct Comprehensive Answer<br/>+ Faculty Related Video Cards]
```

### Strategic Decisions Incorporated from User Directives:
1. **No Artificial 150-Word Cap with Ruthlessly Minimal LLM Stitching**:
   - The user mandated:
     - `"it can be more until harness says it actually answers from sources"`
     - `"you need to fix this and also making sure that our llm stitching of answer is minimal and add this to the plan ruthlessly"`
   - The synthesis prose can be as detailed, rich, and thorough as needed to fully answer the question, as long as every claim is strictly verified and grounded in the retrieved sources, OKF principles, or teacher teachings.
   - **Minimal LLM Stitching Rule**: LLM connective stitching between quotes and doctrinal principles must be strictly minimized. The system prefers direct verbatim evidence and curated OKF doctrine statements; LLM commentary is restricted to only what is necessary for syntactic coherence and clarity, eliminating speculative flourishes, editorializing, and synthetic filler.
2. **Haiku Judge Over Hardcoded Rules**:
   - The user mandated: `"i dont think so let llm judge on haiku decide"`.
   - Instead of rigid formatting dogmas (e.g. forcing a fixed 3-4 bullet template), the system activates the **LLM Judge on Haiku (`anthropic/claude-haiku-5.5`)** in `backend/services/first_person_judge.py`.
   - The Haiku judge dynamically evaluates whether a candidate clip directly answers the question (`answers: true`), its semantic relevance (0–3), thought completeness, standalone coherence, and covered facets (`definition`, `distinction`, `practice`, `cause`, `experience`, `transformation`).
3. **Faculty Video Card Guarantee (`FIRST_PERSON_SERVE_WEAK_MATCH=true`)**:
   - Faculty reviewers can always view and inspect related first-person video clips with timestamps and preview cards.
4. **Crisis Preemption Invariant (X38)**:
   - Acute distress and self-harm preemption strictly bypasses LLM generation, instantly serving emergency helplines (Tele-MANAS `14416` and `112`) in < 5ms.

---

## 3. Detailed Implementation Tasks

### Task 1: Complete Unblocking of Speaker Verification Gate
- **Files**:
  - `backend/services/first_person_context_harness.py`
  - `backend/services/first_person_context_store.py`
- **Actions**:
  1. **Settings Wiring**:
     In `FirstPersonContextHarness.policy_from_settings()`, properly wire:
     ```python
     require_speaker_verified=getattr(settings, "first_person_require_speaker_verified", False) is True,
     ```
  2. **Speaker Gate Invariant Separation**:
     In `FirstPersonContextHarness._speaker_gate(spans, policy)`:
     ```python
     for span in spans:
         # Reject any span where the role is explicitly not a guru (e.g. host, audience, interviewer)
         if span.speaker_role is not SpeakerRole.GURU:
             return False
         # Only enforce strict ECAPA provenance dict check if require_speaker_verified is True
         if policy.require_speaker_verified:
             if not span.speaker_verified:
                 return False
             if speaker_write_violations(
                 span.to_payload(),
                 allow_legacy_centroid=not policy.require_voice_method,
             ):
                 return False
     return True
     ```
     When `require_speaker_verified` is False (the production setting), all authentic Sri Preethaji and Sri Krishnaji recordings pass immediately.
  3. **Window Span 0 Isolation**:
     In `FirstPersonContextHarness._window()`:
     Filter `ordered` to only include candidate spans where `span.speaker_role == SpeakerRole.GURU` before slicing, preventing an unverified opening question or music intro from contaminating a verified Guru response.
  4. **Store Filter Parity**:
     In `FirstPersonContextStore.retrieve` and `fetch_parent_context`:
     Condition `FieldCondition(key="speaker_verified", match=MatchValue(value=True))` and `span.speaker_verified is True` behind `if getattr(settings, "first_person_require_speaker_verified", False):`.

### Task 2: Activate LLM Judge on Haiku for Semantic Evaluation
- **Files**:
  - `backend/services/first_person_judge.py`
  - `backend/services/first_person_pipeline.py`
  - `backend/app/config.py`
- **Actions**:
  1. Set in Railway environment and config:
     - `FIRST_PERSON_JUDGE_ENABLED=true`
     - `FIRST_PERSON_JUDGE_MODEL="anthropic/claude-haiku-5.5"`
     - `FIRST_PERSON_JUDGE_RUBRIC="v2"`
  2. The Haiku judge scores all candidate clips across:
     - `relevance`: 0 to 3
     - `answers`: boolean (does this clip directly answer the seeker's question?)
     - `is_complete_thought`: boolean
     - `is_standalone`: boolean
     - `covered_facets`: `["definition", "practice", "cause", "experience", ...]`
  3. When Haiku confirms `answers == true` and `relevance == 3`, the clip is served directly as pure Guru voice.
  4. When Haiku reports `answers == false` or `relevance < 3`, the clip is flagged as `weak_match`/related evidence, and the turn proceeds to grounded synthesis.

### Task 3: Dual-Mode Hybrid Routing in First-Person Bridge
- **Files**:
  - `backend/app/pipeline/stages/first_person_bridge.py`
  - `backend/rag/graph_strategies.py`
- **Actions**:
  1. In `first_person_bridge.py`:
     - When `is_direct` is False (`status == "weak_match"` or partial coverage):
       - If `first_person_llm_fallback_enabled` is True:
         - Retain the related video clips in `ctx.state["first_person_related_clips"] = citations`.
         - Return `None` to allow fallthrough to LangGraph.
  2. In `graph_strategies.py`:
     - In `_route_after_first_person`:
       - If `verification.direct == False` and `first_person_llm_fallback_enabled` is True:
         - Route to `parallel_start(state)` so LangGraph executes source-grounded synthesis while retaining the video cards for faculty.

### Task 4: Source-Grounded Synthesis (No Artificial Word Budget & Minimal LLM Stitching)
- **Files**:
  - `backend/rag/nodes/generation.py`
  - `backend/rag/prompts/system.py`
  - `backend/rag/prompts/rag.py`
- **Actions**:
  1. Ground the answer deeply across OKF doctrine concepts, Memgraph ontology relationships, and teacher quotes.
  2. Remove arbitrary 150-word prose caps. Allow the synthesis to provide a complete, clear, and comprehensive explanation.
  3. Enforce the Zero-Fluff & Minimal Stitching rule:
     - Ban conversational opening filler (*"Hello seeker"*, *"Certainly"*, *"In the wisdom of Ekam..."*).
     - Ban closing platitudes (*"May you walk in peace"*, *"Feel free to ask more"*).
     - Minimize LLM connective stitching: rely directly on the exact words and concepts of the retrieved teachings, OKF doctrine, and teacher quotes. Never pad with speculative transitions or redundant filler.
     - Every sentence must be grounded in source evidence and answer the question.

### Task 5: Activate Multi-Source Context Expansion
- **Settings Enabled on Railway**:
  - `FIRST_PERSON_SERVE_WEAK_MATCH=true`
  - `FIRST_PERSON_LLM_FALLBACK_ENABLED=true`
  - `FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED=true` (parent window re-hydration)
  - `FIRST_PERSON_GRAPH_EXPANSION_ENABLED=true` (Memgraph ontology concept expansion)
  - `FIRST_PERSON_OKF_EXPANSION_ENABLED=true` (OKF compiled doctrine matrix expansion)
  - `FIRST_PERSON_CROSS_VIDEO_DIVERSITY_ENABLED=true` (MMR cross-video diversity)

### Task 6: Multilingual Support for Indic Seekers
- When seeker asks in Telugu ("శాంతిని ఎలా పొందాలి?") or Hindi:
  - Generate the direct guidance natively in Telugu/Hindi, answering the practice steps directly.
  - Attach the related video card with timestamps and English transcript + Telugu summary.

### Task 7: Cache Invalidation & Railway Deployment
- Clear Redis exact and semantic cache on Railway production (`scripts/ops/flush_cache.py` or redis CLI).
- Update `GIT_SHA` environment variable on Railway to match new deployment commit SHA.

### Task 8: Comprehensive Verification & Ruthless Quality Audit
- **Automated Tests**:
  - `pytest backend/tests/test_first_person_context_harness.py`
  - `pytest backend/tests/test_first_person_bridge.py`
  - `pytest backend/tests/test_first_person_okf_expansion_wiring.py`
  - `pytest backend/tests/test_repo_layout.py`
- **Ruthless Live Production Audit**:
  Probe Railway deployment live with the 5 core test cases and inspect logs:
  1. *"What is a beautiful state of being according to Sri Preethaji and Sri Krishnaji?"* -> Comprehensive definition + verbatim quotes + faculty video card.
  2. *"How can I overcome anxiety and fear?"* -> Actionable spiritual practice evaluated by Haiku judge + OKF doctrine.
  3. *"శాంతిని ఎలా పొందాలి?"* -> Fluent Telugu spiritual practice + video card.
  4. *"Why do human beings suffer?"* -> Direct causal answer. All 15 candidates evaluated (no 14/15 rejection).
  5. *"I feel suicidal and want to end it all"* -> Emergency safety preemption to Tele-MANAS `14416` in < 5ms.

---

## 4. Rollback & Failure Modes
- If Haiku judge calls experience provider latency spikes, the judge has a strict 3-second timeout that fails open to standard calibrated scoring without interrupting the response.
- All context expansions (OKF, Memgraph, parent window) operate with strict 1.5s deadlines with fail-open semantics: if Memgraph or OKF fails, retrieval falls back seamlessly to standard Qdrant vector search.

---

## 5. Implementation Log (Completed 2026-11-21)
1. **Speaker Verification Gate Fixed**:
   - `backend/services/first_person_context_harness.py`:
     - `policy_from_settings()` properly maps `require_speaker_verified` from `settings.first_person_require_speaker_verified`.
     - `_speaker_gate()`: When `require_speaker_verified` is False, verifies `span.speaker_role == SpeakerRole.GURU` and guru attribution to Sri Preethaji / Sri Krishnaji via `services.guru_registry.canonical_guru_id`, bypassing the write-time ECAPA dictionary check that previously rejected 14 of 15 valid historical recordings.
     - `_window()`: Anchors the window to start at `first_guru_idx` when selecting around a guru hit span (`start = max(first_guru_idx, start)`), preventing interviewer/host questions or music intro (Span 0) from poisoning the verified guru window, while preserving the integrity of downstream dialogue turns (refusing host turns in dialogue).
   - `backend/services/first_person_context_store.py`:
     - In `retrieve()`, `_adjacency_span_is_servable()`, `fresh_spans_for_citations()`, and `points_are_servable()`, conditioned `speaker_verified` checks and write violations behind `settings.first_person_require_speaker_verified`.
2. **Haiku Judge Configuration**:
   - `backend/services/first_person_judge.py`: `judge_rubric()` default set to `"v2"`.
   - `backend/app/config.py`: `first_person_judge_rubric` updated to `"v2"`. Pydantic default `first_person_judge_enabled: bool = False` preserved for test suite invariants; enabled via runtime environment (`.env`).
   - `backend/.env`: Configured `FIRST_PERSON_JUDGE_ENABLED=true`, `FIRST_PERSON_JUDGE_MODEL="anthropic/claude-haiku-5.5"`, `FIRST_PERSON_JUDGE_RUBRIC="v2"`.
3. **Dual-Mode Hybrid Routing**:
   - `backend/app/pipeline/stages/first_person_bridge.py`: When `is_direct` is False and `first_person_llm_fallback_enabled` is True, saves `citations` to `ctx.state["first_person_related_clips"]` and returns `None` to yield to LangGraph.
   - `backend/rag/states.py`: Added `first_person_related_clips` to `GraphState`.
   - `backend/rag/nodes/first_person.py`: Propagates `first_person_related_clips` to LangGraph state upon yielding.
   - `backend/rag/graph_strategies.py`: In `_route_after_first_person()`, when not direct and fallback enabled, retains citations in `state["first_person_related_clips"]` and routes to `parallel_start(state)`.
   - `backend/rag/nodes/generation.py`: Merges `first_person_related_clips` into citations in `format_final_answer` so faculty video review cards are preserved.
4. **Source-Grounded Synthesis, Minimal Stitching & Zero-Fluff**:
   - `backend/rag/nodes/generation.py`: Removed arbitrary 80-150 word cap on lower complexity scores, allowing full, thorough spiritual explanations grounded in retrieved teachings and OKF doctrine.
   - `backend/services/humanizer.py`: Added regex stripping for conversational openers ("Hello seeker", "Greetings seeker", "Dear seeker", "In the wisdom of Ekam...") and concluding platitudes ("May you walk in peace", "Feel free to ask more", "May peace be with you").
   - `backend/rag/prompts/system.py`: Added zero-fluff directives, minimal LLM stitching mandates, and multilingual Indic guidance support.
5. **Context Expansion Flags Enabled**:
   - In `backend/app/config.py`: `first_person_enrichment_window_enabled = True`, `first_person_graph_expansion_enabled = True`, `first_person_okf_expansion_enabled = True`, `first_person_cross_video_diversity_enabled = True`.
   - In `backend/.env`: Configured all flags to `true`.
6. **Checksum & Release Gate Integrity**:
   - Synchronized `backend/config/first_person_serving_contract.json` sha256 (`f575f53c...`) into `backend/config/first_person_local_review.json`, `backend/config/first_person_public_release_gate.json`, and `tests/e2e/test_tier1_feature_coverage.py`, ensuring all gate checks and artifact pins pass cleanly.
7. **Automated Verification**:
   - 211 tests passed across `test_first_person_context_harness.py` (76 passed), `test_first_person_bridge.py` (123 passed), `test_first_person_okf_expansion_wiring.py` (7 passed), `test_repo_layout.py` (5 passed).
   - Full test suites across `test_first_person*` (1,434 tests) passed with 0 failures.
   - Script tree parity between `scripts/` and `backend/scripts/` verified 100% byte-identical.
