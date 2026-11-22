# Recon Map: Frontier AI Product Harness & Data Source Wirings

**System Scope:** Enterprise-grade AI Product Serving Harness and Multi-Modal Ingestion Pipeline  
**Target:** AskMukthiGuru Spiritual Wisdom Engine (incorporating design patterns from Anthropic, Perplexity, Glean, and Cursor)  
**Date:** 2026-11-23  

---

## 1. Sources & Benchmark References

| # | Reference Source | Pattern Analyzed | Architectural Takeaway for Harness & Wirings |
|---|---|---|---|
| 1 | **Anthropic** (Contextual Retrieval & Constitutional Safety) | Chunk-situating context without quote mutation | Prepend 50–100 tokens of contextual metadata headers; strict ordered gate isolation (safety precedes cache/provider). |
| 2 | **Perplexity** (Grounded Pro Search & Citation Alignment) | Sentence-level citation extraction & verification | Strict separation of verbatim evidence quotes from downstream directness metadata; millisecond timestamp alignment. |
| 3 | **Glean** (Enterprise Search & Permission Graph) | Register → Stamp → Filter → Enforce | Independent legal/rights registry decoupled from vector payload; query-time filtering on licensed status; rejection telemetry. |
| 4 | **Cursor** (Deterministic Chunking & Shadow Indexing) | Hash-stable chunk identities & semantic boundaries | Deterministic UUID5 generation (`uuid5(NAMESPACE_URL, ...)`); parent unit grouping; immutable blue-green collection cutover. |
| 5 | **Cohere** (Multi-Stage Retrieval & Cross-Encoder Reranking) | Hybrid dense+sparse fusion + RRF / MaxSim | Dual-lane BGE-M3 (dense 1024-d + sparse lexical) fused with graph prefetch and cross-encoder reranker. |

---

## 2. Core Loop

**Seeker asks a spiritual or life question → Fast-path safety & cryptographic cache gate check → Multi-channel hybrid retrieval (dense + sparse + ontology graph) → Provenance & verbatim evidence validation → Parent window enrichment → Deterministic grounded response with millisecond audio-slice player.**

---

## 3. Screens & Interaction States

| ID | Screen / UI State | Route / Trigger | Purpose | Key Components | States Seen |
|---|---|---|---|---|---|
| **S01** | **Main Seeker Interface** | `/` or `/chat` | Inquiry input & conversational session | Query composer, language selector, guru filter, past sessions | Empty, typing, thinking, streaming, completed |
| **S02** | **Direct Verbatim Teaching View** | Chat message result (`status="served"`) | Present exact verbatim quote from verified guru | Verbatim quote container, speaker badge, source audio player, share button | Single-span, multi-span parent window, audio playing |
| **S03** | **Weak Match / Related Clips Accordion** | Chat message result (`status="weak_match"`) | Present related teachings without falsely claiming direct answer | Accordion header ("Related teachings"), clip snippets, relevance disclaimer | Collapsed, expanded, audio preview |
| **S04** | **Citation & Evidence Inspector** | Click citation badge on S02/S03 | Prove attribution, timestamp, and source video context | YouTube embed at exact timestamp, transcript diff, ASR confidence, rights status | Open, seeking, error/unavailable |
| **S05** | **Compassion & Distress Rail** | Router detected `intent=DISTRESS` | Clinical safety intervention for distress/crisis | Compassion message, verified helpline buttons, crisis escalation | Immediate alert, contact info expanded |
| **S06** | **Operator Corpus Health Dashboard** | `/admin/corpus-health` | Observability into data plane invariants | Qdrant optimizer status, deletion ratio, snapshot age, drift meter | Healthy (green), warning (amber), breach (red) |
| **S07** | **Human Review Packet Queue** | `/admin/reviews/human-gates` | Human-in-the-loop review of speaker conflicts & rights | Evidence audio slice player, confidence scores, sign-off buttons | Unreviewed, verified, quarantined |

---

## 4. Execution Flows

