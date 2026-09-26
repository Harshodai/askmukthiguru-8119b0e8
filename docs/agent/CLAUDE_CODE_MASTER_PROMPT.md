# AskMukthiGuru — Master Claude Code Session Prompt (2026-09-26)

Copy and paste this prompt directly into Claude Code at the start of a session or use it as your task definition:

```markdown
You are an expert systems engineer and AI researcher working on AskMukthiGuru.
Your task is to govern, implement, test, and maintain the First-Person Verbatim Audio-Video Retrieval Architecture.

You MUST follow these binding architectural invariants across all frameworks:

---

### 1. The Core Invariant: Verbatim Serving (Zero-LLM at Runtime)
- In the first-person serving path (`/api/first-person/query` / `FirstPersonPipeline`), the system serves a **cryptographically verified pointer into authentic audiovisual recordings** of Sri Preethaji and Sri Krishnaji.
- **Zero LLM at serve-time**: Never synthesize, paraphrase, or hallucinate teacher quotes. Response latency must remain bounded at 20–40ms p95.
- Offline LLM usage is permitted only for:
  1. Synthetic seeker question generation (`question_dense` vectors for symmetric search).
  2. ASR decoding token priors via `SACRED_VOCABULARY_PROMPT` to protect Sanskrit concepts (*Ekam, Mukthi, Deeksha, Sadhana, Samskara, Vasanas, Ahamkara, Chitta, Ananda, Seva, Beautiful State*).

---

### 2. Cryptographic Integrity & Data Quality (DDIA 2e & Ingestion Safety)
- **SHA-256 Verbatim Gate**: Every clip in Qdrant has a `transcript_hash`. Before returning any citation, `spot_check_verbatim` must enforce:
  `SHA-256(chunk_text) == stored_hash`
  If a hash is missing or mismatched, fail closed (`return False`) and quarantine the point.
- **Ingestion Filtering (`L-INGEST-1`, `L-INGEST-2`)**: All extracted text must pass `find_artifact()`. Never allow provider graceful-degradation canned strings ("I'm currently experiencing a connection issue...") or ASR repetition loops into Qdrant.
- **Manifest DAG**: Verify stage-to-stage hashes in `artifact_manifest.json` before skipping or re-extracting videos.

---

### 3. Conformal Risk Control & Calibration (Learn-Then-Test)
- Never use uncalibrated heuristic similarity thresholds (e.g. `0.75`).
- The operating threshold $\hat{\lambda}$ must be dynamically loaded from `first_person_calibration.json`, fitted via exact finite-sample Clopper-Pearson beta quantiles (`math.lgamma` in log-space) to ensure:
  $$\text{UCB}_{\delta=0.05}(\text{Risk}(\hat{\lambda})) \le 0.01 \quad (\ge 99\% \text{ Precision})$$
- If similarity is below threshold, return `status: "weak_match"` and explicitly label the result as "Related, not a direct answer". Honest abstention is an architectural requirement.

---

### 4. Storage, Idempotency & Blue-Green Lifecycle (DDIA 2e & Qdrant)
- **Deterministic Point IDs**: Derive point IDs via UUIDv5:
  `uuid5(NAMESPACE, f"{source_url}:{chunk_index}:{raptor_level}")`
  Never use random UUIDs or pure transcript hashes (which change on re-transcription).
- **Blue-Green Aliasing**: All re-indexing must write to timestamped shadow collections (`first_person_vYYYYMMDD_HHMMSS`) using `QdrantAliasManager`. When calling `create_collection`, always convert read-side config objects to write-side Diff models (`HnswConfigDiff`, `OptimizersConfigDiff`, `WalConfigDiff`).
- **Diff-Based Stale Pruning**: When applying index builds, snapshot existing IDs first, track produced IDs, and delete stale points (`existing_ids - produced_ids`) via `PointIdsList`. Stale-point cleanup must run even when `indexable_clips` is empty.

---

### 5. Acoustic Segmentation & UX Contracts (RAG Made Simple & Dexa Pattern)
- **VAD Gating**: Silero VAD drops audio windows with <10% speech energy to suppress Whisper hallucination on silent meditation.
- **Clip Builder v2**: Enforce sentence-boundary cuts (12 to 200 words) and merge adjacent teacher turns across micro-pauses.
- **Host-Leak Prevention**: Exclude all segments matching `FORBIDDEN_HOST_SPEAKER_LABELS` (`host`, `questioner`, `interviewer`, `translator`, `narration`).
- **Acoustic Padding**:
  - `playback_start_seconds`: Snapped strictly to the teacher's segment start ($0.25\text{s}$ pad, clamped at $\ge 0$). Multi-second lead-in is strictly prohibited.
  - `playback_end_seconds`: Acoustic resonance tail ($+1.8\text{s}$) to preserve natural speech decay.
  - YouTube player timestamps must use floored integers (`&t=142s`).

---

### 6. Architecture Isolation & API Contracts (Clean Architecture & API Design)
- **Bounded Context**: Keep the first-person route strictly behind `FIRST_PERSON_MODE` / `first_person_route_enabled`.
- **Cache Isolation**: The semantic cache is strictly bypassed on the first-person route. Only SHA-256 exact-match Redis caching (24h TTL) is permitted.
- **Dependency Flow**: Domain core entities and statistical calibrators must remain pure Python without dependencies on FastAPI or Qdrant.
- **Async Safety**: Never inject synchronous `def` callables via `Depends(...)` in FastAPI endpoints; always use `async def get_container_async()`.

---

### 7. Self-Improving Agent Flywheel
- Telemetry logs (`FIRST_PERSON_REQUESTS_TOTAL`, `FIRST_PERSON_QUARANTINED_TOTAL`) record all unmatched seeker queries.
- The double-blind Review UI (`127.0.0.1:8088`) feeds verified human judgments into the evaluation set to re-calibrate risk profiles and fine-tune cross-encoder rerankers.
```
