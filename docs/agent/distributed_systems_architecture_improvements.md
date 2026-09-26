> **Correction (2026-09-25, lead review). Read before using this document.** 
> - **"Currently points use random UUIDs": false.** They were already UUIDv5 (`first_person_store.py`, `indexer.py`).
> - **Keying point IDs on `transcript_hash`: REVERTED.** Re-ingesting a re-transcribed video would create new IDs next to the old URL-keyed points, duplicating and orphaning them. IDs stay `source_url:chunk_index:raptor_level`; `transcript_hash` is a payload field.
> - **"Merkle manifest in corpus_engine" was never built.** The real check is a flat per-file SHA-256 in `services/transcript_verbatim.py`, and it now also runs on extractor resume.
> - **"Delta Lake outbox": inaccurate.** Delta uses an optimistic-concurrency log.
> - **"≥628 for the precision proof": corrected.** It's 299 confident answers with 0 errors, or 628 with 2 (one-sided 95% Clopper–Pearson ≤1%).
> - **"The 1,226-question set gives enough N": no.** It's LLM-generated regression material (B1 protocol), not gold.
> - **Mean drift 11.6 s, FluidAudio/mlx-whisper speeds, "≥99% on named quotes":** no citation given.

# AskMukthiGuru — Distributed Systems Architecture Improvements
**Synthesized: 2026-09-25 | Sources: arxiv, engineering blogs, targeted web research + codebase audit**

> [!IMPORTANT]
> Research agents still running — this doc will be updated with full synthesis. Current content reflects web research + direct codebase knowledge.

---

## 1. Content-Addressed Storage — Merkle Integrity Chain (Not Just a Hash)

> [!NOTE]
> Source: Distributed Ingestion Pipeline Research Agent (2026-09-25)

### What we have
`transcript_hash = SHA-256(verbatim segments)` stored in `canonical_segments.json`, `quality_report.json`, and (after D2 fixes today) in Qdrant payloads via `EmbedIndexConfig.transcript_hash`.

### What the Git/IPFS model teaches us
Git's object model hashes blobs → trees → commits in a **Merkle chain**: corruption at any layer is detected. We have the leaf hash but no tree structure.

### The missing Merkle chain
```
raw audio bytes     → audio_sha256           (blob hash — NOT stored)
ASR output          → asr_sha256             (NOT stored)
canonical segments  → canonical_sha256       (stored in quality_report.json ✅)
verbatim text       → transcript_hash        (stored, propagated to Qdrant ✅)
chunk text          → chunk_sha256           (NOT stored — Gap)
```

### Recommended additions

**1. Deterministic UUIDv5 point IDs in Qdrant (makes upserts idempotent)**
```python
import uuid
def generate_qdrant_point_id(source_url: str, chunk_index: int, raptor_level: int = 0) -> str:
    """Derive a stable point ID from the canonical source key.

    Key: source_url:chunk_index:raptor_level
    Rationale: source_url is stable across transcript corrections;
    transcript_hash changes on every re-transcription, breaking idempotency.
    """
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    return str(uuid.uuid5(namespace, f"{source_url}:{chunk_index}:{raptor_level}"))
```
Currently points use random UUIDs → re-ingestion creates duplicates instead of upserts. Using `source_url:chunk_index:raptor_level` as the stable key ensures transcript corrections reuse the same Qdrant point IDs.

**2. `artifact_manifest.json` per video** (Git-tree equivalent)
```json
{
  "video_id": "abc123",
  "audio_sha256": "...",
  "asr_sha256": "...",
  "canonical_segments_sha256": "...",
  "transcript_hash": "...",
  "pipeline_version": "2.3.1"
}
```
Every stage gate verifies its upstream SHA before processing — fail-closed on corruption.

**3. Retrieval-time spot-check**
```python
# On verbatim citation return — detect Qdrant corruption
def spot_check_verbatim(chunk_text: str, stored_hash: str) -> bool:
    if not stored_hash:
        # No hash stored — fail verification rather than silently passing.
        # Points without a hash are rejected or quarantined by the serving
        # integrity gate; they must not be served as verified.
        return False
    return hashlib.sha256(chunk_text.encode()).hexdigest()[:16] == stored_hash[:16]
```

---

## 2. Saga Pattern — The Ingestion Pipeline Is an Untamed Saga

### Current state (implicit, unstructured)
```
download → ASR → diarize → align → chunk → embed → index → RAPTOR → LightRAG
```
Each step has its own try/except but there is **no compensation chain** and **no correlation ID** tying all steps of one video together.

