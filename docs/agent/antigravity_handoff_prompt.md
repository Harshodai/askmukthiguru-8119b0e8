# AskMukthiGuru — Antigravity end-to-end handoff prompt (2026-09-25)

Paste everything below the line into Antigravity as the task prompt.

---

You are taking over an in-progress workstream in the AskMukthiGuru repo at `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`. The goal is a **production-safe first-person, verbatim-answer baseline**: an answer is the teacher's own recorded words (Sri Preethaji / Sri Krishnaji), with the right speaker and the exact second, served as a validated pointer. It is never LLM-written text. You are continuing a previous Claude Code session, and nothing is committed yet.

## STATUS UPDATE 2026-09-28: First-Person v5 Ruthless Audit & Conjunction Integrity
> **Authoritative Current Handoff:** See [`docs/agent/HANDOFF_2026-09-28_FIRST_PERSON_V5_RUTHLESS_AUDIT.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/agent/HANDOFF_2026-09-28_FIRST_PERSON_V5_RUTHLESS_AUDIT.md)
> - **Ruthless Paraphrase Audit**: Probed 15 semantic variants across 5 categories against `first_person_v2` and `first_person_v5`. Proved `v5` wins over `v2` on 5 queries by eliminating sub-8s fragments (`0k5f8G9uXqY` and `NFlAszNFZdQ`).
> - **Sentence Boundary Conjunction Guard (Invariant 10)**: Identified trailing conjunction bug on financial anxiety queries (`hUmlujE6SN0` ending in `"...fear or"`). Implemented defense-in-depth conjunction guards across Serving (`first_person_pipeline.py`), Indexing (`build_first_person_index.py`), and Segmentation (`speaker_diarization.py`).
> - **Unit & Docker Verification**: 85/85 tests passed (`pytest`). Live container verified: corrupt trailing conjunction clips automatically quarantined, complete teachings served, and clean abstention on broken premises.
> - **Lessons & Guidelines**: 9 lessons added to `lessons.md`; Invariants 10 and 11 added to `CLAUDE.md`.

## STATUS UPDATE 2026-09-27: supersedes 2026-09-25 update below

> **Corrected later on 2026-09-27** — several claims below did not survive re-measurement (doctrine-keyword rescue removed, idle-breaker trap not reproducible, `first_person_v4` is worse than live `v2` on host leak, the 46 "rights" exclusions are unavailable videos). See `docs/agent/STATE_RECONCILIATION_2026-09-27.md`.

Full authoritative handoff & engineering record: `docs/agent/SESSION_HANDOFF_2026-09-27.md`. Summary:
- **Phase 0A (`golden_028` Kannada Grader)**: FIXED & TESTED in `backend/rag/nodes/reranking.py`. Indic Unicode block `[\u0900-\u0D7F]` rescues core doctrine concepts and high rerank scores ($\ge 0.40$) from false binary rejection by English LLM graders. `tests/test_grade_documents_crosslingual.py` passed in 0.14s.
- **Phase 0B (`speaker_verified` Citation Contract)**: FIXED & TESTED end-to-end (`citation_extractor.py`, `schemas/__init__.py`, `generation.py`, `orchestrator.py`, `chat_engine.py`, `CitationCard.tsx`). Backend tests 6/6 passed; Vitest 19/19 passed.
- **Docker Stack Rebuild & Virtiofs Fix**: Rebuilt `backend-backend` with entrypoint fallback (`exec gosu appuser "$@"`). Fixed macOS virtiofs out-of-memory bug by pruning orphan containers (`friendly_roentgen`, `exciting_johnson`) and disabling virtual memory cap via `PYTHON_MEMORY_LIMIT_MB=0`. Backend container running healthy on port 8000 with 0 restarts in 13+ hours. In-container tests passed: 26 passed + 76 passed.
- **Unified Benchmark (`retry1`)**: Completed at 00:01:58 AM on 2026-09-27 (1,226 items). Refusal rate 0.041 (PASS), Must-mention coverage 0.5948 (PASS), Citation validity 100% (PASS), Zero retrieval rate 0.0% (PASS), p95 latency 86.28s (PASS), Misattribution rate 0.0093 (PASS). Error rate was 38.3% due to `--resume` retaining 400 early crash rows prior to memory fix; clean Run 2 is next.
- **Live Verification**: `first_person_live_eval.py` passed 8/8 gates (top-1 0.4337, p95 209.5ms, zero non-teacher leaks, zero hash errors). Live chat turn completed in 27s with HTTP 200, `intent=QUERY`, `grounding_state=grounded`.
- **Corpus Ingestion Blueprint**: 526 cleared unindexed videos audited. Dual-ASR consensus (Whisper + Parakeet) with 16 kHz mono audio WAV and ROVER agreement $\ge 0.80$ prepared for shadow collection `first_person_v5`.
- **Accrual Failure Detector Idle Trap**: Identified bug in `services/health_monitor.py` where overnight zero-traffic inflates idle gap, causing $\phi = 10.0$ and tripping circuit breaker on morning's first request.

## STATUS UPDATE 2026-09-25 (evening): supersedes §2, §3 "Live status" and every Appendix B "Already done / Next" line

Full verified record: `handoff.md` (rewritten 2026-09-25). Summary per brief:

- **B0-BASELINE.**
  - Done: run 1 reached 71/1226, then the lead stopped it (owner: pilot first). `bench.py` no longer retries ReadTimeout; it still counts as an error, but each failing row drops from 547 s to 180 s.
  - Next: after the pilot and the owner's container rebuild, `cd ~/mukthiguru_attribution_data && JOBS="run1 run2" nohup ./watchdog.sh >> watchdog.log 2>&1 &`. Compare the runs with a clustered bootstrap CI on the difference. Run 1 is expected INVALID (error rate above 1%). "±1.73%" is unsourced; don't use it.
- **P0-FINISH.** Unchanged: done and verified.
- **D1-PILOT50.**
  - Done: the 8 bake-off videos are frozen (the eval is keyed to them). The 42 new videos first failed at the speaker step (48 kHz audio; ECAPA needs 16 kHz mono) and were fixed: converted, and the download now requests 16 kHz mono. They're re-running under `watchdog.sh`, whose done-check validates every video.
  - Next: `pilot_report.json` + `PILOT.md`, then the owner approves the full-corpus plan.
- **D2-SPEAKER-CLIPS.**
  - Done: `speaker_diarization.py` splits runs over 60 s (no drop); one hash definition, `sha256(text)`. It is still NOT wired into `ingest/`, and the real speaker pipeline is still offline (`pilot50/run_speaker.py`, ECAPA).
  - Next: wire speaker turns, clips and forced alignment into shared ingestion, and add `transcript_hash` at the other 3 `EmbedIndexConfig` sites.
- **D3-STORE.**
  - Done: the `build_first_person_index.py` fail-closed builder with a rights gate. Dry-run: 8/8 videos, 520 clips. Point IDs in the chat collection reverted to `source_url` keying.
  - Next: apply (lead), then apply again to prove deterministic IDs. Alias swap only after all gates and owner approval.
- **R-RETRIEVAL.**
  - Done: the calibrator is fixed (fixed-sequence LTT from n_min=299, plus `to_profile`). `verbatim_metrics` is a real aligned ratio.
  - Next: needs HUMAN gold (the owner's 150 questions, 0/150). Then the fine-tuned reranker and the profile fit. Don't threshold raw RRF.
- **F-ROUTE.**
  - Done: the route works in code. The container embedder is used (the old `embed_query` didn't exist). Real integrity gate; profile-gated "direct" (none yet, so every answer is "Related, not a direct answer"); `crisis_helplines` text; flags `FIRST_PERSON_ROUTE_ENABLED` / `FIRST_PERSON_SERVE_UNREGISTERED` (default False); metrics.
  - Next: the live eval via `backend/scripts/ops/first_person_live_eval.py` (results in `handoff.md` §4).
- **LABEL-ASSIST.**
  - Done: `review_server.py` hardened (judge blindness, whitelist, atomic writes, loopback). It is running as judge A on port 8088.
  - Next: the owner labels. AI never labels.
- **R-REVIEW.** Done: the independent and security reviews PASS for this round.
- **OPS-CRASH-VERIFY.** Unchanged; RestartCount 0.
- **New rules:**
  - use `pgrep -fl`, not `ps | grep`;
  - mock services with `create_autospec`;
  - don't use worktree-isolated agent types for uncommitted files.

## 0. Read first (authoritative, in this order)
1. `docs/agent/first_person_baseline_prompt.md`. **This is the governing spec.** Its rules, phases, gates and decision points override anything below that conflicts with them.
2. `docs/agent/first_person_research_2026-09-24.md`: the research and the recommended stack. Its correction header overrides the body.
3. `docs/agent/B1_gold_set_protocol.md`: the human labelling protocol.
4. `~/mukthiguru_attribution_data/bakeoff_2026-09-25/COMPARISON.md`: the 8-video bake-off results.
5. Root `CLAUDE.md`: the #1-priority banner, plus the "Faithfulness verification", "Native model concurrency invariant", "OKF pipeline" and "Caching invariants" sections. Also `backend/CLAUDE.md` and `src/CLAUDE.md`.
6. `lessons.md`: L-TEACHER-TAG-1 at the top, then L-ATTRIB-*, L-OKF-QUOTES-1 and L-VERBATIM-*.

## 1. Non-negotiables (summary; the spec has the full list)
- **Never fabricate** labels, quotes, timestamps or speaker identity. **Gold labels come only from humans** (see §6).
- **Persistent-data writes** (Qdrant, OKF, Memgraph/Neo4j, Supabase) always go: dry-run → report → snapshot → **explicit owner approval** → apply. Every write must be idempotent.
- **Never commit or push** unless the owner asks. Other sessions edit this repo in parallel, so run `git status` first and touch only this workstream's paths.
- **Scratch data, audio and models stay outside the repo.** Put them under `~/mukthiguru_attribution_data/…`. Never use `/private/tmp`: it was purged mid-session and lost hours of work.
- **The first-person route stays behind `FIRST_PERSON_MODE`,** with crisis detection in front of it. Ordinary chat is unchanged, including its semantic cache.
- **Every claim you report** is marked VERIFIED, PARTIAL or UNVERIFIED, with its evidence (a command, count or file).

## 2. Current state (verified at handoff unless marked)
| Phase | State | Evidence |
|---|---|---|
| **T1** teacher attribution | **DONE.** Identity is source-only; text mentions produce only `mentions:<t>` tags. Removed 3,121 false Sadhguru/ISKCON/Amma Bhagavan tags from Qdrant (snapshot `spiritual_wisdom_contextual-1111874297854021-2026-09-24-11-36-10.snapshot`). Affected points were credited to both teachers; `teacher_id` untouched. | `backend/services/teacher_attribution.py`, `tests/test_teacher_attribution.py`, `scripts/ops/fix_teacher_tags.py`, lessons L-TEACHER-TAG-1 |
| **B0** honest bench runner | **DONE.** Timeouts, 429s, empty and malformed answers count as errors; retry/backoff and `--resume` work. The 09-19 runs actually had 96.8% and 75.3% errors. | `backend/evaluation/bench.py`, `schema.py`, `tests/test_bench_honesty.py` |
| **B0** data-quality audit | **DONE.** It reproduces the audit numbers. | `backend/scripts/ops/data_quality_audit.py`, `backend/services/transcript_verbatim.py` |
| **B0** full 1,226-question baseline ×2 | **IN FLIGHT** (run 1). Check it; see §3. | `~/mukthiguru_attribution_data/baseline_2026-09-25/` |
| **B0** topology | Local is Memgraph plus Qdrant (14,033 points, 1024-dim dense+sparse, INT8). **Production graph UNVERIFIED:** Railway is down, and the 09-15 audit says Neo4j. | `docs/RAILWAY_GO_NO_GO_2026-09-15.md` |
| **Backend crash** | **FIXED** (2/2 clean smoke runs). Root cause: unbounded native input to the LettuceDetect answer side and to the ONNX embedder (8,192 tokens), both now capped at 1,024. Over-long answers are scored lexically **in full**, which fails closed. **The owner still has to rebuild the container:** `cd backend && docker compose up -d --build backend`. | `lettuce_detect_service.py`, `embedding_service.py`, `tests/test_lettuce_*`, `test_embedding_onnx_max_length_bound.py` |
| **Citation contract** | **DONE.** `timestamp_seconds`, `text_snippet` and `speaker` are carried end to end. The speaker is shown only when voice-verified, and the snippet only comes from `verbatim_text`. A timestamp of 0 is valid, and the hardcoded "Ekams Wisdom" is gone. The browser check is PARTIAL because no data carries timestamps yet. | `app/schemas`, `rag/nodes/citation_extractor.py`, `CitationCard.tsx`, `ChatMessage.tsx`, `tests/test_citation_contract.py`, `src/test/citation-contract.test.tsx` |
| **P0** OKF gates | **DONE and VERIFIED by the lead (2026-09-25): exact Qdrant counts 4,818 / 3,473; extractor copies identical; flag defaults to False; 27 tests pass.**<br>• Extraction gate drops non-verbatim quotes (including partial matches).<br>• Load gate `settings.okf_verbatim_quote_gate` in `OKFStore.list_entries()` is **default OFF**, per the owner.<br>• Shared `strip_fabricated_quotes()` in `transcript_verbatim.py`; both extractor copies delegate to it and are byte-identical.<br>• OKF dry-run: 715 entries, 397 quotes (111 verbatim / 95 partial / 190 not found); 188 entries affected; 174 would be left with no verbatim quote.<br>• Summary labels **APPLIED**, additive payload only:<br>&nbsp;&nbsp;– 3,473 video-less summary points got `first_person_eligible=false` and `provenance_kind=machine_summary`.<br>&nbsp;&nbsp;– 4,818 video-less points in total got `first_person_eligible=false`.<br>&nbsp;&nbsp;– Snapshot `spiritual_wisdom_contextual-1111874297854021-2026-09-25-04-54-26.snapshot`; idempotent re-run made 0 changes.<br>• Tests: `-k okf/label_summary/quote_gate` 2,936 passed; `test_okf_pipeline_integrity` 11 passed. | `app/config.py`, `services/memory/okf_store.py`, `services/transcript_verbatim.py`, both extractor copies, `scripts/ops/okf_quote_gate_report.py`, `scripts/ops/label_summary_points.py`, `tests/test_okf_load_gate.py`, `tests/test_label_summary_points.py`, `~/mukthiguru_attribution_data/p0/okf_quote_gate_report.json` |
| **D1** 8-video bake-off | **DONE.** Parakeet and Whisper large-v3 vote (85–94% agreement). The zero-change punctuation check passed on 8/8. ECAPA speaker ID was correct on both anchor videos, with 0 host leaks. 520/520 clips are exact substrings with valid hashes. **Qwen3-ASR dropped** (161× real-time). Qwen3-ForcedAligner is usable (0.15×). | `COMPARISON.md`, `asr_bakeoff.json` |
| **R** retrieval | **PARTIAL.** No mode wins; the CIs overlap. **`FIRST_PERSON_MODE=retrieval_only` (R0) is chosen**, and R3 stays behind the flag. Top-1 is about 47%, so 99% is not reachable until the gold set, a fine-tuned reranker and calibration exist. | `bakeoff_2026-09-25/scores.json` |
| **D2** ingestion | **PARTIAL.** Done:<br>• verbatim layer, word timestamps and confidence, glossary prompt<br>• fail-closed quarantine gate and OKF gate<br>• `transcript_hash` computed from the verbatim layer and stored in `canonical_segments.json` and `quality_report.json`; a mismatch triggers quarantine<br>• `transcript_hash` and `video_id` carried into the Qdrant payload, additively, on the `_ingest_video` path<br>• end-to-end scratch test (`ingest_e2e_scratch_check.py --run`, video cHAJiF2byzg): 11/11 assertions passed, broken copy quarantined, scratch collection deleted<br><br>**Not done:**<br>• hash not wired into 5 other `EmbedIndexConfig` call sites (enhanced, playlist, raw-text)<br>• chunk-level start/end in the payload (a D3 schema change)<br>• speaker turns, clip boundaries, the two-ASR vote and forced alignment inside ingestion<br><br>Caveat: the end-to-end test's word timestamps were synthetic (interpolated), because no local audio was available. | `transcript_verbatim.py`, `corpus_engine.py`, `ingest/youtube_loader.py`, `ingest/pipeline.py`, `tests/test_transcript_hash.py`, `backend/scripts/ops/ingest_e2e_scratch_check.py` |
| **D1 pilot** (50 videos) | **IN FLIGHT.** It starts after the baseline finishes. | `~/mukthiguru_attribution_data/pilot50_2026-09-25/` |
| **B1** gold tooling | **DONE.** Protocol plus `backend/evaluation/gold/*` (κ, Clopper–Pearson, metrics, video split), with 10 tests. The blank pilot sheets exist. **The owner labels.** | `~/mukthiguru_attribution_data/gold_pilot/` |
| **D3** store rebuild, **F** first-person route, **S5** memory, **P** production | **NOT STARTED.** The production **NO-GO** verdict stands. | — |

Known test state: the backend suite has 7,568 passed and 1 failed. The failure is the mypy ratchet (1,329 vs 1,326), which was already failing at HEAD from other sessions' commits, not from this work. The frontend has 631 passing.

## 3. First actions: reconcile in-flight work
Background agents from the previous session may have died. Check each output directory, then finish or redo whatever is incomplete.
1. **Baseline** (`~/mukthiguru_attribution_data/baseline_2026-09-25/`).
   - If the report is missing or incomplete, re-run `cd backend && QDRANT_URL=http://localhost:6333 .venv/bin/python -m evaluation.bench --mode all --resume …`. Check `--help` for the output and checkpoint flags.
   - Pace it. `/api/auth/anon-session` allows 5 requests per 60 s per IP, and the bench mints one session per question, so use concurrency 1–2.
   - If more than 1% of results are 429s or errors, stop and propose the exact harness change, for example reusing one authenticated eval identity per worker. Never weaken the production limits.
   - Record **two** valid runs and report whether they reproduce within noise.
2. **P0** (`~/mukthiguru_attribution_data/p0/`). Done and verified by the lead. Nothing further is needed.
   - Confirm the numbers in `okf_quote_gate_report.json`, and that the `okf_verbatim_quote_gate` flag exists and defaults to False.
   - For the summary labelling, confirm the dry-run counts (≈3,473 summaries; ≈4,818 points with no video_id), the snapshot name, and that a re-run changes 0 points.
   - If the labelling didn't apply, re-run the dry run and **ask the owner** before applying.
3. **D2 transcript hash and end-to-end test:** done in the previous session (see §2). Re-run `python backend/scripts/ops/ingest_e2e_scratch_check.py --run` after any further ingestion change. It must use a scratch collection only, and you must confirm it was deleted afterwards.
4. **Pilot50** (`pilot50_2026-09-25/`). If it's incomplete, resume it with the same scripts as `bakeoff_2026-09-25/run_all.sh`, and wait for the baseline to finish first (§7).


### Live status at handoff (2026-09-25 10:29 IST)
- **Baseline run 1 is RUNNING**, 26/1,226 questions done. At about 1.2 questions/min, a full run takes about 17 h (each question takes 17–28 s through the full pipeline, run one at a time). Its checkpoint can be resumed.
  - If the process died, resume it with exactly this:
    `cd backend && QDRANT_URL=http://localhost:6333 .venv/bin/python -m evaluation.bench --mode all --concurrency 1 --pace-seconds 15 --max-attempts 3 --max-error-rate 0.01 --resume --out ~/mukthiguru_attribution_data/baseline_2026-09-25/run1_report.json --checkpoint ~/mukthiguru_attribution_data/baseline_2026-09-25/run1.checkpoint.jsonl`
  - To speed it up, use `--concurrency 2 --pace-seconds 12`, which stays under the anon-session limit of 5 requests per 60 s per IP. Watch the 429 share: stop above 1%.
  - Check whether it is alive with `ps -axo command | grep -E "[p]ython.* -m evaluation\.bench"`.
  - Watch progress with `tail ~/mukthiguru_attribution_data/baseline_2026-09-25/run1.log` and `monitor.log`, which record health and RestartCount.
  - Run 2 goes to `run2_report.json` / `run2.checkpoint.jsonl`, and only after run 1 is VALID.
- **The 50-video pilot is RUNNING**, downloading audio (24/50 at handoff).
  - Some videos return YouTube 403. The runner substitutes from `backup_candidates.json` in the same stratum.
  - It waits for the baseline before doing heavy ASR, so it will sit idle for hours while the baseline runs. That's expected.
  - If it died, run `cd ~/mukthiguru_attribution_data/pilot50_2026-09-25 && ./venv/bin/python run_pilot.py`. It resumes, and a finished video is never redone.
  - Log: `logs/run_pilot.log`. The scripts in the directory are run_asr / run_vote / run_align / run_punct / run_speaker / run_clips.
- **Decide the ordering.** If the owner wants the pilot sooner, pause the baseline (stop the process; `--resume` continues later), let the pilot run its ASR, then resume the baseline. Never run both heavy jobs at once: that causes false timeouts.
- **The session scratchpad at /private/tmp was purged twice.** Everything that matters is under ~/mukthiguru_attribution_data/.

## 4. Owner decisions already made (don't re-ask)
- **Serving mode:** `retrieval_only` (R0) is the default. R3 stays behind the flag and is deleted only after production data confirms the choice.
- **Weak match:** show the closest clip labelled **"Related, not a direct answer"**. Up to 3 clips, at most 1 per video, plus a full-video link.
- **OKF quote load gate:** build it and report, but **don't enable** it.
- **Video-less summaries:** labelled and kept in general chat, never used as first-person.
- **Compute:** a **50-video pilot first**, then decide on the full corpus.
- **Gold labels:** the **owner labels the pilot** as annotator A.
- **Teacher tags:** the corpus is Preethaji & Krishnaji. `teacher_id` waits for voice attribution, because title-based labels scored no better than the current ones against the voice census.

## 5. Remaining work, in order (gates from the spec)
1. **Finish B0:** two valid baseline runs, reproducible, with system errors under 1%.
2. **Finish P0:** see §3.
3. **D1 pilot analysis.**
   - Summarise `pilot_report.json`: RTF, agreement, and the videos where the voice contradicts the title. In the bake-off, two joint-titled videos turned out to be single-speaker.
   - Recommend a compute plan for the full corpus. Options: Parakeet for everything plus Whisper only on disputed spans; a rented GPU; or full two-ASR.
   - **Ask the owner** before starting the full corpus.
4. **D2 completion.** Build it all in the shared ingestion pipeline, never as one-off scripts:
   - speaker turns from voiceprints (reuse the `bakeoff_2026-09-25/run_speaker.py` logic, the anchor clips, and the `~/mukthiguru_attribution_data` voiceprints);
   - turn-based clip boundaries that exclude host words;
   - the two-ASR vote as an optional stage behind a setting;
   - forced alignment.

   Every new video must produce the verbatim and display layers, word timestamps, speaker turns, clips, a transcript hash, and `quality_report.json` with its quarantine flag. Nothing is indexed if the gate fails. Gate: the end-to-end scratch test passes.
5. **D3 versioned store.**
   - Create a new Qdrant collection (e.g. `first_person_v1`) whose payloads are pointers: video_id, start_ms/end_ms, speaker, transcript_hash, group_id, source_url, teacher identity, provenance and quality status.
   - It has three fields: passage dense, passage sparse, and a separate **question** field (the host question plus offline-generated questions, **never embedded in the passage text**).
   - Rebuild twice; the IDs must be identical. Keep the old collection. Swap the alias only after all gates pass **and the owner approves**.
6. **R.**
   - Tune the convex fusion weights on labelled data.
   - Fine-tune a small cross-encoder (Ettin or ModernBERT, Apache-2.0; verify the licence) on in-domain pairs with hard negatives, split by video, and test only on human-gold questions. Export to ONNX INT8 and update the allowlist in `services/onnx_reranker.py`.
   - Fit a logistic calibrator with an SGR threshold (risk 1%, δ 5%), and report the precision/coverage curves. **The owner picks the operating point.**
   - To claim at most 1% error you need a one-sided 95% Clopper–Pearson bound on ≥628 confident gold answers, with a clustered bootstrap.
7. **F: the first-person route** behind `FIRST_PERSON_MODE`.
   - Path: crisis check → exact cache (**no semantic cache on this route**) → hybrid retrieval over `first_person_v1` → rerank → calibrated decision → 1–3 clips → render from the verbatim layer → exact-substring and hash check → citations → timestamped playback.
   - Add backend, frontend and **browser** tests: the clip starts at the right second, and the speaker is named only when verified.
   - The ordinary chat regression suite must stay green.
8. **S5** (a separate workstream) and **P** (production hardening), per the spec. The NO-GO stands until there's evidence against it.

## 6. Labelling: what AI may and may not do
**Gold labels are human-only.** This is a hard rule: without it the ≥99% claim is circular and indefensible.

**AI MAY:**
- Prepare and extend the blank sheets with `backend/evaluation/gold/sheets.py`.
- Produce a **silver** file, `gold_pilot/silver_*.json`, separate from the gold CSVs and never written into them. For each relevance row it holds:
  - a proposed label;
  - the evidence: the exact transcript span and timestamp;
  - an audio-grounded check where possible: re-run ASR and speaker ID on that clip's audio from the pilot50 or bake-off audio.
- **Check videos end to end for labelling readiness:** audio available, transcript present, hash matches, speaker turns plausible against the voiceprints, clip boundaries within the video duration, no host speech inside teacher clips. Flag every anomaly for human review.
- **Validate filled sheets:** schema, blanks, contradictions, and at most 3 questions per video.
- Compute Cohen's κ and the adjudication queues with `agreement.py`, and prioritise human review where the silver and human labels disagree.
- Build a small local review helper, such as a static HTML page or a CLI, that plays each clip at `start_ms` next to its text so human labelling goes fast.

**AI MUST NOT:**
- fill in `judge_a`, `judge_b`, `adjudicated`, `question_text` or `equivalent_group` in the gold sheets;
- author gold questions from target passages;
- show silver labels to an annotator **before** they have labelled (the protocol is blind);
- report silver-based numbers as accuracy. Report silver only as "silver/unverified".

**Note:** `gold_pilot/relevance_pilot.csv` currently uses the 116 AI-authored bake-off questions. It's useful for calibrating retrieval, but it is not the non-circular gold set. The gold set is `question_authoring_pilot.csv`, whose 150 questions the owner writes.

## 7. Environment gotchas (learned the hard way)
- **Detect a running benchmark** with `ps -axo command | grep -E "[p]ython.* -m (evaluation\.bench|benchmarks\.run)"`. This is the **only verified method**. **Never `pgrep -f`**: it matches its own command line and waits forever. **Never `ps aux | grep bench`**: that also matches the grep process itself.
- **macOS has no `timeout` command.**
- **Docker:** if `docker` isn't found, run `export PATH="$HOME/.docker/bin:$PATH"`. The backend container is `mukthiguru-backend`.
- **Qdrant from the host:** export `QDRANT_URL=http://localhost:6333`, because the `.env` hostnames are compose-internal.
- **Shared Mac:** don't run heavy ASR while a benchmark is running, because it causes false timeouts. Wait for the benchmark to clear.
- **Crash detection:** check `docker inspect mukthiguru-backend --format '{{.RestartCount}}'` before and after load, and grep the logs for `fatal|segment|libgomp`.
- **Keep the repo clean:** set `PYTHONDONTWRITEBYTECODE=1` so no `__pycache__` lands in the repo, and keep speechbrain's `pretrained_models/` out of it.
- **Model caches** live in `~/.cache/huggingface/hub`. The Qwen3-ASR cache (~4.7 GB) can be deleted once the owner agrees.
- **Blind label files:** never open `docs/attribution/label_*.csv`, `pilot_audit_60_quotes*`, `*_KEY.json`, or the prediction files for videos with open label sheets.
- **Extractor copies:** `backend/scripts/extract_okf_from_stores.py` and `scripts/extract_okf_from_stores.py` must stay byte-identical. Check with `cmp`.
- **Cost:** keep agent contexts small. Summarise JSON with one-liners and tail logs. Long-context agents hit usage limits repeatedly in the last session.

## 8. Ask the owner before
- any Qdrant/OKF/graph apply;
- enabling the OKF load gate;
- the full-corpus compute plan;
- accepting gated or non-commercial model licences (pyannote needs terms acceptance; DiariZen and Sortformer v1 are non-commercial);
- the precision/coverage operating point;
- deleting losing modes or models;
- the alias swap;
- production traffic;
- copying `scripts/ingestion/corpus` into the Docker image. Without it, OKF extraction inside the container strips every quote (and logs why);
- any commit or push.

## 9. Verification (run before you claim a phase done)
```bash
cd backend
.venv/bin/pytest tests/test_teacher_attribution.py tests/test_cross_tenant_leak_probe.py tests/test_citation_contract.py tests/test_bench_honesty.py tests/test_gold_eval.py tests/test_data_quality_audit.py tests/test_okf_extractor_transcript_quote_gate.py tests/test_lettuce_shed_no_native_race.py tests/test_lettuce_answer_length_bound.py tests/test_embedding_onnx_max_length_bound.py -q
.venv/bin/pytest tests/ -q -p no:cacheprovider          # expect only the known mypy-ratchet failure
cd .. && npx vitest run && npm run build
cmp backend/scripts/extract_okf_from_stores.py scripts/extract_okf_from_stores.py
git diff --check && git status --short
```

## 10. Report format (after every phase)
A table with the columns: Phase | Result | Evidence (command/count/file) | Confidence (VERIFIED/PARTIAL/UNVERIFIED) | Still unproven. Then list:
- the files changed;
- the exact next gate;
- anything that needs the owner.

Remind the owner that these still block launch after every gate:
- native-speaker crisis review and a clinician reviewer;
- content-rights/Ekam approval;
- Railway is down, and Supabase is on the Free plan with zero backups;
- PLAN.md Phases C–I;
- mobile store accounts.

---

## Appendix A — how to run this with subagents
- **Work shape.** Run long. Split every phase into self-contained subagent tasks. Run read-only or independent tasks in parallel; run persistent-data writes one after another, with owner approval.
- **Brief contents.** Each brief below is self-contained: paste it as the subagent's task. Every brief inherits §1 (non-negotiables) and §7 (gotchas). Tell each subagent to read those two sections of this file first.
- **Model choice.** Use a fast/cheap model for read-only checks and a strong model for design or safety-critical code.
- **Keep subagent contexts small.** They should tail logs and summarise JSON with one-liners. In the last session, agents at 300–450k tokens of context kept dying on usage limits.
- **Outputs go to disk.** Every subagent writes to a persistent directory under `~/mukthiguru_attribution_data/` and ends with a short report: files changed, commands run, numbers, and VERIFIED/PARTIAL/UNVERIFIED per claim.
- **Verify every subagent report yourself** by re-running its key command. A summary is not proof. In the last session this caught:
  - a fake "exit 0" (the command never ran);
  - a mis-measured 0.01 pass rate (it compared the wrong transcript);
  - a self-matching `pgrep` deadlock;
  - a fail-open truncation.
- **After each phase,** run an independent read-only review subagent on the diff (brief R-REVIEW below).

## Appendix B — subagent briefs (copy one per task)

### B0-BASELINE — honest full benchmark (runs for hours)
**Already done:** The bench runner fix is done (tests/test_bench_honesty.py, 18 tests). The 09-19 runs were re-scored as INVALID (96.8% and 75.3% errors), and the 20-question smoke runs were clean after the crash fix. **Run 1 is in progress:** 26/1,226 at handoff, concurrency 1, pace 15 s, checkpoint `baseline_2026-09-25/run1.checkpoint.jsonl`. Resume it with the exact command in §3 'Live status'. Do NOT restart from zero.
**Next after this:** Two reproducible valid runs close B0. Their per-source numbers become the regression baseline that F must not fall below. Then hand off to D3/F.
> Run the honest full AskMukthiGuru benchmark baseline, phase B0. The repo is /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8, and the backend venv is backend/.venv. No code edits, no Docker restarts, never print secrets, no commits. Write outputs under ~/mukthiguru_attribution_data/baseline_2026-09-25/.
>
> 1. **Pre-check.** `/api/health` must return ready:true. Record the RestartCount. Confirm no other bench is running, using the `ps … grep "[p]ython.* -m (evaluation\.bench|benchmarks\.run)"` check. Read `.venv/bin/python -m evaluation.bench --help`.
> 2. **Pacing.** The anon-session endpoint allows 5 requests per 60 s per IP, so use concurrency 1–2. Stop after about 20 questions if 429s exceed 1%, and propose a harness fix instead. Never weaken production limits.
> 3. **Run.** `cd backend && QDRANT_URL=http://localhost:6333 .venv/bin/python -m evaluation.bench --mode all --resume --max-error-rate 0.01 …`, with output and checkpoint paths in the baseline dir. Run it in the background and monitor it.
> 4. **Report:** n_success/n_error by class, system_error_rate, VALID/INVALID, quality metrics per source (successful rows only), p50/p95, RestartCount before and after. Then do a second run and state whether the two reproduce within noise.

### P0-FINISH — OKF load gate and summary labels
**Already done:** P0 is COMPLETE per the worker report above: the gate is built and OFF, the dry-run report exists, and the summary labels are applied with a snapshot and an idempotent re-run. This brief is now for VERIFICATION ONLY:
- `cmp` the two extractor copies.
- Count in Qdrant, with an exact count on a filter: `first_person_eligible=false` should be 4,818 and `provenance_kind=machine_summary` should be 3,473.
- Confirm `okf_verbatim_quote_gate` defaults to False.
- Re-run the two tests.
**Next after this:** D3 must include only points with `first_person_eligible` != false in first_person_v1. Enabling the OKF load gate (174 entries would lose all their quotes) is an OWNER decision: present the report JSON first.
> Finish phase P0 for AskMukthiGuru. The owner decided: build the OKF load-time quote gate but keep it OFF (`settings.okf_verbatim_quote_gate`, default False, applied in `OKFStore.list_entries()`), plus a dry-run report; and LABEL video-less summary points (`first_person_eligible=false`, `provenance_kind="machine_summary"`), keeping them in general chat.
> - Check `~/mukthiguru_attribution_data/p0/` and the git diff for work already done. Finish whatever is missing.
> - OKF report: `backend/scripts/ops/okf_quote_gate_report.py`, read-only.
> - Summary labels: `backend/scripts/ops/label_summary_points.py`, following the pattern of `fix_teacher_tags.py`. Dry run by default; snapshot before `--apply`; payload-only and additive.
> - Apply only if the counts are within ±5% of 3,473 summaries and 4,818 points without video_id, **and the owner confirms**.
> - Prove idempotency: a re-run must report 0 changes.
> - Tests: flag off → unchanged; flag on → fabricated and partial quotes removed, verbatim quotes kept. The two extractor copies must stay byte-identical (`cmp`).

### D1-PILOT50 — new transcript design on 50 videos
**Already done:** The 8-video bake-off is done (COMPARISON.md). Parakeet runs at 0.013–0.037× RTF and Whisper large-v3 at 0.45–1.66×. The two ASRs agree on 85–94% of words, and the zero-change check passed 8/8. Speaker ID is correct on both anchors, and 2 videos titled as joint talks are single-speaker. 520/520 clips are self-consistent. Qwen3-ASR was dropped (161× real-time); the aligner is usable (0.15×). **The pilot is in progress:** `pilot50_2026-09-25/` has videos.json (50 chosen, stratified, including the 8 bake-off videos and the gold-pilot videos), backup_candidates.json, run_pilot.py and run_align.py (aligner added). Audio download was at 24/50, and some 403s were substituted. It waits for the baseline before ASR. Resume with `./venv/bin/python run_pilot.py`; it doesn't redo finished work.
**Next after this:** Recommend a full-corpus compute plan (Parakeet for everything plus Whisper on disputed spans, a rented GPU, or full two-ASR) and ASK the owner. The pilot outputs feed D2-SPEAKER-CLIPS (real audio for the end-to-end test) and D3 (first 50 videos in first_person_v1).
> Run the owner-approved 50-video pilot. Reuse ~/mukthiguru_attribution_data/bakeoff_2026-09-25/ (scripts run_asr/run_vote/run_punct/run_speaker/run_clips/run_all.sh, and a venv with faster-whisper-large-v3, parakeet-mlx, punctuators and speechbrain). Workdir: ~/mukthiguru_attribution_data/pilot50_2026-09-25/. The repo is read-only.
> - **Videos.** Choose 50 non-empty, non-quarantined videos from scripts/ingestion/corpus: about half interview and half monologue, spread across years. Include the 8 bake-off videos and the 50 videos in gold_pilot/question_authoring_pilot.csv.
> - **Audio.** yt-dlp audio-only with `--sleep-requests 2 --sleep-interval 5` and one retry. Reuse cached audio where it exists.
> - **CPU.** Before each video's ASR, wait until no bench is running (§7).
> - **Pipeline.** parakeet → whisper → vote → Qwen3-ForcedAligner (0.15× RTF; add it if it's not already in the scripts) → punctuation with a zero-change assert → ECAPA speaker ID (voiceprints in ~/mukthiguru_attribution_data) → clips.
> - **Report** in pilot_report.json and PILOT.md:
>   - RTF distribution;
>   - agreement and disputed rate;
>   - assert pass rate;
>   - speaker shares, and videos where the voice contradicts the title/metadata;
>   - host leaks;
>   - clip self-consistency (exact substring of the clip's OWN verbatim layer, plus a hash match);
>   - wall time and disk;
>   - extrapolation to the ~650 h corpus.
> - Don't claim which transcript is correct: there is no human reference.

### D2-SPEAKER-CLIPS — finish shared ingestion
**Already done:** Done: the untouched verbatim layer plus a display layer, word timestamps and confidence, a glossary initial_prompt of ≤30 terms, and a configurable ASR model. The fail-closed quarantine gate is a hard import. `transcript_hash` is written to canonical_segments.json and quality_report.json, and a mismatch triggers quarantine. video_id and transcript_hash are in the Qdrant payload on the `_ingest_video` path. The end-to-end scratch test passes 11/11. Teacher attribution is source-only, and the OKF extraction gate is live.
**Next after this:** Once this passes, D3 builds first_person_v1 from these clips. Re-run the end-to-end check and R-REVIEW on the diff.
> Finish phase D2 inside the SHARED ingestion pipeline (scripts/ingestion/parallel_corpus_extractor.py, corpus_engine.py, backend/ingest/pipeline.py, services/qdrant/indexer.py). No one-off scripts.
> - Port the bake-off logic from ~/mukthiguru_attribution_data/bakeoff_2026-09-25/run_speaker.py and run_clips.py (and run_vote.py as an OPTIONAL stage behind a setting) into ingestion:
>   - speaker turns from ECAPA voiceprints, with a threshold plus margin, anchored on human-confirmed clips (hUmlujE6SN0@563s = Preethaji, rGcNJ_Nsuy8@386s = Krishnaji);
>   - turn-based clips with host words excluded, padded 150–300 ms and snapped to silence;
>   - a per-clip `transcript_hash`;
>   - Qwen3-ForcedAligner word times.
> - Wire `transcript_hash` into the 5 remaining `EmbedIndexConfig` call sites in ingest/pipeline.py (enhanced, playlist and raw-text paths).
> - Everything is fail-closed: on a gate failure the video is quarantined and not indexed.
> - Tests: unit tests plus the end-to-end run `backend/scripts/ops/ingest_e2e_scratch_check.py --run`, which uses a scratch collection only and deletes it afterwards. Use real audio from pilot50 where you can, so word timestamps are real rather than interpolated.
> - Run `pytest tests/ -k "ingest or okf or corpus or transcript or quality or teacher"`. It must stay green.

### D3-STORE — versioned first-person collection
**Already done:** Nothing is built yet. Its inputs are D2 clips (speaker turns, clip boundaries, hash) and the pilot50 outputs. Decided: first-person serving uses retrieval_only; summaries are excluded from first-person. Measured on the bake-off: the host-question field did not help untuned, so tune fusion in R.
**Next after this:** R-RETRIEVAL tunes on first_person_v1 with the human gold set. Then F serves from it. The alias swap only happens with owner approval.
> Build a NEW Qdrant collection `first_person_v1`. Never mutate `spiritual_wisdom_contextual`.
> - **Source.** Build it from D2-hardened, gate-passing videos only (start with the pilot50 set).
> - **Points** are pointers: video_id, start_ms, end_ms, speaker, speaker_confidence, transcript_hash, group_id (near-duplicate teaching group via MinHash, then cosine 0.87–0.90), source_url, teacher identity (source + voice), provenance, quality_status, first_person_eligible=true.
> - **Vectors:** named dense (BGE-M3 1024, INT8) and sparse passage vectors, plus a separate `question` vector for the host question plus 5–15 offline LLM-generated, Doc2Query-filtered questions. Never embed questions into the passage text.
> - **Determinism:** rebuild twice; the IDs and payloads must be identical.
> - **Invariant:** every point's verbatim_text is an exact substring of its video's verbatim layer, and the hash matches.
> - **Rollback:** keep the old collection. The alias swap happens ONLY after all gates pass and the owner approves.
> - Payload-write rules from §1 apply.

### R-RETRIEVAL — fusion, reranker fine-tune, calibration
**Already done:** The bake-off R0–R3 is done: strict top-1 ≈0.47 with overlapping CIs; the untuned prod reranker (temsa mMiniLMv2) didn't help; R3 (LLM) added 8–26 s for no gain. retrieval_only was chosen. The research recommends a question field, a fine-tuned small reranker, and a logistic calibrator with SGR. Gold tooling exists (backend/evaluation/gold/*, Clopper–Pearson verified). Human labels are pending: the owner is annotator A.
**Next after this:** Give the owner the precision/coverage curve to pick the operating point. Then F uses the calibrated threshold. Re-test R3 only after the reranker and gold data exist.
> Improve first-person retrieval on `first_person_v1`. Baseline: R0 (hybrid, no LLM, the chosen default). The bake-off gave strict top-1 of about 0.47.
> - **Fusion.** Tune convex fusion weights across passage-dense, passage-sparse and question fields, on the TRAIN split of human-labelled data (backend/evaluation/gold/split.py).
> - **Reranker.** Fine-tune a small Apache-2.0 cross-encoder (Ettin/ModernBERT; verify the licence) on in-domain question–passage pairs with 5 mined hard negatives, split by video. Test only on human-gold held-out questions. Export ONNX INT8 and update the allowlist in services/onnx_reranker.py. Latency budget: p95 under 1 s for the top 20–30.
> - **Calibration.** Fit a logistic calibrator (features: top-1 score, top-1 minus top-2 margin, lexical overlap, question-field hit, query type) with an SGR threshold (risk 1%, δ 5%).
> - **Report:** strict and group top-1/top-3 with CIs clustered by video, precision/coverage curves, and unanswerable handling. Use backend/evaluation/gold/metrics.py (Clopper–Pearson).
> - The owner picks the operating point. Never claim ≥99% below 628 confident gold answers.

### F-ROUTE — first-person serving path
**Already done:** The citation contract is done end to end: timestamp_seconds, text_snippet, speaker (voice-verified only), and a timestamp of 0 is valid. The hardcoded 'Ekams Wisdom' is removed, 631 frontend tests pass, and the browser check is PARTIAL (no timestamps in data yet). Crisis detection exists in the pipeline. `FIRST_PERSON_MODE` is decided but not yet implemented in code.
**Next after this:** Canary behind the flag, then an owner decision on production traffic. Monitoring: answer/abstain/thumbs-down rates, a weekly audit of 50–100 confident answers, and a 20% quarterly gold refresh. Production still needs the P gates (NO-GO stands).
> Implement the first-person route behind `FIRST_PERSON_MODE` (retrieval_only default; off in production until the owner approves).
> - **Path:** crisis/safety pre-check (reuse the existing distress stage, unchanged) → exact-match cache (NO semantic cache on this route) → hybrid retrieval on first_person_v1 → rerank → calibrated decision → 1–3 clips (at most 1 per video) → text rendered only from the verbatim layer → exact-substring and transcript_hash check (drop the clip on failure) → citations {video_id, timestamp_seconds, text_snippet, speaker only if voice-verified, provenance/verbatim status} → full-video link.
> - **Below threshold:** return the closest clip labelled "Related, not a direct answer".
> - **Scope:** no knowledge-graph call. Tenant isolation, rights policy and ordinary chat stay unchanged.
> - **Tests:** backend, frontend (Vitest), and a BROWSER check that the clip starts at the right second and no unverified speaker is named. The full backend suite must still pass, apart from the known mypy ratchet.

### LABEL-ASSIST — prepare and QA labelling (AI never writes gold)
**Already done:** Done: the B1 protocol (docs/agent/B1_gold_set_protocol.md), and tooling in backend/evaluation/gold/ (sheets, κ, metrics, split; 10 tests). Blank pilot sheets are in ~/mukthiguru_attribution_data/gold_pilot/: question_authoring_pilot.csv (150 rows, 50 held-out videos, 60/20/20 mix) and relevance_pilot.csv (2,129 rows pooled from the bake-off R0–R2, no scores or ranks; its questions are AI-authored, so it's calibration-only). Nothing is labelled yet.
**Next after this:** Once the owner and a second annotator have labelled: compute κ, adjudicate, and hand the held-out gold set to R-RETRIEVAL. Scale toward ~2,000 questions over time.
> Help the owner label the B1 pilot. Follow §6 strictly: AI never fills judge_a, judge_b, adjudicated, question_text or equivalent_group.
> 1. **Readiness check per video** in gold_pilot and pilot50: audio present, transcript present, hash valid, speaker turns plausible against the voiceprints, clip bounds within duration, no host speech in teacher clips. Write gold_pilot/readiness_report.json and flag anomalies.
> 2. **Silver pre-labels** in a SEPARATE file, gold_pilot/silver_relevance.json. For each row: a proposed label, the exact supporting transcript span and timestamp, and an audio-grounded re-check where audio exists. Never show these to an annotator before they have labelled.
> 3. **Review helper:** a local static HTML page, outside the repo in ~/mukthiguru_attribution_data/gold_pilot/review/, that lists each relevance row with an embedded YouTube player at `start`, the clip text, and editable label fields. It saves to the owner's CSV only when the human clicks. No auto-fill.
> 4. **After the human labels:** validate the sheets, compute κ (backend/evaluation/gold/agreement.py), and build adjudication queues that put silver/human disagreements first.

### R-REVIEW — independent review after each phase
**Already done:** Earlier reviews found, and the lead fixed: OKF partial quotes passing the gate; a LettuceDetect generic fallback still racing ONNX; a broken __main__ self-check; answer truncation leaving the tail unchecked (fail-open); OKF extraction in the container silently stripping every quote (now logs an error).
**Next after this:** BLOCK findings must be fixed and re-reviewed before a phase is reported done.
> Do an independent, read-only, ruthless review of this phase's diff (`git diff -- <paths>`) against docs/agent/first_person_baseline_prompt.md (non-negotiables and invariants), plus root CLAUDE.md "Faithfulness verification" and "Native model concurrency invariant".
> - **Hunt for:** fail-open paths, partial scoring, unverified speaker naming, non-verbatim text shown as the teacher's words, host words attributed to a teacher, bypassable gates, native-model races, silent fallbacks, vacuous tests, and persistent writes without dry-run and approval.
> - **Output:** PASS or BLOCK, then findings most-severe first. One line each: path:line, the failure scenario, the fix, and confidence.

### OPS-CRASH-VERIFY — after any backend rebuild
**Already done:** The segfault root cause was found and fixed: unbounded native input lengths, plus lexical-only fallbacks. It passed 2/2 clean runs on the rebuilt container. The final fail-closed change to over-long answers is NOT in the running container until the owner rebuilds. A previous one-off pass was later contradicted by a crash, so 2 clean runs are the minimum.
**Next after this:** If it crashes again, capture the faulthandler stack and route it to a fix brief. If it holds, B0-BASELINE can run.
> Verify the backend is stable after a rebuild. Record RestartCount. Confirm no benchmark is running. Run the 20-question smoke test twice at concurrency 2: `cd backend && QDRANT_URL=http://localhost:6333 .venv/bin/python -m evaluation.bench --mode e2e --limit 20 --concurrency 2 --max-attempts 2`. Then grep the logs for `fatal|segment|libgomp|Unable to create tensor|DequantizeLinear`.
>
> Verdict: FIX HOLDS (2/2 clean with RestartCount flat), CRASHED AGAIN (capture the faulthandler stack), or INCONCLUSIVE (with the reason).
