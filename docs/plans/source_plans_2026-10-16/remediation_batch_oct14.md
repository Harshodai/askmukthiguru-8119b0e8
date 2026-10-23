# Production-Readiness & Remediation Master Plan (Oct 14, 2026)

## 1. Operating Frame & Product Invariants
- **Role**: Sole writer continuing production-readiness work on AskMukthiGuru (`feat/clip-quality-grading`).
- **Target**: Make the product safe and usable for faculty testing on Railway (Gate 2/3), then public users, proving every step with empirical evidence.
- **Product Truth**: A seeker asks a question and receives a verbatim recorded clip of Sri Preethaji or Sri Krishnaji with speaker and timestamp, or an honest abstain. Crisis handling runs before anything else. General chat is off by default; the general graph runs only when a signed-in seeker clicks Personalize. Every clip is labelled "Related, not a direct answer" until a calibration profile fitted on human labels exists.
- **First-Person Invariants**: Answers are the teacher's recorded clips, never text generated in the teacher's voice (the model speaks "never as the founders themselves"). CLAUDE.md lines 116-119 conflict with these invariants (handoff PA-1); the root first-person invariants and task list prevail.

---

## 2. Current Starting State (Inspection & Diagnosis)
- **Git Branch & HEAD**: `feat/clip-quality-grading` at `fb608569498d7a019c05fabfc09199630ca03758`.
- **Docker & Stack Status**:
  - All 9 Docker containers (`mukthiguru-backend`, `mukthiguru-redis`, `mukthiguru-qdrant`, `mukthiguru-memgraph`, `mukthiguru-frontend`, etc.) are **UP and healthy**.
  - Backend internal health check returns HTTP 200 `ready: true, status: healthy`.
  - Host port forwarding from macOS host can experience resets; container-internal access via `docker exec mukthiguru-backend` has direct, low-latency access to the running stack.
- **PR #68 Checks**: 4 checks failing on GitHub from earlier commit; local branch has resolved all underlying issues (`gitleaks`, `trivyignore`, `dependency-check`, `license-exceptions`, etc.).
- **Uncommitted Files**: 41 files in working tree (28 code review findings + tests + documentation updates completed in Phase 0). Ready for explicit commit when approved.
- **First-Person Running Configuration**:
  - `first_person_mode`: `hybrid` (**superseded 2026-10-20: the code default is
    `retrieval_only`; `hybrid` is opt-in via `FIRST_PERSON_MODE=hybrid` — see
    `lessons.md` `L-FP-MODE-DEFAULT-1`**) — this snapshot records how the stack
    was running on 2026-10-16, not the current default.
  - `first_person_uncalibrated_direct_enabled`: `False`
  - `first_person_relevance_min_score`: `3`
  - `first_person_quality_allowlist_path`: `""`
  - `first_person_quality_blocklist_path`: `""`
  - `first_person_answerability_check_enabled`: `True`

---

## 3. Work Sequence

### Phase 0: Block 0 — Unblock & Code Review Fixes (COMPLETED)
- [x] All 28 code review findings implemented and verified across 19 files.
- [x] Pre-commit Gitleaks failure resolved via `.gitleaks.toml` allowlist.
- [x] Prompt audit hunks H2 (`CLAUDE.md`) and H4 (`first_person_pipeline.py`) applied.
- [x] Frontend tests passed: 841 vitest tests green, TypeScript 0 errors.
- [x] Backend tests passed: 173 unit tests green across modified components.

---

### Phase 1: Critical Safety Fix — LV-1 in `backend/rag/nodes/intent.py` (IN PROGRESS)
- [ ] **Subagent 1: Distress & Safety Specialist**:
  - **Root Cause**: `handle_distress` in `backend/rag/nodes/intent.py:1405` ran inline retrieval over the chat corpus and called `ollama.generate()` with `STIMULUS_RAG_PROMPT` to synthesize model prose for MODERATE/MILD distress, generating ungrounded claims attributed to founders ("Sri Preethaji & Sri Krishnaji teach us that...") with speakerless citations.
  - **Fix Implementation**:
    - For MODERATE (and MILD) distress, remove the `ollama.generate()` founder teaching prose path.
    - Return the safety boundary combined with either a verified verbatim first-person clip (if available) or the fixed, clinician-reviewed Serene Mind template `serene_mind.get_response(assessment)`.
    - Set `citations = []` when no verbatim clip is served.
    - Preserve SEVERE and CRISIS pre-emption and 24/7 helpline blocks (14416 / 988) exactly as-is.
  - **Testing & Verification**:
    - Add regression test `test_lv1_distress_no_generated_teachings.py` proving no distress response contains generated text claiming to be founder teachings ("teach" + teacher name).
    - Update existing distress tests to verify the zero-generation contract.
    - Ensure 100% pass rate on crisis probes.
