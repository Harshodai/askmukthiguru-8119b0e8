# Master Engineering Handoff: First-Person Verbatim Pipeline & Ruthless Paraphrase Audit

**Date:** 2026-09-28  
**Author:** Antigravity / Pair Programming Agent  
**Context:** First-Person Verbatim Serving (`first_person_v5` vs `first_person_v2`), Sentence Boundary Conjunction Guard, and Philosophical Context Windowing.  
**Target Audience:** Incoming Staff Engineer / Antigravity Agent continuing this stream.

---

## 1. The Goal We Are Working Toward

The objective is to establish an uncompromised, production-safe **First-Person Verbatim Teaching Route** (`FIRST_PERSON_MODE`) for AskMukthiGuru.
- **Verbatim Integrity:** When seekers ask spiritual and life questions, Sri Preethaji and Sri Krishnaji's recorded discourses must be served in their exact spoken words, with millisecond-accurate video timestamp pointers and cryptographic SHA-256 hashes matching the raw transcript.
- **Zero Hallucination / Zero Severed Thoughts:** Answers must NEVER be LLM-manufactured summaries or fragmented mid-sentence snippets. Every clip served must form a complete grammatical, conceptual, and philosophical unit.
- **Fail-Closed Architecture:** If a clip lacks proper speaker verification, has transcription artifacts, terminates on a dangling conjunction, or falls below calibration thresholds, the system must fail closed (honest abstention or crisis redirect), never serving broken fragments.

---

## 2. Current State of Code

1. **Docker Backend Container (`mukthiguru-backend`):**
   - Running, healthy, and verified on `http://localhost:8000/api/health` (`ready: true, status: healthy`).
   - All core components operational: Qdrant (`first_person_v2`, `first_person_v5`, `spiritual_wisdom`), Redis, Memgraph, ONNX INT8 BGE-M3 Embedder, FlashRank, and LettuceDetect.
2. **Serving Layer Integrity Gate (`backend/services/first_person_pipeline.py`):**
   - Implemented `_DANGLING_CONJUNCTION_RE = re.compile(r"\b(or|and|so|but|because)\s*[.,;:!?…—–-]*$", re.IGNORECASE)`.
   - Wired into `_passes_integrity_gate(clip)`: any clip terminating on a dangling coordinating conjunction is rejected and quarantined from serving.
   - Live verified inside Docker: on queries 3A, 3B, and 3C, corrupt clips from `hUmlujE6SN0` (`"...fear or"`) and `cHAJiF2byzg` were automatically quarantined from serving, successfully serving complete teachings or safely abstaining.
3. **Indexing Layer Hard Gate (`backend/scripts/ops/build_first_person_index.py` & `scripts/ops/build_first_person_index.py`):**
   - Added `_DANGLING_CONJUNCTION_RE` to `_gate_clip()`: returns `"dangling_conjunction"`, dropping defective clips or quarantining corrupt video passages.
   - Synchronized `backend/scripts/ops/build_first_person_index.py` with `scripts/ops/build_first_person_index.py`.
4. **Diarization & Segmentation Pipeline (`backend/services/speaker_diarization.py`):**
   - Defined `_COORDINATING_CONJUNCTIONS = frozenset({"or", "and", "so", "but", "because", "nor", "for", "yet", "although", "though"})`.
   - Updated `_find_sentence_end()`: skips coordinating conjunctions even if punctuated.
   - Updated `_cut_point()`: evaluates inter-word pauses; if the word preceding the pause is a coordinating conjunction, shifts the cut *before* the conjunction (`return best_idx, "pause"`). The conjunction stays with the following clause, preventing dangling clips.
   - Updated `_split_run()`: strips trailing conjunctions from chunks and run tails.
5. **Test Suite Status:**
   - **85/85 passed in Docker (`pytest`)**:
     - `backend/tests/test_first_person_pipeline.py`: 49 passed (includes parametrized tests for trailing conjunctions and positive sentence controls).
     - `backend/tests/test_build_first_person_index.py`: 21 passed (includes `test_dangling_conjunction_quarantined`).
     - `backend/tests/test_clips_v2.py`: 15 passed (includes `test_n_pause_at_conjunction_does_not_split_after_conjunction`).
