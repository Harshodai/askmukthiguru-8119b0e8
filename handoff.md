# AskMukthiGuru — Session Handoff (first-person verbatim route)

## 2026-09-28 — consolidated handoff, all lanes (read this first)

Written by the "First-person production hardening plan" session with the other two live sessions ("Session handoff and warning remediation" = committer, "AskMukthiGuru engineering W0–W6" = crisis lane). Each lane owner corrects **only its own subsection in §10**, in place. Labels: **VERIFIED** = re-run by the writing session with the command/file shown; **REPORTED** = measured by another session, not re-run here; **PENDING** = not yet measured.

### 0. Resume in 5 minutes
1. Read `docs/agent/SESSION_COORDINATION.md`: lanes, single committer, restart and Qdrant rules.
2. Read `.claude/tasks/first-person-prod-hardening-2026-09-28.md` (plan rev 2, task cards B1–B5, C1, C2, S1).
3. Read `docs/agent/EXPERIMENT_LEDGER_2026-09-27.md` for measured numbers and the commands that produced them.
4. `git log --oneline -8` on branch `fix/first-person-harness-translation-crisis-2026-09-28`. The owner pushes; agent pushes are denied by permission settings.
5. Check `~/mukthiguru_attribution_data/eval_v6/` for the independent v6 vs v2 vs v5 eval (running at the time of writing).

### 1. Goal
A first-person answer IS Sri Preethaji's / Sri Krishnaji's own recorded words: right speaker, exact second, **a complete thought** (FP invariants 10/11). It is served as a pointer to a verified clip, with no LLM at serve time. Target: ≥99% precision on confident answers, proven on human gold (≥299 confident items with 0 errors). Until then, every answer is "Related, not a direct answer." Near-term goal: a v6+ index that beats the live v2 on the pinned harness, with clean clip boundaries and no more host leak.

### 2. Current state
- **Commits (branch above):** `d1e9d019` harness + real translation + crisis-routing gaps → `fc100964` B2 sentence snapping, per-clip ASR disputed rate, B4 guard, PCS → `c1ccd2b8` dangling conjunction drops the clip, not the video → `011fc135` boundary module, boundary audit, question generator → `0147a240` coordination doc. Owner pushed up to `d1e9d019` (REPORTED).
- **Serving:** local backend `FIRST_PERSON_COLLECTION=first_person_v2` (pinned-harness winner). The route is off by default (`FIRST_PERSON_ROUTE_ENABLED`). No calibration profile, so there are 0 direct answers.
- **Qdrant first-person collections:**

| Collection | Points | Built from | Status |
|---|---|---|---|
| v1, v3, v4 | — | older builders | historical; not deleted. v3 (boundary-fixed, 202 pts, REPORTED) was never A/B'd |
| v2 | REPORTED 280 | earlier builder | **live**; top-1 0.438/0.427 (two runs); host leak 8.6%; 72 `rights_cleared=false` clips served only because `FIRST_PERSON_SERVE_UNREGISTERED=true` locally (REPORTED) |
| v5 | 260 | passages_B (old fragment-prone builder) | 9.23% boundary-clean (VERIFIED); top-1 0.382–0.398, host leak 11.2% (REPORTED) |
| **v6** | **147 (VERIFIED, status green)** | passages_C + B2 shrink snap, 45 videos (pilot50 + bakeoff) | written 2026-09-28 under the owner's delegated decision; applied IDs == dry-run IDs; **not served**; eval PENDING |

- **Tests (VERIFIED 2026-09-28):**
  - Full backend suite: 8,133 passed / 4 failed / 12 skipped, with `test_build_first_person_index.py` deselected while it was being edited.
  - All 4 failures were in `test_crisis_w2_expansion.py`, during the crisis lane's mid-edit. After that lane's 03:00 test update, 1 remains: `test_kill_myself_laughing_is_a_known_accepted_false_positive`. It is stale versus the intentional `IDIOM_EXCLUSIONS_RE` and is with the crisis agent.
  - First-person focused set: 149 passed.
  - `evals/run_safety_scenarios.py` ran. A mechanical pass is not a safety sign-off.
- **Flags added:** `first_person_boundary_guard_enabled` (B4, default **off**: it would quarantine 166/280 v2 and 177/260 v5 clips, REPORTED), `first_person_rerank_enabled` (default off), and the `--snap-boundaries` / `--max-disputed-rate` builder flags.

