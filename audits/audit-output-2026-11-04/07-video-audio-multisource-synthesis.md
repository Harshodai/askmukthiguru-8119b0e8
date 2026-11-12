# 07 — Video, audio and multi-source teaching synthesis

> **2026-11-06:** Superseded in part by `specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` (decision-free Variant A, wire contract, staged gates for §4). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: Specialist S2. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Scope: audio and transcript processing, speaker attribution, timestamps, segmentation, and the ability to answer from more than one video. Prompt and answer-voice specifications belong to S3 (`09`, `10`). Lineage and stores are in `06`.

## 1. Summary

1. **No answer today combines teaching from several videos into one explanation.**
   - The legacy path serves one verbatim clip. It can add **one second clip** from a different video, quoted separately and "never merged" (`first_person_pipeline.py:5225-5235,5505-5530`).
   - The v10 harness abstains when spans come from two parents or two teachers (`cross_parent_contamination`, `cross_guru_contamination`; `first_person_context_harness.py:47-60`).
   This is a product gap against Pillar 2.3 (RET-03 in `08`).
2. The building blocks for honest multi-video answers exist but are off or restricted:
   - deterministic facet planner;
   - set selector with `supported | partial | conflicted | insufficient`;
   - compound-question path;
   - graph expansion;
   - TeachingUnit graph.
   The set selector runs only when `IS_PRODUCTION=false` (`first_person_pipeline.py:1958-1964`).
3. The compound path does not retrieve per sub-question. It reuses the whole-question vector and gives each facet the next three clips by whole-question rank (`first_person_pipeline.py:5684-5690,5817-5822`). That design cannot find a second video that answers only the second sub-question (RET-04).
4. Segmentation, not selection, is the binding constraint:
   - Measured clip lengths contradict the 18–25 s invariant: median 38 s, p75 72 s, max 180 s `[DOC-CLAIM]`.
   - The 120 s serve cap and the orphan-opener rule caused 579 of 842 quarantine events on the 128-question bank `[DOC-CLAIM]` (`PROD_READINESS_TASK_LIST_2026-10-11.md` §0, 2026-10-19 note).
5. `backend/ingest/verbatim/` is used by the offline builders, not by the online `IngestionPipeline` `[V-STATIC]`. Root `CLAUDE.md` invariant 7 says "not wired". That is true for online ingestion only.
6. Root `CLAUDE.md` names `persona_discriminator.py` as the speaker-attribution ground. The file (`backend/services/guru_brain/persona_discriminator.py:1-9`) is an LLM judge that scores **generated Guru responses** for "Direct Intimacy & Face-to-Face Realism". It is not a speaker attribution tool. Real attribution is ECAPA per-span verification in the builders. Cross-reference for S3: this is a generated-teacher-voice component.

## 2. Current processing chain

