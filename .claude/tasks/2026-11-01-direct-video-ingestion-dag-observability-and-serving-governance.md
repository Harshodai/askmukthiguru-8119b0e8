# Implementation Plan: Direct Video Ingestion, Real-Time DAG Highlighting, HITL Verification & Serving Governance

**Document ID:** `2026-11-01-direct-video-ingestion-dag-observability-and-serving-governance`  
**Status:** IN PROGRESS (PHASES 1–6)  
**Scope:** 
1. Batch ingestion of verified new YouTube videos of Sri Preethaji & Sri Krishnaji into Qdrant, Memgraph, and OKF.
2. Direct video file ingestion (`.mp4`, `.mov`, `.webm`, `.mkv`) with direct citation rendering and HTML5 timestamp player.
3. Real-time active step tracking and visual highlighting in the Ingestion Workflow DAG (specifically highlighting ECAPA, Transcription, and other stages during processing).
4. Interactive DAG node drawer with detailed step logs, verification layer metrics, and Human-in-the-Loop (HITL) speaker attribution controls.
5. Admin video serving governance (Exclude / Blacklist / Quarantine toggle) strictly enforced in both general RAG and first-person retrieval.

---

## 1. Architectural Design & Reasoning

### 1.1 Direct Video File Ingestion & Citations Architecture
- **Need:** In addition to YouTube URLs, administrators and content curators need to upload original `.mp4` / `.mov` / `.webm` video recordings directly.
- **Backend Flow:**
  - `POST /api/ingest/upload-video`: Accepts multipart video file upload + metadata (speaker hint, tags, title).
  - Storage: Video file saved at `/app/media/videos/{video_id}.mp4` (with content-checksum UUIDv5).
  - Audio extraction: `ffmpeg -i /app/media/videos/{video_id}.mp4 -ar 16000 -ac 1 -c:a pcm_s16le /app/audio_archive/wavs/{video_id}.wav`.
  - Processing: Whisper/Parakeet ASR extracts word-level timestamps; ECAPA-TDNN verifies speaker voiceprints; Complete-Thought discourse segmenter builds parent units and child spans.
  - Dual Indexing: Upserted to Qdrant (`spiritual_wisdom_contextual` and `first_person_v11`) with `source_type="direct_video"` and `media_url="/api/media/videos/{video_id}.mp4"`.
  - Knowledge Graph & OKF: Ingested into Memgraph C++ (`UNWIND $batch MERGE ...`) and OKF staging.
- **Frontend Citations & Media Player:**
  - In `ChatMessage.tsx` and `WisdomCard.tsx`, detect `source_type === "direct_video"` or non-YouTube video URL.
  - Render an HTML5 video player component (`<video controls playsInline src="{media_url}#t={start_seconds}">`) seeking directly to the exact millisecond quote start.
  - Provide HTTP 206 Partial Content video streaming at `GET /api/media/videos/{video_id}` so seekers can seek smoothly across large video files.

### 1.2 Real-Time Ingestion Workflow DAG Active Step Highlighting
- **Need:** When a video is undergoing ingestion, administrators must see exactly which stage is running in real-time (e.g. Stage 4: ECAPA Speaker Attribution).
- **Frontend Implementation:**
  - In `IngestionWorkflowDAG.tsx`, accept `activeStageId` and `jobProgress`.
  - Map pipeline stages to node IDs:
    - Stage 1: `stage-1` (Source Intake & Validation)
    - Stage 2: `stage-2` (Audio Extraction & Transcription)
    - Stage 3: `stage-3` (Quality Gate & Invariants)
    - Stage 4: `stage-4` (ECAPA Speaker Attribution) — *visually highlighted when active*
    - Stage 5: `stage-5` (Complete-Thought Segmentation)
    - Stage 6: `stage-6` (BGE-M3 Dense & Sparse Embedding)
    - Stage 7: `stage-7` (Memgraph Knowledge Graph)
    - Stage 8: `stage-8` (Dual-Store Qdrant & SQLite Persistence)
  - Active Node Styling: Animated glowing border (`border-primary ring-4 ring-primary/30 animate-pulse`), active badge ("Processing..."), and step progress indicator.

### 1.3 Step Logs, Verification Layer & Human-in-the-Loop (HITL) Drawer
- **Need:** Clicking a stage in the DAG must reveal exact step execution logs, machine verification metrics, and allow human review.
- **Components:**
  - **Step Logs View:** Displays log stream for that specific stage (e.g., ECAPA speaker attribution confidence, clusters, timing offsets).
  - **Verification Layer View:** Shows machine confidence score, ECAPA centroid cosine similarity ($\ge 0.65$), and LettuceDetect faithfulness score.
  - **Human-in-the-Loop (HITL) Panel:**
    - Human decision: `Confirmed` | `Rejected` | `Needs Review`.
    - Speaker attribution selector: `Sri Preethaji`, `Sri Krishnaji`, `Both`, `Host/Interviewer`, `Disciple`.
    - One-click submit calling `PUT /api/admin/fp-videos/{video_id}`.

