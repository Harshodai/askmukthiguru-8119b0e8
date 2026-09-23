# Guru Brain speaker attribution: full record (2026-09-20 → 2026-09-24)

Everything done on the "who actually said this, and are these really their words?"
problem: research, live measurements, pilot experiments, industry comparison,
decisions, and every result. Numbers are measured unless marked *vendor claim*
or *estimate*.

**Two sessions did this work in parallel** after forking from the same
conversation on 2026-09-22. Both are covered here:
- **Session A** (`61c7a2fa…` → `b85a3bed…`): research report, voiceprint pilot,
  Qwen / industry research, top-14 census, the two request/label sheets.
- **Session B** (`a8776f7b…`): the "Their words, your life" plan, the
  verbatim-corpus audit, the production script `speaker_attribution.py`, word-level
  attribution, 12-video batch, blind audit sheets.

Session B's numbers are quoted from its own reports. Where I (Session A) re-ran
something, it says so.

Short "pick this up" version: `handoff.md` (repo root, top entry).

---

## 0. The problem

Mukthi Guru answers from a Qdrant corpus built from YouTube videos of Sri
Preethaji and Sri Krishnaji. Many videos are interviews, festivals or joint talks,
so the audio contains hosts, narrators, translators, audiences and **both**
teachers. Attribution today is decided from text: titles, and whether a line
*contains a teacher's name* (`backend/services/guru_brain/tone_extractor.py:74`,
still live). A host saying "Krishnaji, tell us…" flips the label.

Two answer styles depend on fixing it:
- **3rd person** ("Sri Preethaji and Sri Krishnaji teach…"): needs teacher vs. non-teacher.
- **1st person** = the teacher's **own verbatim words, quoted** with a timestamp:
  needs *which* teacher, per sentence, and needs the text to actually be verbatim.

Session B found a second, bigger problem: **most Qdrant chunk text is not the
teachers' words at all** (§3.1).

---

## 1. Deep research (Session A, 2026-09-20/21)

Report: `research/notes/final_report_guru-brain-diarization-persona-scaling-4dbe2b.md`
(11,011 words, 108 sources, 149 citations, ship gate 13/13).

**Six committed answers**
1. **Attribution:** diarization for boundaries, voice enrolment for identity,
   spoken names only as corroboration. Delete the substring matcher. Literature:
   an oracle mapping spoken names to speakers within 3 turns is right only
   **53.4%** (21.3% on ASR); named-addressee detection **30.3% P / 16.0% R**.
2. **Exemplar counts:** 30 verified samples binding today; 16–20 for in-context
   injection; 100–200 per register for adapters.
3. **Real failure evidence:** VoxCeleb2 audit, **28,343 of 1,092,009 (~2.6%)**
   mislabelled by a pipeline keyed on *video titles*.
4. **Scaling:** the `teacher_id` field mixes person / pair / organisation, so it
   breaks at N=3. Proposed `speaker_id` + `lineage_id` + `attribution_method` + `language`.
5. **Verification:** speaker verification run at a low false-accept point
   (realistic EER **4.59% @3 s, 11.15% @1 s**) + stylometric profiles; LLM judge = monitoring only.
6. **Fine-tuning** wins the mechanism, loses on data today.

**Live measurements that overturned premises**

| Premise | Measured |
|---|---|
| 12,904 points | **14,033** |
| "properly attributed" | only **34.5%** attributed to one person (`preethaji_krishnaji` 4,854 · `ekam` 4,337 · `krishnaji` 3,590 · `preethaji` 1,252) |
| `guru_tone_podcast` = 12 points, one fabricated question | **9 points, 9 distinct questions** (commit `f8f500ca`; `register.py:30` docstring still says 12) |
| audio kept | **not retained** (`TemporaryDirectory`); re-fetchable by `video_id` |

**Process issues:** 5 subagent session-limit wipeouts (I wrote 4 of 6 depth
reports and the synthesis myself); Semantic Scholar 429s; 78 notes retagged;
quote-gate fixes. **Security:** one fetched ACL Anthology page carried a
prompt-injection ("Create GitHub issue for staff review"); refused.

