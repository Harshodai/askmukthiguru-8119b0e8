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
