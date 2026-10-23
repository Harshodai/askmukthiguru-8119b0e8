# First-Person Collection Evolution: From v1 to v10

> **Document Status**: Architecture & provenance record — **not release evidence**  
> **Date**: October 21, 2026 (claims corrected; see §5.1 and §7)  
> **Target Collection**: `first_person_v10` (Alias: `first_person`)  
> **Total Points**: 4,197 (2,737 retrieval child spans + 1,460 parent discourses)  
> **Acoustic Verification**: **per-video** ECAPA-TDNN check (`speechbrain/spkrec-ecapa-voxceleb`) over the **first 60 seconds** of each WAV, against a **hard-coded `0.4668`** floor/margin; every span of a video that cleared that check was written with `speaker_verified=true`. **Per-span verification does not exist in this build.**  
> **Zero-Hallucination Rate**: 100.0% **under a bag-of-words/exact-text benchmark only** — it is not proof that no hallucination is possible. See §5.1.

---

## 1. Executive Summary & Purpose

The **First-Person Pipeline** is designed to serve the verbatim spoken teachings of Sri Preethaji and Sri Krishnaji directly to seekers. Unlike General RAG (which synthesizes responses with an LLM and injects Ontological Knowledge Framework doctrine), the First-Person system operates under an inviolable product invariant:

> **The Zero-Hallucination Invariant**: The system must never author, extrapolate, or paraphrase spiritual teachings. Every served response must be deterministically reconstructed from immutable transcript spans whose speaker attribution passed the verification this document describes, complete with the stored video timestamps and YouTube playback offsets.

Reaching `first_person_v10` required a 10-iteration engineering evolution. Each prior version was retired because of specific integrity defects—ranging from truncated sentences and unverified student/interviewer voices, to pronoun reference loss and lack of hierarchical discourse context.

This document records the exact failure modes, technical breakthroughs, and architectural shifts across all 10 versions.

---

## 2. Chronological Lineage & Failure Matrix

| Version | Points | Core Design | Fatal Failure Mode / Limitation | Reason for Retirement |
|---|---|---|---|---|
| **v1** | 580 | Naive sliding window chunking | Cut off mid-sentence; dangling clauses ("Because...", "And so..."). | Unusable verbatim clips; broken speech boundaries. |
| **v2** | 280 | Punctuation-based splitting | Lost speaker turns; merged interviewer questions with guru answers. | Attributed seeker/interviewer words to the guru. |
| **v3** | 202 | Strict paragraph chunking | Aggressive filtering dropped 65% of valid teachings; tiny corpus. | Severe coverage deficit; high abstention rate. |
| **v4** | 580 | Fixed-character chunking + overlap | Duplicate segments; repeated sentence fragments in playback. | Choppy seeker experience; duplicate search results. |
| **v5** | 260 | Heuristic boundary filters | Over-filtered long meditative discourses; dropped key teachings. | Inability to handle multi-minute meditative journeys. |
| **v6** | 147 | Conservative safety subset | High precision but starved retrieval; answered <20% of benign queries. | Under-indexing; collection too small for production. |
| **v7** | 2,294 | First broad unverified compilation | Included 493 boundary defects (`tail_no_terminal`, `headless_predicate`); unverified speaker attribution. | Dirty data; served unverified audio and truncated sentences. |
| **v8** | 1,801 | Filtered v7 with boundary regexes | Stripped 493 defects, but flat single-vector representation lost discourse context and pronoun references. | Coreference deficit ("he", "this", "they" without context). |
| **v9** | 1,981 | v8 + 180 mass-ingest clips | **1,202 / 1,981 points (60.68%) lacked `speaker_verified` key**; 35 context fields missing on 100% of points. | Violated speaker integrity invariant; lacked parent/child hierarchy. |
| **v10** | **4,197** | **Strict `fp-context-v1` schema + ECAPA verification + BGE-M3 dense/sparse** | **Known limitations**: speaker verification is a per-video check over the first 60 s with a hard-coded floor, so every span of a cleared video is written `speaker_verified=true`; word timings may be synthesized; several readiness-audit fields are unpopulated (§7). Boundary clean, rights cleared per channel, 7-gate context harness at serve time. | **Active collection**, pending per-span verification. |

---

## 3. Deep-Dive: Why Each Version Was Retired

### The Early Boundary Iterations (`v1` to `v6`)
Early iterations relied on standard text-splitting algorithms (LangChain RecursiveCharacterTextSplitter, fixed-token windows). In audio transcript processing, these methods fail catastrophically:
- **Speech Boundary Defect**: A chunk ending with *"When the mind becomes silent and"* followed by silence cut off the teacher's thought.
- **Interviewer Contamination**: Dialogue turns in talk shows or podcasts were indexed as a single chunk, attributing the host's framing to Sri Preethaji or Sri Krishnaji.
- **Over-Pruning Defect**: Tightening boundary rules without acoustic grounding caused `v6` to shrink to 147 points, making the bot refuse 80% of genuine spiritual queries.

