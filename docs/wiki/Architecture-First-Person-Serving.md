# First-Person Context Serving Architecture

The **First-Person Serving Pipeline** is a specialized subsystem in AskMukthiGuru engineered to deliver the verbatim spoken wisdom of **Sri Preethaji and Sri Krishnaji** directly to seekers. Unlike General RAG (which synthesizes responses with an LLM and injects Ontological Knowledge Framework doctrine), the First-Person system operates under an absolute, non-negotiable architectural invariant:

> **The Zero-Hallucination Invariant**: The system must never author, extrapolate, or paraphrase spiritual teachings. Every served response must be deterministically reconstructed from immutable transcript spans whose speaker attribution passed acoustic verification, accompanied by verified video playback timestamps.

---

## 1. Core Invariants & Product Philosophy

The repository enforces strict first-person serving invariants. Any violation is classified as a P0 defect:

### Invariant 1: "Answer text is evidence, directness is metadata"
* A served clip's `answer` or `teaching` body consists exclusively of the **verbatim quote plus its speaker and source attribution** — nothing else.
* "Related, not a direct answer" is a UI affordance carried strictly in structured metadata:
  * `status = "weak_match"`
  * `is_direct_answer = False`
  * `verification["direct"] = False`
* **Rule**: Never prepend a heading or editorial commentary to a verbatim quote. Where a section heading must be communicated (e.g., in the bridge abstain flow), it is transmitted via `route_metadata.related_clips_heading`.

### Invariant 2: Master Posture Switch & Directness Knob
* `first_person_primary_mode`: The master posture switch (defaults to `True`).
* `first_person_serve_weak_match`: Finer knob under the master switch (defaults to `True`).
* Neither switch is permitted to weaken a core gate (relevance threshold, semantic boundary check, integrity verification, or output guardrail).
* A served first-person response explicitly sets `route_metadata.fp_served = True`. Abstain, crisis, or error responses never do.

### Invariant 3: Additive Context Expansion (Zero LLM Generation)
* `first_person_enrichment_window_enabled`: Rehydrates a retrieved child span to its full parent discourse window so that antecedent pronouns and conversational context are clear.
* `first_person_graph_expansion_enabled`: Appends concept-filtered graph retrieval *after* vector matches.
* `first_person_okf_expansion_enabled`: Appends one payload-filtered retrieval keyed on curated `memory/okf/compiled.json` doctrine concepts (added 2026-11-10, default `False`).
* `first_person_cross_video_diversity_enabled`: Re-orders the candidate pool with MMR + a per-video cap, **deferring** (never dropping) capped candidates (added 2026-11-10, default `False`).
* None of these features may reorder, drop, or replace a primary context, and `retrieval_only` mode strictly forbids LLM-authored teaching prose.

---

### Invariant 4: Fail-Closed Grading With One Transport Retry
* `first_person_relevance_max_attempts` (default `2`, bounded `1..3`): the relevance scorer asks the provider for a digit score on a **read-only** clip, so a timeout or a dropped connection is repeated once. Under the sequential contract an indeterminate context blocks every later context, so without this a single slow provider call turned the whole turn into *"I couldn't finish checking the teachings"*.
* Only transport outcomes are retried, and only when the failed attempt died **fast** (under half of `FIRST_PERSON_RELEVANCE_TIMEOUT_S`). A call that consumed the whole deadline is provider congestion: repeating it doubled a live 15 s stall to 31.4 s for the same abstain, so it abstains after one deadline. A provider refusal, a rate-limit push-back, a budget denial or a malformed/wrong-length reply is answered **once** and stays `relevance_indeterminate`; when every attempt fails the turn still abstains with `verification.passed = False`. A retry never relaxes a gate and never authors text.
* Measured 2026-11-10/11: 16 concurrent scorer calls completed in 5.03 s (max 5.03 s) while a 4-way semaphore made it slower, so the retry — not a concurrency limit — is the correct fix.

---

## 2. Public-Release Status & Operating State

> [!CAUTION]
> **Current Public-Release Verdict: NO-GO (Enforced & Immutable)**
> As ratified in `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`, public first-person context serving remains gated off in all production configurations until human-certified acoustic verification (B7) is complete.

* **Configuration**:
  * `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` and inside the Docker runtime container.
  * Public Qdrant alias `first_person` points at `first_person_v10` (4,197 points).
  * **Prohibitions**: No Qdrant writes, no alias mutations, no Redis mutations, and no Railway deployments may alter this status.
