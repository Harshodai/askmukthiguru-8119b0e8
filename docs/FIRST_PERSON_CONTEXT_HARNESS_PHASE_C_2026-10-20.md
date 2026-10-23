# Phase C evidence — first-person context index build (2026-10-20)

Plan: `FIRST_PERSON_CONTEXT_HARNESS_AND_TAGGING_PLAN_2026-10-20.md` (phase C).
Status: **C1, C3, C4 done for the verifiable subset; C2 tools implemented (compare_asr_models.py, verify_speakers_ecapa.py) with execution pending against the WAV archive; C5 recorded, restore not exercised.**

## What was available, measured

| Input | Reality in this workspace |
| --- | --- |
| Teacher audio | **Available on system.** 680 `.wav` files (7.4 GB) located in `mukthiguru_attribution_data/audio_archive/wavs/` with `manifest.json`. |
| ASR & Speaker Tools | `backend/scripts/ops/compare_asr_models.py` (Whisper/ASR comparison), `backend/scripts/ops/verify_speakers_ecapa.py` (ECAPA-TDNN verification), and builder options `--speaker-verdicts` and `--asr-dir` in `build_fp_context_from_v9.py`. |
| Plain transcripts | `transcripts/<video_id>.md`, **767 files**, `## Transcript` section, no timings, `Fetched 2026-08-16`. |
| Source clips | `first_person_v9`, **1,981 points / 410 videos**, all `rights_cleared`, all `quality_status=verified_verbatim`, all `provenance_kind=speech_turn_clip`, vectors `passage_dense` (1024, cosine) + `passage_sparse`. |
| Speaker status | `speaker_verified=True` on **779**, key absent on **1,202** (60.7%). Automated ECAPA verification tooling is available; updated measurement run is pending. |

`transcripts/*.md` are **not** the transcript the verbatim layer was built from: the
video-level `transcript_hash` on the v9 payload never equals `sha256` of the
`.md` body (194/200 sampled), and only 148 clips appear as exact substrings.
They are a different (cleaned) ASR pass, so they cannot be used as the
authority for verbatim text — only as a location reference.

## Method (build_fp_context_from_v9.py)

`backend/scripts/ops/build_fp_context_from_v9.py`, dry-run by default:

1. Read the source collection (payload + vectors).
2. Quarantine, before any alignment work: unresolved guru/video, empty text,
   `rights_cleared is not True`, `quality_status != verified_verbatim`,
   `speaker_verified is not True`, invalid `transcript_hash`. **A missing
   `speaker_verified` is never defaulted to true.**
3. Locate the clip inside its transcript: take the first six normalized words as
   a probe, score every occurrence with `difflib.SequenceMatcher` over a window
   of the clip's length, keep the best. Accept only `ratio >= 0.90`;
   `word_start` = probe position, `word_end = word_start + len(clip words)`.
4. Build strict `SourceSpan`/`ParentUnit` records (deterministic IDs, clip-level
   `source_text_hash`, neighbour links, boundary/completeness classifiers).
5. `--apply` writes to a **new** collection only, copying the source clip's
   `passage_dense`/`passage_sparse` vectors (same text, same model → no
   re-embedding), then requests a snapshot. The source collection is untouched.

## Results

```
total source points            1981
kept (derived spans)            591   (368 krishnaji / 223 preethaji)
parents                         491
quarantined speaker_unverified  1202
quarantined not_locatable       168   (all with alignment < 0.90)
quarantined transcript_missing   20
alignment median / p10 / min    0.98 / 0.9403 / 0.90
```

Applied to `fp_context_v1_local` (new, local Qdrant):

```
children 591 · parents 491 · points 1082
structural audit       0 defects (invalid records, hash mismatches, orphan
                       children, parents with missing children)
deterministic rebuild   manifest sha256 identical across two dry runs
snapshot               fp_context_v1_local-1111874297854021-2026-10-20-13-02-59.snapshot
```

End-to-end read of the built collection (host-side, read-only):

- `FirstPersonContextStore.retrieve` on three self-vectors, with
  `guru_id ∈ {None, krishnaji, preethaji}` → 9/9 query/filter combinations
  returned only the requested guru's parents.
- `FirstPersonContextHarness.decide(answerability="yes")` reached
  `GROUPED_BY_PARENT → … → CITATION_AND_AUDIO_GATE → SERVE`, produced a verbatim
  `answer_text`, one citation with the stored YouTube URL and audio offsets
  `(20000, 59520)`.
- Mixed outcomes across queries were `serve_single_span`,
  `serve_related_not_direct`, and one `abstain` — the gates still discriminate.

## Harness-local soak (no provider calls)

200 iterations over 40 distinct query vectors against `fp_context_v1_local`,
`limit_parents=5`, `spans_per_parent=8`, all harness gates active:

```
retrieval   p50 14.25 ms   p95 18.36 ms   p99 31.86 ms
harness     p50  0.18 ms   p95  0.23 ms   p99  0.33 ms
decisions   965 serve_related_not_direct, 35 abstain (answerability="indeterminate")
metrics      3 counter keys, RSS peak 0.13 GB
```

This is transport + gate latency, not answer quality: `answerability` was left
`indeterminate` on purpose, so almost everything is correctly labelled
"related, not direct".

## Honest limits

- **This is not an ASR rebuild.** Word offsets are transcript *locations*, the
  corpus version is `fp-context-transcript-v1`, and the derivation is recorded
  per clip in `.work/fp_context/report.json`. Anyone comparing IDs across a
  future ASR build must expect different `source_span_id`s.
- **The majority of the corpus is currently quarantined pending verification.** 1,202 clips have no speaker
  verification and were excluded rather than assumed. Automated verification tooling (`verify_speakers_ecapa.py`) is implemented; execution against the WAV archive is pending.
- **C2 status**: Model comparison tooling (`compare_asr_models.py`) is implemented to evaluate Whisper/ASR engines against the teacher WAV archive; updated measurements are pending execution.
- **C5** has a snapshot and a deterministic rebuild, but a restore was not
  exercised (no second Qdrant instance to restore into). Treat rollback as
  *reproducible rebuild + snapshot artifact*, not as a tested restore.
- Serving is still unwired: `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` and no
  serving call site, so this collection is not read by `/api/chat`.