```
F01 Standard Direct Question Flow (Happy Path)
    S01 (Enter inquiry) -> Pipeline (Safety -> Cache -> Retrieval -> Rerank -> Evidence Gate) -> S02 (Verbatim Quote) -> S04 (Inspect Source)
    Happy path latency: < 650 ms (uncached) / < 120 ms (cached)
    Edge cases: Low relevance score -> S03 (Weak Match); Distressed tone -> S05 (Compassion Rail)

F02 Data Ingestion & Blue-Green Promotion Flow
    Raw YouTube Video / Discourse -> Rights Register Check -> Dual ASR -> Diarization & Anchor Matching -> Deterministic Chunking -> Staging Collection -> Evaluation Benchmark -> Atomic Alias Swap
    Edge cases: Unlicensed rights -> Quarantined in public.corpus_gate_rejections; Speaker voice mismatch -> Flagged for S07 review

F03 Human Review Packet Resolution
    Operator opens S07 -> Plays audio slice -> Compares against ECAPA reference -> Signs off decision -> Ingestion resumes with updated provenance
```

---

## 5. Components & UI Subsystems

| Component | Variants | States | Used On |
|---|---|---|---|
| **VerbatimQuoteCard** | Primary teaching, Related clip | Default, highlighted, audio-sync active | S02, S03 |
| **AudioTimestampPlayer** | Compact inline, Full drawer | Stopped, buffering, playing, scrubbed | S02, S03, S04, S07 |
| **CitationBadge** | Human-verified, Automated candidate, Channel-shared | Verified (green), Automated (cyan), Shared (amber) | S02, S03, S04 |
| **SafetyAlertBanner** | Distress intervention, Kill-switch refusal | Active, escalated | S01, S05 |
| **CorpusHealthMetricCard** | Optimizer, Drift, Snapshot, Deletion ratio | Nominal, degraded, critical | S06 |

---

## 6. Inferred Data Model & State Entities

```
1. SourceRelease (Lineage & Catalog)
   - id (uuid), source_url, title, media_type, published_at, rights_status, release_version, content_checksum, created_at
   - Evidence: docs/rights/CONTENT-RIGHTS.md, public.source_releases
   - Confidence: High (Locked by invariant X40)

2. CorpusChunkPoint (Vector Data Plane)
   - point_id (uuid5), parent_id (uuid5), chunk_index, chunker_version, embedding_model, embedding_dim, text_verbatim, audio_start_ms, audio_end_ms, speaker_id, speaker_verified, domain_rights_status, content_checksum
   - Evidence: skills/corpus-data-contract/SKILL.md, Qdrant payload schema
   - Confidence: High

3. CorpusGateRejection (Audit & Quarantine Ledger)
   - id (uuid), source_url, source_release_version, tier, rejection_reason, error_details (jsonb), quarantined_at
   - Evidence: public.corpus_gate_rejections, invariant X40
   - Confidence: High

4. ExactCacheFingerprint (Cryptographic Serving Cache)
   - cache_key (sha256), query_normalized, prompt_template_hash, model_revision, collection_version, rights_register_hash, policy_fingerprint, response_payload (jsonb), expires_at
   - Evidence: backend/services/first_person_serving_contract.py, invariant X13
   - Confidence: High

5. HumanReviewPacket (Speaker & Rights Governance)
   - id (uuid), packet_type, video_id, window_start_ms, window_end_ms, wav_sha256, ecapa_score, expected_guru, review_status, reviewer_id, reviewed_at
   - Evidence: docs/reviews/2026-11-14-human-gates/, invariant X41
   - Confidence: High
```

---

## 7. Scope Boundaries

### In Scope
- Full product serving harness (ordered stages, exact cache fingerprinting, circuit breakers, verbatim evidence gate).
- Multi-modal ingestion wirings (dual ASR, ECAPA voiceprint verification, boundary chunking, hybrid vector & graph indexing).
- Blue-green immutable collection promotion via Qdrant atomic aliases.
- Postgres DDL for rights registers, rejection tracking, evaluation runs, and cache fingerprints.

### Out of Scope (Prohibited by Repository Invariants)
- LLM-authored teaching prose or synthetic doctrine generation (forbidden by invariant X24/Serving Invariants).
- In-place mutation of live serving vector collections (`first_person_v10`, `spiritual_wisdom_contextual`).
- Bypassing rights status checks or defaulting missing rights to "licensed" (forbidden by invariant X40).
- Relabeling speaker conflicts without signed human review packets (forbidden by invariant X16/X41).
