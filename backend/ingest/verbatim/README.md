# `ingest/verbatim/` — shared first-person verbatim ingestion

Ports the offline pilot scripts
(`~/mukthiguru_attribution_data/pilot50_2026-09-25/run_vote.py`,
`run_speaker.py`, `run_clips.py`, `run_punct.py`) into small, testable stage
functions plus one resumable orchestrator, so **production ingestion**
produces the same verified verbatim clips the pilot proved out on 50+8
videos — not a one-off script only one person can re-run.

Two layers, per `backend/CLAUDE.md`'s #1 priority: a **verbatim layer**
(`transcript.json` — per-word ASR text, nothing ever cleans it) and a
**derived display layer** (`punct.json` — punctuation/truecasing for
rendering), kept separate so a served quote can always be checked as an exact
substring of the verbatim layer.

ASR itself (Whisper/Parakeet) is **out of scope** here — this module starts
from already-produced ASR word lists (`whisper_json`/`parakeet_json`, each
`{"ok": bool, "words": [{"w", "start", "end", ...}]}`). Wiring a live ASR step
in front of this pipeline is future work (see "Not yet wired" below).

## Stages

| Module | Function | Input | Output | Gate |
|---|---|---|---|---|
| `vote.py` | `vote_stage(a_words, b_words)` | two ASR word lists (whisper=A, parakeet=B) | ROVER-voted words (tagged `disputed`/`alt`) + agreement rate, WER, hallucination-span flags, doctrine-glossary hit counts | — |
| `gates.py` | `check_asr_agreement(vote_result)` | a `vote_stage` result | `None` (clears the gate) or a quarantine reason string | `agreement_rate >= 0.80` (`MIN_ASR_AGREEMENT`) |
| `speaker_verify.py` | `verify_speakers(wav, voiceprints, thresholds, embedder=...)` | audio path + enrolled voiceprints | per-window teacher label (`P`/`K`/`O`/`?`) + time-share breakdown | ECAPA-cluster match to an enrolled voiceprint (`scripts/ops/speaker_attribution.py`, imported not copied) |
| `speaker_verify.py` | `label_words_by_speaker(voted_words, t_centres, win_lab)` | voted words + speaker windows | per-word `spk` label | nearest-window snap (1.5s) + isolated-flicker trim (0.5s) |
| `clips.py` | `clips_stage(voted_words, t_centres, win_lab, video_id, **kw)` | voted words + speaker windows | sentence-bounded teacher clips (host/questioner turns excluded) | `services.speaker_diarization.build_clips_from_labelled_words` (imported, owned by another agent — never copied) |
| `punctuation.py` | `punctuate_stage(voted_words, model=...)` | voted (verbatim) words | display-layer words + `zero_change_assert_passed` | strict **zero word change**: display normalises identically to verbatim, or the stage flags the diff rather than silently serving a mismatch |

Every model call (ECAPA speaker embedding, the ONNX punctuation-restoration
model) sits behind an injectable interface (`speaker_verify.Embedder`,
`punctuation.Punctuator`) so every stage's tests run on synthetic fixtures —
no model ever loads in `pytest`.

## Orchestrator

`pipeline.run_verbatim_pipeline(video_id, paths: VerbatimPaths, cfg: VerbatimConfig | None)`:

```
vote -> asr_agreement gate (recorded, not a hard stop)
     -> speaker_verify -> clips
     -> punctuation
```

The agreement gate is recorded in the returned summary
(`asr_agreement_gate_reason`) but does not block the other stages — matching
the pilot, where the gate is applied downstream at index-build time
(`scripts/ops/build_first_person_index.py`), not at clip-build time.

**Resumability**: each stage's checkpoint key is `verbatim:<video_id>:<stage>`,
tracked via the existing `ingest.handlers.checkpoint.IngestionCheckpoint`
(Redis → Supabase → local-JSON fallback, same as the rest of ingestion — no
new checkpoint format). A stage already marked processed is skipped and its
prior output reloaded from `VerbatimPaths` instead of recomputed, so a crash
mid-video resumes from the last completed stage rather than re-running
everything (including any model calls).

## Verification (no models, no writes)

```bash
cd backend
.venv/bin/pytest -q tests/test_verbatim_vote.py tests/test_verbatim_speaker_verify.py \
    tests/test_verbatim_clips.py tests/test_verbatim_punctuation.py \
    tests/test_verbatim_gates.py tests/test_verbatim_pipeline.py
```

Each module also runs a self-check standalone: `.venv/bin/python -m ingest.verbatim.<module>`.

## Not yet wired

This module is not called from `ingest/pipeline.py` yet. Wiring it in means:
deciding where a live ASR step (Whisper/Parakeet) produces
`whisper_json`/`parakeet_json` per video during ordinary ingestion (today only
the offline pilot scripts produce these), and deciding whether
`scripts/ops/build_first_person_index.py` should read this module's output
paths directly or keep reading `passages_B`/`transcripts_B` from the pilot
layout. Both are product/ops decisions, not a code gap in this module.
