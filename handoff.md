# AskMukthiGuru — Session Handoff (first-person verbatim route)

**Date:** 2026-09-25 · **Repo:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8` · **Data (outside git):** `~/mukthiguru_attribution_data/`
**Governing spec:** `docs/agent/first_person_baseline_prompt.md` · **Research:** `docs/agent/first_person_research_2026-09-24.md` · **Gold protocol:** `docs/agent/B1_gold_set_protocol.md` · **Non-negotiables:** `docs/agent/NON_NEGOTIABLES.md`
**Nothing committed or pushed.** `origin/main` is ahead of local `main` (commit `ed46747a`, from another session); not pulled.

> This file replaces an earlier version that claimed "100% Complete", "81/81 passing", "n ≥ 628 with k=0", "±1.73% variance", and a rollback recipe that crashed. Those claims were false or unsourced. Everything below is VERIFIED unless marked otherwise.

## 1. Goal

A first-person answer IS Sri Preethaji's / Sri Krishnaji's own recorded words, with the right speaker and the exact second. It is served as a pointer to a verified clip; no LLM runs at serve time. Target: ≥99% precision on *confident* answers, proven on human-labelled held-out data, at under 1 s. Every uncalibrated answer is labelled **"Related, not a direct answer."**

## 2. Verified state (2026-09-25)

| Area | State | Evidence |
|---|---|---|
| Route `POST /api/first-person/query` | Works in code, behind the flag `FIRST_PERSON_ROUTE_ENABLED` (default **False**). Serves cleared channels only unless `FIRST_PERSON_SERVE_UNREGISTERED` (default **False**). | `tests/test_first_person_route.py` (autospec'd embedder) |
| Serve-time integrity | `sha256(verbatim_text)==transcript_hash`, speaker ∈ {Sri Preethaji, Sri Krishnaji}, `find_artifact` clean. Also re-run on cache hits. | Mutation check: gate forced open → 3 tests fail |
| Confidence | top-1 dense cosine. "Direct" only with a valid profile (`FIRST_PERSON_CALIBRATION_PATH`); **no profile exists** (needs human gold). | Mutation check: forced profile → test fails |
| Calibrator | Fixed-sequence Learn-then-Test starting at n_min=299 (rank-only), plus `to_profile()` | `tests/test_calibrator_ltt.py`; CP(0,299)=0.00997, CP(0,298)=0.0100024 |
| Index builder | `backend/scripts/ops/build_first_person_index.py`: fail-closed per-video gates (substring of the voted-word layer, hash, teacher speaker, timestamp ≤ duration, rights by yt-dlp channel). Dry-run by default. | Dry-run on 8 bake-off videos: 8/8, 520 clips (423 P / 97 K) |
| Rights (N7) | Cleared: "Sri Preethaji & Sri Krishnaji" (6 bake-off videos). Uncleared: "TEDx Talks", "Marie Forleo" (1 each). Uncleared clips are indexed but not served by default. | `~/mukthiguru_attribution_data/first_person_index/channels.json` |
| Backend suite | **7,726 passed, 0 failed**, 12 skipped (re-run after the review-fix round) | `~/mukthiguru_attribution_data/fullsuite_2026-09-25_r2.log` |
| Safety scenarios | 32/32 tier-3 PASS; **42 live-backend scenarios NOT RUN** | `evals/reports/latest_tier3_mechanical_run.json` |
| Frontend | vitest 631 passed | `~/mukthiguru_attribution_data/vitest_2026-09-25.log` |
| Reviews | Independent (non-negotiables, 11 traps) PASS; security review PASS | — |
| Blast radius | code-review-graph `detect_changes`: risk 0.65, 40 tracked files. Its test-gap list (Settings, lifespan, EmbedIndexConfig, IngestionPipeline) comes from earlier-session edits and is covered by the full suite. | — |
| `first_person_v1` collection | **580 points / 45 videos**, deterministic (applied twice, identical ID set) | §4 |
| Live E2E eval | **PASS on all 8 checks**: 8-video index top-1 0.470 (= B.R0); full 45-video index top-1 0.410, p95 37 ms; 0 non-teacher; 0 hash failures | §4 |

## 3. Defects found and fixed today

**The first-person path had never served an answer**
1. The route called the nonexistent `EmbeddingService.embed_query`, so every call returned 500; the test patched the class. Now it uses `container.embedding.encode_single_full_async`, `Depends(get_container_async)`, `asyncio.to_thread`, `chat_rate_limit`, generic 503s, and one cached pipeline per process with the container's crisis engine.
2. The integrity check read a `(bool, reason)` tuple as a bool, so it never fired. Replaced with the gate above.
3. The 0.015 threshold on raw RRF scores made every rank-1 hit "direct". Replaced with the profile-gated cosine.
4. Crisis text was hardcoded. It now uses `crisis_helplines.format_helplines_block()` (owner-approved `helplines.yaml`), before retrieval.
5. Store: the `teacher_id` default "both" broke the teacher filter; `question_dense` duplicated the passage vector (double-counted in RRF). Fixed: per-clip teacher, RRF over dense and sparse (B.R0 parity), vectors in RAM, richer payload, `caption_status="auto_transcript"`.
6. The calibrator picked the max-coverage passing threshold (multiple testing). It now uses fixed-sequence LTT.

**Unapproved regressions reverted (owner decision)**
- `services/qdrant/source_policy.py` re-blocked The Four Sacred Secrets against the 2026-09-23 rights confirmation. It now equals HEAD.
- `services/qdrant/utils.py` point IDs keyed on `transcript_hash` would duplicate points on re-ingest. They're back to `source_url:chunk:level`.
- `rag/nodes/retrieval.py` had an integrity filter added to ordinary chat. Removed; the file equals HEAD.

**Other fixes**
- `speaker_diarization.py` split long runs instead of dropping them past 60 s, and there's one hash definition.
- `verbatim_metrics.py`: a real aligned-span token ratio. A dropped "not" is now rejected.
- `qdrant_aliases.py`: rollback ledger, and cleanup protects every alias target.
- `review_server.py`: judge blindness, column and value whitelist, atomic locked writes, escaping, loopback only.
- `readiness_check.py`: host labels and unadjudicated disagreements are hard failures.
- `silver.py`: word-boundary matching.
- `ingest_e2e_scratch_check.py`: try/finally cleanup; it no longer writes a Supabase row.
- `parallel_corpus_extractor.py`: token bucket on every tier; manifest verified on resume; NameError fixed; `condition_on_previous_text=False`.
- `bench.py`: ReadTimeout is no longer retried (it made each failing row 547 s); it still counts as an error.
- Pilot audio: 42 new WAVs were 48 kHz stereo, and ECAPA needs 16 kHz mono (it fails closed). Converted, and the download now requests 16 kHz mono.

**False claims corrected** (banners added to the PROD_READY plan and research docs 2–5):
- there is no Merkle manifest in `corpus_engine`;
- there is no ECAPA in CorpusEngine;
- the session pool has no caller;
- "scratch 11/11" wrote a real Supabase row;
- the Dexa pre-roll, MRL "70%" and "±1.73%" claims are unsourced.

## 4. Jobs, results, resume commands

- **Pilot50** (`~/mukthiguru_attribution_data/pilot50_2026-09-25`):
  - The 8 bake-off videos keep their frozen ASR, because the 116-question eval is keyed to them.
  - The 42 new videos are re-running the speaker and clips steps under the self-healing supervisor.
  - Resume: `cd ~/mukthiguru_attribution_data && JOBS=pilot nohup ./watchdog.sh >> watchdog.log 2>&1 &`.
  - "Done" means every video has all 7 steps ok (`pilot_run_summary.json`).
- **B0 benchmark:**
  - Run 1 was at 71/1226 when the lead stopped it (owner: pilot first).
  - After the pilot AND the container rebuild: `cd ~/mukthiguru_attribution_data && JOBS="run1 run2" nohup ./watchdog.sh >> watchdog.log 2>&1 &`.
  - Compare the runs with `rescore_report` plus a clustered bootstrap CI on the difference.
  - Expect run 1 to be reported INVALID (error rate above 1%, from timeouts), which is honest.
- **Index:**
  - `cd backend && QDRANT_URL=http://localhost:6333 .venv/bin/python scripts/ops/build_first_person_index.py --passages-dir ~/mukthiguru_attribution_data/bakeoff_2026-09-25/passages_B --passages-dir ~/mukthiguru_attribution_data/pilot50_2026-09-25/passages_B --videos-json ~/mukthiguru_attribution_data/pilot50_2026-09-25/videos_final.json [--apply]`.
  - Apply twice to prove deterministic IDs.