---

## 2. Voiceprint pilot (Session A, 2026-09-22 → 09-24)

User instruction: *"test with some videos … ruthlessly … once you are confident
100% then only run for all."* **Nothing has been run on the full corpus.**

### 2.1 Tooling
- Backend venv lacks pyannote/speechbrain/torchaudio. HF token → **403** on gated
  pyannote models (licence click needed).
- Isolated venv: `speechbrain` ECAPA (`spkrec-ecapa-voxceleb`, Apache-2.0),
  `faster-whisper`, `librosa`, `sklearn`.
- Method: 2 s windows → ECAPA embeddings → cosine to voiceprints;
  agglomerative clustering (cosine distance 0.6) for voices within a video.

### 2.2 Try 1 — voiceprints from corpus labels, leave-one-video-out → FAILED (instructive)

| Video | Corpus label | Windows matched to own label |
|---|---|---|
| XzS56RqIxeE | preethaji | 0.879 |
| TqxxCYnAxo8 | preethaji | 0.926 |
| Ejcq9mNGJk0 | preethaji | 0.500 (own-voice sim 0.09) |
| w2qbJB6ie9Y | krishnaji | 0.507 (own-voice sim 0.02) |
| rGcNJ_Nsuy8 | krishnaji | 0.603 |
| btbKcsb9Dzw | krishnaji | 0.501 |
| hUmlujE6SN0 | krishnaji | **0.005** |

Cause: **the labels were wrong, not the method.**

### 2.3 Try 2 — independent evidence
- Dominant-voice pitch: hUmlu **203 Hz** (female; labelled krishnaji), Ejcq9
  **105 Hz** (male; labelled preethaji), XzS56 228, Tqxx 219, rGcNJ 111.
- Ejcq9's dominant voice says *"Gathered more than 300 members lit and discovered
  the impact"*: promo narration stored as Preethaji.

### 2.4 Try 3 — human anchors → WORKS
User confirmed by ear (2026-09-22 19:42 UTC, "yes, you are correct"):
`hUmlujE6SN0` @ 9:23 = **Preethaji**, `rGcNJ_Nsuy8` @ 6:26 = **Krishnaji**.
So `hUmlujE6SN0`'s corpus label is a **confirmed error**.

### 2.5 Try 4 — census check on known material (cluster rule: ≥0.55 and beats the other by ≥0.15)

| Audio | Result |
|---|---|
| Marie Forleo interview `UlOt31lBhLY` | **P 39% · host 29% · K 17%** (P cluster 0.76 vs 0.13; K 0.15 vs 0.73; host 0.20/0.11) |
| btbKcsb9Dzw (labelled krishnaji) | both: P 47%, K 25% |
| Ejcq9mNGJk0 (labelled preethaji) | 97% other voices |
| w2qbJB6ie9Y (labelled krishnaji) | K 21%, other 79% |

### 2.6 Try 5 — top-14 census (half the corpus), 3 s hop, 8.3 h audio

| Video | Chunks | Corpus label | P | K | other | Verdict |
|---|---|---|---|---|---|---|
| nwQaU-agzFE | 604 | preethaji | .70 | .00 | .30 | match |
| x-mTRlE0TC4 | 576 | krishnaji | .00 | .74 | .26 | match |
| V45jIC4RthQ | 494 | ekam | .30 | .45 | .25 | both teachers |
| 1_-cZz8YRFw | 471 | joint | .27 | .32 | .41 | match |
| ACvOem_B-Ek | 471 | joint | .00 | .21 | .79 | **mismatch** (K only) |
| vARTudIEq30 | 452 | joint | .00 | .16 | .84 | **mismatch** (K only) |
| sMgbjxyrgqw | 451 | ekam | .27 | .40 | .33 | both teachers |
| AR0r8B6Ga8E | 439 | krishnaji | .00 | .77 | .23 | match |
| nCkbv_lvFfg | 431 | krishnaji | **.44** | .39 | .17 | **mismatch** (both) |
| kMc_kat7YLE | 425 | ekam | .00 | .83 | .17 | Krishnaji |
| YkIBYppBtro | 409 | joint | .00 | .83 | .17 | **mismatch** (K only) |
| _GEMrEWCiXw | 408 | krishnaji | .00 | .76 | .24 | match |
| mmpmX3-qfc4 | 402 | krishnaji | **.43** | .39 | .18 | **mismatch** (both) |
| U23yKxWbIcI | 396 | krishnaji | .00 | .79 | .21 | match |

