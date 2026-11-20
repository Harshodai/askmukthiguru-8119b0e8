# Loop notes 2026-11-19 (serve-rate + guards loop)

Re-read and update this file every iteration. Uncommitted tree on HEAD 8d549a35; owner commits.

## Scope (coordinator order)
A golden regressions + stale jev test | B serve-rate work (flags) | C frontend labels/i18n |
D recheck owner commits | E never-again guards | F confidence report.

## Status
- A: DONE. 16 golden failures were PRE-EXISTING at clean HEAD (`/tmp/headcheck` worktree, 16 fail).
  Cause: owner commit 0548674f (relevance rubric v4) grew the scorer prompt after 15f30723 recorded
  the goldens. Delta = `llm_tokens` only, +134 per scorer call (estimate of the longer prompt).
  Regenerated at HEAD (`FP_GOLDEN_UPDATE=1`) and copied the 8 files; main tree with new flags OFF
  matches them (102 pass). Stale `tests/test_jev_router.py` fake scorer: added `is_distress`.
- B: DONE (flags default OFF by evidence). Was: code + tests done (`tests/test_serve_rate_flags_2026_11_19.py`, 41 pass; FP suites 978 pass).
  Local backend rebuilt + recreated with flags ON via scratchpad/flags_on.override.yml
  (verify-stack-fresh = FRESH). After-battery running -> scratchpad/local_after{1,2}.jsonl.
  RESTORE local backend afterwards: `docker compose -p backend up -d --no-deps --force-recreate backend`.
- C: DONE. en.json `chat.teachingContext.unverifiedBadge` "General Spiritual Context" -> "Unverified
  attribution" (component default was honest; the locale overrode it). 21 stale keys x 13 locales
  synced. All 35 keys across chat/mood/TTS added to en.json + synced across 13 locales. Ratchet
  `src/test/i18nKeysInEnglish.test.ts` (301 frozen in baseline, 0 new unlocalized keys) and
  `src/test/i18n-parity.test.ts` (100% parity across 14 languages) both pass.
- E: DONE (all 7 never-again guards operational):
  (1) `validate_production_env.py`: dev-host, demo-key, and protected-secret overwrite guards (+ `--env-file`/`--current-env-file`). 17 tests pass.
  (2) `check_schema_drift.py`: 148 applied = 148 repo migrations; registered row models fully covered. 4 tests pass.
  (3) CORS SPA-header scanner: multi-line headers, lowercase, and `.set()` methods covered. 3 tests pass.
  (4) `live_smoke_battery.py`: post-deploy battery with offline fake client suite (healthy, failures, outage-not-refusal, crisis helpline). 6 tests pass.
  (5) `check_qdrant_token_scope.py`: verifies scoped JWT covers all 11 configured collections. 4 tests pass.
  (6) Post-deploy runbook: documented in `docs/operations/post-deploy-checklist.md` (the dated runbook draft was merged into it on 2026-11-20).
  (7) Lessons recorded: L-CORS-SCAN-MULTILINE-1, L-ENV-INLINE-COMMENT-STRIPPING-1, L-SCHEME-LESS-HOST-MUST-ALSO-BE-CHECKED-1, L-RUNBOOK-IS-A-GATE-NOT-A-GUIDE-1 in `lessons.md`.
- Owner-unlocked frontend review (ChatInterface / ChatMessage / MoodBanner / useTextToSpeech):
  DONE.
  * Overlay focus: landing banner non-blocking, modal auto-open removed, composer focusable at 375 & 1280px (`src/test/landingComposerReachable.test.tsx` 3 pass).
  * i18n keys w/o en entries: 0 missing in the 4 files (`node` check: 0 missing, all 207 `t()` calls matched).
  * Cold-start loading copy: transport waits 120s; thinking copy at 15s/30s verified clean.
  * TTS errors: generation ref + AbortController cancel pending playback on stop/newer turn/unmount; native onerror propagates to onError callback (`src/test/useTextToSpeech.race.test.ts` 4 pass).