6. **Invariants & Documentation:**
   - Updated [`lessons.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/lessons.md): Added 9 verified lessons (`L-V5-EVAL-PROMOTION-1` through `L-SEMANTIC-DRIFT-DENSITY-1`).
   - Updated [`CLAUDE.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/CLAUDE.md): Added Invariant 10 (Sentence Boundary & Conjunction Integrity) and Invariant 11 (Philosophical Context Windowing).
   - Working tree contains zero unapproved git commits.

---

## 3. Files Actively Edited

- [`backend/services/first_person_pipeline.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/first_person_pipeline.py): Serving-time integrity gate for trailing conjunctions.
- [`backend/scripts/ops/build_first_person_index.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/scripts/ops/build_first_person_index.py): Indexing gate for trailing conjunctions.
- [`scripts/ops/build_first_person_index.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/ops/build_first_person_index.py): Synced repo-root indexing script mounted into Docker.
- [`backend/services/speaker_diarization.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/services/speaker_diarization.py): Sentence boundary detection, pause cut shifting, and conjunction look-ahead.
- [`backend/tests/test_first_person_pipeline.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/tests/test_first_person_pipeline.py): Added unit tests for trailing conjunction gating.
- [`backend/tests/test_build_first_person_index.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/tests/test_build_first_person_index.py): Added index gating test for dangling conjunctions.
- [`backend/tests/test_clips_v2.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/tests/test_clips_v2.py): Added segmentation cut test for pause at conjunction.
- [`lessons.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/lessons.md): Documented root causes and rules.
- [`CLAUDE.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/CLAUDE.md): Added Invariants 10 and 11.
- [`.claude/tasks/conjunction_guard_and_docker_test.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.claude/tasks/conjunction_guard_and_docker_test.md): Task tracking and verification log.

---

## 4. Everything Tried and Failed (Forensic Post-Mortem)

1. **Attempted: Naively splitting on pause boundary following a conjunction.**
   - *What happened:* In `speaker_diarization.py`, when a speaker uttered a coordinating conjunction (`"or"`, `"and"`) and took an acoustic hesitation pause (0.5–0.8s), naive segmentation cut right after the conjunction. This caused clip `hUmlujE6SN0 (328.42s–339.82s)` to end with `"...from stress and anxiety and fear or"`, severing the thought before Sri Krishnaji's resolution.
   - *Why it failed:* Hesitation pauses after conjunctions are acoustically salient but grammatically internal to the coordinate structure.
   - *Fix:* In `_cut_point()`, when the word preceding a pause is in `_COORDINATING_CONJUNCTIONS`, shift the cut index *before* the conjunction (`return best_idx, "pause"`). The conjunction remains at the head of the following clause.
2. **Attempted: Skipping conjunction tokens in pause scanning.**
   - *What happened:* When we initially tested `if w in _COORDINATING_CONJUNCTIONS: continue` inside the pause gap scanning loop, `_cut_point` completely ignored the 0.8s pause following "or" and fell back to cutting on minor 0.05s internal gaps between random words (e.g. cutting after "anxiety").
   - *Why it failed:* Skipping the token prevented the algorithm from identifying where the major pause actually occurred.
   - *Fix:* Evaluate every pause gap to find `best_gap`, and only *then* check if the chosen token is a conjunction; if so, step back before it.
3. **Attempted: Running `pytest` in Docker without mounting `build_first_person_index.py`.**
   - *What happened:* `test_build_first_person_index.py` failed with `ImportError: cannot import name 'build_first_person_index' from 'scripts.ops'`.
   - *Why it failed:* `backend/docker-compose.yml` mounts `- ../scripts:/app/scripts`. The repo root `scripts/` shadowed `backend/scripts/`, and `build_first_person_index.py` only existed in `backend/scripts/ops/`.
   - *Fix:* Synchronized `backend/scripts/ops/build_first_person_index.py` to `scripts/ops/build_first_person_index.py`.
4. **Attempted: Reloading backend via `docker compose restart backend`.**
   - *What happened:* Uvicorn inside `mukthiguru-backend` runs without `--reload`. A simple restart did not re-initialize modified service containers cleanly.
   - *Fix:* Followed lesson `L-DOCKER-ENV-1`: recreate or run `docker restart mukthiguru-backend`, then verify via `/api/health`.

---

## 5. Next Steps to Take

1. **Re-segment and Re-index Pilot 20 / Batch 2 Videos:**
   - Run the updated `speaker_diarization.py` pipeline over the raw transcripts of the 38 indexed videos plus the newly cleared Pilot 20 / Batch 2 videos.
   - Build a fresh collection `first_person_v6` using the updated `build_first_person_index.py` with 18–25s rolling windows.