### 3. Files actively being edited (never commit another lane's mid-edit files)
- **Crisis lane (W0–W6), MID-EDIT, unverified:** `services/serene_mind_engine.py`, `app/pipeline/stages/distress_stage.py`, `guardrails/lightweight_handler.py`, `tests/test_crisis_w2_expansion.py`, `scripts/ops/measure_distress_llm_escalation.py` (untracked).
- **Committer lane:** `scripts/ops/build_first_person_index.py`, `services/first_person_pipeline.py`, `app/api/first_person.py`, `evaluation/first_person_harness.py` + tests. Stable as of `c1ccd2b8`.
- **First-person boundaries lane (writer of this entry):** nothing mid-edit. Committed in `011fc135`: `backend/ingest/verbatim/boundaries.py`, `backend/scripts/ops/{audit_first_person_boundaries,generate_first_person_questions,measure_first_person_boundary_repair}.py` + tests, and the plan file.

### 4. What was tried and failed or was rejected
| Try | Result | Why |
|---|---|---|
| Plan rev 1 §6.4 RAG-Fusion (LLM rewrites per query) | rejected before building | LLM at serve time breaks FP invariant 1; the offline form is C1 |
| `linto-ai/whisper-timestamped` | rejected | AGPL-3.0 |
| `deepmultilingualpunctuation` | rejected | no Indic languages; repo already ships `punctuators` `pcs_en` |
| Late chunking (jina) on BGE-M3 | deferred | jina-v2 models only; re-embeds 14k general-RAG points; outside FP scope |
| Hard-coded "situational trap" gate (Yasme/Nomi, "addiction") | rejected | overfit: passages_C introduces "Two monks, Yasmi and Nomi" properly, so the trap was a passages_B fragmentation artifact |
| Old audit `scripts/ops/audit_first_person_v5.py` | retired (moved out of tree) | its regexes were copied from the clips it scored (circular). The generic re-audit still gave v5 = 24/260 clean, so the headline number held |
| Grow-back (B3): extend a clip's start to its sentence start within the same teacher label | no gain: 226 vs 227 clean, +214 words | 139/153 mid-sentence heads are preceded by `O`/`?` labels, so growing is blocked. Root cause is S1 |
| First B2 run, clips mapped to words by time window (REPORTED) | lost 31 clips as `span_not_found` | clip edges aren't on word timings; fixed by anchoring on the exact word sequence (0 lost) |
| Reranker A/B on v2 (REPORTED) | 0.427 fusion vs 0.416 rerank, p=1.0, p50 10 → 197 ms | no gain at 20× latency; stays off |
| Sentence-level builders v4/v5 (REPORTED) | host leak 15.5% / 11.2% vs v2 8.6%; v5 top-1 0.398 vs v2 0.42–0.45 (p=0.48) | finer clips cut into host turns |
| C1 smoke before setting Redis | "OpenRouter budget ledger unavailable" | the budget ledger needs the authenticated Redis; set `REDIS_URL` to the `.env` URL with host → `localhost` |

### 5. Results per try
| Measurement | Result | Source |
|---|---|---|
| Generic boundary audit, v5 (VERIFIED) | 260 clips, 24 clean (9.23%), head defects 197, tail 177 | `docs/evidence/first_person_boundaries_first_person_v5_2026-09-28.json` |
| Generic audit, passages_C ≥ 8 s (VERIFIED) | 295 clips, 112 clean (37.97%), head 182, tail 10 (before the And/So/Or decision) | `docs/evidence/first_person_boundaries_pilot50_2026-09-25_passages_C__bakeoff_2026-09-25_passages_C_2026-09-28.json` |
| Repair strategies on 295 passages_C clips (VERIFIED) | none 92 clean (31.2%); shrink 269 survive / 227 clean (76.9%) / 153 clean and ≥ 18 s; grow 226 clean | `docs/evidence/first_person_boundary_repair_2026-09-28.json` |
| B2 builder dry run (REPORTED) | baseline 174 / 73 clean (42%); snapped 147 / 127 clean (86%); 90 snapped, 26 `boundary_unrecoverable`, 27 < 8 s; ASR disputed-word rate median 3.5%, p90 25%; 78% of clips have ≥1 disputed word | `~/mukthiguru_attribution_data/v6_dryrun_2026-09-28/` |
| v6 apply (VERIFIED) | 147 points, 45 videos (79 Preethaji / 68 Krishnaji), IDs == dry-run IDs | `~/mukthiguru_attribution_data/v6_apply_2026-09-28/report_20260928T062402Z.json` |
| C1 generator smoke, 3 v5 clips, OpenRouter 8B (VERIFIED) | 15 generated, 8 kept by self-retrieval on the real hybrid retriever (53%) | scratch run |
| v6 vs v2 vs v5, pinned harness, twice each | **PENDING** | `~/mukthiguru_attribution_data/eval_v6/` |