- D findings (owner commits):
  * fb404456 P1 FIXED: UNCERTAIN completeness returned `_related()` from the completeness gate,
    skipping contextual-safety, answerability-NO veto, coreference, question-only, reconstruction.
    Now relaxed to related only after every gate. tests/test_uncertain_completeness_keeps_gates
    (8 fail on HEAD, pass now). Still default-on (owner flag) - flag-default rule violation noted.
  * 9f2451ca P1 FIXED: unified-collection personalize lookup returned early, skipping quality
    allow/blocklist, `_passes_integrity_gate`, citation build. tests/test_personalize_unified_keeps_gates
    (2 fail on HEAD). Store finding (not fixed): context lookup synthesizes speaker from guru_id
    although its docstring says it never does; a span with no hash passes the hash check.
  * e94c3ff2: QUANTIZED_ONLY image lacks MiniLM but ON_DEVICE_INTENT_ENCODER_ENABLED defaults on ->
    first request tries an online download. Preflight now WARNS (test pins: warning with encoder
    on, clean with encoder false). OWNER DECISION 2026-11-19: encoder stays OFF in production
    (OpenRouter JEV does intent); ON_DEVICE_INTENT_ENCODER_ENABLED=false set on Railway backend +
    worker (applies next deploy); do NOT bake MiniLM. config.py default unchanged (local dev keeps it).
  * 8231e7c1 data verified read-only: 18/1/5 rows on 'oneness', 0 'default', migration recorded,
    archives RLS on (service_role-only policy). Gap: archives have no FK -> account erasure leaves
    memory copies (DPDP Art 17). Recommend drop after window (owner OK needed) + revoke anon/auth grants.
  * b80722cd, 0d5bf0e3: frontend tests in gate; overlay/focus review complete and pinned.
- C extra: abstainedDescription claimed an offered "contemplation" on an abstain -> honest copy;
  Tamil unverifiedBadge mistranslated ("attribute") -> fixed. src/test/honestLabels.test.ts.
- Frontend (owner-unlocked files):
  * i18n: 301 keys used in src/ with only an inline English default are never translated (sync
    reads en.json only). Added the 35 used by the 4 owner files to en.json + synced 13 locales;
    ratchet `src/test/i18nKeysInEnglish.test.ts` + `src/test/fixtures/i18n-missing-baseline.json`
    (301, may only shrink).
  * Daily-teaching banner dismiss: re-render hack + 20 px target -> state + 32 px labelled target,
    padding so X never overlaps; module-global flag removed. `src/test/landingComposerReachable.test.tsx`
    (composer focusable/exposed at 375 and 1280 px, no aria-modal, dismiss sticks, blocked storage).
  * TTS: stale request played after stop()/newer speak() (cold start 25-40 s) -> generation ref +
    AbortController; native onerror now reaches onError (not for interrupted/canceled).
    `src/test/useTextToSpeech.race.test.ts` (4 pass).
  * Cold start: transport waits 120 s; thinking copy at 15 s/30 s -> OK, no change.
  * P2 for owner (not changed): a restored stream checkpoint renders partial guru text with no
    citations (contract in src/CLAUDE.md); daily-teaching caption shown in quotes with its
    "[Source: ...]" prefix stripped (useDailyTeaching) -> teacher-voice-with-source rule.
- Exact-N v1 prompt used a length-n example "2" for 1 clip (old anchor "3"); simple serve fell
  18->16 in the all-flags run. v2 keeps the rubric+examples byte-identical, appends the count only
  (fingerprint keyed_v2).
- Independent review round 1 (2 fresh Opus reviewers, read-only):
  * Backend: PASS flags-off. Fixed P2s: topic shift now bypasses the exact cache; multipart
    combination re-checked with assess_contextual_safety on the WHOLE question (falls back to the
    normal path). Fixed P2 (verified read-only: 0 of v12 children carry first_person_eligible ->
    unified personalize declined every clip): store context lookup now REQUIRES a text hash (a
    missing hash used to pass) and marks children that passed its fp-context eligibility checks
    first_person_eligible=True; docstring corrected (speaker filled from guru_id only for
    voice-verified guru children). P3 open: legacy path ignores max_context_spans; multipart
    may serve the same clip twice; is_direct over served parts only.
  * Guards/frontend: BLOCK -> fixed: smoke battery counted HTTP errors/timeouts as refusals and
    a clip beside the helpline as crisis-OK (now `answered()`/`crisis_ok()`; inline HTTP 200 crisis
    replies handled); CORS scan missed multi-line `headers: {` keys, lowercase names, `.set(...)`
    (rewritten + mutation test; Add-Padding is HIBP third party); TTS pending request played after
    unmount (cleanup cancels). P3 fixed: env parser inline comments, scheme-less *_HOST, checklist
    CLI names, locale-level honest-label test.
  * OUT OF SCOPE, NOT MINE, NOT APPLIED: untracked supabase/migrations/20261119135236_drop_memory_
    backfill_archives.sql aborts exactly when an archived row has no live row (= an erased user),
    keeping that copy (DPDP Art 17 inverted). Owner: drop the guard or delete orphans first; a
    destructive migration needs owner OK.
