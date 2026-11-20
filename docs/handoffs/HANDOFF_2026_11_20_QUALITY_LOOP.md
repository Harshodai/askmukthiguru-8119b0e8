# Handoff 2026-11-20: answer-quality loop, whole-tree review, Railway deploy plan

Read with `docs/handoffs/HANDOFF_2026_11_19_RAILWAY_GO_LIVE.md` (infra) and `docs/handoffs/LOOP_NOTES_2026_11_20.md` (protocol, runs, failures log; the "LEAD CORRECTION 13:30" section supersedes the older results and deploy list there). Company survey: `docs/handoffs/COMPANY_PRACTICE_SURVEY_2026_11_20.md`. Faculty brief draft: `docs/handoffs/FACULTY_TEST_BRIEF_2026_11_20.md`.

## Git state
- `main` has 3 unpushed commits (`8d549a35`, merge `5c32ddcb`, `459c805e`) plus the uncommitted tree. Claude commits nothing; the main session commits the set below after verifying gates, owner pushes if the classifier blocks it.

## Measured (blind Opus judges; tune / holdout; 73 / 55 answer-expected turns per rep)
| Arm | serve | RIGHT per answer-question | WRONG per served |
|---|---|---|---|
| PROD posture x2 (haiku scorer, min 2, v12_shadow, answerability on) | 0.555 / 0.755 | 0.199 / 0.300 | 0.161 / 0.107 |
| PROD + R flags x1 | 0.534 / 0.764 | 0.192 / 0.200 | 0.051 / 0.119 |
| PROD at min 3 x1 | 0.110 / 0.182 | 0.096 / 0.164 | 0 / 0 |
| local deepseek OFF x3 | 0.79 / 0.78 | 0.155 / 0.139 | 0.357 / 0.290 |
Judge reliability: anchors 14/16 agree with the earlier judges, self-agreement 11/12. Prod posture: 0 crisis/OOC/jailbreak serves; crisis helpline 16/16; p50 13 s, p95 25 s. Prod logs (22 h, old code): 116 speaker-gate abstains vs 133 serves.
Decisions from evidence: all 5 flags stay OFF (R gives nothing on prod); keep min score 2 (measured), docs/railway.ts still say 3 (owner).

## Fixed today (TDD; independent reviewer PASS)
1. Grief clip "If you're thinking of dying because you have lost a loved one": root cause `SELF_HARM_RE` missed "thinking of dying"; the widened detector (kept) excludes it on non-exempt turns on both serving paths. Reverted three unsafe or unmeasured additions found in the tree: widening of the educational exemption, an unflagged serve-time LLM check (`"SAFE" in "UNSAFE"` failed open), and scorer rubric v5 (unmeasured; it broke 6 golden tests).
2. `tasks.web_ingest_tasks` registered in Celery (admin URL ingest was dead).
3. Applied migration `20261119135236` had a DROP of `user_brain_keys_archive_20261119` appended after it ran: removed.

## Gates (final tree)
Pass 1 and pass 2: vitest 1241 passed / 6 skipped; build OK (29 routes prerendered); safety scenarios 198 PASS, 4 documented harness-limitation fails, recall 106/110, control FP 0/49; guards publication/claims/fp-writes/guru-literal/types OK. Backend pass 1: 14853 passed, 22 skipped, 0 failed. Backend pass 2: 1 load flake (`test_c20_async_lane_does_not_starve_the_executor`, a 0.256 s loop stall while vitest and the build ran alongside; it passed 3 of 3 in isolation). Backend passes 3 and 4 (host idle, final tree, consecutive): 14853 passed, 22 skipped, 0 failed, both. Lint: 12 pre-existing errors in `src/hooks/useVoiceConversation.ts` (owner commit a9ede754), not fixed (the `any` types need real SpeechRecognition types; the empty catches need a decision to log rather than swallow).

## Measured vs shipped
The widened `SELF_HARM_RE` newly matches 1 of 158 unique served clips (the target grief clip), so it has no other measured collateral. `first_person_store.py`, `first_person_bridge.py`, `resolve_followup.py` and parts of `first_person_pipeline.py` changed after the arms ran (flags off, but some changes are unflagged: the HyDE language gate, store fail-closed hash, completeness gate order). The post-deploy live battery is the measurement of the shipped code. `.railway/railway.ts` is NOT applied on deploy; running `railway config apply` today would move prod to v10 / min score 3 (measured 11% serve).
`types.ts` keeps the hand removal of `user_brain_keys_archive_20261119`: HEAD's types.ts fails `supabase_types_lint.py` because no migration creates that out-of-band table.

## Open, owner or clinician
- Clinician: "Nothing seems to matter anymore" after "feeling low for weeks" gets a generic clip and no helpline (reproduced in the prod posture). Also: should "anxiety"/"therapy" queries keep unlocking self-harm clips (HEAD exemption)?
- 200 speaker labels (`audits/work/2026-11-19-serve-rate/speaker_label_sample.csv`, 0/200): the largest quality lever. Do not use `scripts/ops/generate_speaker_label_reviewed_workbook.py`: it writes AI labels into the human column (excluded from the commit).
- `user_brain_keys_archive_20261119`: still in prod, removed by hand from `types.ts`. Keep (then regenerate types and record it in a migration) or drop (new migration, after confirming it is not the KEK backup).
- Waitlist (459c805e): RLS final state verified correct; missing DPDP retention/unsubscribe/erasure and privacy-page text; global 100/10 min throttle can be exhausted by one script; legacy backend `/waitlist` now always 503 if enabled.
- Wiring (not fixed; evidence in the final report): LangGraph drops ~14 undeclared state keys (`high_confidence_retrieval`, `orphan_citations_stripped`...); Railway IaC (`.railway/railway.ts`) describes always-on worker+beat and v10 posture, not the live on-demand worker and v12; 401-refresh retry skips the 202 job path in `src/lib/chat/transport.ts`; quota 429 would sleep 1 h if `Retry-After` were ever exposed; Qdrant write key for memory/cache vectors on Railway unverified; usage-monitor per-session dict never evicts.

## Deploy steps (main session executes)
1. Commit the set in the lead's final report; push.
2. Railway: `connect-service-source` on backend `18690f24-5e2d-4fdb-95f6-42142111df7e` with the new `commitSha`; redeploy worker `9ac523d7-4eae-4db5-9b2a-37906634203b`; HARD STOP: the boot log line "Serving posture: ..." must show `collection=first_person_v12_shadow`, `min_score=2` and `model=anthropic/claude-haiku-5.5`; anything else (v10, min 3, deepseek) means roll back. Then publish Lovable.
3. `python3 backend/scripts/ops/live_smoke_battery.py` (must exit 0), then the live battery: `BATTERY_BASE=<prod url> python3 audits/scripts/quality_2026_11_20/run_eval.py audits/work/2026-11-20-quality/eval_set_v2.json audits/work/2026-11-20-quality/live/LIVE_r1.jsonl --arm LIVE --rep 1 --conc 2 --live --per-kind 4`, then `judge_packet.py` + blind judges + `analyze.py --split all`. About 17 of the run's ~30 minutes are serial token minting (5/min/IP); the runner stops on any 402 or on 3 x 429. Read-only extras: `curl -s -o /dev/null -w '%{http_code}' https://askmukthiguru.lovable.app/guides/serene-mind-practice` (signup page, expect 200; never submit an email in prod) and an anonymous `GET /api/profile` (expect 401, never 5xx).
4. Rollback: `connect-service-source` back to `fb404456` (current prod) and redeploy.