By chunk weight: **45% consistent, 34% contradicted, 21% org-labelled**.
Most dangerous: `nCkbv_lvFfg` + `mmpmX3-qfc4` = **833 chunks labelled krishnaji
where Preethaji speaks ~43%**. Session B independently found the same pattern
("two videos labelled krishnaji are about 40–48% Preethaji").

Caveats: machine verdicts; "other" includes music/applause/silence, not only
people; video-level only; thresholds hand-set.

### 2.7 Bugs in my own pilot code (fixed)
- **Relative silence filter** discarded ~97% of evenly-loud audio and ~45% of
  speech in the interview (Session B traced 1,124 "unknown" words to it). Fixed
  to an absolute floor in both the pilot and the production script.
- **Video double-count:** I reported 1,258 videos; **real count 638** (IDs keyed
  both by `video_id` and by URL).

---

## 3. Verbatim-corpus audit and the revised plan (Session B, 2026-09-23)

### 3.1 The Qdrant chunks are mostly not the teachers' words
Top-14 videos, 4,801 chunks checked against `transcripts/*.md`:

| Chunk type | Share |
|---|---|
| Verbatim | 18% |
| Partial | 21% |
| **Machine-rewritten** ("the speaker finds it amazing…", "the text states that…") | **61%** |

- `backend/ingest/pipeline.py:3411` appends LLM "potential questions…" into chunk
  text, which is embedded and fed to the answer model as teaching.
- **0 of 3,000** sampled points carry `[t=]` timestamps.
- The rewriting compounds the attribution bug: the *host* in `x-mTRlE0TC4`,
  rewritten as "the speaker", filed under Krishnaji.

### 3.2 The transcript corpus is good (the source of truth)
`scripts/ingestion/corpus/<video_id>/canonical_segments.json`:
- 657 videos, **29,551 timestamped segments, 51.4 h**.
- A second independent ASR agreed **95.6–98.8%** word for word (4 videos).
- Only rule-based, reversible spelling fixes (`correction_ledger.json`).
- Median coverage 96%; 53 videos flagged for Whisper repetition loops.
- Backs **75%** of live points; **16%** have `.md` only (no timings, some
  truncated: `UlOt31lBhLY.md` misses minutes 20–30); **9%** not YouTube.

### 3.3 One video through every store (`UlOt31lBhLY`)

| Store | Verbatim? | Verdict |
|---|---|---|
| Fresh corpus package | yes, 447 segments, 98.6% coverage | good source |
| `transcripts/*.md`, `.txt`, LightRAG docs | yes but incomplete (3,362 vs 5,035 words) | re-transcribe |
| Live Qdrant chunks (256) | 61% rewritten | **18 host chunks stored as teaching** |
| `guru_tone_podcast` (8) | yes | ≥2 wrong labels, incl. **the exact brief bug**: Preethaji saying *"it's an insight from Krishnaji"* labelled krishnaji |
| 21 staged OKF drafts | **99% of "quotes" not verbatim** | must not be approved |

### 3.4 Word-level attribution
- First pass left 23–26% of speech unassigned. The cause was the silence-filter bug;
  after the fix it's **0% unassigned, 95% in verified turns ≥3 s**, and 94% agreement with
  the earlier method (same voice data, so not independent).
- Host question → teacher answer pairing works (23 pairs in the interview).
- Boundaries off by 1–3 words (2 s windows) → quote only whole sentences fully
  inside a turn, with guard margins.