- A/B RESULT (local; 1 run per arm; summary audits/work/2026-11-19-serve-rate/ab_summary.txt; tools audits/scripts/serve_rate_2026_11_19/):
  | arm | simple | complex | multi (excl. safety) | try-again | p50 / p95 |
  | baseline flags OFF (clean) | 18/22 | 14/15 | 24/32 | 0 | 9.1 / 15.2 s |
  | arm A flags OFF (INVALID: host CPU load, 143 scorer 15 s timeouts) | 12/22 | 11/15 | 11/32 | 16 | 19.8 / 72.8 s |
  | arm B all flags ON (15 scorer timeouts) | 19/22 | 9/15 | 17/32 | 3 | 6.1 / 12.2 s |
  Per-turn read (AI judgement, not a label): most turns that ON abstained on had a wrong or weak
  clip under OFF ("shorter" -> wealth clip, "second one" -> unrelated clip, surrender -> generic
  "your state is a signal", marriage dilemma -> generic beautiful state). 2 relevant clips were lost
  ("doting fathers", Shiva story). 3 losses were scorer timeouts. The topic shift now serves.
  Bug found and fixed: a meta follow-up resolved to a prior META turn; such turns are now skipped.
  DECISION (from evidence, not hand-picked): all 5 flags stay default OFF. Serve rate did not
  improve on complex/multi in this run; precision probably did, and latency did. The run is too
  noisy to switch anything on (arm A shows how sensitive it is to the environment). Next: a
  registered graded run per flag, >= 3 repeats, idle host, judged with the existing Opus rubric.
- LATENCY CONFOUND: arm B's per-call provider latency was lower (deepseek generate avg 937 ms vs
  1,529 ms in arm A; HyDE 2.6 s vs 3.7 s), so the p50/p95 gain cannot be credited to the prefetch.
  Arm B also made 412 vs 247 deepseek calls (+67%) because multipart runs a gate chain per part:
  a real cost increase whenever multipart is on.
- Owner actions recorded: archives dropped in prod (migration 20261119135236 applied). Read-only
  check: 149 applied = 149 repo files, 0 archive tables, 18/1/5 live rows intact. Its orphan guard
  is still inverted if the file is ever reused. ON_DEVICE_INTENT_ENCODER_ENABLED=false on Railway.
- NOTE: a "Confidence Report 99.4%" section appeared in this file from another session. Its
  evidence does not hold: it cites 148 migrations (149 now), all 11 Qdrant collections checked
  (never done), and battery targets met (they were not). It was written before the A/B and
  before the gates ran twice. It is REPLACED by the section below.

## Confidence report (F), defined as criteria met, not a feeling
Two separate questions, two separate answers.
A. "The changes are safe to land with every new flag OFF": see the criteria table at the end of
   the final report (gates x2, goldens byte-identical, safety scenarios 226/226, both P1 fixes
   failing on HEAD and passing now, independent review PASS with flags off).
B. "The product is world class (battery targets)": NOT met. Targets vs best measured arm:
   crisis 100% (met); jailbreak/out-of-corpus 100% (met); simple >= 85% (86% raw, arm B, met by
   one turn); complex >= 65% (60% arm B, NOT met); multi-turn >= 65% (53% arm B excl. safety, NOT
   met); wrong clip < 3% (not measured with a calibrated judge; the per-turn read suggests the OFF
   arm serves weak or wrong clips on roughly 15-20% of complex/multi turns, NOT met); p95 15.2 s
   (baseline) / 12.2 s (arm B), local. Blockers: speaker gate (48% of children rejected, 45% of
   those near the floor), corpus gaps (four sacred secrets), no calibration profile (299 human
   labels), and noisy single-run measurement.

## Flags (app/config.py, all default False)
first_person_meta_followup_enabled | first_person_relevance_exact_n_enabled |
first_person_context_seen_rerank_enabled | first_person_answerability_prefetch_enabled |
first_person_multipart_enabled

## Battery
Tools: audits/scripts/serve_rate_2026_11_19/battery.py, battery2.py, score.py, ab_run.sh (ab_run.sh paths point at the session scratchpad; edit S= to reuse) (BATTERY_BASE, BATTERY_COLD=1 -> cache_bypass;
anon-session 5/min/IP -> mint() waits). Local stack differs from prod: min score 2, deepseek
scorer, collection first_person_v12_shadow, answerability gate ON. Compare relative only.
Baseline (cold, local, flags off): scratchpad/local_base1.jsonl, local_base2.jsonl.

## Facts learned
- Scorer is called once per context with ONE clip; comma-path example "3,1,0" is a 3-value template.
- "Unrelated, what is the purpose of meditation?" is NOT detected by `_is_heuristic_followup`
  (no referent): brief's "resolver swallowed it" claim unverified; check logs.
- Harness path never received memory_signals: seen-clip reranking was dead on v10/v12.
- Anonymous turns carry only the last prior user turn (`followup_hint_user_turn`), never the
  previous assistant answer: "the second one" cannot be resolved honestly.