| Step | Implementation | Status | Evidence |
|---|---|---|---|
| Acquisition | `scripts/ops/audio_archive.py`: yt-dlp with `android,ios,mweb,web` clients, hash-partitioned workers, manifest with lock | Host only | Root `CLAUDE.md` invariant 17 [DOC-CLAIM]; file exists [V-STATIC] |
| Online acquisition (separate) | `ingest/youtube_loader.py`: transcript API, then yt-dlp subtitles, then audio download + Whisper | Online ingestion; contradicts invariant 17 | `youtube_loader.py:7-12`; `backend/ingest/pipeline.py:542-555` [V-STATIC] |
| ASR | Whisper with `initial_prompt` = sacred-vocabulary prompt, `condition_on_previous_text=False` | Live in both paths | `services/speech_config.py:11-38` [V-STATIC] |
| Voice activity detection | None | Absent | Root `CLAUDE.md` invariant 7 [DOC-CLAIM] |
| Multi-ASR vote | `ingest/verbatim/vote.py` | Tested; offline only | [V-STATIC] |
| Cleaning | `ingest/verbatim/asr_cleaner.py` (stutters, fillers); `punctuation.py` | Offline builders; legacy store re-cleans before ID | `first_person_store.py:115-134` [V-STATIC] |
| Boundaries | `ingest/verbatim/boundaries.py`: `CONJUNCTIONS = {and, or, so, but, because, nor, yet}`; defect `head_conjunction` | Offline builders | `boundaries.py:29,251` [V-STATIC] |
| Word timings | From a transcript alignment. A video without one is quarantined `no_word_timings`. Timings are never synthesised. | v10 builder | `build_full_corpus_v10.py:9-17,986` [V-STATIC] |
| Speaker verification | ECAPA-TDNN on each span's own slice. Calibrated floors. `calibration_v2`: 0 false accepts in 1,400 impostor trials; 95% upper bound 0.21% `[DOC-CLAIM]` | v10/v11 builders | `backend/scripts/ops/build_full_corpus_v10.py:4-17`; `audits/evidence/first_person_v11_speaker_backfill_and_build_2026-10-31.md` |
| Teacher identity | `guru_id` from voice + metadata agreement. A mismatch is skipped. | v10 builder | `backend/scripts/ops/build_full_corpus_v10.py:1041-1050` [V-STATIC] |
| Rights | Builder and serve time read the same pinned register | Both | `06` DATA-02 |
| Language | Transcripts are English. Non-English questions are translated before embedding. Quotes are never translated; a gloss is optional. | Live | `config.py` (`first_person_translation_timeout_s` comment) [V-STATIC] |
| Playback | `start_ms − 0.25 s` to `end_ms + 0.25 s`, capped at duration. Played from YouTube. Availability is checked by oEmbed with a 600 ms fail-open timeout and a 24 h cache (`yt:avail:*`). | Live | `first_person_pipeline.py:154,1697-1700`; `services/youtube_availability.py:1-37` [V-STATIC] |

### 2.1 Segmentation against the invariants

| Invariant | Statement | Evidence | Verdict |
|---|---|---|---|
| 10 | No split on a trailing conjunction without forward resolution | Rule exists in `boundaries.py`. v10 `boundary_defect_rate` 24.48% `[DOC-CLAIM]` | Implemented, not achieved |
| 11 | Rolling 18–25 s context | Median 38 s, p75 72 s, max 180 s; 134 of 1,981 v9 clips over 120 s `[DOC-CLAIM]` | Not met by the data |
| 14 | ≥ 15 words | Policy now 23–300 words (`first_person_evidence_policy.py:138-150`) [V-STATIC] | Stricter than stated |
| — | 120 s serve cap | `first_person_max_clip_seconds = 120.0` (`config.py:500`) [V-STATIC] | Causes 292 of 842 quarantine events `[DOC-CLAIM]` |

The serve-time gates now carry the segmentation burden. They remove clips after retrieval. Combined with per-video de-duplication before gating, this costs whole videos (RET-01 in `08`).

## 3. Multi-video capability today

