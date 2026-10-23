# First-person v10 — Phase 3 evidence report (ASR coordinates and audio windows)

**Date:** 2026-10-21
**Plan:** `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
**Release verdict after this run:** **NO-GO (unchanged).**
`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** in the
running container. Phase 2 was **not** started. No Qdrant, Redis, alias,
environment, Docker-volume, Railway or production change was made.

Machine-readable companions:

| File | What it holds |
|---|---|
| `audits/evidence/public_release_phase3_summary_2026-10-21.json` | Phase-3 summary under the default `exact` reconstruction policy |
| `audits/evidence/public_release_phase3_summary_coverage_2026-10-21.json` | The same run under `coverage` (comparability only) |
| `audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl` | 1,600 candidate spans (sha256 `5806658e…`) |
| `audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl` | 1,137 quarantined spans (sha256 `3f4b64fd…`) |
| `audits/evidence/public_release_phase3_variants_2026-10-21.jsonl` | 1,127 transcription-variant spans (sha256 `27840df4…`) |
| `audits/evidence/public_release_phase3_parents_2026-10-21.jsonl` | 1,106 rebuilt parent units (sha256 `9d571bd8…`) |
| `audits/evidence/public_release_phase3_candidate_coverage_2026-10-21.jsonl` | 2,661 candidates under the coverage policy |
| `audits/evidence/public_release_phase3_verification_2026-10-21.txt` | Every command, cwd, start/end time and **real exit code** |

Implementation:

| File | Purpose |
|---|---|
| `backend/scripts/ops/rebuild_v10_asr_coordinates.py` | Read-only rebuild + validator. sha256 `2a884e61acf63f3d…` |
| `backend/tests/test_rebuild_v10_asr_coordinates.py` | 24 focused tests. sha256 `e19835cd1edaa6fb…` |
| `backend/scripts/ops/run_public_release_phase3_verification.sh` | Transcript runner. sha256 `720fc35c3482a510…` |

---

## 1. Root cause (measured, not assumed)

The live v10 collection was built from **two different transcripts**:

* `build_full_corpus_v10.py::parse_transcript` took the **text** from the
  markdown *display* transcript (`transcripts/{video_id}.md`, casing and
  punctuation restored, 763 files);
* `build_full_corpus_v10.py::get_word_timings` took the **timings** from the
  *voted* word-timed artifact (`transcripts_B/{video_id}.json`, identical to
  `raw/{video_id}_voted_words.json` plus a `spk` label).

The two layers disagree in wording — dropped words, duplicated words,
homophones (`nati shastra` / `natya shastra`), restored casing. When the word
counts differed, the builder aligned them with a whole-file `SequenceMatcher`
(`_align_words_to_timings`), so the recorded `word_start`/`word_end` belong to
the *display* layer while the millisecond offsets belong to the *voted* layer.
The payload therefore indexes neither consistently, which is the direct cause
of **B2** (298 citation-window failures) and **B3** (2,107 word-coordinate
disagreements, 41 out of range).

A second, structural defect was found while inspecting the archive: for the
1,838 children inherited from the legacy v9 lineage,
`build_fp_context_from_v9.py` copies `transcript_hash` **from the legacy clip
payload**, where it is a *clip-level* hash (`sha256(verbatim_text)`), not the
video-level transcript identity the fp-context-v1 contract documents. 313 of
485 videos therefore carry more than one distinct `transcript_hash`, and the
deterministic span id for those spans is derived from a clip hash rather than
from a source transcript.

## 2. The rebuild

Coordinate space **`fp-coords-v1`**, normalization **`fp-norm-unicode-v1`**:

* the source of truth is the immutable word-timed artifact
  `transcripts_B/{video_id}.json` — its sha256 is the rebuilt
  `transcript_hash`, and it is the artifact the timings come from;
* `word_start` / `word_end` are indices into **that artifact's word list**;
* `audio_start_ms` / `audio_end_ms` are the min/max of the artifact's own word
  timings over `[word_start, word_end)` — never spread across the WAV
  duration, never copied from the legacy v9 clip store;