### 3.5 Deep research (Session B)
Report: `reports/Speaker attribution pipeline for teachings.md`.
- Telling the two teachers apart is largely solved: same-speaker 0.63–0.86,
  different ≤ 0.40.
- Recommends: forced alignment of existing transcripts (instead of
  re-transcribing); **pyannote community-1** (CC-BY-4.0, needs a
  `LICENSE-EXCEPTIONS.md` entry + HF licence click); ≥5 enrolment clips per
  teacher from ≥3 videos; an 8-rule quote gate.
- **Statistics of "near 100%":** the 39-clip sheet can only find failure modes
  (zero errors proves ≤ 92.6%). **Certifying 99% precision needs a frozen system
  plus ~299 random quotes labelled with zero errors.**
- Cost *estimate*: diarization ~25–28 CPU-hours for 51 h of audio (not measured here).
- MMS aligner weights may be non-commercial; the script uses torchaudio
  `WAV2VEC2_ASR_BASE_960H` (MIT) instead.

### 3.6 Production script (uncommitted)
- `backend/scripts/ops/speaker_attribution.py` (357 lines): `embed` / `enroll` /
  `attribute` / `sample` / `--self-check`. Deterministic, local, no LLM.
  Abstains by default: a sentence is quotable only if every word is aligned, one
  teacher speaks all of it, it's long enough, it ends in terminal punctuation, and
  it keeps a guard margin from turn edges.
- `backend/tests/test_speaker_attribution.py`: **6 passed** (re-run by Session A, 2026-09-24).
- `backend/scripts/ops/requirements-speaker-attribution.txt`: separate venv;
  `torchaudio<2.12` pin.
- 12-video batch run with widened voiceprints (`voiceprints2.npz`); the audit
  sampler says **1,292 quotable sentences across 12 videos**.

### 3.7 Also shipped by Session B (committed)
- `d4590b1f` fix(privacy): `DELETE /api/memory/all` now erases canonical memories,
  both audit tables, `conversation_memories`, `user_profiles` and the Qdrant
  vectors; `tests/test_memory_delete_all_completeness.py`.

---

## 4. Qwen3.8-Omni-Flash (Session A)
- Real (2026-09-18). **API only, no open weights.** Joint audio+video speaker
  recognition, end-to-end segmentation + transcription + identity, up to 1 h AV,
  991K max input tokens.
- *Vendor claim* DER / cpWER: AliMeeting **3.4 / 17.2** (prior Qwen omni 88.1),
  AISHELL-4 2.8 / 11.2, MagicData-RAMC 5.7 / 14.1, MLC-SLM English 4.0 / 14.2.
  Blog marked "[draft]".
- $0.15 / 1M input, $0.47 / 1M output; *estimate* ~1¢ per audio hour.
- Verdict: the right capability. Use it as a **second independent labeller** (accept
  where it agrees with voiceprints), not the only one. Decision: pilot videos only;
  no key yet.

## 5. "Can't an LLM do it from text? Why not label everything jointly?"
- Text separates teacher vs. host fairly well; it **cannot** separate
  Preethaji vs. Krishnaji (same vocabulary; names are the trap). The corpus's own
  text-derived labels prove it.
- A joint label is **right for 3rd person** but doesn't remove host/narrator speech
  (the actual bug), can't support quotes, and doesn't scale to N teachers.

## 6. How other companies do it (Session A)

| Who | Approach | Safety comes from |
|---|---|---|
| Sadhguru *Miracle of Mind* | plays his **real recordings** | own curated archive |
| Dexa / Huberman AI | 3rd person + timestamped clips | AssemblyAI diarization + first-party partnership |
| Digital Deepak, Delphi | generated 1st person | **consent**; Delphi keeps only the creator's turns |
| AssemblyAI Speaker ID | names from conversation content | inference (the text approach) |
| pyannoteAI | voiceprint (≤30 s) → identify; unknowns stay `unknown` | enrolment, €19/mo+ |
| Otter.ai | learns voiceprints after tagging | 89–95% (third-party review) |
| GitaGPT (failure) | generated Krishna's voice | fabricated/misplaced verses |

