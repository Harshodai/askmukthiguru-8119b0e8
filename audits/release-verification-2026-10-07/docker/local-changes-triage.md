# Mac local changes triage — snapshot vs origin/main

- Snapshot: `67b8b5d7` (branch `snapshot/mac-local-2026-10-07`, parent `bd41c948`; **local only, push was denied by permission check**)
- Compared against: `origin/main` = `0a254c5d` (contains #45 `f860371d`, #46, #48)
- Scope: the 101 files the snapshot commit changed vs its parent. `git diff --stat 67b8b5d7 origin/main` = 295 files, +17528/-4292 (mostly lineage differences, not local work).
- Method: blob-hash equality, then `git diff origin/main 67b8b5d7` per file reading the lines only the snapshot has. Verdicts are from code reading; nothing was run.

Summary: MISSING BUT WRONG/RISKY: 13, MISSING AND CORRECT: 1, LOCAL-ONLY: 4, ALREADY IN MAIN: 83

| Verdict | File | Diff (snapshot vs main) | Why |
|---|---|---|---|
| MISSING BUT WRONG/RISKY | `backend/Dockerfile.railway` | (+2/-1) | snapshot sets CURL_CA_BUNDLE="" (disables TLS CA verification); main dropped it |
| MISSING BUT WRONG/RISKY | `backend/ingest/cleaner.py` | (+47/-0) | hardcoded Whisper patches ("problems would arise eyes", "In February when we meet") + word-repeat collapse that rewrites speech; overfit, untested on corpus |
| MISSING BUT WRONG/RISKY | `backend/ingest/verbatim/boundaries.py` | (+23/-1) | severed-clause regex flags complete sentences ("Observe the action which you do.", "where you live.") and trims them; high false-positive risk |
| MISSING BUT WRONG/RISKY | `backend/ingest/verbatim/speaker_verify.py` | (+2/-4) | re-adds host "O"->"?" rewrite that main removed on purpose (host speech rendered as teacher voice, 2026-10-05) |
| MISSING BUT WRONG/RISKY | `backend/services/first_person_pipeline.py` | (+132/-83) | hardcoded per-video LLM-written discourse_context + live-event regex; violates verbatim-only/no-LLM-text invariants (CLAUDE.md FP 1,12); main has its own content-quality gate |
| MISSING BUT WRONG/RISKY | `backend/services/quote_weaver.py` | (+41/-89) | loosens verbatim token-overlap gate 1.0 -> 0.95 (main comment: <1.0 lets an LLM edit a quote) + footnote/numbered-list rules |
| MISSING BUT WRONG/RISKY | `backend/tests/test_quote_weaver_fidelity_gate.py` | (+1/-1) | asserts the speaker-header shape of the risky quote_weaver variant |
| MISSING BUT WRONG/RISKY | `backend/tests/test_verbatim_boundaries.py` | (+10/-0) | pins the false-positive severed-clause behaviour |
| MISSING BUT WRONG/RISKY | `deploy_railway.sh` | (+3/-22) | re-adds hardcoded default graph password "mukthiguru_neo4j_pass"; main removed it |
| MISSING BUT WRONG/RISKY | `src/components/chat/ChatMessage.tsx` | (+11/-31) | pre-#45 copy: "Grounded — N verified sources", "Living Master Voice"; main has honest labels |
| MISSING BUT WRONG/RISKY | `src/components/chat/DiscourseAudioStrip.tsx` | (+8/-7) | "Listen in Guru's Voice"/"living master voice" copy and speaker fallback to "Sri Preethaji & Sri Krishnaji" for unverified clips; main removed |
| MISSING BUT WRONG/RISKY | `src/lib/chat/types.ts` | (+2/-9) | treats is_verbatim as speaker_verified and swallows errors (catch {}); main removed |
| MISSING BUT WRONG/RISKY | `src/test/components/DiscourseAudioStrip.test.tsx` | (+3/-4) | pins the removed "Guru's Voice" copy |
| MISSING AND CORRECT | `lessons.md` | (+55/-323) | 9 Oct-5 lesson entries absent from main (L-FP-DUAL-BOUNDARY-1 ... L-TEST-BACKEND-CWD-1); main has 323 lines snapshot lacks; land only lessons whose code landed (several describe the risky items above) |
| LOCAL-ONLY | `audit_results.json` | (+1/-1) | audit output data; trailing-newline diff only |
| LOCAL-ONLY | `backend/benchmarks/reports/ruthless_report.json` | (+1/-1) | benchmark output; newline diff only |
| LOCAL-ONLY | `docs/scenarios/seeker_inquiry_scenarios.md` | absent | mock doc absent from main; claims "Cryptographic SHA-256 100% Corpus Match", "Living Master" copy; do not land as-is |
| LOCAL-ONLY | `scripts/analysis/oral_cadence_results.json` | (+1/-1) | analysis output; newline diff |
| ALREADY IN MAIN | `CLAUDE.md` | (+0/-2) | main adds the 2026-10-08 handoff paragraph; snapshot has nothing extra |
| ALREADY IN MAIN | `audit_script.py` | (+19/-19) | whitespace-only diff vs main |
| ALREADY IN MAIN | `backend/Dockerfile` | (+1/-0) | trailing blank line only |
| ALREADY IN MAIN | `backend/app/api/first_person.py` | (+9/-58) | older exact-cache/gloss version; main superset (+58) |
| ALREADY IN MAIN | `backend/app/config.py` | (+5/-20) | same flag declared in main; main has 20 more lines |
| ALREADY IN MAIN | `backend/app/middleware/idempotency.py` | (+3/-9) | older version; main has 9 more lines |
| ALREADY IN MAIN | `backend/app/orchestrator_utils.py` | (+2/-5) | docstring wording only; main newer |
| ALREADY IN MAIN | `backend/app/pipeline/stages/first_person_bridge.py` | (+6/-94) | older version; main has +94 |
| ALREADY IN MAIN | `backend/app/pipeline/stages/guardrail_stage.py` | (+0/-125) | snapshot lacks 125 lines main has |
| ALREADY IN MAIN | `backend/benchmarks/expanded_live_run.py` | (+1/-3) | one print line; main newer |
| ALREADY IN MAIN | `backend/ingest/verbatim/asr_cleaner.py` | (+1/-27) | main has 27 more lines |
| ALREADY IN MAIN | `backend/ingest/verbatim/vote.py` | (+13/-49) | formatting only (dict one-per-line in main) |
| ALREADY IN MAIN | `backend/requirements.lock` | (+2/-0) | mutagen via yt-dlp extra; main pins yt-dlp differently |
| ALREADY IN MAIN | `backend/requirements.txt` | (+1/-9) | yt-dlp present in main with a different spec |
| ALREADY IN MAIN | `backend/scripts/ops/build_first_person_index.py` | (+1/-1) | one-line older display_text handling |
| ALREADY IN MAIN | `backend/services/conformal_calibrator.py` | (+1/-1) | import line only |
| ALREADY IN MAIN | `backend/services/crag_evaluator.py` | (+2/-4) | older fallback; main newer |
| ALREADY IN MAIN | `backend/services/embedding_service.py` | (+2/-6) | main has more offline/local-only handling (11 vs 9 refs) |
| ALREADY IN MAIN | `backend/services/first_person_ingest_service.py` | (+1/-6) | log line only; main newer |
| ALREADY IN MAIN | `backend/services/nim_service.py` | (+0/-1) | snapshot lacks 1 line main has |
| ALREADY IN MAIN | `backend/services/openrouter_service.py` | (+0/-1) | snapshot lacks 1 line main has |
| ALREADY IN MAIN | `backend/services/second_brain/second_brain_service.py` | (+7/-10) | older version; main newer |
| ALREADY IN MAIN | `backend/tests/test_celery_video_ingest.py` | (+1/-19) | main has 19 more lines |
| ALREADY IN MAIN | `backend/tests/test_conformal_calibrator.py` | (+1/-1) | import line only |
| ALREADY IN MAIN | `backend/tests/test_crag_evaluator.py` | (+2/-0) | import line only |
| ALREADY IN MAIN | `backend/tests/test_first_person_boundary_layer.py` | (+14/-30) | older wording of same guard tests |
| ALREADY IN MAIN | `backend/tests/test_first_person_bridge.py` | (+2/-113) | main has +113 |
| ALREADY IN MAIN | `backend/tests/test_first_person_pipeline.py` | (+0/-12) | main has +12 |
| ALREADY IN MAIN | `backend/tests/test_first_person_zero_hallucination.py` | (+4/-6) | older call signature |
| ALREADY IN MAIN | `backend/tests/test_fp_shadow_index_parity.py` | (+2/-1) | older fixture |
| ALREADY IN MAIN | `backend/tests/test_idempotency_middleware.py` | (+1/-43) | main has +43 |
| ALREADY IN MAIN | `backend/tests/test_quote_weaver.py` | (+27/-97) | main has +97 |
| ALREADY IN MAIN | `backend/tests/test_second_brain.py` | (+6/-20) | main newer |
| ALREADY IN MAIN | `backend/tests/test_second_brain_context_injection.py` | (+1/-3) | main newer |
| ALREADY IN MAIN | `backend/tests/test_verbatim_speaker_verify.py` | (+0/-14) | main has 14 more lines (incl. guard against the O->? rewrite) |
| ALREADY IN MAIN | `docs/FP_ANSWER_QUALITY_2026-10-04.md` | (+3/-3) | trailing-whitespace diff only |
| ALREADY IN MAIN | `generate_report.py` | (+16/-16) | whitespace-only diff vs main |
| ALREADY IN MAIN | `handoff.md` | (+0/-7) | snapshot lacks 7 lines main has |
| ALREADY IN MAIN | `scripts/ingestion/mass_first_person_ingest.py` | (+1/-1) | one-line older timeout |
| ALREADY IN MAIN | `src/components/chat/DeepenAndTuneBar.tsx` | (+3/-8) | older version |
| ALREADY IN MAIN | `supabase/migrations/20261005060000_revoke_public_execute_backend_only_rpcs.sql` | absent | byte-identical to main 20261005060158_revoke_public_execute_backend_only_rpcs.sql (timestamp rename) |

## ALREADY IN MAIN — byte-identical (42 files)

- `.github/workflows/dependency-check.yml`
- `.github/workflows/lint-test.yml`
- `.github/workflows/nightly-eval.yml`
- `.github/workflows/production-readiness.yml`
- `backend/app/openrouter_budget.py`
- `backend/benchmarks/quote_fidelity_check.py`
- `backend/pyproject.toml`
- `backend/rag/resolve_followup.py`
- `backend/scripts/ingestion/repair_v7_clips.py`
- `backend/services/circuit_breaker.py`
- `backend/services/first_person_store.py`
- `backend/services/graphrag_fusion.py`
- `backend/services/guru_voice_langhanam.py`
- `backend/services/qdrant_service.py`
- `backend/services/quote_fidelity.py`
- `backend/services/rankers.py`
- `backend/services/resilience.py`
- `backend/services/second_brain/ebbinghaus.py`
- `backend/start_railway.py`
- `backend/tasks/ingest_tasks.py`
- `backend/tests/test_circuit_breaker_governance.py`
- `backend/tests/test_cognitive_memory.py`
- `backend/tests/test_distributed_resilience.py`
- `backend/tests/test_first_person_store.py`
- `backend/tests/test_okf_compiler.py`
- `backend/tests/test_openrouter_budget.py`
- `backend/tests/test_quote_fidelity.py`
- `backend/tests/test_verbatim_vote.py`
- `config/first_person_calibration_first_person_v7.json`
- `config/first_person_calibration_v7.json`
- `docs/DOCS_TRUTH_SWEEP_2026-10-04.md`
- `docs/FP_CUTOVER_PLAN_2026-10-04.md`
- `docs/FP_QUALITY_AUDIT_2026-10-04.md`
- `docs/PROD_READY_CHECKLIST.md`
- `docs/SECURITY_SWEEP_2026-10-04.md`
- `docs/SOTA_ARCHITECTURE_SPEC_2026-10-04.md`
- `docs/engineering-notes/quote-fidelity-2026-10-04.md`
- `scripts/analysis/analyze_oral_cadence.py`
- `src/components/chat/CitationPanel.tsx`
- `src/test/components/DeepenAndTuneBar.test.tsx`
- `supabase/migrations/20261005053723_user_brain_nodes_bitemporal.sql`
- `supabase/migrations/20261005053805_second_brain_bitemporal.sql`