### The Scale vs. Integrity Crisis (`v7` & `v8`)
`first_person_v7` was the first attempt to index the entire available catalog (2,294 points). While coverage expanded, audit revealed:
1. **493 Structural Boundary Defects**:
   - `tail_no_terminal`: 218 points ended without terminal punctuation (`.`, `?`, `!`).
   - `headless_predicate`: 141 points began with a hanging verb phrase.
   - `leading_conjunction`: 134 points opened with *"And"*, *"Because"*, or *"Therefore"*.
2. **Uncalibrated Speaker Attribution**: Video metadata ("Channel: Sri Preethaji & Sri Krishnaji") was used as a proxy for speaker identity. Narrators and guest speakers were wrongly indexed as the teachers.

`first_person_v8` stripped the 493 defects (yielding 1,801 points), but exposed a deeper architectural ceiling: **the Flat-Vector Ceiling**.

### The Flat-Vector Ceiling & The "Ravana Problem" (`v8` & `v9`)
In a flat single-chunk architecture, each clip is an isolated island (typically 30–60 seconds). This created two critical vulnerabilities:
1. **The Pronoun / Coreference Deficit**:
   A clip began: *"He was consumed by his own arrogance and could not see the light."*  
   Without the preceding sentence (*"Consider the story of Ravana..."*), the seeker had no idea who "he" was. An LLM had to either guess/hallucinate the subject or serve a confusing fragment.
2. **The Attribution Void in `v9`**:
   `v9` added 180 clips to `v8` (total 1,981 points). When rigorously audited on October 20, 2026, forensic inspection revealed:
   - **1,202 out of 1,981 points (60.68%) had NO `speaker_verified` field**.
   - **35 `fp-context-v1` fields were missing on 100% of points**.
   - Defaulting `speaker_verified` to `True` was strictly forbidden by repository invariant `L-FP-CONTEXT-GURU-SET-1` (never invent credit for an unverified voice).

`first_person_v9` could not safely power the context harness. A ground-up rebuild from source transcripts and acoustic audio was mandatory.

---

## 4. The Solution: Architecture of `first_person_v10`

`first_person_v10` was constructed from scratch following the master specifications in `First-person context harness and tagging plan.md`.

```text
transcripts/*.md (763 files) + audio_archive/wavs/ (708 WAVs)
                       │
                       ▼
    [1] ECAPA-TDNN Acoustic Voice Verification
        (speechbrain/spkrec-ecapa-voxceleb against teacher centroids;
         HARD-CODED margin >= 0.4668 / cosine >= 0.4668 floor, checked once per
         video over the FIRST 60 s of audio -> every span of a cleared video
         inherits speaker_verified=true)
                       │
                       ▼
    [2] Boundary Defect Audit & Sentence Integrity
        (ingest.verbatim.boundaries: sentence-level boundary defects removed
         by the same filter used for serving)
                       │
                       ▼
    [3] Hierarchical Discourse Clustering
        ParentUnit (Discourse Context)
            ├── SourceSpan 0 (Child Span: passage_dense + passage_sparse)
            ├── SourceSpan 1 (Child Span: passage_dense + passage_sparse)
            └── SourceSpan 2 (Child Span: passage_dense + passage_sparse)
                       │
                       ▼
    [4] Dual-Vector BGE-M3 Representation
        - Dense: 1024-dim Cosine
        - Sparse: BGE-M3 Lexical Tokens
                       │
                       ▼
    [5] First-Person Context Harness Decision Engine
        7 Strict Gates: Guru Isolation ➔ Speaker Verified ➔ Rights Cleared
        ➔ Hash Match ➔ Boundary Completeness ➔ Coreference ➔ Citations
                       │
                       ▼
    [6] Zero-Hallucination Deterministic Assembly
        Answer Text assembled strictly from source_span_ids
        + Exact Video ID, start_ms, end_ms, and YouTube playback URL
```

### Key Technical Specs of `first_person_v10`
1. **Hierarchical Topology**:
   - **Parent Units** (`record_type = parent_unit`): 1,460 points. Payload-only discourse containers carrying overarching topic, guru ID, video metadata, and child span orders.
   - **Child Spans** (`record_type = retrieval_child`): 2,737 points. Named vectors (`passage_dense` 1024d Cosine + `passage_sparse`).
2. **Acoustic Verification (per video, not per span)**:
   - Speaker identity was checked **once per video**, by embedding the **first 60 seconds** of the WAV and comparing it against the verified guru voice centroids with a **hard-coded** `0.4668` cosine floor and the same margin. 80 ambiguous/low-margin videos were rejected into quarantine.
   - Every span of a video that cleared that check was written `speaker_verified=true`. A span's own `start_ms`/`end_ms` audio was **not** embedded, so a guest voice appearing later in a cleared video is not detected by this build.
   - No per-span `speaker_verified` claim may be made from this collection until `backend/scripts/ops/build_full_corpus_v10.py` verifies each span from its own slice against calibrated floors (§7).
3. **Payload Indexing**:
   - Filter-indexed fields: `record_type`, `guru_id`, `video_id`, `parent_unit_id`, `source_span_id`, `rights_cleared`, `speaker_verified`.