### 6. What we learned
1. **Fix the builder, not the gate.** 90% of v5's defects came from building on passages_B. The v2 builder plus a sentence snap moves boundary-clean clips from about 9% to 77–86% with no new engine.
2. **Clip heads are a speaker-diarization problem, not a text problem.** The teacher's first 1–6 words land under host/unknown labels (example: `It[O] is[O] | beyond attitudes.`), so text trimming can only drop them. The listening sheet decides whether to relabel.
3. **Audits must use generic rules.** An audit built from the failures it scores can't be trusted, even when its headline happens to hold.
4. **Measure the retriever the product uses.** C1's doc2query filter calls `FirstPersonStore.search_hybrid` (dense + sparse), not a copy of it.
5. **Top-1 gaps under ~0.05 on ~83 questions are noise** (L-EMBED-DRIFT-1: identical builds differ by 2–4 questions). Record encoder hashes with every eval.
6. **Check upstream licenses and languages before a plan names a tool.** Rev 1 named an AGPL dependency and a model with no Indic support.
7. **Coordination works when it is explicit:** one committer, per-file lanes, announce before editing outside your lane, and dry-run → report → owner approval before any Qdrant write. (v6 was applied on a delegated decision before rule 4 existed; future writes ask first.)

### 7. Next steps (in order; owner in brackets)
1. **[W0–W6 grader + committer harness] v6 vs v2 vs v5**, twice each, sign test, host-leak %, encoder hashes. Promote v6 only if it beats **v2** on top-1 with host leak ≤ v2 and 0 integrity failures. Changing `FIRST_PERSON_COLLECTION` needs explicit owner approval.
2. **[Owner, ~10 min] Listening sheet** `docs/evidence/first_person_speaker_edge_listening_sheet_2026-09-28.csv`: 20 rows, YouTube timestamps, verdict column.
3. **[First-person lane] S1:** if ≥ 18/20 are "teacher", relabel a ≤ 6-word `O`/`?` prefix of a sentence whose remainder is one teacher (`ingest/verbatim/speaker_verify.label_words_by_speaker`). Rebuild as v7 (dry run → owner approval → apply) and re-measure boundaries and host leak.
4. **[First-person lane] C1 on the winning collection:** `generate_first_person_questions --collection <winner> --out ~/mukthiguru_attribution_data/genq/<winner>.json` → human review → approved build with `question_dense` → add `Prefetch(using="question_dense")` → measure. Emit `paraphrase_group` so PCS stops reporting None.
5. **[Crisis lane] Finish the re-tier:** update the stale idiom test, run the full suite + `evals/run_safety_scenarios.py`, then give the committer the file list.
6. **[First-person lane] Anaphora false positive:** `text_quality_filter.find_artifact` → `has_repetition_loop` quarantines Sri Krishnaji's rhetorical anaphora (UlOt31lBhLY, REPORTED). Regression-test both directions.
7. **[First-person lane] Indic/low-signal collapse:** Hindi, Telugu, Marathi, "Why?" and gibberish all return the same 1–2 clips (REPORTED). Confirm translation before retrieval on the live build, and add a low-signal abstain.
8. **[Human] C2 gold set:** video-disjoint human questions toward ≥ 299 confident items, blind second annotation. No "direct answer" ships before this.

### 8. Decisions and open gates
- **Made on the owner's delegation ("use your intelligence", 2026-09-28):**
  - No hard duration window: 8 s floor and no 25 s cap, because a cap cuts thoughts mid-sentence, which breaks invariant 10.
  - Capitalised sentence-initial And/So/Or allowed (`boundaries.py`).
  - **No** first-person alias; invariant 4 stands.
  - v6 written as a new, non-serving collection.
- **Open, human-only:**
  - **Rights:** v5 and v6 each contain 1 TEDx Talks + 1 Marie Forleo video marked `rights_cleared=True` by the builder's channel map. Third-party channels need the rights register before serving.
  - **v2:** 72 `rights_cleared=false` clips.
  - **Clinician and native-speaker review** of crisis changes.
  - **Human gold.**
  - **Promotion approval.**
- **Not available to agents here:** Similarweb (connector needs OAuth; it measures web traffic, not clip quality) and the `/internet-skill-finder` and `/github-gem-seeker` skills (not installed).

### 9. Open-source worth adopting (licenses checked 2026-09-28)
- `segment-any-text/wtpsplit` (MIT code): punctuation-agnostic sentence segmentation, 85 languages incl. hi/te/ta/mr/kn, ONNX-CPU. Better sentence source for Indic/code-mixed talks; verify the HF weights license first.
- `jianfch/stable-ts` (MIT): word-timestamp refinement with silence suppression. Candidate for sharper word edges feeding S1.
- Already in the repo: `punctuators` (Apache-2.0) and WhisperX (BSD-2).

### 10. Lane notes (each owner edits only its own subsection)