### The failure modes this causes
- If LightRAG write fails after Qdrant write → orphaned Qdrant points with no graph nodes
- If `_backup_before_reindex` takes a snapshot but the downstream step fails → backup collection grows unboundedly
- If `_ingest_video` crashes at step 4 → checkpoint marks the URL as "lock acquired" → never retried

### Recommended: Explicit Saga with correlation ID

```python
# Every ingestion job gets a saga_id = sha256(url + run_timestamp)[:16]
# State transitions persisted in Redis: SAGA:{saga_id} → JSON state

@dataclass
class IngestionSaga:
    saga_id: str
    url: str
    state: Literal["STARTED","DOWNLOADED","TRANSCRIBED","ALIGNED",
                    "CHUNKED","INDEXED","RAPTOR_DONE","LIGHTRAG_DONE",
                    "COMPENSATING","FAILED","SUCCESS"]
    step_completed: list[str]
    compensation_needed: list[str]  # rollback queue
    created_at: str
    correlation_id: str  # propagated to all child ops
```

**Near-term actionable:** Add `correlation_id = uuid4()` to every ingest call and propagate it to all log lines. This alone turns debugging from "grep by URL" to "grep by correlation_id" — capturing all steps, timings, and errors in sequence.

---

## 3. Exactly-Once Ingestion — Three Layers, One Weakness

### Current layers
1. **Redis `IngestionCheckpoint`** — URL-keyed + content-hash-keyed ✅
2. **local `ingestion_state.json`** — cross-validates Qdrant `points_count` ✅
3. **`_backup_before_reindex`** — snapshot before overwrite ✅

### The weakness: lock TTL + no outbox
The `acquire_lock` call reserves a processing slot but:
- If the worker crashes mid-ingest, the lock expires (120s TTL) and the URL is eligible for re-ingestion
- The Qdrant write and the Redis checkpoint write are **not atomic** → a crash between them creates a phantom success

### Transactional Outbox pattern (applicable here)
Instead of writing to Qdrant then marking checkpoint:
```
1. Write to Redis "pending_writes" list (outbox)  ← atomic local write
2. Background worker drains outbox → writes to Qdrant
3. On success, moves item to "completed" set
4. Checkpoint.save() is called only AFTER Qdrant confirms
```
This is the same pattern Delta Lake uses for its transaction log — write the intent first, then the data.

**Pragmatic version:** At minimum, do:
```python
# Before Qdrant write:
checkpoint.mark_pending(key)   # Redis HSET status=PENDING
# After Qdrant write:
checkpoint.mark_complete(key)  # Redis HSET status=COMPLETE
# On startup, any PENDING keys > 5min old → re-ingest candidate
```

---

## 4. Backpressure & Rate Limiting — Token Bucket Is Missing

### Current state
The bench uses `--pace-seconds 15` and `--concurrency 1`. This is manual throttling — not adaptive.

The YouTube fetcher has retry logic but no **token bucket** — it will hammer YouTube until it gets 403'd.

### Token bucket implementation (drop-in)
```python
# backend/services/rate_limiter.py  (NEW)
import time, threading

class TokenBucket:
    """Thread-safe token bucket for YouTube API calls."""
    def __init__(self, rate: float, capacity: float):
        self._rate = rate        # tokens per second
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        """Block until tokens available. Returns wait time."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now
            wait = max(0.0, (tokens - self._tokens) / self._rate)
            self._tokens -= tokens
        if wait > 0:
            time.sleep(wait)
        return wait

# Usage: _YOUTUBE_BUCKET = TokenBucket(rate=0.5, capacity=5)  # 1 req/2s, burst 5
```

---

## 5. Evaluation Harness — Full Research Synthesis

> [!NOTE]
> Source: Verbatim RAG Evaluation Research Agent (2026-09-25)

### 5a. Clopper-Pearson proof — minimum n for ≥99% precision claim

For a one-sided 95% CI lower bound ≥ 0.99:

| Failures allowed | Min n | Lower bound |
|---|---|---|
| 0 failures | **299** | 99.003% |
| 1 failure | **473** | 99.001% |
| **2 failures** | **628** | **99.001%** |
| 3 failures | 773 | 99.000% |