---

## 5. Benchmark Snapshot (42-Question Soak) — not release evidence

The `first_person_v10` collection was subjected to the 42-question benchmark suite (29 on-topic queries + 13 out-of-corpus negative controls). The numbers below are a one-off local sample measured on **this** collection with **this** builder's speaker flags; they are not a quality proof for the pipeline and must not be quoted as release evidence.

| Metric | Measured Value | Standard / Invariant | Status |
|---|---|---|---|
| **Zero-Hallucination Rate (benchmark definition, §5.1)** | **100.0% (28/28 served)** | 100% | ✅ PASSED (benchmark only) |
| **Hallucinated Tokens Count (benchmark definition)** | **0** | Exactly 0 | ✅ PASSED (benchmark only) |
| **Cryptographic Hash Matches** | **28 / 28** | 100% byte-for-byte | ✅ PASSED |
| **Out-of-Corpus Leak Rate** | **0.00% (0 / 13 leaked)** | Exactly 0 | ✅ PASSED |
| **Pipeline Latency (P50)** | **694.6 ms** | < 2,000 ms | ✅ PASSED (~16x speedup) |
| **Wall-Clock Latency (P50)** | **817.4 ms** | < 3,000 ms | ✅ PASSED |
| **Direct Answer Rate** | **93.1% (27/29 on-topic)** | > 75% | ✅ PASSED |

### 5.1 What the "Zero-Hallucination" number actually measures

`scripts/benchmark_42_evaluation.py` verifies that the served answer text is an exact match for one cited `verbatim_text` (or all citations concatenated in order, after stripping the deterministic response template) **and** that no answer token is missing from that cited text. That is a **bag-of-words / exact-text benchmark over the shipped citations**:

- It proves the benchmark answers were copied from citations, which is what the assembly step is supposed to do.
- It does **not** prove the cited text was correctly transcribed, correctly attributed, correctly bounded, or free of ASR error.
- It says nothing about retrieval quality, answer relevance, or abstention correctness.
- A served answer can pass it while the citation's audio window is wrong, which is why §7's per-span gates matter.

---

## 6. Deprecation & Cleanup Record

On October 21, 2026, all legacy and prototype collections were backed up with snapshots and safely purged from Qdrant:
- **Snapshots Archived**:
  - `first_person_v7-1111874297854021-2026-10-21-09-13-28.snapshot`
  - `first_person_v8-1111874297854021-2026-10-21-09-13-28.snapshot`
  - `first_person_v9-1111874297854021-2026-10-21-09-13-31.snapshot`
  - `first_person_v10-1111874297854021-2026-10-21-08-49-04.snapshot`
- **Purged Collections**:
  `first_person_v1`, `first_person_v2`, `first_person_v3`, `first_person_v4`, `first_person_v5`, `first_person_v6`, `first_person_v7`, `first_person_v8`, `first_person_v8_shrunk_20261018`, `first_person_v9`, `first_person_v9_pilot`, `fp_context_v1_local`.
- **Live Alias Configuration**:
  ```text
  Alias: first_person ──────► Target: first_person_v10 (4,197 points)
  ```

---

## 7. Unresolved Audit Gates (read before citing this document)

These are open defects of the build that produced `first_person_v10`. Release evidence for the collection is deferred until they are closed.

1. **Speaker verification is per video, over the first 60 s.** The builder embedded one slice per WAV and applied a hard-coded `0.4668` cosine floor and margin; every span of a cleared video was written `speaker_verified=true`. A guest/narrator voice later in the same video is not detected. The corrected builder (`backend/scripts/ops/build_full_corpus_v10.py`) now embeds **each span's own `start_ms`/`end_ms` slice** via `verify_speakers_ecapa._slice`, loads calibrated `cosine_floor`/`margin_threshold` from the `verify_speakers_ecapa` output, and fails closed when that calibration is unavailable. **No collection built by the corrected flow exists yet.**
2. **Word timings may be synthesized.** The build in production-time use wrote word timings that were inferred by spreading the WAV duration evenly across transcript words when a Transcripts_B alignment was absent or only loosely matched. Those offsets are not measured speech alignments, so a citation or playback offset built from them may land on the wrong audio. The corrected builder returns an explicit "no timings" result and quarantines the video as `no_word_timings` instead.
3. **Readiness-audit fields are unpopulated.** The collection carries no `asr_engine`, no `asr_model_version`, and no `audio_start_ms` / `audio_end_ms` for its spans, so an auditor cannot reconstruct which ASR model produced the text or exactly which audio window was verified.
4. **Zero-hallucination is a benchmark, not a property (§5.1).** It does not validate transcription, attribution, boundary correctness, or retrieval relevance.
5. **No per-span acoustic evidence file.** There is no stored per-span cosine/margin alongside the flag, so "verified" cannot be independently re-checked per span from the payload alone.

Until (1) and (2) are re-built against the corrected flow and (3) is populated, treat this document as an architecture record and **not** as release evidence for acoustic certainty, defect freedom, or per-span match.