- **Live eval:**
  - `cd backend && .venv/bin/python scripts/ops/first_person_live_eval.py`. The route must be enabled in the container env; the local root `.env` has `FIRST_PERSON_ROUTE_ENABLED=true` and `FIRST_PERSON_SERVE_UNREGISTERED=true` for the **local eval only**.
  - Acceptance: top-1 CI overlaps B.R0 [.37,.56]; p95 < 1 s; 0 non-teacher speakers; 0 hash failures; crisis and teacher probes pass.
- **Labelling UI:** `cd backend && .venv/bin/python -m evaluation.gold.review_server --csv ~/mukthiguru_attribution_data/gold_pilot/relevance_pilot.csv --port 8088 --judge a` → http://127.0.0.1:8088 (backup: `relevance_pilot.backup_2026-09-25.csv`).
- **Rollback of an alias:** `QdrantAliasManager(client).rollback_alias("<alias>")` reads the previous target from `~/mukthiguru_attribution_data/qdrant_alias_ledger.json`. No alias exists yet.

### Live E2E eval results (VERIFIED, 2026-09-25 18:31 IST)

- **Setup:** container rebuilt 12:51Z with the owner's approval; healthy after ~160 s, RestartCount 0.
- **Index:** `first_person_v1` held 333 points (all 8 bake-off videos plus 12 pilot videos).
- **Report:** `~/mukthiguru_attribution_data/first_person_live_eval/summary_20260925T130152Z.json`.