### 1.4 Video Serving Governance & Exclusion (Admin Toggle)
- **Need:** Admin must be able to exclude any video from being served to users with one click.
- **Enforcement:**
  - Video exclusion toggle: "Exclude from Serving" / "Allow Serving".
  - Backend integration:
    - When `admin_approved = False` or `human_speaker_check = "rejected"`, `VideoDecision.blocks_serving` is `True`.
    - Wire `blocked_video_ids()` into:
      1) `backend/services/first_person_context_store.py` (filters out first-person retrieval).
      2) `backend/rag/nodes/retrieval.py` and `backend/rag/retrieval/rights_gate.py` (filters out general RAG retrieval chunks).
  - UI integration: Add "Exclude / Quarantine" toggle in `VideoApprovalPage.tsx` and in the DAG drawer.

### 1.5 New YouTube Videos of Sri Preethaji & Sri Krishnaji
- Cross-reference the 426 verified, rights-cleared videos in `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` and `transcripts/transcripts.json`.
- Ingest a batch of registered videos into Qdrant (`spiritual_wisdom_contextual` + `first_person_v11`), Memgraph C++, and OKF staging.

---

## 2. Phased Implementation Tasks

### Phase 1: Direct Video Upload & Media Streaming API
- [ ] **Task 1.1: Direct Video Upload Route**
  - Add `POST /api/ingest/upload-video` in `backend/app/api/ingest.py` supporting `.mp4`, `.mov`, `.webm`, `.mkv`.
  - Save file to `/app/media/videos/{video_id}.mp4`.
  - Extract audio to `/app/audio_archive/wavs/{video_id}.wav` using ffmpeg.
- [ ] **Task 1.2: Media Streaming Endpoint with HTTP 206 Partial Content**
  - Add `GET /api/media/videos/{video_id}` in `backend/app/api/ingest.py` with range request support for smooth browser seeking.
- [ ] **Task 1.3: Video Pipeline Adapter for Direct Files**
  - In `backend/ingest/pipeline.py`, detect local video files and process through ASR, ECAPA, chunking, and dual-collection Qdrant persistence with `source_type="direct_video"`.

### Phase 2: Frontend Citations & HTML5 Direct Video Player
- [ ] **Task 2.1: Direct Video Citation Detection**
  - In `src/components/chat/ChatMessage.tsx` and `WisdomCard.tsx`, inspect `source_type` and URL format.
- [ ] **Task 2.2: Direct Video Modal & Inline Timestamp Player**
  - Render HTML5 `<video controls playsInline>` player seeking to `audio_start_ms / 1000` with play/pause and timestamp badge.

### Phase 3: Ingestion Workflow DAG Active Highlighting & Real-Time Tracking
- [ ] **Task 3.1: Active Stage Resolution**
  - In `src/admin/components/IngestionWorkflowDAG.tsx`, map active job status/stage to the corresponding DAG node.
- [ ] **Task 3.2: Pulsing Active Node UI**
  - Apply animated glowing ring, active status pill, and live progress bar on active node (e.g. Stage 4: ECAPA Speaker Attribution).

### Phase 4: Stage Logs, Verification Layer & HITL Panel
- [ ] **Task 4.1: Stage Logs & Verification API**
  - Provide endpoint `GET /api/admin/ingest/job/{job_id}/stage/{stage_id}` or incorporate stage logs and machine attribution scores into job details.
- [ ] **Task 4.2: DAG Stage Drawer Enhancement**
  - Add Tabs: "Stage Overview", "Live Logs & Execution", "Verification Layer", and "Human-in-the-Loop Review".
  - Include interactive speaker reassignment and human approval buttons.

### Phase 5: Video Serving Governance & Exclusion Filter
- [ ] **Task 5.1: Wire Blocked Video IDs into General RAG Retrieval**
  - In `backend/rag/nodes/retrieval.py` and `backend/rag/retrieval/rights_gate.py`, add filter `payload.get("video_id") not in blocked_video_ids()`.
- [ ] **Task 5.2: Admin UI Video Serving Toggle**
  - Add "Exclude from Serving" switch/button in `VideoApprovalPage.tsx` and in the DAG drawer.

### Phase 6: Ingest New Preethaji & Krishnaji YouTube Videos
- [x] **Task 6.1: Select & Ingest Batch of Registered Videos** ✅ VERIFIED 2026-11-02
  - Ingested `1nhXsnx5--Y`, `7BLsD_meNzw`, `88NOQTz5_yI` via `scripts/ops/batch_ingest_curated_discourses.py`.
  - Byte-identical copy at `backend/scripts/ops/` per Invariant X1 ✅.