* the span text is the artifact's own words in that range, and
  `source_text_hash` is `sha256` of exactly that text;
* `source_span_id` is `make_source_span_id(guru_id, video_id,
  corpus_version, word_start, word_end, transcript_hash)` — the contract's own
  helper, re-derived and asserted on every row;
* parent units keep the live *grouping* (which spans belong together is a
  serving decision, Phase 5) but their identity and window are re-derived
  from the rebuilt children.

The normalizer is Unicode-aware (NFKC, Unicode-category aware). Letters of any
script survive, so Devanagari and Urdu spans are tokenized and validated
instead of being erased by an ASCII-only filter.

**Corpus version.** The rebuilt candidate declares
`corpus_version = fp-context-transcript-v2`. This is required, not cosmetic:
**502 of the 1,600 candidate spans would collide with a live v10 span id** if
the live corpus version were reused, because the coordinate space and the
transcript identity both change. The new corpus version makes a collision
impossible by construction.

## 3. Before / after

Every "before" figure is measured on the live payload with the same validators
the rebuild uses; every "after" figure is measured on the rebuilt candidate.

| Measure | Before (live payload) | After (rebuilt candidate) |
|---|---|---|
| v10 children | 2,737 | 1,600 admitted (1,127 variants quarantined) |
| **valid coordinates** | 2,696 | **1,600 / 1,600** |
| **invalid coordinates** | **41** | **0** |
| **valid audio windows (ordered, inside the archived audio)** | 2,737 | **1,600 / 1,600** |
| **out-of-bounds windows (past the archived WAV)** | **0** | **0** |
| **windows past the ASR-aligned extent** | **18** | **0** |
| **no-overlap windows (zero token coverage)** | **13** | **0** |
| audio-window coverage failures | 302 | **0** |
| **multilingual / unverifiable by the ASCII checker** | **2** | **0** (2 tokenized and validated) |
| **deterministic id mismatches** | 0 | **0** |
| coordinates changed vs live | — | 1,098 / 1,600 |
| `transcript_hash` changed vs live | — | 1,600 / 1,600 |
| rebuilt text hash identical to the live one | — | 1,248 / 1,600 |
| **quarantined spans** | — | **1,137** |
| rebuilt parent units | 1,460 live | 1,106 (354 live parents fully quarantined) |