#### First-person boundaries lane
- Tools: `boundary_defects`, `snap_to_sentences`, `grow_to_sentence_start` (tested, not wired); `audit_first_person_boundaries` (read-only); `measure_first_person_boundary_repair` (read-only); `generate_first_person_questions` (JSON staging only, never Qdrant).
- Sentence source: `raw/<vid>_punct.json` `display_words` only when `zero_change_assert_passed` and the length matches (169/295 clips). bakeoff `raw/` has 8 punct files, so the rest fall back to verbatim punctuation.

#### Committer lane ("Session handoff and warning remediation")
- _Owner: fill in B2/B4/PCS details, harness results, push status._

#### Crisis / safety lane ("AskMukthiGuru engineering W0–W6")
**Committed in `d1e9d019` (VERIFIED live, local Docker, 2026-09-27/28):**
- **Defect 1: English crisis took the weak path.** `InputGuardrailStage` runs before `DistressStage`, and its English-only `self_harm` regex answered "I want to end my life" with a 2-line template: `112` plus the US-only `988` mislabelled "International", with no Tele-MANAS. Hindi, Marathi and Kannada ideation reached real crisis pre-emption.
  - Fix: the guardrail sets `ctx.state["guardrail_self_harm_match"]` and defers. `DistressStage` then forces `CRISIS` unconditionally and never consults the LLM downgrade.
- **Defect 2: the first fix regressed.** Its unchecked claim that `assess_distress` covers every guardrail phrase was wrong. "I am suicidal", "hurting/harming/cutting myself", "how/way to die" and "not worth living" scored `NONE`, and live they got no helplines at all. That is what forced the flag design above.
  - Guard: a parametrized test runs every regex in `_BLOCKED_TOPICS["self_harm"]` through the stage chain.
- **Other fixes:**
  - `compact_two_line` now labels regions by their real name.
  - Dangling empty "please reach out:" list in the SEVERE copy.
  - `\bsuicid\b` never matched "suicide" or "suicidal".
- **W2 fixes:**
  - Passive ideation, spiritual framing ("leave my body tonight") and third-party concern are covered; third-party concern has a new helper response.
  - The divergence between the pre-screen and the engine was the romanized-Kannada root cause. Fixed structurally: `distress_stage` pre-screen = `get_non_english_crisis_patterns()`.
  - `async_assess_distress` was overwriting `recommended_response_type`.
  - Review packet: `docs/agent/W2_CRISIS_REVIEW_PACKET_2026-09-27.md`.
- **Live evidence:** `crisis_preempted` + Tele-MANAS on English, Hindi, Marathi, romanized Kannada, "I am suicidal" and "way to die without pain". Doctrinal controls stay `NONE`: moksha, "soul leaves the body at death", "merge with the divine in meditation".

**Mid-edit, uncommitted, owner-approved design ("escalate-only + re-tier", 2026-09-28). Do not commit until the lane says done:**
0. Translation safety check. Real translation on openrouter (`d1e9d019` plus the root `.env` change by the committer session) may LLM-translate crisis copy for Indic seekers. Required outcome: safety copy is only fixed reviewed text, and helpline numbers are verbatim.
1. Re-tier:
   - passive ideation (C-SSRS screener item 1 style) and ambiguous "leave this body" → SEVERE check-in with helplines, never `NONE`;
   - intent, plan, method or timeframe → CRISIS;
   - third-party → helper copy.
2. `IDIOM_EXCLUSIONS_RE` (e.g. "kill myself laughing"), with a guard that no real ideation phrase is ever excluded. The stale test `test_kill_myself_laughing_is_a_known_accepted_false_positive` is being updated to the owner's decision.
3. Escalate-only LLM classifier behind a new flag, **default OFF**: it may only raise the level, and a failure keeps the regex level. Separate from `distress_llm_downgrade_enabled`, which also stays **OFF**.
4. Measurement with the flag ON, 3 runs per language: misses must be 0, plus false alarms and latency.
5. AI-SUGGESTED pre-labels in the review packet. Never gold.

**Still open / human:**
- Clinician sign-off on all crisis copy, tiers and patterns.
- Native-speaker review for every language: hi, te, ta, kn, mr, hinglish.
- Two unexplained clean `mukthiguru-backend` restarts (ExitCode 0, not OOM). The cause is unknown; logs don't survive the restart.
- The red-team eval's 42 live-backend scenarios are skipped in the offline run, which is how Defect 1 went unseen. A live safety run belongs in the gate.

---

## 2026-09-25 handoff (historical, preserved)

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
- top-1: v1 **0.361** (116 frozen questions, in-process evaluator, first_person_v1 index snapshot) → v2 **0.410** (same 116 questions, same evaluator, first_person_v2 index);
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