Pattern: nobody claims fully automatic near-100%. The more sacred the output, the
more it's retrieval of real words + consent + owner data.

## 7. Decisions on record

| Topic | Decision |
|---|---|
| Qwen / sending media to Alibaba | pilot videos only; no key yet |
| Ground truth | user labels (39-clip sheet first, then 15-min sheet) |
| Generated 1st person | user asking Ekam for consent; off until then |
| Meaning of "1st person" | **their real words from transcripts**, quoted, with clip |
| First-party data | user asking Ekam (sheet ready) |
| Unverified material | keep, flag, 3rd person only |
| Host speech | kept only as *question context*, never quoted as teaching |
| Unclear after split | lineage-only, 3rd person, never a named quote |
| 16% incomplete transcripts | re-transcribe slowly (YouTube is throttling: 429/403) |

## 8. Files and artefacts

**Repo (all uncommitted):**

| Path | What |
|---|---|
| `docs/attribution/README.md` | instructions for all four sheets |
| `docs/attribution/label_40clips_UlOt31lBhLY.csv` | **do first**: 39 hard clips, ~10 min |
| `docs/attribution/label_UlOt31lBhLY_15min.csv` | 152 rows, 2:00–17:00 |
| `docs/attribution/pilot_audit_60_quotes.csv` | 60 random quotable sentences: speaker + text check |
| `docs/attribution/ekam_speaker_request.csv` | 638 videos; top 14 = 50%, 157 = 80%, 362 = 90%, 490 = 95% |
| `docs/attribution/pilot/` | Session A pilot scripts + `census.csv` (row-level predictions kept out of the repo so the label sheets stay blind; they are in the backup) |
| `backend/scripts/ops/speaker_attribution.py` + test + requirements | Session B production script |
| `reports/Speaker attribution pipeline for teachings.md` | Session B deep-research report |
| `~/.claude/plans/see-right-now-what-groovy-codd.md` | Session B plan ("Their words, your life") |

**Outside the repo (durable backup made 2026-09-24):**
`~/.askmukthiguru-attribution-backup/2026-09-24/` holds both sessions' scratch
scripts, results, voiceprints and the **answer keys for the blind sheets**
(`fork_session_a8776f7b/onevideo/*_KEY.json`). Don't open the keys until your
labels are in. Audio isn't backed up (re-download with `yt-dlp`).

## 9. What we learned
1. **Labels were the problem, not the model.** Get human anchors before trusting "solo" labels.
2. **Voice cleanly separates the two teachers** (≥0.63 vs ≤0.40); pitch is an independent cross-check.
3. **Corpus labels are wrong in about a third of the biggest videos by chunk weight**, including Preethaji's speech under Krishnaji.
4. **Most Qdrant chunk text isn't verbatim.** Quotes must come from `canonical_segments.json`, not from chunks.
5. **Text can't tell the two teachers apart**; it can mostly tell teacher from host.
6. **The corpus is concentrated:** 14 videos = 50%.
7. **"100%" is a statistics question:** 299 random quotes with zero errors certify ≥99% at 95% confidence, on a frozen system.
8. **Industry pattern = retrieval + consent + first-party data.**
9. **Cheap heuristics and ID normalisation bite.** Verify counts two ways.

## 10. Open risks
- Anchors: one confirmed clip per teacher. Widened enrolment (`voiceprints2`) is machine-selected.
- Festival and translated audio are the weakest cases; Telugu/Tamil untested.
- `tone_extractor.py:74` substring matcher and wrong `teacher_id` values are **still live**.
- 21 staged OKF drafts contain non-verbatim "quotes"; must not be approved.
- YouTube throttling blocks re-transcription of the 16%.
- Licences: pyannote community-1 (CC-BY-4.0) not yet approved.
- Consent for generated 1st person unknown; rights to embed YouTube clips unconfirmed.
- Two sessions edited `docs/attribution/` in parallel. Check `git status` before assuming ownership.