| Check | Result |
|---|---|
| Top-1 strict (83 answerable single-video questions, video-clustered 95% CI) | **0.470 [0.398, 0.542]**, identical to offline B.R0 0.470 |
| Latency over HTTP (embed + retrieval + gate) | p50 139 ms, **p95 329 ms** |
| HTTP 200 | 116/116 |
| Non-teacher speakers served / hash failures served | **0 / 0** |
| Answers marked "direct" | 0 (no calibration profile; every answer is "Related, not a direct answer") |
| Unanswerable questions (27) | 26 got a related clip, 1 was a crisis redirect. No true abstention without a calibrated threshold. |
| Crisis redirects | 2/116; both score SEVERE on `assess_distress`, the same rule chat uses |
| Crisis probe / teacher-filter probe | PASS / PASS |
| Top-1 host-leak (text heuristic only) | 0.138 |
| **Acceptance** | **PASS on all 8 checks** |

**What this proves:** the verbatim route works end to end locally, matches the benchmarked retriever, and is fast and fail-closed.

**What it does NOT prove:** ≥99% precision. The right clip is ranked first only 47% of the time, and precision on *confident* answers needs the human gold set plus a fitted profile.

Note: top-1 was 0.446 before the review fix that raised the RRF prefetch depth from 12 to 60 (B.R0 parity).

#### Final index + full-index eval (VERIFIED, 2026-09-25 19:28 IST)

**Pilot50:** 50/50 videos passed all 7 steps; 1,017 raw clips; mean Whisper-vs-Parakeet agreement 0.89. Reports: `pilot50_2026-09-25/PILOT.md`, `pilot_report.json`.

**Data inspection (Haiku, read-only):**
- 0 hash or substring failures, 0 bad timestamps, 0 cross-video duplicates.
- 17 teacher clips end in "?". They look like the teacher's own rhetorical questions; a human should spot-check them.

**New fail-closed gate:** Whisper-vs-Parakeet agreement below 0.80 (`MIN_ASR_AGREEMENT`, provisional) quarantines the whole video. The reason: a clip's hash proves it matches its own transcript, not the audio. Quarantined: `AK435vKMtlo` 0.064, `8xJampnp9qc` 0.080 (Hindi talk), `207izZBbqVg` 0.688, `-i-QFyNg8Io` 0.698, `CZ_r5sYeTyY` 0.765. Every bake-off video is at 0.855 or above.

**Final `first_person_v1`:**
- 45 videos, **580 points**.
- Applied twice: identical ID-set hash (`7c622cea51dfebd5`), 0 count mismatches, so the build is deterministic.
- Each apply also deletes points of videos no longer indexable.
- Rights: 43 videos cleared; TEDx Talks and Marie Forleo (1 each) uncleared.

**Live eval on the full index** (`summary_20260925T135916Z.json`): **PASS on all 8 checks.**
- **Top-1 0.410 [0.337, 0.488].** It fell from 0.470 because the index grew from 8 to 45 videos, which adds distractor clips. This is the realistic number, and accuracy drops as the corpus grows, which is what the fine-tuned reranker and calibration (both needing human gold) are for.
- p50 29 ms, p95 37 ms. 116/116 HTTP 200. 0 non-teacher speakers, 0 hash failures, 0 "direct" answers.

**B0 benchmark:** run 1 resumed at 71/1226 at 19:29 under `watchdog.sh` (`JOBS="run1 run2"`), and run 2 follows automatically. Expect run 1 to be reported INVALID (timeouts), which is honest.

#### v2 clips live (VERIFIED, 2026-09-25 ~22:45 IST)

