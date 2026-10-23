# First-person v10 — Phase 2 evidence report (per-span ECAPA speaker evidence)

**Date:** 2026-10-22
**Plan:** `.claude/tasks/first-person-v10-phase2-ecapa-regeneration-2026-10-22.md`
**Overall public-release verdict after this run:** **NO-GO (unchanged).**
`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` and in the
running container. Phase 2 closes or **measures B1 only**. B4, B5, B6 and B7
and the final integration / safety / rollback gates remain open.

Machine-readable companions:

| File | What it holds |
|---|---|
| `audits/evidence/public_release_phase2_calibration_2026-10-22.json` | The regenerated calibration record (sha256 `0d044a45…`) |
| `audits/evidence/public_release_phase2_verdicts_2026-10-22.json` | 1,600 verdict rows **keyed by `source_span_id`** (sha256 `cef4c80e…`) |
| `audits/evidence/public_release_phase2_verdicts_2026-10-22.jsonl` | The same rows, one JSON object per line (sha256 `a654116d…`) |
| `audits/evidence/public_release_phase2_summary_2026-10-22.json` | Machine-readable Phase-2 summary (sha256 `21b066e7…`) |
| `audits/evidence/public_release_phase2_verification_2026-10-22.txt` | Every command, cwd, start/end time and **real exit code** (sha256 `bf313818…`) |

Implementation:

| File | Purpose | sha256 |
|---|---|---|
| `backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py` | Read-only generator. No Qdrant client, no write mode. | `9d1b1c44…` |
| `backend/tests/test_regenerate_v10_span_ecapa_verdicts.py` | 49 focused tests. | `d58afbff…` |
| `backend/scripts/ops/run_public_release_phase2_verification.sh` | Transcript runner. | `faa5d7b3…` |

---

## 1. What Phase 2 produced

| Measure | Value |
|---|---|
| Exact candidate spans requested | **1,600** |
| Verdict rows emitted | **1,600** (one per span, none omitted) |
| Output keyed by | **`source_span_id`** for every row (never a legacy v9 point id) |
| Quarantined spans excluded | **1,137 rows** (1,127 with a rebuilt id, 10 with none, 1,126 unique ids) |
| Verified | **1,529** |
| Refused — guru mismatch | **45** |
| Refused — below cosine floor | **26** |
| Refused — below margin | 0 |
| Missing / invalid / out-of-bounds / too short / not run | **0 / 0 / 0 / 0 / 0** |
| Calibration available | **true** |
| Positive trials (calibration / test) | **267 / 262** |
| Impostor trials (calibration / test) | **267 / 262** |
| False accepts (test split, held out) | **0 / 262 → 0.0** |
| False rejects (test split, held out) | **0 / 262 → 0.0** |
| `cosine_floor` | **0.282826** |
| `margin_threshold` | **1e-06** |
| Audio files opened | **447** (every video the candidate touches) |
| Audio slices generated | **1,600** (all from `audio_archive/wavs/`) |
| Model | `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` (device `mps`) |
| Calibration revision | `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e` |
| Run id (deterministic input manifest hash) | `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977` |

Verdicts per split (the split is by **video**, so a held-out video is never in
the reference and never in the calibration):

| Split | Spans | Verified | Below floor | Guru mismatch |
|---|---|---|---|---|
| train | 1,002 | 941 | 16 | 45 |
| calibration | 306 | 297 | 9 | 0 |
| test | 292 | 291 | 1 | 0 |

The 45 guru mismatches are all in the train split: those spans were used to
build the reference centroids, so they are the ones whose corpus assignment
the acoustic evidence contradicts.

## 2. Method

### 2.1 The reference is human-grounded, not payload-derived

The repository's only human ground truth for speaker identity is the pair of
anchor moments recorded in `backend/scripts/ops/speaker_attribution.py`:

```python
ANCHORS = {"preethaji": ("hUmlujE6SN0", 563.0), "krishnaji": ("rGcNJ_Nsuy8", 386.0)}
```