- [ ] **Subagent 2: Independent Safety Reviewer**:
  - Perform independent adversarial code review of the LV-1 fix and recent safety changes (`9c33dcb4` to HEAD) to verify zero-generation invariant, lack of founder impersonation, fail-closed posture, and crisis pre-emption.

---

### Phase 2: LV-3 Diagnostic Evaluation (Coverage Collapse)
- [ ] **Subagent 3: Live Pipeline and Eval Specialist**:
  - **Problem**: In 12-question reading, only 1 of 7 on-topic spiritual questions served a clip ("Soul Sync" abstained on `relevance_below_min`).
  - **Diagnostic Experiment**: Run the frozen 29 diagnostic questions through the running stack toggling suspected factors one at a time:
    1. Arm A (Baseline): current defaults (QBUG-7 full-clip input, CA-3 JSON schema, word floor 15, relevance min 3).
    2. Arm B: QBUG-7 toggled (first 350 chars vs full clip).
    3. Arm C: CA-3 toggled (plain text JSON vs structured output).
    4. Arm D: Word floor toggled (10 words vs 15 words).
    5. Arm E: Relevance min toggled (2 vs 3).
  - Record per-arm served counts and blind-judged precision in `PROD_READINESS_TASK_LIST_2026-10-11.md`.
  - Maintain invariant: do NOT permanently lower relevance min without explicit owner decision.

---

### Phase 3: Re-run 12-Question Live Reading
- [ ] Query the running stack with the 12 questions from `HANDOFF_2026_10_14.md` Section 12.
- [ ] Record question-by-question results in Section 12: clip text, speaker, timestamp, label, abstain phrasing, and latency.
- [ ] Confirm question 11 (loneliness) returns the compassionate Serene Mind template without generated founder teaching prose (closing LV-1).

---

### Phase 4: Block 1 — Gate 1 Live Proof (E-1, E-2)
- [ ] **10 Real Questions Reading**: Query running app via `/api/chat` and `/api/first-person/query` and evaluate answers from a faculty member's perspective.
- [ ] **Six-Language Crisis Probes**: Execute `evals/scenarios/tier3_crisis/007_six_language_crisis_distress_probes.yaml`. Verify 100% trigger crisis pre-emption, zero rate-limiting, zero load-shedding.
- [ ] **Out-of-Corpus Leak Test**: Run 30+ off-topic questions; verify 100% honest abstention with zero leaks.
- [ ] **Snapshot Restore Drill (QD-1)**: Rehearse restore of `first_person_v8` snapshot into a scratch collection in Qdrant.
- [ ] **Quiet-Stack Latency Baseline**: Measure latency distribution (p50, p95) on uncached distinct questions.
- [ ] **Independent Subagent Audit**: Review all safety and serving changes.

---

### Phase 5: Confidence & Release Gate Reporting
- [ ] Compute and record Section 15 confidence scores for E-1 through E-8 with verifiable evidence.
- [ ] Summarize rows closed with commit IDs.
- [ ] Detail human-only blockers for Owner.

---

## 4. Subagent Delegation Architecture
1. **Subagent 1 (Safety Implementation)**:
   - Type: `self`
   - Role: `Distress Safety Specialist`
   - Scope: `backend/rag/nodes/intent.py`, `backend/tests/test_distress_*.py`, new test `backend/tests/test_lv1_distress_no_generated_teachings.py`.
2. **Subagent 2 (Safety Audit)**:
   - Type: `self`
   - Role: `Safety Reviewer`
   - Scope: Independent code review of `backend/rag/nodes/intent.py`, `backend/app/pipeline/stages/distress_stage.py`, `backend/app/pipeline/stages/personalize_stage.py`.
3. **Subagent 3 (Live Evaluation)**:
   - Type: `self`
   - Role: `Live Pipeline and Eval Specialist`
   - Scope: Live execution of 12-question reading, 6-language crisis probes, 29-question diagnostic evaluation, and snapshot restore drill inside the running stack.

---

## 5. Decision & Evidence Log
- **2026-10-14 Phase 0**: All 28 code review findings implemented and verified. Gitleaks 0 leaks confirmed.
- **2026-10-14 Docker Status**: Confirmed healthy backend on internal container port 8000.