**What changed.** Clip builder v2 (`speaker_diarization.build_clips_from_labelled_words`, `scripts/ops/build_clips_v2.py`, 10 tests):
- it merges teacher speech that flickering speaker labels had split, across short unknown gaps;
- it never includes a host word or the other teacher's word;
- it cuts at sentence ends (falling back to the largest pause);
- it emits a parent of 200 words or fewer on its own, without a duplicate child;
- it drops fragments under 12 words.

Median clip length rose from 15–19 words to about 60.

**Index.** `first_person_v2` holds 280 points from 45 videos. Two applies gave an identical ID-set hash (`a7a077ceba14d219`). `first_person_v1` (580 points) is kept as the rollback: to roll back, set `FIRST_PERSON_COLLECTION=first_person_v1` and rebuild.

**Route.** `FIRST_PERSON_COLLECTION=first_person_v2` in the root `.env`; container rebuilt; health 200.

**In-process comparison (same code, 116 frozen questions):**
- top-1: v1 0.361 → v2 **0.410**;
- median served clip: 30 → **78** words;
- fragments served: 28/114 → **0/114**;
- host-leak heuristic: 21 → **9**;
- answers ending mid-sentence: 74 → 75 (unchanged; clips end where the speaker label changes, which is a speaker-audit issue).

**Live HTTP eval on v2** (`summary_20260925T171641Z.json`): **PASS on all 8 checks.**
- **top-1 0.434 [0.325, 0.529]**; top-1 host-leak heuristic 6.9%, down from 17.2% on v1;
- 0 non-teacher speakers, 0 hash failures, 0 "direct" answers, 116/116 HTTP 200;
- p95 209 ms, measured while the B0 benchmark ran on the same backend.

**Review UI.** Live at 127.0.0.1:8088, with the YouTube player at the clip, clip facts, ±40 words of transcript context with machine speaker tags, a `clip_quality` label, and keyboard shortcuts. Judge blindness is kept.

**Prompt audit.** Report and proposed diff at `~/mukthiguru_attribution_data/prompt_audit/PROMPT_AUDIT_2026-09-25.md`; nothing applied.
- Two real bugs: a duplicate `CANONICAL_URLS_LOGISTICS`, and corrector leak regexes that no longer match their own prompt.

## 5. Owner actions and remaining work

**Production checklist and next-session prompt: `docs/agent/NEXT_PROD_READY.md`.**

- **Write the 150 questions** in `~/mukthiguru_attribution_data/gold_pilot/question_authoring_pilot.csv` (0/150 now). This is the only route to proving ≥99%.
  - `relevance_pilot.csv` uses the AI-authored bake-off questions, so under B1 it's dev and calibration data only.
- **Label relevance** in the review server.
  - Fit the profile (`SelectiveRiskCalibrator(...).find_operating_threshold()` then `.to_profile()`) once ≥299 confident human-labelled answers exist.
  - You sign off the operating point.
- **Decide:**
  - copying the verbatim layer into Docker (needed for a serve-time substring check; today it's index-time substring plus serve-time hash);
  - deleting the Qwen3-ASR cache (~4.7 GB);
  - the OKF load gate;
  - clearing more channels in `CONTENT-RIGHTS.md` (TEDx Talks, Marie Forleo are uncleared);
  - the full-corpus compute plan after `PILOT.md`.
- **Deferred:**
  - the fine-tuned reranker, convex fusion and a logistic calibrator (these need human gold);
  - the question field, ColBERT and MRL (no measured gain);
  - D2 wiring into `ingest/` (speaker turns, clips, forced alignment, `transcript_hash` at the other 3 `EmbedIndexConfig` sites);
  - UI;
  - Railway (NO-GO stands);
  - S5 secure memory.
- **UNVERIFIED:**
  - production latency and topology;
  - native-speaker crisis review;
  - which transcript is correct, old or new (needs human transcript gold).

## 6. What not to retry

- Trusting `ps | grep` for job liveness: use `pgrep -fl` plus checkpoint growth.
- Mocking services with a bare patch: use `create_autospec`.
- Thresholding raw RRF scores.
- Keying point IDs on `transcript_hash`.
- The Dexa pre-roll (plays host audio).
- Overlapping sub-clips.
- Re-running bake-off ASR (it would break the frozen eval basis).
- Qwen3-ASR (161× real-time on CPU).
- Running ASR and the benchmark together.
- Agents with worktree isolation (`grounding-engineer`, `docs-writer`) for edits to uncommitted files: their worktree starts from `origin/main`, without the working tree. Use in-place agent types (e.g. `ecc:tdd-guide`).