| Component | What it does | Default | Documented local `.env` | v10-only posture | Multi-video? |
|---|---|---|---|---|---|
| Legacy `FirstPersonPipeline.execute` | One clip; an optional second clip from another video if it also scores ≥ min | Live (collection `first_person_v8` by default) | Live (collection per local `.env`, unknown `[LIVE-L]`) | Not used | Two separate quotes; no synthesis |
| Context harness | Up to 3 spans (`first_person_context_max_spans`) from **one** parent | Off | Off (example) | **On** | No: abstains on cross-parent or cross-guru |
| Validated cross-parent edge | Adds the predecessor span from the adjacent parent in the same video | With the harness | — | On | Same video only |
| Enrichment window | Re-hydrates the whole parent | Off | Off | Off | Same video |
| Facet split (`_decompose_query_facets`, `_execute_compound`) | Up to 3 sub-questions, one clip each, "continuous layout" | Off | — | Disabled by terminal mode (`first_person_pipeline.py:3686`) | Yes, but without per-facet retrieval |
| Facet planner + set selector | Deterministic plan; keyword facet scoring; near-duplicate removal (Jaccard > 0.80); one context per video; set status | Off; non-production only | — | Off | Yes (design); keyword heuristics, unmeasured |
| Graph expansion (T3) | Ontology neighbours → extra payload-filtered retrieval | Off | Off | Off | Possible |
| TeachingUnit graph | Span-level neighbours from a Memgraph projection | Off | — | Off | Possible; builder defects (RET-06) |
| Quote weaver | Hero-clip verification, audio strips, glue text | Live for verification and strips. LLM glue is opt-in (`first_person_editorial_rewrite_enabled=False`) | — | — | Assembles quotes only |
| Generating graph (`rag/nodes/generation.py`) | Multi-document LLM synthesis with citations | Not reached for teaching questions when the first-person module claims | Same | Same | Yes, but it generates prose; forbidden as teacher voice (invariants 1, 15, 21) |

Answer to the directive question: **No.** A single answer cannot today combine clips from different videos into one explained teaching with per-claim provenance. The closest live behaviour is two independent verbatim quotes, each with its own citation.

## 4. Target design: evidence-grounded multi-video teaching synthesis

### 4.1 Principles (binding)

1. The teacher's words appear only as verbatim spans with citations. Nothing generated is rendered in the teacher's voice (invariants 1, 12, 15).
2. A generated explanation is allowed only in the **assistant's own voice**. It must be labelled as an explanation, and each sentence must point to the span IDs that support it. Whether the owner permits assistant-voice explanation at all is an open product decision (S3 `10`, S4 `23`) `[HUMAN]`.
3. Each claim carries `(video_id, start_ms, end_ms, source_span_id, guru_id)`.
4. One teacher's words are never attributed to the other. A cross-teacher answer shows two labelled sections.
5. Missing evidence produces a visible "not covered" statement, not a filled gap.

### 4.2 Pipeline

```mermaid
flowchart TD
  Q[Question] --> P[Facet planner\ndeterministic, plus an optional small-LLM split\nselection-only output]
  P --> F1[Facet 1 query] & F2[Facet 2 query] & F3[Facet 3 query]
  F1 & F2 & F3 --> R[Per-facet hybrid retrieval\ndense + sparse RRF, group by parent\nfilters: rights, speaker_verified, guru]
  R --> G[Gate pool BEFORE de-dup\nintegrity, hash, standalone, length]
  G --> D[De-duplicate\nsame text 8-gram ≥ 0.6 → keep the earliest-recorded;\ncontained spans → keep the container]
  D --> S[Set selector\ncoverage per facet: direct / indirect / absent\nsource diversity: ≤ 1 span set per video per facet\nteacher scope]
  S --> C{Conflict / context check}
  C -->|different contexts| L[Label context: 'In a talk on X…' from metadata only]
  C -->|apparent contradiction| K[Show both, mark 'different emphasis', no resolution claim]
  S --> V[Relevance scorer per (facet, span)\nselection-only, min score 3]
  V --> A[Assembly\nordered verbatim spans per facet + citations\noptional assistant-voice bridge sentences with span pointers]
  A --> VER[Verifier\nevery bridge sentence entails from cited spans\nelse drop the sentence]
  VER --> OUT[Answer + evidence table + 'not covered' facets]
```

### 4.3 Data contracts