* **Owner-Only Preview Mode**:
  * Operates only when `FIRST_PERSON_LOCAL_REVIEW_ENABLED=true` **and** `IS_PRODUCTION=false`.
  * Refuses to start if any pinned artifact is missing or if its SHA-256 checksum has drifted.
* **The Two Canonical Warning Labels**:
  Every served response in preview mode carries two canonical labels:
  ```text
  REVIEW CANDIDATE — NOT PUBLIC RELEASE
  AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION
  ```
  A contract pinning a different label is considered stale and the mode will refuse to initialize.

---

## 3. Serving Contract B4 Schema Isolation

Public-release blocker **B4** resolved a critical failure mode: legacy clip collections (`first_person_v1..v9`) and modern context collections (`first_person_v10..v11`) operate on incompatible schemas. In earlier iterations, `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` could point at the same collection, causing queries to fail silently.

### 3.1 The B4 Contract Specification (`backend/services/first_person_serving_contract.py`)
Schema isolation is enforced offline and deterministically via `backend/config/first_person_serving_contract.json`:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            B4 SERVING CONTRACT ISOLATION                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   LEGACY SERVING PATH                               CONTEXT SERVING PATH         │
│   ┌────────────────────────────────┐                ┌──────────────────────────┐ │
│   │ FirstPersonStore (Role: legacy)│                │ FirstPersonContextStore  │ │
│   └───────────────┬────────────────┘                └─────────────┬────────────┘ │
│                   │                                               │              │
│                   ▼                                               ▼              │
│   ┌────────────────────────────────┐                ┌──────────────────────────┐ │
│   │ Schema: legacy-clip-v1         │                │ Schema: fp-context-v1    │ │
│   │ • first_person_eligible        │                │ • record_type (parent/ch)│ │
│   │ • teacher_id                   │                │ • source_span_id         │ │
│   │ • verbatim_text                │                │ • parent_unit_id         │ │
│   │ • video_id                     │                │ • guru_id                │ │
│   │ • start_ms, end_ms             │                │ • source_text_hash       │ │
│   │                                │                │ • speaker_verified       │ │
│   │                                │                │ • rights_cleared         │ │
│   │                                │                │ • corpus_version         │ │
│   └────────────────────────────────┘                └──────────────────────────┘ │
│                   │                                               │              │
│                   └───► [FAIL CLOSED: Incompatible Schema] ◄──────┘              │
│                         Abstain Reason: serving_contract_violation               │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Inviolable Isolation Rules
1. **No Shared Collections**: A legacy store may not point at an `fp-context` collection; a context store may not point at a legacy-only collection; the two paths must never share a collection name or alias.
2. **Fail-Closed Behavior**:
   * In **production**, any serving-contract violation raises an unrecoverable exception at startup, halting deployment.
   * Outside production, the legacy path fails closed gracefully (`abstain_reason="serving_contract_violation"`) without crashing the application.
3. **Serving-Policy Cache Fingerprinting**:
   The exact-answer cache key must change whenever what is served changes. The cache key includes four mandatory components:
   $$\text{Fingerprint} = \text{Hash}(\text{collection} + \text{schema} + \text{corpus\_version} + \text{evidence\_policy})$$
   Any modification to collection schemas invalidates the 24-hour exact cache automatically.

---

## 4. Acoustic Evidence & Speaker Attribution Gates