Phase 2 recomputes those anchor voiceprints itself from
`audio_archive/wavs/<anchor video>.wav` with the **pinned** ECAPA revision, by
clustering the video's 2 s windows (cosine distance 0.6, average linkage) and
averaging the cluster the confirmed moment belongs to — the repository's own
recipe. Measured: 241 windows for Preethaji, 617 for Krishnaji, and an anchor
cross-cosine of **0.078** (the two teachers are acoustically far apart).

Nothing in the pipeline reads `speaker_verified`, a legacy v9 verdict, a
display label, a filename or a channel name as evidence.

`backend/scripts/ops/speaker_attribution.py` loads the same model **unpinned**
(`EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb")`).
Reusing it verbatim would break the binding HF-pin invariant
(`AGENTS.md` → *HF model pins*), so the recipe is re-implemented locally with
the pin and the deviation is recorded in the calibration artifact.

### 2.2 Splits

Videos are partitioned deterministically by `sha256("fp-phase2-split-v1|<video_id>")`
into **train 60 % / calibration 20 % / test 20 %** (274 / 91 / 82 videos). The
two anchor videos are forced into `train`: they seed the references, so they
can never be a held-out trial.

### 2.3 Calibration

* A held-out slice becomes a **trial** only when it clears `ANCHOR_LABEL_MIN`
  (0.55, the repository's `THRESHOLD_FLOOR`) against its anchor voiceprint and
  beats the other anchor by `ANCHOR_MARGIN` (0.15, the repository's `MARGIN`).
  39 calibration slices and 30 test slices were unlabeled and excluded.
* A **positive trial** is a labelled slice scored against its own guru's
  reference centroid; the same slice scored against the *other* guru's
  reference is an **impostor trial**.
* `cosine_floor` = strictly above the largest calibration-split impostor
  cosine (0.282825); `margin_threshold` = strictly above the largest
  calibration-split impostor margin, floored at zero (1e-06).
* The calibration-split false-accept rate is **0 by construction** (the floor
  sits above every observed impostor). The honest number is the held-out test
  measurement: **0 false accepts / 262 impostor trials, 0 false rejects / 262
  positive trials**.

Score distributions (cosine to the reference):

| Population | min | p01 | p05 | p50 | p95 | max |
|---|---|---|---|---|---|---|
| calibration impostor | 0.022 | 0.069 | 0.095 | 0.173 | 0.244 | **0.283** |
| calibration positive | **0.576** | 0.627 | 0.680 | 0.791 | 0.883 | 0.910 |
| test impostor | 0.046 | 0.075 | 0.090 | 0.166 | 0.225 | **0.289** |
| test positive | **0.569** | 0.598 | 0.659 | 0.781 | 0.886 | 0.935 |

The gap between the impostor maximum (0.289) and the positive minimum (0.569)
is the separation the floor is derived from.

### 2.4 Decision rule

`calibration_available` → `predicted_guru == expected_guru` →
`cosine >= cosine_floor` → `margin >= margin_threshold`. A guru mismatch
outranks the score gates: a span whose voice contradicts the corpus assignment
is refused even when it scores high.

**Honest note on the margin gate.** Every held-out impostor margin is negative
(max −0.365 on calibration, −0.422 on test), so the margin threshold collapses
to 1e-06 and the margin gate is a strict *ordering* requirement ("the predicted
reference must be the best one") rather than a *separation* requirement. The
separation evidence is in the cosine floor and in the distributions above. This
is recorded in the artifact's `decision_rule.margin_gate_note`.

## 3. The 71 refused spans — what they are

| Verdict | Count | Cosine range | What it means |
|---|---|---|---|
| `refused_guru_mismatch` | **45** | −0.024 … 0.841 | The voice contradicts the corpus assignment. 40 are `krishnaji → preethaji`, 5 are `preethaji → krishnaji`, across 11 videos. 25 of the 45 are in a single video (`MmiI3xo5Ju4`), 5 in `4LIZkNHlNaM`, 4 in `sCCLfLa0gyw`, 3 in `-i-QFyNg8Io`. This is the corpus's per-video teacher label being wrong — the 2026-09-26 voice census found 5 of the 10 individually/jointly labelled videos among the top 14 mislabelled. |
| `refused_below_cosine_floor` | **26** | −0.108 … 0.265 | The window does not sound like either teacher (host, translator, audience, music). 13 expected Krishnaji, 13 expected Preethaji, spread over 13 videos. |

These are the two failure modes the Phase-2 gate exists to catch, and both
fail closed: the span is **never** promoted to `verified`.

## 4. Dependency work — no change was required

`soundfile` is absent from `backend/requirements.txt`,
`backend/requirements.lock` and the runtime image. It is **not needed**:

* every file in `audio_archive/wavs/` is **16-bit PCM, mono, 16 kHz** (680/680
  verified), which the Python standard library `wave` module reads exactly;
* the slice reader parses the RIFF chunk list itself so it can compare the
  file size against the declared `data` chunk size and reject a header-only
  stub;
* `torch` (2.14.1) and `scikit-learn` (1.9.1) are already in
  `backend/requirements.lock`;
* `speechbrain` is **not** in the lock, so it is imported lazily inside the
  embedding function — the app import graph and the CI test suite never touch
  it, exactly as `backend/scripts/ops/speaker_attribution.py` already does.

**Result: `backend/requirements.txt` and `backend/requirements.lock` are
unchanged, no lock regeneration was run, the runtime image was not modified and
no service was recreated.** `git diff --check` on both files is clean.

If the owner later wants this runnable inside the release image, the change
would be `soundfile` (optional — the stdlib reader is enough) and `speechbrain`
(required), compiled with:

```bash
uv pip compile backend/requirements.txt --output-file backend/requirements.lock
git diff --check backend/requirements.txt backend/requirements.lock
```

That needs a separate approval because it changes the release artifact.

## 5. Commands run and real exit codes

Every command below is in
`audits/evidence/public_release_phase2_verification_2026-10-22.txt` with its
cwd, start/end time and real exit code.

| # | Command (cwd) | Exit | Result |
|---|---|---|---|
| 1 | `backend/.venv/bin/python -m py_compile backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py` (repo root) | **0** | compiles |
| 2 | `backend/.venv/bin/python -m pytest tests/test_regenerate_v10_span_ecapa_verdicts.py -q …` (`backend/`) | **0** | **49 passed**, 0 failed, 0 skipped |
| 3 | `backend/.venv/bin/python backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py --help` (repo root) | **0** | help |
| 4 | generation, shipped artifacts, pinned `--generated-at-utc 2026-10-22T00:00:00+00:00`, **cold embedding cache** (repo root) | **1** | documented release-blocking status; **1,600 slices embedded fresh** |
| 5 | determinism repeat, same pinned timestamp, warm cache (repo root) | **1** | documented release-blocking status; 1,600 slices reused from the cache |
| 6 | `cmp` of verdicts / verdicts-jsonl / calibration / summary against the repeat run (repo root) | **0** | **all four byte-identical** |
| 7 | verdict schema validation (`pytest -k "shipped or schema or verdict"`) (`backend/`) | **0** | 49 passed |
| 8 | `backend/.venv/bin/python -m ruff check scripts/ops/regenerate_v10_span_ecapa_verdicts.py tests/test_regenerate_v10_span_ecapa_verdicts.py` (`backend/`) | **0** | All checks passed |
| 9 | `backend/.venv/bin/python -m pytest tests/test_repo_layout.py -q …` (`backend/`) | **0** | 5 passed |
| 10 | `git diff --check` (repo root) | **0** | clean |
| 11 | Phase-3 regression tests (`tests/test_rebuild_v10_asr_coordinates.py`) (`backend/`) | **0** | 24 passed |
| 12 | reconciliation regression tests (`tests/test_reconcile_v10_ecapa_verdicts.py`) (`backend/`) | **0** | 28 passed |
| 13 | focused first-person suite, 11 modules (`backend/`) | **0** | 232 passed, 1 skipped |
| 14 | `backend/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider --no-header -rf --tb=line` (`backend/`) — full regression suite | **0** | **10,784 passed**, 25 skipped, 2 deselected, 3 xfailed, **0 failed** (162.86 s) |

Exit-code contract: `0` = report produced, nothing blocking; `1` = report
produced and **release-blocking** (the ordinary Phase-2 outcome — the harness
stays off); `2` = no trustworthy report (unreadable input, a duplicate span id,
a candidate/quarantine overlap, a schema failure, or a refused write mode —
`--write-to-qdrant` exits 2 and the script has no Qdrant client at all).

## 6. Required validation — per span and per artifact

Every check is enforced in code (`validate_row`) and re-run over the shipped
artifact by the test suite.

| Check | Result |
|---|---|
| The span exists in the exact Phase-3 candidate | 1,600 / 1,600 |
| The audio file exists and is a real PCM WAV | 1,600 / 1,600 (447 files, 0 stubs) |
| The audio window is inside the archived WAV | 1,600 / 1,600 |
| `audio_end_ms > audio_start_ms` | 1,600 / 1,600 |
| The slice uses the candidate coordinates | 1,600 / 1,600 (candidate `audio_start_ms` / `audio_end_ms` only) |
| The slice belongs to the right video | 1,600 / 1,600 (`audio_archive/wavs/{video_id}.wav`, sha256 recorded per file) |
| The expected guru is explicit and not a display label | 1,600 / 1,600 (registry ids only; `"Sri Krishnaji"` is rejected by the loader) |
| The calibration fields are finite and present | 1,600 / 1,600 |
| The verdict is reproducible from the recorded score and thresholds | 1,600 / 1,600 (recomputed and compared) |
| No verdict is emitted for a quarantined span | candidate ∩ quarantine = ∅ |
| The output is deterministic apart from the documented timestamp | two runs byte-identical |

## 7. Mutations

**None.**

* **Qdrant reads:** 0. **Qdrant writes:** 0. No upsert, no delete, no payload
  update, no `speaker_verified` change. The script imports no Qdrant client and
  has no write path; `--write-to-qdrant` is parsed and refused with exit 2. The
  only inputs are files on disk.
* **Collection creation / deletion:** 0.
* **Alias changes:** 0. `first_person → first_person_v10` unchanged; the live
  collection still carries its defective coordinates.
* **Redis:** 0 reads, 0 writes, 0 flushes.
* **Environment changes:** 0. `backend/.env` and the container both still carry
  `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`.
* **Docker images / containers / volumes:** 0.
* **Git:** no `reset`, no `clean`, no `checkout`, no `stash`, no commit, no
  push. (`git diff --check` and `git status` only.)
* **Railway / deployment:** 0. Railway stays paused.

```
No Qdrant write.
No alias change.
No Redis mutation.
No harness enablement.
No deployment.
No Railway action.
```

## 8. What Phase 2 does **not** prove — the honest limits

1. **The false-accept rate is not human-certified.** The trial labels come from
   the two human-confirmed anchor moments, and the reference centroids are
   widened from the same anchors, so the measured FAR/FRR is a *relative*
   consistency measurement on held-out videos, not an independent
   certification. The repository has no filled human speaker-label sheet
   (`docs/attribution/pilot_audit_60_quotes.csv`,
   `label_40clips_UlOt31lBhLY.csv` and `label_UlOt31lBhLY_15min.csv` all have
   blank speaker columns), so a human-certified FAR is **not available** and
   remains a **B7** dependency. Per the research report's own rule of three,
   even 0 errors in a 39-clip sheet would only bound the error at 7.4 %.
2. **The expected guru is a claim, not evidence.** It is the corpus
   assignment carried by the Phase-3 candidate. 45 spans contradict it
   acoustically, and those are refused, never verified. The corpus's per-video
   teacher label is itself unreliable (the 2026-09-26 voice census found 5 of
   its top 10 videos mislabelled).
3. **Nothing was written.** The candidate and the verdicts are file artifacts.
   The live v10 collection still carries the defective Phase-3 coordinates, and
   the `first_person` alias still points at it. Applying either needs its own
   authorisation, a snapshot and a corpus-version-isolated collection.
4. **The margin gate is an ordering gate**, not a separation gate (see §2.4).
5. **The 1,137 quarantined spans are still quarantined.** Phase 2 does not
   admit the 1,127 transcription variants or the 10 unlocatable spans; the
   variant tier needs a separate owner decision.
6. **Determinism is scoped to the recorded device.** The artifacts are
   byte-identical across two runs on the same host, model revision and device
   (`mps`). The embedding cache key includes the device, so a CPU run and an
   MPS run never mix.

## 9. Blocker status after Phase 2

| Blocker | Status |
|---|---|
| **B1** per-span ECAPA evidence | **Measured, and largely closed for the candidate.** 1,600 / 1,600 spans now have an auditable, span-keyed verdict with model revision, calibration revision, source span id, audio identity + sha256, start/end ms, cosine, runner-up, margin, floor, threshold and run id. 1,529 verified, 71 refused with an explicit reason. **Remaining B1 item:** a human-labelled held-out set to certify the false-accept rate (B7). |
| **B2** citation ↔ audio window | Fixed **in the candidate only** (Phase 3). The live collection is untouched. |
| **B3** deterministic span-id coordinates | Fixed **in the candidate only** (Phase 3). The live collection is untouched. |
| **B4** legacy / context-harness schema separation | **Open** (Phase 5). |
| **B5** independent rights register | **Open.** The candidate still carries the payload's `rights_cleared` flag; it is not independently verified. |
| **B6** distress boundary + clinician review | **Open.** Nothing was tuned. |
| **B7** gold labels / public-scale evidence | **Open**, and now also carries the human speaker-label dependency for B1. |

**Overall: NO-GO.** The harness stays disabled.

## 10. Artifact locations and hashes

| Artifact | Path | sha256 |
|---|---|---|
| Generator | `backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py` | `9d1b1c44cd95add153bd2497ba1d42e2a60a0c1958820afb042f34067872fc08` |
| Tests | `backend/tests/test_regenerate_v10_span_ecapa_verdicts.py` | `d58afbfffc91296aebd762b280c21608ab337730d71e53ae8ef0a20b93c7a05a` |
| Verification runner | `backend/scripts/ops/run_public_release_phase2_verification.sh` | `faa5d7b381a7ee8d44280e1d6dda72e257c6ba40d471936701c882e63a77260a` |
| Calibration artifact | `audits/evidence/public_release_phase2_calibration_2026-10-22.json` | `0d044a452a469ec3314ad2d1fdb5df256278bcebc48dc11a58d66308561acb28` |
| Verdict index (keyed by `source_span_id`) | `audits/evidence/public_release_phase2_verdicts_2026-10-22.json` | `cef4c80eeca217c5a908848774a047b2a6f185a0403e9b505094593f409d0f73` |
| Verdict rows (JSONL) | `audits/evidence/public_release_phase2_verdicts_2026-10-22.jsonl` | `a654116db77238695de2837eadc58541fb5c00e0b06d99deb7845ed8dc6c7040` |
| Summary | `audits/evidence/public_release_phase2_summary_2026-10-22.json` | `21b066e7aeabc67a491de507794f67301dc45169be72f93aff728db30acdbd88` |
| Command/exit-code transcript | `audits/evidence/public_release_phase2_verification_2026-10-22.txt` | `bf31381879e8a687f882774554748ae1a06dcc9e20dd1d88aece046bc8835d0a` |
| Phase-3 candidate (input) | `audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl` | `5806658e5a714aba88902202508fb6f3db027eb6b8e8944e226d00c5545114bc` |
| Phase-3 quarantine (input) | `audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl` | `3f4b64fd75a0e9fd9572d2db8dbd1fd17225d0b66f14373dbd72e8fce7991700` |
| Old verdict archive (**not** overwritten) | `.work/fp_context/speaker_verdicts.json` | unchanged |

The old verdict archive was **not** modified; every Phase-2 artifact is a new
versioned file.
