# Quote fidelity audit of the 2026-10-04 "8/8 PASS" benchmark

The expanded ruthless benchmark (run from `scratch/run_ruthless_benchmark_expanded.py`
and `scratch/display_expanded_responses.py`, plus a local `backend/services/quote_weaver.py`)
reported 8/8 PASS. None of those three files is committed on any branch, so the
renderer itself could not be read. This note checks the rendered output against what
the repo records about each video.

**What could not be checked:** the stored chunk text. Qdrant runs on Railway, which is
scaled down, and YouTube is unreachable from the audit container. So "quote appears
verbatim" is unchecked for every case, not confirmed. Everything below comes from repo
metadata: `docs/attribution/ekam_speaker_request.csv`,
`scripts/ingestion/remaining_videos_durations.json`, `scripts/ingestion/ingestion_state.json`
and `backend/benchmarks/reports/corpus_audit_20260801_full.json`.

| Case | Rendered as | Video's recorded title, speaker label, length | Chunks stored (snapshots differ) | Verdict |
|---|---|---|---|---|
| 1 | Preethaji · "Universal Intelligence & The Neurobiology of Consciousness" · 04:40–07:30 | "Universal Intelligence breaks down if we think with our brain or our heart" · `preethaji_krishnaji` · length not recorded | 2–7 | Title invented. A video this small is short, so a 170 s span at 04:40 is unlikely (unverified). |
| 2 | Krishnaji · "Dissolving the Inner Wall" · 01:55 | "pkconsciousnes - Field Of Abundance - My Story of Transformation - Rob" · 4:41 | 501 (164 poisoned, verdict REFETCH_FROM_ORIGIN) | Wrong speaker and title: it is a testimonial by "Rob". 501 chunks for a 4:41 clip means the stored content under this URL is itself wrong. |
| 3 | Krishnaji · "The Living Reality of Oneness Beyond Philosophy" · 05:20 | "IEC 2023 \| Mukti Guru Sri Preethaji ... Speaks On Consciousness Superpower \| Times now" · `preethaji` | 10–16 | Wrong speaker (Harsha confirmed by listening) and invented title. Harsha confirmed the words are not in the video. |
| 4 | Preethaji · "Four Sacred Secrets" | same video as case 3 | 10–16 | Third title for one video. |
| 5 | Preethaji · "Soul Sync Meditation - The Power of the Aham Chant" · 00:45 | "Feel the Power of the chant \| Soul Sync Meditation Challenge - 5 with Preethaji" · `preethaji` · 3:45 | 2–5 | Speaker plausible. Title paraphrased. A handful of chunks of a 3:45 clip are unlikely to hold all six stages verbatim (unverified). |
| 6 | Preethaji · "सुंदर स्थिति और आंतरिक सत्य" | same video as case 3, an English-language interview | 10–16 | Hindi title invented for an English video. |
| 7 | Crisis safety response | no quote | – | Not a quote case. Helpline text not re-checked here. |
| 8 | Preethaji · "Spiritual Practice & Medical Wisdom" · 00:30 | same video as case 5 (Soul Sync challenge 5) | 2–5 | Title invented. A chant clip is an unlikely source of medical guidance. |

At least 7 of 8 titles do not match any recorded title. One video id is shown under three
titles and two speakers. The 8/8 PASS was wrong: the pass criteria checked formatting
only.

## Why the repo could not catch this

1. **No check compared the quote with its source.** `askmukthiguru_ruthless_benchmark.py`'s
   citation category passes on keyword score plus link presence, and it records
   `faithfulness=kw`, which is the keyword score again.
2. **Runtime quote guards only see quotation marks.** `_unquote_unverifiable_spans`
   (`rag/nodes/generation.py`) and `verify_citation_ngrams` (`services/citation_service.py`)
   match `"..."` spans. A blockquoted hero teaching with no quotation marks bypasses both.
   `check_continuous_ngram_match` also passes a whole quote when any single 8-word run matches.
3. **The store cannot back a timestamp.** `ingest/pipeline.py` keeps only the text of
   `chunk_youtube_transcript`'s chunks and drops `timestamp_start`/`timestamp_end`. Only an
   inline `[t=XXs]` marker survives, and only for videos with fetched captions; Whisper-path
   videos have no timing at all. Any `&t=` deep link must be guessed or come from a marker.
4. **Stored titles are often just the video id** (`ingestion_state.json` `title == video_id`),
   and `teacher_id` is inferred from the title and first chunks
   (`services/teacher_attribution.py`). `docs/attribution/README.md` already says these labels
   are unverified and at least one is known wrong.

## What landed