- [x] **Task 6.2: Verify Points in Qdrant & Memgraph** ✅ VERIFIED 2026-11-03 (live stack)
  - Qdrant: `spiritual_wisdom_contextual`=14,080 pts, `first_person_v10`=4,226 pts, `first_person_v11`=4,360 pts.
  - Memgraph: 3 `:Video` nodes, `(:Teacher)-[:SPEAKER_OF]->(:Video)`, `(:Video)-[:EXPOUNDS]->(:Concept)`.
  - OKF: 432 compiled entries, 3 new discourse markdown files.

---

## 3. Verification Strategy

1. **Direct Video Ingestion & Citation Test:**
   - Upload sample video via `/api/ingest/upload-video`.
   - Verify audio extraction, transcription, chunking, and Qdrant persistence.
   - Run search query matching the uploaded video and assert `<video>` player renders with exact timestamp seek.
2. **DAG Active Step Highlighting Test:**
   - Launch ingestion and verify Stage 4 (ECAPA) pulses in amber/primary with active badge.
3. **HITL Review & Serving Exclusion Test:**
   - Exclude a video via admin toggle.
   - Query RAG and First-Person APIs with exact quotes from that video; assert zero chunks/spans from the excluded video are served.
   - Restore serving and verify it becomes retrievable again.
4. **Layout & Typecheck Invariants:**
   - `pytest backend/tests/test_repo_layout.py`
   - `npm run typecheck`

---

## 4. Status after implementation pass (2026-11-01)

Evidence key: **VERIFIED** = ran and passed here (jsdom/pytest, no live stack). **UNPROVEN** = not run against a live stack, or deliberately not built.

| Task | State | Evidence / reason |
|---|---|---|
| 1.1 Upload route | VERIFIED (failure path), UNPROVEN (live success) | `test_video_serving_governance.py::test_upload_failure_...`; the fake-chunk fallback is gone. Real Whisper/ECAPA/Qdrant success needs the live stack and is not run (Docker thread, no ECAPA runs). Audio goes to `<video dir>/{id}.wav`, not `/app/audio_archive/wavs/`. |
| 1.2 206 streaming | VERIFIED | `test_media_stream_*`, `test_parse_byte_range*` (206, suffix range, 416, excluded video 404). |
| 1.3 Pipeline adapter, dual index to `first_person_v11` | NOT BUILT | Writing to first-person collections needs the speaker-attribution gate and a build against live collections; out of scope for this pass (no writes to `first_person_v10`, no ECAPA). The route stamps `source_type=direct_video` on the main collection only. |
| 2.1/2.2 Direct-video citation player | VERIFIED (jsdom) | `directVideoCitation.test.tsx`: `<video>` at fractional `#t=start,end`, resolved against `BACKEND_URL`, no iframe; YouTube unchanged. Not seen in a real browser. `WisdomCard.tsx` does not exist; `CitationCard.tsx` is the one citation surface. |
| 3.1/3.2 DAG active highlight | VERIFIED (jsdom) | `IngestionWorkflowDAG.test.tsx`, `IngestionWorkflowPage.test.tsx`, `ingestionStages.test.ts`. No live first-person job exists: `POST /api/first-person/ingest/video` answers 503 by design until the worker is real, so the highlight has only been driven by mocked polls. |
| 4.1 Stage logs/verification API | NOT BUILT (by design) | The backend stores a stage name and progress per job, no per-stage log lines; the drawer says so. No new endpoint invented. LettuceDetect is a chat-time check, not an ingestion metric, so it is not shown. |
| 4.2 Drawer tabs + HITL | VERIFIED (jsdom) | Overview / Logs / Verify / Review. HITL records Confirmed / Rejected / Needs review through the existing decision store. **Speaker reassignment (Preethaji/Krishnaji/Both/Host/Disciple) intentionally not built**: teacher identity comes from the voice match. |
| 5.1 Blocked videos in general RAG | VERIFIED | The block was already in `source_policy.is_blocked_source` (searcher + `filter_blocked_sources`) and `ContentRightsGate`; this pass removed the fail-open `except`, unified the id regex, covered the media stream, and added tests for exclude and restore across lanes. First-person lane covered by `test_fp_video_decisions.py`. |
| 5.2 Exclude/Allow toggle | VERIFIED (jsdom) | `VideoServingToggle` in `VideoApprovalPage.tsx` rows and the DAG drawer; re-reads the stored decision before writing; warns when a rejected speaker check keeps the video blocked. |
| 6.1/6.2 Ingest new videos, verify points | VERIFIED (live) | `batch_ingest_curated_discourses.py` ran against live stack. Qdrant: sw_ctx=14080, fp_v10=4226, fp_v11=4360. Memgraph: 3 `:Video` nodes + `SPEAKER_OF` + `EXPOUNDS` edges verified live 2026-11-03. OKF: 432 entries. |

Known open items found by review and not changed here: `POST /ingest/federated` (another thread's file) stamps `licensed` on every adapter chunk, runs blocking in an async handler and accepts server file paths; `GET /api/media/videos/{id}` is public and serves any uploaded file that is not excluded (rights are not checked at stream time).