Baseline reproduction (all three are pinned by tests against the real
artifacts, using the strict audit's own helpers):

| Known defect | Expected | Measured |
|---|---|---|
| Audio-window coverage failures (`audit_first_person_v10_strict`) | 298 (+2 unverifiable) | **298 + 2** |
| Citations past the ASR-aligned audio extent | 18 | **18** |
| Word coordinates past the end of the transcript | 41 | **41** |

### A correction to the "18 beyond-audio" label

The prior report described 18 spans as citing "past the end of the archived
audio". That is **not** what the number measures. Measured against the
**complete archived WAV** (`audio_archive/wavs/*.wav`, which is what exists on
disk), **0** spans cite past the audio: the cited end never exceeds the file
duration. The 18 are spans whose cited window runs past the **ASR-aligned
extent** — the last aligned word of the word-timed artifact. The audio file
contains trailing material with no aligned words; a citation that reaches into
it points at audio whose transcript is not covered. Both numbers are reported
in the summary (`within_archived_audio` and `beyond_asr_aligned_extent`) so the
distinction is explicit.

### The archived audio is in `audio_archive/wavs`, not in the ASR roots

`mass_ingest_2026-10/audio/*.wav` are **86-byte header-only stubs**: a valid
RIFF/WAVE header that declares the correct duration with **no PCM data behind
it**. 515 of 516 files in that directory are stubs (8 of 50 in
`pilot50_2026-09-25/audio`). The complete audio lives in
`audio_archive/wavs/` (680 files), which covers **485 / 485** v10 videos.

The rebuild resolves the audio in that order and **rejects a stub**: the
declared duration of a stub exists, but there is no audio behind it, so using
it would justify a citation window and an ECAPA slice that point at nothing.
A dedicated test writes a header-only stub and asserts the span is quarantined
with `archived_audio_truncated`. **Phase 2 must slice from
`audio_archive/wavs/`, not from `<asr_root>/audio/`.**

## 4. Why 1,137 spans are quarantined

| Reason | Spans | What it means |
|---|---|---|
| `reconstruction_variant_not_exact` | 1,127 | The span text came from the display transcript and the voted timing artifact words it differently (dropped/duplicated words, homophones, casing). The rebuilt window covers the span's words at ≥ 0.90, but the reconstruction is not byte-exact under `fp-norm-unicode-v1`. |
| `audio_window_coverage_below_floor` | 66 | The rebuilt window covers the span text at < 0.90. These are also variants. |
| `span_not_located_in_asr` | 10 | The span's text does not occur in the timed artifact at all. 8 are multilingual/garbled (Urdu, Devanagari, mixed-script); 2 have a live word range that runs past the end of the artifact (the display transcript is longer than the voted artifact). |

The 1,127 variants have a reconstruction ratio distribution of
min 0.40 / p10 0.923 / p50 0.989 / p90 1.000 — i.e. most are one dropped or
duplicated word away from an exact reproduction, but a documented minority are
not.

### The `coverage` policy (comparability only)

`--reconstruction-policy coverage` admits a variant whose rebuilt window
covers the span text at or above the floor, flagged
`transcription_variant: true`:

| Policy | Candidate | Exact | Variant admitted | Quarantined | Rebuilt parents |
|---|---|---|---|---|---|
| `exact` (default) | 1,600 | 1,600 | 0 | 1,137 | 1,106 |
| `coverage` | 2,661 | 1,600 | 1,061 | 76 | 1,456 |

The default is fail-closed: a span whose text is not exactly reproducible from
the timing artifact does not enter the candidate. The coverage run is provided
so the owner can see the size of the relaxation before deciding; it is **not**
release evidence.

## 5. Commands run and exit codes

Every command below is in
`audits/evidence/public_release_phase3_verification_2026-10-21.txt` with its
cwd, start/end time and real exit code.

| Phase | Command (cwd) | Exit |
|---|---|---|
| 3 | `backend/.venv/bin/python -m py_compile backend/scripts/ops/rebuild_v10_asr_coordinates.py` (repo root) | **0** |
| 3 | `backend/.venv/bin/python -m pytest tests/test_rebuild_v10_asr_coordinates.py -q …` (`backend/`) | **0** — 24 passed |
| 3 | `backend/.venv/bin/python backend/scripts/ops/rebuild_v10_asr_coordinates.py --help` (repo root) | **0** |
| 3 | rebuild, default `exact` policy (repo root) | **1** — documented release-blocking status |
| 3 | rebuild, `coverage` policy (repo root) | **1** — documented release-blocking status |
| 3 | determinism repeat with pinned `--generated-at-utc` (repo root) | **1** — release-blocking status |
| 3 | `cmp` of candidate / quarantine / parents / variants against the repeat run (repo root) | **0** — all four byte-identical |
| 3 | `backend/.venv/bin/python -m ruff check scripts/ops/rebuild_v10_asr_coordinates.py tests/test_rebuild_v10_asr_coordinates.py` (`backend/`) | **0** |
| 3 | `backend/.venv/bin/python -m pytest tests/test_repo_layout.py -q …` (`backend/`) | **0** — 3 passed |
| 3 | `git diff --check` (repo root) | **0** |
| 3 | focused first-person suite, 11 modules (`backend/`) | **0** — 181 passed, 1 skipped |
| — | `backend/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider --no-header -rf --tb=line` (`backend/`) — full regression suite | **0** — **10,733 passed**, 25 skipped, 2 deselected, 3 xfailed, 0 failed (162.82 s) |

Exit-code contract: `0` = report produced, nothing blocking; `1` = report
produced and release-blocking; `2` = no trustworthy report (unreadable input,
duplicate record ids, or a refused write mode — `--apply-to-qdrant` is
rejected and the script has no Qdrant client at all).

## 6. Mutations

**None.**

* No Qdrant write, upsert, delete, alias, snapshot or collection change. The
  rebuild reads the v10 children from a file export; the script imports no
  Qdrant client and has no write path.
* No Redis operation.
* No environment change: `backend/.env` and the container both still carry
  `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`.
* No alias change: `first_person -> first_person_v10` unchanged; the live
  collection is still 4,197 points, green, 2,737 indexed vectors.
* No Docker volume operation, no container recreate, no deployment; Railway
  untouched.
* No source manifest mutated (asserted by test).
* Git: no reset, clean, checkout, stash, commit or push.

Files **created** by this run (all additive):

```
backend/scripts/ops/rebuild_v10_asr_coordinates.py
backend/scripts/ops/run_public_release_phase3_verification.sh
backend/tests/test_rebuild_v10_asr_coordinates.py
audits/evidence/public_release_phase3_summary_2026-10-21.json
audits/evidence/public_release_phase3_summary_coverage_2026-10-21.json
audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl
audits/evidence/public_release_phase3_candidate_coverage_2026-10-21.jsonl
audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl
audits/evidence/public_release_phase3_quarantine_coverage_2026-10-21.jsonl
audits/evidence/public_release_phase3_variants_2026-10-21.jsonl
audits/evidence/public_release_phase3_parents_2026-10-21.jsonl
audits/evidence/public_release_phase3_verification_2026-10-21.txt
audits/evidence/public_release_phase3_report_2026-10-21.md      (this file)
```

## 7. Blocker status after Phase 3

| Blocker | Status |
|---|---|
| **B1** per-span ECAPA evidence | **Still open.** Phase 3 produced trustworthy audio windows for the candidate spans, which is the precondition Phase 2 needs. No acoustic measurement was made. |
| **B2** citation ↔ audio window | **Measured and fixed in the candidate.** Live: 302 coverage failures, 13 zero-coverage, 18 past the ASR-aligned extent. Rebuilt candidate (1,600 spans): 0 / 0 / 0. The live collection is untouched, so the *live* defect stands until the candidate is applied — that application is not authorised here. |
| **B3** deterministic span-id word coordinates | **Measured and fixed in the candidate.** Live: 41 invalid, 2,107 disagreeing. Rebuilt candidate: 0 invalid, 0 id mismatches. 1,098 of 1,600 candidates have different word coordinates from the live payload. |
| **B4** legacy/context schema conflation | Still open (Phase 5). Additionally surfaced: the live `transcript_hash` is clip-level for the 1,838 v9-lineage children and video-level for the 899 full-corpus children. |
| **B5** independent rights register | Still open. The rebuilt candidate carries the live `rights_cleared` flag; it is **not** independently verified and must not be treated as cleared. |
| **B6** distress boundary | Still open — clinician decision outstanding; nothing tuned here. |
| **B7** gold labels / public-scale evidence | Still open. |

**Overall: NO-GO.** The harness stays disabled.

## 8. What Phase 2 needs, and what it must not assume

Phase 2 may now start **only with owner approval**, and only against the
rebuilt candidate's audio windows — never against the live payload's offsets.

1. **Slice from `audio_archive/wavs/`**, not from `<asr_root>/audio/`. The
   latter holds header-only stubs for 515 / 516 files.
2. **Use the rebuilt candidate's `[audio_start_ms, audio_end_ms]`**, not the
   live payload's. 1,098 of 1,600 candidates have different word coordinates,
   and the live offsets are the ones with the 302 coverage failures.
3. **The calibration archive must be regenerated.** The archived
   `speaker_verdicts.json` has no `cosine_floor` and no `calibration_available`,
   and its threshold is the p01 of *correct*-clip margins rather than an
   impostor-measured floor.
4. **`soundfile` is still absent** from `backend/requirements.txt` /
   `requirements.lock` and from the runtime image. The host venv has it
   (0.14.0) but the release image does not; it must go through the repository's
   normal dependency process.
5. **Only the 1,600 exact-reconstruction spans are Phase-2 ready** under the
   default policy. If the owner wants the 1,061 admitted variants verified
   too, that is a policy decision, not a code decision.
6. **The candidate has not been written anywhere.** Applying it needs its own
   authorisation, a Qdrant snapshot, and a corpus-version-isolated collection
   (the live alias must not be repointed at a `fp-context-transcript-v2`
   collection while Phase 1's speaker evidence is still open).

## 9. Honest limits of this report

* The candidate covers **1,600 of 2,737** spans under the default policy. The
  remaining 1,137 are not "fixed but hidden" — they are quarantined with a
  reason, and 1,127 of them are quarantined because the corpus's text and its
  timings come from two different transcripts. That is a corpus-level defect
  with an owner decision attached (rebuild the text from the voted layer, or
  accept the variant tier).
* The rebuilt audio windows are **trustworthy as windows**, not as evidence:
  nothing here measures whether the voice in the window is the teacher.
* The "18 beyond-audio" figure was relabelled after measurement; the prior
  report's wording was wrong, and the corrected definition is now stated in
  the summary and pinned by a test.
* Phase 2 has not started. B1 is measured and unchanged.

---

## 10. Final evidence verification — 2026-10-22

Machine-readable companion:
`audits/evidence/public_release_phase3_final_verification_2026-10-22.json`
(sha256 `0340fa4e1a0fcd92…`), produced by re-deriving every number from the
artifacts on disk.

### 10.1 Authoritative ASR / timing artifacts

| Item | Value |
|---|---|
| Artifact kind | word-timed transcript (the voted ASR layer) |
| Artifact path pattern | `<attr-root>/<root>/transcripts_B/{video_id}.json` |
| Roots used | `mass_ingest_2026-10` (448 files), `pilot50_2026-09-25` (37 files) |
| Artifacts used | **485** (one per v10 video) |
| Root manifest digest, `mass_ingest_2026-10` | sha256 `b63068da565b7a967752bb3c3b856a73b273d9ddd358765d3034c40cef17b9db` (448 files) |
| Root manifest digest, `pilot50_2026-09-25` | sha256 `2ffed5b74db9d50fc41ecff679a48f1c3633692754191d8f025d35a3dd5f9ac8` (37 files) |
| ASR engine / model | `parakeet-tdt-0.6b-v3` on **485 / 485** artifacts |
| Alignment artifact | `raw/{video_id}_align.json`, `ok=true` on **485 / 485** |
| Normalization version | **`fp-norm-unicode-v1`** (Unicode-aware; NFKC → lowercase → number-join → hyphen/slash to space → smart quotes dropped → Unicode-category punctuation to space → whitespace collapsed) |
| Coordinate space version | **`fp-coords-v1`** (`word_start`/`word_end` index the timed artifact's own word list) |
| Corpus version declared | **`fp-context-transcript-v2`** |
| Audio source | `audio_archive/wavs/{video_id}.wav`, **complete** (declared data bytes present in file) for 2,737 / 2,737 live spans and 1,600 / 1,600 candidate spans |

Each artifact's own sha256 is recorded per row as `timed_transcript_sha256`
and is re-checked against the file on disk in §10.3.

### 10.2 Before / after over all 2,737 v10 children

| Measure | Before (live payload) | After (rebuilt candidate) |
|---|---|---|
| total children | 2,737 | 2,737 accounted (1,600 candidate + 1,137 quarantined) |
| valid word coordinates | 2,696 | **1,600 / 1,600** |
| out-of-range coordinates | **41** | **0** |
| deterministic span-id mismatches | 0 | **0** |
| valid audio windows (ordered, inside the complete WAV) | 2,737 | **1,600 / 1,600** |
| audio-end violations (past the archived WAV) | **0** | **0** |
| windows past the ASR-aligned extent | **18** | **0** |
| no-overlap windows (zero token coverage) | **13** | **0** |
| audio-window coverage failures | 302 | **0** |
| multilingual / unverifiable by the ASCII checker | **2** | **0** (2 tokenized and validated) |
| quarantined spans | — | **1,137** |
| rebuilt parent units | 1,460 live | 1,106 (354 live parents fully quarantined) |
| parent ids that re-derive | — | **1,106 / 1,106** |

Quarantine reasons: `reconstruction_variant_not_exact` 1,127,
`audio_window_coverage_below_floor` 66, `span_not_located_in_asr` 10.

### 10.3 Reproduction matrix — every surviving span, every field

All **1,600** candidate spans were re-checked independently of the rebuild
against the artifact on disk. **Zero failures on all eleven checks:**

| Check | Result |
|---|---|
| exact source text reproduces (normalized) | **1,600 / 1,600** |
| exact source-text hash (`sha256` of the reconstruction) | **1,600 / 1,600** |
| `word_start` / `word_end` in range and ordered | **1,600 / 1,600** |
| `audio_start_ms` / `audio_end_ms` equal the artifact's own word timings | **1,600 / 1,600** |
| deterministic `source_span_id` re-derives | **1,600 / 1,600** |
| `transcript_hash` equals the artifact's sha256 | **1,600 / 1,600** |
| recorded `timed_transcript_sha256` matches the file on disk | **1,600 / 1,600** |
| audio window inside the complete archived WAV | **1,600 / 1,600** |
| audio window ordered (`end > start`) | **1,600 / 1,600** |
| cited window covers the span text (≥ floor) | **1,600 / 1,600** |
| no WAV-duration synthesis (window is artifact-derived, not a duration spread) | **1,600 / 1,600** |

Additionally: rebuilt span ids are **unique** (1,600 / 1,600), rebuilt parent
ids **re-derive** (1,106 / 1,106), and all **2,737** live span ids are
accounted for (candidate + quarantine + variants).

Two leakage checks on the rebuilt values: **502** candidates keep the live
payload's word coordinates and **1,266** keep the live payload's audio window
— the window is right far more often than the word index is. No rebuilt
coordinate or window was copied from the legacy v9 clip store; every value is
derived from the timed artifact.

### 10.3.1 The coverage-policy set, checked the same way

For completeness, the 2,661 spans admitted under the relaxed `coverage` policy
were checked identically: **0** failures on word range, source-text hash,
audio window derivation, audio bounds, window ordering, window coverage,
deterministic span id and artifact-hash identity — and **1,061 failures on
`exact_source_text`**, which is precisely the defect that makes them
variants. Under the default `exact` policy those 1,061 are quarantined, so the
shipped candidate reproduces exactly on every one of its 1,600 spans.

### 10.4 Two independent rebuilds are byte-identical

Two fresh runs of the rebuild script, separate output paths, pinned
`--generated-at-utc`:

| Artifact | Run A | Run B | Shipped evidence package |
|---|---|---|---|
| candidate.jsonl | `5806658e5a714aba…` | `5806658e5a714aba…` | `5806658e5a714aba…` |
| quarantine.jsonl | identical | identical | identical |
| parents.jsonl | identical | identical | identical |
| variants.jsonl | identical | identical | identical |
| summary.json | `54fde255d7ece90f…` | `54fde255d7ece90f…` | — |

`cmp` is clean on every pair; both runs also match the shipped package
byte-for-byte.

### 10.5 Test commands and exit codes (re-run 2026-10-22)

| Command (cwd) | Exit | Result |
|---|---|---|
| `backend/.venv/bin/python -m py_compile backend/scripts/ops/rebuild_v10_asr_coordinates.py` (repo root) | 0 | compiles |
| `backend/.venv/bin/python -m pytest tests/test_rebuild_v10_asr_coordinates.py -q -p no:cacheprovider --no-header -rf --tb=short` (`backend/`) | 0 | **24 passed**, 0 failed, 0 skipped |
| `backend/.venv/bin/python -m pytest tests/test_reconcile_v10_ecapa_verdicts.py -q …` (`backend/`) | 0 | **28 passed**, 0 failed, 0 skipped |
| `backend/.venv/bin/python -m pytest tests/test_repo_layout.py -q …` (`backend/`) | 0 | **5 passed**, 0 failed, 0 skipped |
| `backend/.venv/bin/python -m ruff check scripts/ops/rebuild_v10_asr_coordinates.py tests/test_rebuild_v10_asr_coordinates.py scripts/ops/reconcile_v10_ecapa_verdicts.py tests/test_reconcile_v10_ecapa_verdicts.py` (`backend/`) | 0 | All checks passed |
| `git diff --check` (repo root) | 0 | clean |
| rebuild, `exact` policy (repo root) | 1 | documented release-blocking status |
| rebuild, `coverage` policy (repo root) | 1 | documented release-blocking status |
| two independent rebuilds + `cmp` (repo root) | 0 | byte-identical |
| `backend/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider --no-header -rf --tb=line` (`backend/`) — full regression suite | 0 | **10,735 passed**, 25 skipped, 2 deselected, 3 xfailed, **0 failed** (164.01 s) |

### 10.6 Artifact locations and hashes

| Artifact | Path | sha256 |
|---|---|---|
| Rebuild script | `backend/scripts/ops/rebuild_v10_asr_coordinates.py` | `2a884e61acf63f3d280b06cf9c39dd13142cc4c95ebcc6a670c6f5bbe15b5c95` |
| Tests | `backend/tests/test_rebuild_v10_asr_coordinates.py` | `e19835cd1edaa6fb576873d7adef9c3577e1129f7f97bf8e1ec486d2370ddd24` |
| Verification runner | `backend/scripts/ops/run_public_release_phase3_verification.sh` | `720fc35c3482a5101cf0390b1a2bcc3e8e938eb4de8b13d4ba58a1dd458f361f` |
| Summary (`exact`) | `audits/evidence/public_release_phase3_summary_2026-10-21.json` | `16a27cdf60fcc2bebc30aa2b8cb51c033bc8c08862703414d5457042e43f070b` |
| Summary (`coverage`) | `audits/evidence/public_release_phase3_summary_coverage_2026-10-21.json` | `9cf934907d7d25ea3d9dd195855f3c0fc3cf0a157ac212432e5e943c1de945ed` |
| Candidate spans (1,600) | `audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl` | `5806658e5a714aba88902202508fb6f3db027eb6b8e8944e226d00c5545114bc` |
| Quarantined spans (1,137) | `audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl` | `3f4b64fd75a0e9fd9572d2db8dbd1fd17225d0b66f14373dbd72e8fce7991700` |
| Transcription variants (1,127) | `audits/evidence/public_release_phase3_variants_2026-10-21.jsonl` | `27840df4fda1e1b7c599d77787e2232adce253771ef1ae147004243899141a8e` |
| Rebuilt parent units (1,106) | `audits/evidence/public_release_phase3_parents_2026-10-21.jsonl` | `9d571bd8fabb9ca3997de5df7eaebec480fdfb3619c9f6064f7325f54c3b2b58` |
| Candidate (`coverage`, 2,661) | `audits/evidence/public_release_phase3_candidate_coverage_2026-10-21.jsonl` | `f010e5ad3066dc343e6dbb0a00fff4e4528d8809455f5a7efab49eab27048693` |
| Quarantine (`coverage`, 76) | `audits/evidence/public_release_phase3_quarantine_coverage_2026-10-21.jsonl` | `5ab7450d9deae4766429c3919dea1662efd597bec6a7b7201ee777cb90c8b743` |
| Final verification JSON | `audits/evidence/public_release_phase3_final_verification_2026-10-22.json` | `0340fa4e1a0fcd92912a98730ca3ff5cd01b764a91dd747e33aaefacaaf79f65` |
| v10 children export (input) | `audits/evidence/public_release_v10_points_export_2026-10-21.json` | `d8dc2e9ccf86a4ee3221d88b575aa5b73dbd7a93b47c4147f724d1be9a407955` |
| Command/exit-code transcript | `audits/evidence/public_release_phase3_verification_2026-10-21.txt` | `a6b8a05d7958b645924635175514b785d64187eb8df72635a42f909c76618c0a` |
