# Implementation Plan: First-Person Verbatim Defect Remediation & LLM Quote-Weaving Layer

## Objective
Address the core quality defects in the First-Person Verbatim Teaching pipeline and implement a lightweight, DSPy-assertion-grounded LLM Quote-Weaver layer. This layer takes verified verbatim clips from Qdrant (`first_person_v7`), contextual doctrine from OKF (`memory/okf/`), and synthesizes a serene, beautifully readable, and 100% grounded response for the seeker—without revamping existing architecture and without running full 515-video re-transcription.

---

## 1. Forensic Diagnosis: Why First-Person & General Chat Felt "Bad"

### A. First-Person Verbatim Deficiencies
1. **Grammatically Severed Heads (Headless Predicates)**:
   - *Symptom*: Clips opening with `"have desired success you have desired companionship..."` instead of `"Throughout your life, you have desired..."`.
   - *Root Cause*: `snap_to_sentences` in `boundaries.py` cuts back to the nearest terminal punctuation. Spoken pauses or Whisper mid-sentence periods sliced the subject clause off, leaving a bare predicate verb (`have desired`).
2. **Missing Practice Pairing (Single-Clip Deduplication Blindness)**:
   - *Symptom*: When a user asks *"What teachings or practices do you suggest for inner peace?"*, only abstract philosophy is returned, with no practical meditation steps.
   - *Root Cause*: `FirstPersonStore.search_hybrid` enforces a hard `deduplicate_clips_by_video(max_clips=dedup_limit)` rule allowing only **1 clip per video**. In discourse `0Fa4Wyv0GOk`, Clip 3 has the doctrine ("Peace is the end of conflict", 52.7s) while Clip 1 has the actual physical meditation practice (Pranamudra / Namaskara Mudra, 30.2s). The deduplicator picked Clip 3 and suppressed Clip 1!
3. **ASR Wall-of-Text (Missing Formatting & Punctuation)**:
   - *Symptom*: Raw Whisper output lacks sentence structure, capitalization, and paragraphing, reading like an unpunctuated transcript dump.
4. **Lack of Connective Synthesis**:
   - *Symptom*: Clips are dumped as raw isolated quotes with zero spiritual framing or gentle guidance.

### B. General Chat Deficiencies
1. **Verification Fail-Closed Abstention**:
   - *Symptom*: Returned: *"That one I cannot answer from the teachings I hold. Ask me differently and let us see what opens."*
   - *Root Cause*: The generator model produced loose philosophical generalizations instead of verbatim citations; `verify_answer` scored `faithfulness=0.00` and correctly failed closed to protect doctrine integrity.

---

## 2. Architecture & Design Decisions (Ponytail Principle)

- **"No revamping this"**:
  - The core first-person retrieval pipeline (`FirstPersonStore`, Qdrant multi-vector hybrid RRF, exact Redis cache, serve-time integrity gate, calibrated confidence) remains completely intact.
  - The Crisis/Safety pre-check remains untouched (zero edits to `distress_stage.py`, `serene_mind_engine.py`, or `lightweight_handler.py`).
- **"Except ingesting all videos do the remaining"**:
  - We do not run the 515-video Whisper/ECAPA re-ingestion.
  - We use the existing 45-video indexed corpus in `first_person_v7` and the 600+ curated doctrine markdown files in `memory/okf/`.
- **The LLM Quote-Weaver (`backend/services/quote_weaver.py`)**:
  - A dedicated, lightweight synthesis module that:
    1. Receives verified verbatim clips from Qdrant + relevant OKF doctrine from `memory/okf/`.
    2. Calls the configured LLM (`OpenRouterService` / `NimService` / `Sarvam`) with a strictly constrained prompt.
    3. Employs DSPy-style assertion validation (`QuoteWeaverAssertionGate`):
       - Asserts that every spiritual claim in quotes is a 100% exact verbatim substring of the input clips or OKF teachings.
       - Asserts zero fabricated quotes or invented doctrine.
       - Asserts proper markdown structure: (1) Spiritual Welcome, (2) Verbatim Teaching, (3) Guided Practice, (4) Living the Wisdom.
    4. If LLM generation fails assertions or experiences network error, fails open to the clean formatted template of the clips.

---

## 3. Tasks Breakdown

### Phase 1: Boundary Integrity & Headless Predicate Repair
- [x] **Task 1.1: Headless Predicate Detection & Subject Recovery in `boundaries.py`**
  - Added detection for auxiliary verb openings without inverted subjects.
  - Sentence snapping preserves true sentence start clause.
- [x] **Task 1.2: Refine Sentence Snapping in `build_first_person_index.py`**
  - Snapping retains `"You have desired for so many things throughout your life you have desired success..."` in `0Fa4Wyv0GOk` (99.76s -> 155.27s).
- [x] **Task 1.3: Apply Fix to Qdrant `first_person_v7`**
  - Re-indexed with `--apply --collection first_person_v7 --snap-boundaries`.
  - 160 of 160 clips boundary-clean (100.0%).

### Phase 2: Multi-Clip Practice Pairing in FirstPersonStore & Pipeline
- [x] **Task 2.1: Enhance `deduplicate_clips_by_video` in `first_person_store.py`**
  - Added `allow_same_video_distinct_spans=True` and `min_span_gap_ms=30_000`.
  - Allows pairing of doctrine + meditation practice from the same discourse.
- [x] **Task 2.2: Practice Intent Routing in `first_person_pipeline.py`**
  - Detects keywords `"practice"`, `"meditation"`, `"how to"`, `"technique"`, `"exercise"` and enables distinct span retrieval.

### Phase 3: In-Memory OKF Vector Matcher & First-Person Pipeline Wiring
- [x] **Task 3.1: Ultra-Fast (<1ms) OKF Matcher in `services/memory/okf_store.py`**
  - In-memory numpy dot product over 715 BGE-M3 embedded entries from `memory/okf/compiled.json`.
  - Measured at 0.28ms search latency.
- [x] **Task 3.2: Wire OKF Matching into `FirstPersonPipeline.execute()`**
  - In `backend/services/first_person_pipeline.py`: retrieves matching OKF entries, priority boosts `type="practice"`, and emits `curated_okf` citations.

### Phase 4: DSPy-Style LLM Quote-Weaver (`services/quote_weaver.py`)
- [x] **Task 4.1: Implement `QuoteWeaverService`**
  - 4-part serene response: Spiritual Orientation, Core Teaching, Guided Practice, Living the Wisdom.
- [x] **Task 4.2: Implement `QuoteWeaverAssertionGate`**
  - Hard assertion gate enforcing 100% exact substring quotation from sources with zero hallucination.
- [x] **Task 4.3: Wire Quote-Weaver into `first_person_pipeline.py` & `api/first_person.py`**
  - Wired into pipeline and router.

### Phase 5: Verification & End-to-End Live Evaluation
- [x] **Task 5.1: Unit & Regression Tests**
  - 89 passed in 0.55s across `test_first_person_store.py`, `test_first_person_pipeline.py`, and `test_quote_weaver.py`.
- [x] **Task 5.2: End-to-End Query Test**
  - Query: *"I want to experience deeper inner peace. What teachings or practices do you suggest?"*
  - First-Person Quote-Weaving: `status="success"`, `is_direct_answer=True`, 5 citations (3 video clips + 2 OKF entries).
  - General Chat: `grounding_state="grounded"`, 21.08s latency.