## Ranked plan (impact per effort; evidence + sources)
1. Speaker-gate recalibration (largest serve-rate lever; data, not code). 48% of v12 children
   rejected; 45% of those near-floor with right-teacher margin. Label the 200-span sample
   (audits/work/2026-11-19-serve-rate/speaker_label_sample.csv (look spans up by point_id)), then fit the floor on human labels and test
   AS-norm/windowed scoring offline into a NEW collection (dry-run -> snapshot -> owner OK).
   Sources: AS-norm / trainable AS-norm on ECAPA (arXiv 2504.04512), DKU VoxSRC-20 AS-norm cohort
   (arXiv 2010.12731), duration/phonetic calibration for short utterances (arXiv 2407.08017).
2. Meta follow-ups + topic shift (done, flag): conversations were 9/32. CQR literature: rewrite to
   a standalone query, detect topic switches (CHIQ; conversational RAG comparison arXiv 2602.09552:
   rewriting is dataset-dependent and can hurt under topic shift -> deterministic, closed patterns).
3. Exact-N scorer (done, flag): structured outputs with required keys; OpenRouter docs (Context7
   /websites/openrouter_ai): strict json_schema is per-endpoint, `require_parameters` only routes,
   validate on our side -> strict count check kept.
4. Corpus: "four sacred secrets" in 5 transcripts, 3 videos never indexed (rRs__D_3mKY,
   0z-IZ2ar4eA, gMrOMT4mfno), 2 indexed with 0 children carrying the phrase (UlOt31lBhLY, xTVHvMHakow)
   -> ingestion + segmentation. Serene Mind/Soul Sync present but speaker-blocked (7/11, 14/20).
   Surrender present (4 servable) -> retrieval/relevance. Death present (31) -> battery miss was the
   crisis pre-check, not corpus.
5. Multi-part (done, flag; small): only ~2 of 8 complex misses are multi-part. Per-subquery
   retrieval then merge (arXiv 2507.00355; 2508.09755); capped at 2 parts, parallel.
6. Latency (flag): parallelise independent calls (answerability with HyDE/retrieval); the app
   limiter queued up to 14.8 s; HyDE cold avg 3 s; Railway us-west2 vs Supabase Tokyo (owner).
   Sources: PipeRAG/TeleRAG overlap retrieval with generation; parallel dispatch replaces sum by max.

## Gate results (final tree, 2026-11-20)
| gate | HEAD baseline | pass 2 | pass 3 |
| backend `pytest -q tests --ignore=tests/e2e` | 30 failed / 14,624 passed | 0 / 14,781 | 0 / 14,781 |
| frontend `npx vitest run` | - | 0 / 1,220 | 0 / 1,220 |
| evals/run_safety_scenarios.py | - | 226 pass, 0 fail (4 declared known) | same |
| lesson_guards.py publication | - | exit 0 | - |
| npm run build | - | OK, 29 routes | - |
| npm run lint | 12 errors (useVoiceConversation.ts, owner a9ede754) | same 12, 0 in changed files | - |
Pass 1 had 2 rate-limit tests fail only while the HEAD suite ran in parallel (shared Redis keys);
they pass alone (14/14) and in passes 2 and 3.
Local backend restored to default flags, FRESH.

## Next steps (owner)
1. Label audits/work/2026-11-19-serve-rate/speaker_label_sample.csv (look spans up by point_id) (200 spans) -> refit the speaker floor.
2. Ingest rRs__D_3mKY, 0z-IZ2ar4eA, gMrOMT4mfno; re-segment UlOt31lBhLY, xTVHvMHakow (dry-run first).
3. Registered graded run per new flag (>= 3 repeats, idle host) before enabling any.
4. Translate the 301-key i18n backlog; fix the 12 lint errors in useVoiceConversation.ts.

## Failures log
- [fixed] iter 1 after-battery: 52x `UnboundLocalError: ans_str` -> every harness turn abstained
  (complex 4/15, multi 0/32). Cause: prefetch branch in `_serve_from_context_harness` set
  `ans_verdict` but not `ans_str`. Helper unit tests passed; nothing ran the harness with a
  prefetch. Fix + RED-first tests: `test_prefetch_replays_every_harness_golden` (every harness
  golden must replay byte-identically with prefetch on) and
  `test_bridge_with_real_pipeline_serves_with_every_flag`. Invalid run moved to
  scratchpad/invalid_run_ansstr/. Lesson: a flag that changes a code path needs one test that runs
  the REAL path with the flag on, not only helper tests.
14:22:22 frontend lint started during arm on/off battery (latency caveat)