- `backend/services/quote_fidelity.py`: `verify_quote()` checks text (every sentence verbatim
  in that video's stored chunks), speaker, title and timestamp, and fails closed when any of
  them cannot be checked. `cross_case_conflicts()` flags one video shown with different
  titles or speakers.
- `backend/benchmarks/quote_fidelity_check.py`: runs that check over rendered answers against
  Qdrant (or a JSON dump) and exits 1 on any failure.
- The renderer (`quote_weaver.py`) should call `verify_quote()` before showing a hero quote,
  and drop the quote when it fails. That wiring waits until the file is committed.

## Follow-up 2026-10-05: root cause, renderer gate, re-run against local Qdrant

### Root cause (read from the local, uncommitted files)

1. **The benchmark invented every quote.** `scratch/run_ruthless_benchmark_expanded.py`
   never retrieves. Each case hand-writes `t1`..`t8` and a clip dict with a made-up
   `speaker`, `teacher_id`, `video_title`, `start_ms` and `source_url` (case 3:
   `speaker="Sri Krishnaji"`, `video_title="The Living Reality of Oneness Beyond
   Philosophy"` on `0z-IZ2ar4eA`). It sets `transcript_hash = sha256(<its own text>)`,
   so the hash gate passes trivially, and appends a literal `True` to `results`.
   `QuoteWeaverAssertionGate.validate` then compares the output with the same invented
   clip, so it can only pass. `scratch/display_expanded_responses.py` adds hard-coded
   concept pills per case index.
2. **The renderer trusted caller metadata.** `quote_weaver._format_clip_block` printed
   `c["speaker"]`, `c["video_title"]` (falling back to the video id as a "title") and
   `c["source_url"]`, adding `&t=0s` when no start was known. The deterministic
   opening template added a topic claim ("her discourse on the nature of
   consciousness"). `first_person_pipeline`'s audio strip invented a title
   ("Living Wisdom Discourse") and an end time (`start + 90`) when none was stored.
3. **The store cannot back what was shown.** `first_person_v7` stores no titles at all;
   `spiritual_wisdom_contextual` stores channel names in `speaker` ("Unknown Channel")
   and keeps no per-chunk timing (only inline `[t=..]` markers).

### What changed

- `quote_fidelity.verify_quote`: whole-quote contiguous match (one chunk, or two
  adjacent chunks with their overlap merged); Unicode-aware normalisation, so Devanagari
  matras survive and curly quotes and repunctuation do not matter; per-chunk speaker wins
  over `teacher_id`; host or interviewer turns, `ekam` and mixed speakers fail; a
  both-teachers video needs the joint label; title and `t=` are checked only when shown,
  and a neutral link label (`Watch on YouTube`) or a bare id is not a title claim.
  `source_from_payloads` reads both store shapes and never trusts a `video_title` key.
- Renderer (local working tree, `quote_weaver.py` and `first_person_pipeline.py`, which do
  not exist on `main`): every clip goes through `verify_hero_clip` against the retrieved
  payloads before it is rendered. Speaker labels come only from payload `speaker` or
  `teacher_id`, titles only from a stored `title`, and `t=` only from `start_ms` or a
  `[t=..]` marker. A failed clip is dropped. If none survive, or the query is crisis,
  medical or another blocked topic, the pipeline abstains: no quote, no citations, no
  audio strip. The audio strip is built only from stored `start_ms` and `end_ms`.

### Re-run (local Qdrant, exact cache off, 2026-10-05)

Original 8/8 renderings, checked against the stored payloads: **0 of 7 quotes verified,
3 cross-case conflicts.** Case 7 has no quote. `y2ZgKdt4Cj0` is in no local collection.
Case 1's `t=280s` lies past the end of `4eV8OvVEm6A` (205.7 s).

Through `FirstPersonPipeline.execute` with production settings, all 8 cases abstain
(7 abstained, case 7 crisis_redirect). Every retrieved clip fails the existing
boundary guard, mostly with `tail_no_terminal`. Without a running Redis the
answerability gate also fails closed (budget ledger unavailable). No quote was
rendered, so nothing was there to verify.

A diagnostic run turned the boundary guard off and forced answerability to YES.
It is **not** a production result. Cases 1–6 served 19 clips. `quote_fidelity_check`
verified 19 of 19, and a raw byte-equality check confirmed every rendered body,
speaker and start second against its `first_person_v7` point. That proves fidelity
only, not relevance: case 3's clips do not answer the question.

### Not fixed

- Fidelity is checked against the store. The store's own diarised `speaker` and
  `teacher_id` are unaudited (see `docs/attribution/README.md`).
- `first_person_v7` has no titles, so every hero link reads "Watch on YouTube".
- The boundary guard currently quarantines most top clips for these queries. That
  is a data and segmentation issue upstream of this gate.