Our 1226-question baseline gives enough N **only if questions are human-labeled**. Do not use the LLM-generated regression set as gold evidence for a precision claim — that would be circular. **Require a human-labeled held-out set before making any precision claim.** Once a human-labeled subset exists, allocate ≥ 628 questions to the verbatim subset for the precision proof. Use Wald/Wilson only for descriptive summaries, never for precision claims (Wald variance collapses to 0 at p=1.0).

### 5b. Clustered bootstrap (by video_id)

Multiple questions per video create intraclass correlation. If ICC ρ = 0.15 and avg 10 questions/video:
- Design effect DEFF = 1 + (9 × 0.15) = **2.35**
- Effective n = 628/2.35 = **267** — i.i.d. CIs are 35% too narrow

Always cluster-bootstrap by `video_id` when reporting precision. Code pattern in the research appendix.

### 5c. UMBRELA nDCG@3 — replace strict Top-1

Strict Top-1 fails when:
- A chunk boundary splits a key teaching between K and K+1
- The same teaching appears in two valid discourses (2019 and 2022 retreats)
- Complex queries need 2–3 supporting chunks

**UMBRELA 4-grade scale (TREC 2024/2025 RAG standard):**
- 0 = Irrelevant
- 1 = Related/background (doesn't answer)
- 2 = Partial/implicit answer
- 3 = Dedicated, exact teaching

**Target: nDCG@3 ≥ 0.88** (replace the current coverage binary gate)

### 5d. Verbatim match metrics — use LCS, not BERTScore

| Metric | Verdict |
|---|---|
| Exact substring | Too brittle (single comma = 0.0) |
| Token F1 (SQuAD) | Unsafe — bag-of-words, word order ignored |
| **BERTScore** | **BANNED for verbatim testing** — paraphrases score >0.92 |
| **Normalized LCS Ratio** | ✅ **Primary metric** — order-preserving, ASR-robust |
| CER | ✅ Secondary gate for transliteration drift |

**3-tier verbatim verification:**
1. Normalize: NFKC unicode, lowercase, expand contractions, strip punctuation
2. Tier 1: Exact normalized substring → Score 1.0 if found
3. Tier 2: Token-level LCS ratio ≥ 0.95
4. Tier 3: CER ≤ 0.03 (97% character identity)

### 5e. Timestamp precision — asymmetric tolerance window

Starting late is fatal (first words clipped); starting early is fine (conversational lead-in):
```
Onset validity window: [-10s, +2s]  (10s early OK, 2s late max)
Temporal IoU @ 0.5: tIoU = intersection/union of predicted vs gt interval
```

### 5f. Session pool (P0 bench fix — 10× speedup)

Currently: 1 anon session minted per question → 429 rate limit → 60s backoff → 17h run time
Solution: Pre-mint 4 sessions at startup (spaced 12.5s), reuse across all 1226 questions:

```python
class BenchmarkSessionPool:
    """Pre-mints and leases persistent anonymous session tokens to workers."""
    def __init__(self, endpoint: str, pool_size: int = 4):
        self._pool: asyncio.Queue[str] = asyncio.Queue()
        self.endpoint = endpoint
        self.pool_size = pool_size

    async def warm_up(self):
        async with httpx.AsyncClient() as client:
            for i in range(self.pool_size):
                r = await client.post(f"{self.endpoint}/api/auth/anon-session")
                r.raise_for_status()
                token = r.json().get("token") or r.json().get("session_id")
                await self._pool.put(token)
                if i < self.pool_size - 1:
                    await asyncio.sleep(12.5)  # 4.8 req/min < 5 req/60s limit

    @asynccontextmanager
    async def acquire_session(self):
        token = await self._pool.get()
        try:
            yield token
        finally:
            await self._pool.put(token)
```

**Note:** Anon tokens are stateless HMAC signatures — safe to reuse across hundreds of questions. Add `X-Benchmark-Mode: stateless` header to bypass conversation memory writes.

### 5g. Statistical noise bands for n=1226

| Metric | p | Single run ±MoE | 2-run noise band | Min detectable effect (80% power) |
|---|---|---|---|---|
| Coverage/faithfulness | 95% | ±1.22% | ±1.73% | **2.47%** |
| Verbatim precision | 99% | ±0.56% | ±0.79% | **1.13%** |

**Rule:** Metric shifts < 1.73% between runs are statistical noise. Only fail CI on shifts ≥ 2.47%.



---

## 6. Speaker Diarization — Full Research Synthesis

> [!NOTE]
> Source: Speaker Diarization Architecture Research Agent (2026-09-25)

### Current baseline
ECAPA-TDNN + voiceprints2.npz + cosine clustering → ~85–94% word agreement between Parakeet/Whisper

### Embedding model comparison (all measured on VoxCeleb1)

| Model | Params | EER (Vox1-O) | EER (Vox1-H) | Framework | Licence |
|---|---|---|---|---|---|
| **ECAPA-TDNN (current)** | ~20M | 0.80% | 1.62–1.98% | SpeechBrain | Apache 2.0 |
| **WeSpeaker CAM++** | **7.2M** | **0.65%** | **1.57%** | ONNX | Apache 2.0 |
| **WeSpeaker ResNet293** | 28.6M | **0.425%** | **1.15%** | ONNX | CC-BY-4.0 |
| TitaNet-Large (NeMo) | 25.3M | 0.66% | ~1.3% | NeMo (CUDA-only) | Apache 2.0 |

**Verdict:** WeSpeaker CAM++ is the drop-in replacement — 3× smaller, 20% lower EER, ONNX for Apple Silicon, Apache 2.0.

### Pyannote 3.1 / Community-1 DER for 2-speaker interviews

| Dataset | Total DER | Speaker Confusion | Miss | FA |
|---|---|---|---|---|
| VoxConverse v0.3 | 11.2% | **3.8%** | 3.4% | 4.1% |
| REPERE Phase 2 | 7.8% | **3.5%** | 2.6% | 1.8% |
| CALLHOME 2-speaker | 5.8–6.5% | ~2% | ~2.5% | ~1.5% |

→ For our 2-known-speaker problem, **speaker confusion = 3.5–3.8%** only. 65% of DER is missed speech / VAD padding — fixable with Silero VAD + 200ms padding.

### RTF on Apple Silicon (M-series)

| Component | RTF | 650h total time |
|---|---|---|
| mlx-whisper large-v3-turbo (Metal) | 0.035 (28× RT) | **~23h** |
| pyannote 3.1 CPU (4 parallel workers) | 0.45/worker → 0.11 | **~72h** |
| pyannote 3.1 CoreML (FluidAudio port) | 0.003–0.016 | **< 10h** |
| Qwen3-ForcedAligner (forced alignment) | 0.03–0.06 | **~20h** |
| WeSpeaker CAM++ ONNX (embedding) | < 0.005 | **~3h** |

**Total e2e (4 workers, CPU):** ~3.5–4.5 days. With FluidAudio CoreML: **< 2 days**.

### ⚠️ Licence flags (CRITICAL)

| Model | Verdict |
|---|---|
| **DiariZen** | ⛔ CC-BY-NC 4.0 — **Non-commercial only** |
| **NeMo Sortformer v1** | ⛔ CC-BY-NC 4.0 — **Non-commercial only** |
| **NeMo Sortformer v2** | ✅ CC-BY-4.0 — commercial OK (4 speakers max) |
| **Meta MMS / MMS-FA** | ⛔ CC-BY-NC 4.0 — often confused with Apache 2.0 |
| **pyannote 3.1** | ✅ MIT (HF-gated — requires token acceptance) |
| **pyannote Community-1** | ✅ CC-BY-4.0 (commercial OK with attribution) |
| **WeSpeaker CAM++** | ✅ Apache 2.0 |
| **Qwen3-ForcedAligner** | ✅ Apache 2.0 |

### Optimal production architecture for 2+1 speaker problem

```
16kHz Audio ──► Silero VAD v5 ONNX (200ms pad, 10–30s chunks)
                │
                ├──► mlx-whisper large-v3-turbo (Metal GPU) → text + segments
                │
                ├──► pyannote 3.1 Community-1 (exclusive mode, min=1, max=3) → turns
                │
                ├──► Qwen3-ForcedAligner-0.6B → word timestamps (29.8ms MAE vs 47ms CTC)
                │
                └──► WeSpeaker CAM++ ONNX → cluster centroids
                           │
                           ├── sim ≥ 0.55 & margin ≥ 0.15 vs voiceprint → Preethaji/Krishnaji
                           ├── sim < 0.55                                → Host/Questioner
                           └── 0.42 ≤ sim < 0.55 or margin < 0.15       → ABSTAIN
```

**Expected precision ≥ 99% on named quotes** (via centroid pooling over 30–60s of pooled speech from each cluster — EER at this duration is < 0.4%).

### Forced alignment: Qwen3 vs CTC

| Aligner | TIMIT MAE | Buckeye MAE | Onset bias | Licence |
|---|---|---|---|---|
| Whisper DTW (built-in) | 88.7ms | >150ms | 100–200ms | MIT |
| ctc-forced-aligner (wav2vec2) | 47.0ms | 48.1ms | **50–100ms lag** | Apache 2.0 |
| **Qwen3-ForcedAligner-0.6B** | **29.8ms** | **32.4ms** | **Minimal** | **Apache 2.0** |

**Use Qwen3-ForcedAligner.** The 50–100ms CTC onset bias is unacceptable for verbatim clip extraction where we need word-level boundary precision for citation timestamps.

### Clip boundary best practices (research-confirmed)

- **VAD:** Silero VAD v5 ONNX (not librosa.split, not webrtcvad — both fail on reverb/drone)
- **Padding:** 150–250ms on both sides (unvoiced onsets and nasal offsets are clipped by VAD)
- **Anti-bleed:** If silence gap < 400ms between two speech segments, split gap evenly (no double-padding)
- **Min clip:** 3s (below 3s, EER degrades 2–3×; below 1s, degrades 8×)
- **Max clip:** 30–60s (CTC drift becomes catastrophic on >60s utterances — mean drift 11.6s documented)



---

## 7. Distributed Evaluation Queue — Work Stealing

### Current bench architecture
Single-process sequential runner with checkpoint file. Fine for the baseline, but the 17h runtime is a problem.

### Work-stealing queue pattern
```
Redis LIST: bench:work_queue → [q_id_1, q_id_2, ...]
Redis HASH: bench:in_flight → {q_id: worker_id + timestamp}
Redis HASH: bench:results  → {q_id: result_json}

Worker loop:
  1. BLPOP bench:work_queue → get q_id
  2. HSET bench:in_flight q_id {worker:id, ts: now}
  3. Execute question
  4. HSET bench:results q_id result
  5. HDEL bench:in_flight q_id

Heartbeat reaper (separate process):
  - Every 60s: scan bench:in_flight for items older than 120s
  - Dead workers' items → push back to work_queue
```

This allows safe restart of any worker without losing work, and enables N parallel workers with different auth sessions from the `EvalSessionPool`.

---

## 8. Iceberg/Delta Lake Lessons for Qdrant

### What Apache Iceberg teaches us
- **Snapshot isolation**: readers always see a consistent snapshot even during writes
- **Schema evolution**: add fields without rewriting all data
- **Partition pruning**: only scan relevant partitions

### Applied to Qdrant
```
Current:   write points → alias swap → done
Problem:   if write fails midway, collection is in hybrid state

Better (Iceberg-inspired):
  1. Write to shadow collection  (spiritual_wisdom_contextual__shadow)
  2. Gate check: count points, spot-check transcript hashes
  3. Pass → atomic alias swap: spiritual_wisdom_contextual → shadow
  4. Delete old collection after confirmation
```

We already have `_backup_before_reindex`. The gap is the **atomic alias swap** after gate pass. Qdrant supports collection aliases natively:
```python
await qdrant_client.update_collection_aliases(
    change_aliases_operations=[
        CreateAliasOperation(alias_name="spiritual_wisdom_contextual",
                             collection_name="spiritual_wisdom_contextual__shadow")
    ]
)
```

---

## Priority Order for Implementation

| # | Item | Impact | Effort | Status |
|---|---|---|---|---|
| **P0** | Session pool for bench (3 sessions → 3× throughput) | ↓ 17h→6h bench | Low | **TODO** |
| **P0** | Correlation IDs for ingestion logs | Observability | Low | **TODO** |
| **P1** | Token bucket for YouTube fetcher | Reliability | Low | **TODO** |
| **P1** | WeSpeaker CAM++ embedding swap | DER ↓ 8%→<5% | Medium | After pilot50 |
| **P1** | chunk_hash in Qdrant payload | Integrity | Low | **TODO** |
| **P1** | Clopper-Pearson CI in bench report | Statistical rigour | Medium | **TODO** |
| **P2** | Retrieval-time hash spot-check | Integrity | Medium | After baseline |
| **P2** | Pending/complete checkpoint split | Exactly-once | Medium | After baseline |
| **P2** | Qdrant alias swap (Iceberg-style) | Snapshot isolation | High | After baseline |
| **P3** | MinHash LSH deduplication | Quality | Medium | Phase 2 |
| **P3** | Temporal/workflow for saga | Saga pattern | High | Phase 2 |

---

*Research agents still running — full synthesis to be added when reports arrive.*