Attribution without acoustic verification is strictly forbidden. The system distinguishes between video-level claims and speech-verified reality:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   ECAPA-TDNN ACOUSTIC VERIFICATION PIPELINE                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────────────────────────┐                                    │
│   │ Master Audio Archive WAV                │                                    │
│   │ (audio_archive/wavs/*.wav)              │                                    │
│   └────────────────────┬────────────────────┘                                    │
│                        │ Acoustic Windowing (audio_start_ms to audio_end_ms)     │
│                        ▼                                                         │
│   ┌─────────────────────────────────────────┐                                    │
│   │ ECAPA-TDNN Embedder (speechbrain rev)   │                                    │
│   └────────────────────┬────────────────────┘                                    │
│                        │                                                         │
│                        ▼                                                         │
│   ┌─────────────────────────────────────────┐     ┌────────────────────────────┐ │
│   │ Cosine Similarity & Margin Calculator   │ ◄───┤ Acoustic Reference Centroid│ │
│   └────────────────────┬────────────────────┘     │ (Widened over ANCHORS)     │ │
│                        │                          └────────────────────────────┘ │
│                        ▼                                                         │
│   ┌─────────────────────────────────────────┐                                    │
│   │ Acoustic Margin Gate:                   │                                    │
│   │ • Cosine >= 0.55                        │                                    │
│   │ • Margin >= 0.15                        │                                    │
│   │ • Cluster Distance <= 0.60              │                                    │
│   └────────────┬───────────────────────┬────┘                                    │
│                │ Pass                  │ Fail / Conflict                         │
│                ▼                       ▼                                         │
│   ┌───────────────────────────┐  ┌─────────────────────────────────────────────┐ │
│   │ speaker_verified = True   │  │ Quarantine Tier:                            │ │
│   │ (automated_evidence_cand) │  │ refused_guru_mismatch                       │ │
│   │                           │  │ (Speaker Conflict Review Queue)             │ │
│   └───────────────────────────┘  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Acoustic Verification Pipeline
* **Model**: ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) loaded with a strictly pinned revision.
* **Audio Sourcing**: Audio slices are extracted exclusively from `audio_archive/wavs/`. Sourcing from `<asr_root>/audio/` is prohibited because mass-ingest staging directories contain 86-byte WAV stubs lacking PCM data.
* **Anchor References**: Speaker references are built from two human-confirmed anchor moments in `backend/scripts/ops/speaker_attribution.py::ANCHORS` and widened across training splits.
* **Method Constants**:
  * `ENROLL_MIN = 0.75`
  * `ANCHOR_LABEL_MIN = 0.55`
  * `ANCHOR_MARGIN = 0.15`
  * `CLUSTER_DISTANCE = 0.60`
  * Windowing: 2.0 second windows with 1.0 second hop offsets.
* **Honest Evaluation Boundary**: Current `first_person_v10` verification was conducted as a per-video check over the first 60 seconds with a hardcoded threshold. Spans carry `automated_evidence_candidate`, **not** human-certified attribution. Final certification awaits completion of B7.

---

## 5. Speaker Schema & Coordinate Geometry

In `first-person-speaker-conflict-v2`, audio coordinates were completely overhauled to eliminate coordinate ambiguity:

```json
{
  "audio_file_duration_ms": 3600000,
  "audio_slice_duration_ms": 45000,
  "audio_start_ms": 125000,
  "audio_end_ms": 170000,
  "video_id": "ehkqJ54DIC0",
  "guru_id": "sri-preethaji",
  "speaker_verified": true,
  "rights_cleared": true,
  "corpus_version": "fp-context-transcript-v1"
}
```

* **Removal of `audio_duration_ms`**: Legacy ambiguity between total file duration and slice duration was permanently retired.
* **Identity Rule**: `(video_id, guru_id)` is **not** an identity. Multiple speakers frequently discourse in a single video. Identity is determined by `source_span_id`.

---

## 6. Quarantine Policies & Rights Register

### 6.1 Speaker-Label Conflict Quarantine
When acoustic models detect conflicting voice prints or when video channel metadata contradicts audio evidence:
* The 45 identified speaker-label conflicts are **quarantined**, never relabeled automatically.
* Human review packet: `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` stores audio slice SHA-256 hashes, playback offsets, and empty decision/reviewer fields awaiting human signoff.

### 6.2 Deterministic ID Collision Quarantine
* Under transcript rebuilds, 502 of 1,600 spans exhibited coordinate overlaps. Both collision members are quarantined in the `deterministic_id_collision_quarantine` tier.
* No namespace fix was applied to avoid invalidating Phase 2 verdicts and pinned contracts.

### 6.3 Rights Verification Invariant (X40)
* **Register $\rightarrow$ Stamp $\rightarrow$ Filter $\rightarrow$ Enforce**: Rights status originates exclusively from the curated rights register (`docs/rights/CONTENT-RIGHTS.md` / `source_releases`), never from an unverified Qdrant payload claim.
* Ingestion stamps `domain_rights_status` onto Qdrant points.
* Retrieval filters strictly on `domain_rights_status == "licensed"`. Unverified or revoked assets are excluded with zero fallback.

---

## 7. Related Wiki Documentation

* [System Architecture Overview](Architecture-Overview) — Multi-tier topology, caching, and gateway routing.
* [12-Layer RAG Pipeline](Architecture-RAG-Pipeline) — General RAG execution, LangGraph state machine, and intent routing.
* [Frontend Architecture & Seeker Experience](Frontend-UI-and-Seeker-Experience) — Discourse audio strip and YouTube embed player.
* [REST & Streaming API Reference](API-Reference) — First-person review endpoints and schemas.
* [Qdrant Vector Database Reference](Data-Qdrant-Vector-Store) — `first_person_v10` schema, payload fields, and BGE-M3 vectors.
* [Neo4j Knowledge Graph & OKF](Data-Neo4j-Knowledge-Graph) — Doctrine ontology and concept relationships.