| Object | Fields |
|---|---|
| `FacetPlan` | `facets[]` (≤ 3), `teacher_scope`, `planner_version` |
| `EvidenceCandidate` | `source_span_id`, `parent_unit_id`, `video_id`, `guru_id`, `start_ms`, `end_ms`, `facet`, `retrieval_rank`, `relevance_score`, `gates_passed[]` |
| `EvidenceSet` | `status ∈ {supported, partial, conflicted, insufficient}`, `facet_coverage{facet: direct/indirect/absent}`, `selected[]`, `rejected[]` with reasons, `selector_version` |
| `AnswerSegment` | `kind ∈ {verbatim_quote, assistant_bridge, not_covered}`, `text`, `support_span_ids[]`, `teacher_label` |
| Persisted citation | See `06` DATA-12 |

### 4.4 Rules for hard cases

| Case | Rule |
|---|---|
| Overlapping teachings | Keep one span per near-duplicate cluster. Prefer the clip with a clean boundary and verified speaker. |
| Apparent contradiction | Show both spans with their context labels. Never state that one supersedes the other. Route to the human-review queue for the guru-review set (S4 `23`). |
| Different contexts (Q&A vs discourse vs meditation) | Label from video metadata, not from generated text. |
| Incomplete evidence | Mark the facet `absent`. Do not fill it. |
| Inaccurate transcript | Spans with `text_edited_vs_source` above a threshold, or with mixed script, are not eligible. |
| Missing timestamps | Not eligible (already quarantined `no_word_timings`). |
| Translation ambiguity | Retrieve with the English translation. Show the original quote. A gloss is labelled "translation, not the teacher's words". |
| Teacher attribution | `guru_id` per segment. A set may cover both teachers only when the question is not teacher-scoped. Sections stay separate. |

### 4.5 Walk-through: "Why do I keep experiencing fear, even when I know intellectually that everything will be fine?"

| Stage | Output (illustrative; contents are hypotheses for human reviewers, not claims about the corpus) |
|---|---|
| Safety pre-check | "fear" is a single-keyword distress trigger today (`PROD_READINESS_TASK_LIST` §0, 2026-10-19 note) `[DOC-CLAIM]`. The design requires the distress classifier to separate inquiry from crisis first (S3 `14b`). |
| Facet plan | F1: what fear is and where it arises. F2: why intellectual understanding does not dissolve it. F3: a practice or reflection for the moment of fear. |
| Retrieval | Per-facet retrieval returns parents from several videos. Expected (hypothesis): discourse segments on fear, segments on thought vs experience, and a guided practice. |
| Gates | The pool is gated before de-duplication, so a long first span does not remove the whole video. |
| Set selection | F1 direct (video A), F2 direct (video B), F3 indirect (video C, Preethaji). Status `supported`. |
| Assembly | Three verbatim spans, each with teacher label and timestamp. Optional assistant bridge, for example: "The second excerpt addresses the gap between knowing and feeling." The bridge points to span B. |
| Verification | Bridge sentences without entailment are dropped. If F2 had no evidence, the answer says "I did not find a teaching that directly addresses the gap between knowing and feeling." |
| Output | Answer, evidence table (video, teacher, time), "open the full talk" links. |

### 4.6 Acceptance criteria

1. On a frozen 60-question multi-facet bank, 0 answer segments cite a span outside the selected set.
2. 0 cases where the `guru_id` of a quote differs from its label.
3. 100% of assistant bridge sentences pass the entailment check (the threshold is set by S3 `18`).
4. Facet coverage reported per answer. Human reviewers agree with `absent` in ≥ 90% of sampled cases `[HUMAN]`.
5. p95 added latency is measured and reported. No target is set before measurement.

## 5. Findings in this document

The multi-video findings RET-03 (no multi-video composition) and RET-04 (no per-facet retrieval) are recorded in `08-qdrant-graph-retrieval.md` with the other retrieval findings, to keep one register. Segmentation quality is DATA-14 in `06`.

## 6. Cross-references

- Data lineage and stores: `06`.
- Retrieval findings: `08`.
- Prompt and answer voice: S3 `09`, `10`.
- Safety pre-check behaviour for "fear" and "anxiety": S3 `14b`.
- Guru review of contradiction cases: S4 `23`.