2. **Expand Corpus Density to 100+ Videos:**
   - Solve dense-vector semantic drift (as observed in Query 2C on childhood education) by increasing point density in pedagogical and family-life clusters.
3. **Human Gold Set Calibration (150 Questions):**
   - Fit conformal risk thresholds against human-reviewed labels rather than synthetic bakeoff queries.

---

## 6. What We Learnt & Results from Each Try

### Paraphrase Benchmark Results (`v2` vs `v5`) Across 15 Queries

| Query Group | Topic | `v2` Winner? | `v5` Winner? | Analysis & Findings |
|---|---|---|---|---|
| **1A, 1B, 1C** | Relationship Healing & Hurt | Parity | **`v5` Won** | `v5` eliminated 1.6s host fragments from `0k5f8G9uXqY` and `NFlAszNFZdQ`. Retrieved Sri Preethaji's discourse on love vs inner division. |
| **2A, 2B, 2C** | Education, Competition & Inner State | Parity | **`v2` Won on 2C** | On 2C (*"Why are children never taught..."*), `v5` suffered semantic drift due to sparse corpus density, trapping on generic "state of stress" (`hUmlujE6SN0`) rather than TEDx schooling discourse (`TqxxCYnAxo8`). |
| **3A, 3B, 3C** | Financial Anxiety & Fear | **`v2` Won** | Failed gate | In `v5`, 11.4s clip ended on dangling conjunction `"or"`. `v2`'s 21s window captured the resolution. **Directly motivated Invariant 10 & 11.** |
| **4A, 4B, 4C** | Family Strangers Under One Roof | Parity | **`v5` Won** | `v5` retrieved Sri Krishnaji's discourse on shared vision with clean teacher boundaries. |
| **5A, 5B, 5C** | Inner State Transforming the Home | Parity | Parity | Both collections cleanly retrieved Sri Preethaji's teaching on emotional contagion and peaceful presence. |

### Key Architectural Lessons Formulated
- **`L-SENTENCE-SPLIT-CONJUNCTION-1`:** Never split or terminate a clip on coordinating conjunctions (`"or"`, `"and"`, `"so"`, `"but"`).
- **`L-CONTEXT-WINDOW-PHILOSOPHY-1`:** 11s windows frequently capture only the seeker's premise without the teacher's resolution; 18–25s rolling windows are required for philosophical completeness.
- **`L-SEMANTIC-DRIFT-DENSITY-1`:** Sparse topic clusters (38 videos) cause dense vectors to drift toward generic high-frequency vocabulary; corpus density must be increased before adjusting encoder weights.

---

## 7. Additional Engineering Intelligence & Verification Recipes

### Verification Recipe for Incoming Engineer

To verify that the conjunction gate and test suites remain intact in Docker:
```bash
# 1. Run all 85 unit tests inside the Docker backend
docker exec -e PYTHONPATH=. mukthiguru-backend pytest \
    tests/test_first_person_pipeline.py \
    tests/test_build_first_person_index.py \
    tests/test_clips_v2.py -v

# 2. Check backend health
curl -s http://localhost:8000/api/health | jq .status
# Expected: "healthy"

# 3. Live probe against FirstPersonPipeline for trailing conjunction fail-closed behavior:
docker exec mukthiguru-backend python -c '
from app.dependencies import get_container
from services.first_person_pipeline import FirstPersonPipeline
from services.first_person_store import FirstPersonStore

container = get_container()
store = FirstPersonStore(collection="first_person_v5")
pipe = FirstPersonPipeline(store=store)

q = "I am having financial fear, what should I do?"
enc = container.embedding.encode_single_full(q)
res = pipe.execute(query=q, query_dense_vector=enc["dense"], max_clips=1)

print("Status:", res.status)
print("Served Citations:", len(res.citations))
if res.citations:
    print("Verbatim Text:", res.citations[0]["verbatim_text"])
    assert not res.citations[0]["verbatim_text"].rstrip(".,;:!?…—–-").split()[-1].lower() in ("or", "and", "so", "but", "because")
'
```

### Critical Operational Invariants
- **Do not commit without review:** Working tree has uncommitted modifications; keep changes staged or cleanly tracked without running automated git pushes.
- **Fail Closed Always:** When in doubt between serving a doubtful clip or abstaining, First-Person Pipeline MUST always abstain (`status="abstained"`, citations count 0).
