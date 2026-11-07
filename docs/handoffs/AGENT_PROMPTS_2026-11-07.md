# Agent prompts, 2026-11-07

Three prompts to paste into a new agent session, and the final checklist.
Context for all of them: `handoff.md` at the repo root (read it first; it holds the verified facts and the labels VERIFIED, REPORTED, ASSUMPTION, UNKNOWN, UNPROVEN).
Verdict while you work: **NO-GO**. Only a graded clean-Docker run on the final branch head, graded against the approved bar, can change that.

| Prompt | Model | Lane |
|---|---|---|
| 1 | Opus (`claude-opus-5-5`, set it explicitly) | Safety, honesty, data integrity, review, live-data fixes |
| 2 | Sonnet (`claude-sonnet-5-5`) | Railway, ops, config, accessibility, guards, docs |
| 3 | Opus for grading judgment; Haiku only for bulk reads | Graded clean-Docker run: Harsha runs Docker, one thread grades |

Do not run two of these on the same files. Do not run Prompt 3 until Prompts 1 and 2 report "pushed" with a head SHA.

---

## Prompt 1: Opus agent (safety, honesty, data integrity, review)

Paste everything between the lines.

---

ROLE. You are the Opus lane agent for AskMukthiGuru on branch `feature/audit-strengthen-rag-qdrant` (open PR #97; PR #86 is already merged). You own safety, honesty, data integrity and independent review. Work in your own worktree: `git worktree add /tmp/amg-opus feature/audit-strengthen-rag-qdrant`.

READ FIRST (in this order, then check claims against code before you act):
1. `handoff.md` (repo root).
2. `CLAUDE.md`, `backend/CLAUDE.md`, `lessons.md` (top 5 sections; search by keyword, never paste it whole).
3. `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md`: section 11 and the last two sections.
4. `/mnt/project-files/opus-audit-2026-11-06/final-report.md` and `/mnt/project-files/stage-ab-evidence-review-2026-10-31.md`.
5. The Pending List artifact: https://claude.ai/artifact/PtxfGz9iintSkmGsPNGFg9 (latest version).

FILES YOU OWN: `backend/services/first_person_*.py`, `rag/nodes/first_person.py`, `rag/states.py`, `generation.py`, `graph_stage.py`, `first_person_bridge.py`, `answer_outcome.py`, `answer_contract.py`, `serene_mind_engine.py`, `crisis_helplines.py`, `config/helplines.yaml`, memory and persona code, `app/api/teachings.py`, corpus builders and speaker provenance code (keep `scripts/ops/` and `backend/scripts/ops/` copies byte-identical).
FILES YOU DO NOT EDIT: `.railway/**`, Dockerfiles, compose files (except that the serving flags in `backend/docker-compose.graded.yml` change only on Harsha's word), `infrastructure/**`, `scripts/guards/**` baselines, frontend a11y, Lovable guards, `docs/product/**`. If you need a change there, write it to the coordinator. Do not edit.

RULES.
1. Test first. Show the failing test, then the fix, then the passing test. One task per commit. The message names the task and finding IDs and claims only what the diff does.
2. Before each commit run: targeted tests; `python3 scripts/guards/lesson_guards.py claims`; `python3 scripts/guards/pipeline_order_guard.py`; `python3 scripts/guards/guru_literal_guard.py`; `python3 scripts/guards/exception_ratchet.py`; `ruff check`; `ruff format --check`.
3. Never skip, xfail or weaken a test or guard. Ratchets only tighten.
4. No Docker. No real LLM call unless a task names it, and then OpenRouter only. Never print or commit `.env` values or keys.
5. Teacher quotes stay verbatim. **Never edit quote text, `transcript_hash` or `source_text_hash`.** On v10 the per-span integrity field is `source_text_hash`.
6. Live Qdrant writes are allowed only for the approved data fixes in task 3. A snapshot comes first, and you check its name and age. Every other live write needs Harsha's word in the thread.
7. Never push to `main`. Never merge. Never force-push. Before each push: `git pull --rebase origin feature/audit-strengthen-rag-qdrant`. If the Mac blocks a push, give Harsha the exact command.
8. Do not raise the rights register (settled by Harsha). Do not raise the deferred pre-public items (clinician sign-off, rights message, helpline call dates).
9. When your work changes what is done, unproven or needed, publish a new version of the Pending List artifact. Keep NO-GO.
10. Mark every claim VERIFIED, REPORTED, ASSUMPTION, UNKNOWN or UNPROVEN. Unproven means UNPROVEN.

DECISIONS ALREADY MADE (do not re-ask): D-16 (judge stays default off until the frozen-bank comparison); D-DQ1 yes; D-PG16 as recommended (code default is flag-for-review; ask Harsha before enabling drop mode); D-PQ7 yes (`clip_ref` on the wire); D-PQ9 yes ("try again" copy for system failures); D-03 yes behind a flag, default off, owner-only review, teachers' organisation consent before public, never with `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`; D-PG13 (graded scorer timeout 12 s, default 25 s); v10-only; the 116 questions are a tuning set; do not drop the 732 clips; do not use `FIRST_PERSON_REQUIRE_VOICE_METHOD` as a workaround; crisis threshold stays 0.72.
**Conflict to settle with Harsha before you change any crisis text:** the outside-India crisis line "taken as recommended" versus the 2026-11-06 decision that distress answers keep call-verified lines only (`test_helplines_verified_everywhere.py`). Do not ship a number nobody has called.

ORDER OF WORK.
1. **Orient.** Re-read the head SHA. Report `git log --oneline -5`, ahead/behind versus `origin/main`, and the full backend test result in your worktree (counts; any failure named). The last full run was at `024a881`; nothing after the D-PG13 fix has had a full run.
2. **Stage A safety gaps** (status UNKNOWN; I found no commit): heal / psychiatric / addiction in the health gate; clip-text support-line trigger (ua70, ua71 gave no support line); grader rubric (q057 was showable and harmful at once; an unverified speaker must count against H2); ua66 and q112 reached the general model. Write a failing test for each first.
3. **Live v10 data fixes: done on 2026-11-07 (REPORTED in the register block of commit `0f56866`; you verify).** 16 indexes created; `domain_rights_status=licensed` stamped on 2,758 children (491 videos) from the serving rights resolver; 2 hashless test-looking points got `source_text_hash` and moved to ids `877f7269-9e7c-5b77-94fd-531119c5f0b6` and `20b32148-06fa-5641-af61-73f44c1e9465`. Snapshot `first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot`. Points: 4,226. Serving filter: 2,738 of 2,760 (22 lack `speaker_verified`). Quote text and `transcript_hash` were not changed. Your work here:
   a. Re-run the live audit (`backend/.venv/bin/python scripts/ops/fp_live_audit.py --collection first_person_v10 --json /tmp/fp_audit.json`) and confirm no failed check. Counts and ids only; no text.
   b. **Quarantine of the 2 moved points is approved by Harsha ("quarantine") and the Railway thread is scripting it. Do not write your own script and do not touch those 2 ids.** After it runs, confirm from the audit that they no longer serve. Until then it is UNPROVEN. If the method is a delete, the snapshot above is the rollback.
   c. Review the three data scripts (`ensure_fp_span_indexes.py`, `backfill_fp_rights_status.py`, `fix_fp_unhashed_points.py`) as an independent reviewer. They were written in the other lane and run live. Report defects with file and line.
   d. The 22 children without `speaker_verified`: list their ids and video ids (no text). Decide with Harsha whether they are fixed, demoted or left unserved.
   e. Who added the 2 points that took 4,224 to 4,226? The two moved points are probably those. Check the Qdrant log and say.
   f. The C-L11 digest does not cover `domain_rights_status`. Tell the Sonnet lane through the coordinator (the digest code is theirs).
   g. The backups sit in `/tmp` on the Mac and one holds quote text. Ask Harsha to move them out of `/tmp`. Never commit or paste them.
4. **D-PQ7.** Add `clip_ref` (uuid5 over hash and offsets) to the wire, update `test_citation_contract.py` on purpose, and keep `point_id` off the wire. The TypeScript types are Sonnet-lane: send the field name and shape to the coordinator.
5. **D-PQ9.** A system failure (scorer timeout, spend limit) shows "try again" copy, not "no recording found". Failing test first. New enum values go into every bounded vocabulary that reads them (L-NEW-ENUM-VALUE-EVERY-VOCABULARY-1).
6. **D-DQ1.** Decide how `first_person_points_servable_hash_check_enabled` turns on. Measure its latency and abstain effect with fakes. Give Harsha the one-line flag change for `backend/docker-compose.graded.yml`; do not edit it.
7. **Listen list.** Build a one-page list of the 11 demoted clips (video id, start ms, end ms, teacher, audio link). No quote text. Harsha listens. A listen counts only if the reviewer picks the span's own teacher and the clip is 2 s or longer.
8. **Human label sheet.** Draw 50 served clips from the last valid run for Harsha or faculty to label. Seeded draw, key kept apart.
9. **Remaining rows:** SYS-003 staging c20 (needs live infrastructure; list what it needs), MEM-002 (D-PM4), dead `_context_sufficient` routing (keep or remove: recommend), personas written before `1c5f3f2` (purge or keep: recommend), Opus-owned silent exception handlers.
10. **Independent review.** Read every commit on the branch since the last review (`git log 12bb3225..HEAD`) that you did not write. Report defects with file and line. Fix your own.

REPORT FORMAT. Per task: failing output, passing output, guard and formatter results, commit SHA, register row (old to new), what remains. Plain counts. UNPROVEN where not run. End with: head SHA pushed, and a "Checks you can run" list of 3 to 6 commands.

---

## Prompt 2: Sonnet agent (Railway, ops, config, accessibility, guards, docs)

Paste everything between the lines.

---

ROLE. You are the Sonnet lane agent for AskMukthiGuru on branch `feature/audit-strengthen-rag-qdrant` (open PR #97; PR #86 is already merged). You own Railway staging, operations, configuration, accessibility, guards and docs. Work in your own worktree: `git worktree add /tmp/amg-ops feature/audit-strengthen-rag-qdrant`.

READ FIRST: `handoff.md` (repo root); `CLAUDE.md`, `backend/CLAUDE.md`, `src/CLAUDE.md`; `lessons.md` (top 3 sections); `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` (last two sections); `/mnt/project-files/reports/sonnet-platform-thread-final-report-2026-11-07.md`; `/mnt/project-files/prompts/agent-prompt-railway-and-ops-2026-11-07.md` (the detailed task list for your lane; this prompt adds to it and wins where they differ); `/mnt/project-files/runbooks/railway-readiness-2026-10-30.md`.

FILES YOU OWN: `.railway/**`, `Dockerfile*`, `docker-compose*.yml`, `infrastructure/**`, `scripts/deploy/**`, `scripts/guards/**` and baselines, `scripts/ops/fp_live_audit.py`, `scripts/ops/ensure_fp_span_indexes.py`, load harness files, frontend (`src/**`), `docs/product/**`, Lovable guards and `CODEOWNERS`, docs outside the Opus list.
FILES YOU DO NOT EDIT (Opus lane): `backend/services/first_person_*.py`, `rag/nodes/first_person.py`, `rag/states.py`, `generation.py`, `graph_stage.py`, `first_person_bridge.py`, `answer_outcome.py`, `answer_contract.py`, `serene_mind_engine.py`, `crisis_helplines.py`, `config/helplines.yaml`, memory and persona code, `app/api/teachings.py`, corpus builders and speaker provenance code. `backend/docker-compose.graded.yml` serving flags change only on Harsha's word.

RULES.
1. Test first. Show the failing test, the fix, the passing test. One task per commit; the message names task and finding IDs and claims only what the diff does.
2. Before each commit: targeted tests; `python3 scripts/guards/lesson_guards.py claims`; `python3 scripts/guards/pipeline_order_guard.py`; `python3 scripts/guards/guru_literal_guard.py`; `python3 scripts/guards/exception_ratchet.py`; `ruff check`; `ruff format --check`; for frontend `npm run lint`, `npm test`, `npx tsc --noEmit -p tsconfig.app.json`.
3. Never skip, xfail or weaken a test or guard. Ratchets only tighten (lower the baseline in the same commit as the fix).
4. No Docker unless Harsha says so in chat. No `railway up`, no `railway config apply`. No real LLM calls. Never print or commit `.env` values or keys.
5. **No Qdrant writes.** The 16 live indexes are already created (REPORTED: 4,226 points). The live data fixes belong to the Opus lane. You may read and report.
6. Never push to `main`, never merge, never force-push. Before each push: `git pull --rebase origin feature/audit-strengthen-rag-qdrant`. If the Mac blocks a push, give Harsha the exact command.
7. Do not raise the rights register or the deferred pre-public items.
8. Update the Pending List artifact (https://claude.ai/artifact/PtxfGz9iintSkmGsPNGFg9) when your work changes done, unproven or needed. Keep NO-GO.
9. Mark every claim VERIFIED, REPORTED, ASSUMPTION, UNKNOWN or UNPROVEN.

DECISIONS ALREADY MADE (do not re-ask): D-26 external `QDRANT_URL`, no Qdrant service on Railway; D-14 v10-only; D-29 faculty access code is the only staging gate; D-30 Celery on, `INCLUDE_CELERY` is the one switch; D-24 Lovable by PR only; D-PK8S1 Kubernetes is reference only; D-PA11Y6 axe only, no new dependency; D-PG13 graded run 12 s, default 25 s; quarantine of the 2 moved test-looking v10 points approved (Railway thread scripts it); **D-PE7: staging load run spend approved; Harsha removed the cap condition, so the harness has no default spend stop (`647ef2c`); `SPEND_CAP_USD` brings abort rule AB-1 back at 80%; the outside backstops are the provider spend limit and the Railway usage limit, which Harsha sets**; required checks approved.

ORDER OF WORK.
1. **Read the CI failure cause.** PR #97 at head `5e23438` shows 30 of 32 check runs failed within 2 to 8 seconds (VERIFIED). Use the GitHub MCP tools (`pull_request_read` `get_check_runs`; `actions_get`/`actions_list`; `get_job_logs` with `failed_only` and `run_id`). Report the first error line of 3 different failed jobs, and say whether it is a code problem or an account/runner/secret problem. If it is code, fix it test-first. If it is account or billing, say so plainly: that is Harsha's step.
2. **Fix check-name guidance.** The required-check names are `release-invariants` and `lovable-guard` (job name). Search `docs/`, `.github/`, `CODEOWNERS` comments and the register for `lovable-pr-guard` used as a check name. Correct them. Add a test that the names Harsha must enter equal the job names in the workflow files.
3. **Re-run the Mac check block** from the earlier prompt on the head (Harsha pastes output, or you run it only where allowed). Report counts. Expect ruff format 0, tsc 0.
4. **Live audit read-only:** `backend/.venv/bin/python scripts/ops/fp_live_audit.py --collection first_person_v10 --json /tmp/fp_audit.json`. Confirm C-L8 now passes. Report the state of C-L3, C-L5 and C-L7 (ids and counts only, no text) and hand them to the Opus lane.
5. **Opus review notes in your lane:** Redis `noeviction` on a Redis that holds cache and quota; the deploy script's unchecked `GIT_SHA` set; the metrics refresh exception list. Failing tests first.
6. **Remaining doable rows:** the 9 silent exception handlers outside Opus files; shrink `import_layer_allowlist.txt`; own images default to `latest` when `IMAGE_TAG` is unset in `docker-compose.prod.yml`; `redis:7-alpine` floats; replace teacher-name literals where logic-bearing, outside Opus files.
7. **Railway staging checklist** for the day after the merge: write one page of steps Harsha follows in a normal session with connectors (variables to set by name only, never values; `FACULTY_ACCESS_CODE`; external `QDRANT_URL` and read-only key; Redis policy; `GIT_SHA`; health gate `/api/healthz`; smoke test: one served clip, one abstain, one crisis route, worker alive).
8. **Staging load run** (D-PE7): prepare only. The run starts when staging exists. There is no default spend stop now; confirm with Harsha that the provider spend limit and Railway usage limit are set before the run, and keep the cost log.
9. **Mac-only extras** (ask Harsha to run): `promtool check rules infrastructure/prometheus/alerting-rules.yml`; Playwright `tests/e2e/a11y-journey.spec.ts` with the app and Supabase up (needs Harsha to allow Docker).
10. Suggest the lesson `L-REQUIRED-CHECK-NAME-IS-JOB-NAME-1` (search `lessons.md` first; append only; rebase before you push).

REPORT FORMAT. Per task: failing output, passing output, guard and formatter results, commit SHA, register row (old to new), what remains. Plain counts. UNPROVEN where not run. End with the head SHA pushed and 3 to 6 "Checks you can run".

---

## Prompt 3: Graded clean-Docker run and grading

This prompt is for the **grading thread**. It does not run Docker. Harsha runs the Docker commands.

Paste everything between the lines.

---

ROLE. You are the grading thread for the graded clean-Docker run of AskMukthiGuru. You do not run Docker, Qdrant writes, or builds. You give Harsha exact commands, wait for the pasted output, check it, and grade the result. One thread does the grading. Do not start a second grader.

START CONDITIONS. Do not begin until all four hold. Note: Stage A (2026-10-31) predates the `domain_rights_status` stamp (the serving filter went from 2 to 2,738 spans), so do not compare this run to Stage A as if the data were the same; report both and say why. Check each and say which you checked.
1. The Opus thread and the Sonnet thread both reported "pushed" with a head SHA. Use the later of the two. Write the SHA down.
2. `git fetch origin` shows the branch head equals that SHA and `git status --porcelain` in a fresh checkout of it is empty.
3. The live v10 data fixes are done (REPORTED: 16 indexes; `domain_rights_status` on 2,758 children; 2 hashless points moved; snapshot `first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot`), the quarantine of the 2 moved test-looking points has run or Harsha defers it in writing (approved; the Railway thread scripts it; UNPROVEN until an audit shows it), a fresh `fp_live_audit.py` shows no failed check, and the Qdrant snapshot is copied off the Mac. Also check `backend/.env`: `grep -n "FIRST_PERSON_.*COLLECTION" backend/.env` must show `first_person_v10` for both `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION`.
4. Harsha has decided what the run does about hard gate H2 (zero served clips with an unverified speaker). The graded compose pins `FIRST_PERSON_REQUIRE_VOICE_METHOD: "false"`. Stage A served 13 of 33 clips with an unverified speaker. Ask once: "Does H2 fail the run, or is it reported as measured and owner-accepted?" Record the answer in the sign-off. Do not change the pin yourself.

READ FIRST: `handoff.md`; `backend/docker-compose.graded.yml` (header); `/mnt/project-files/path-to-graded-run-2026-10-31.md`; `/mnt/project-files/stage-ab-evidence-review-2026-10-31.md`; `/mnt/project-files/runbooks/go-no-go-kill-switch-monitoring-2026-10-31.md`; `/mnt/project-files/research/final-pass-bar-2026-10-30.md`; `evals/first_person/grading_pass_bar.json` (approved 2026-10-31).

THE FLOW (one pass; the coordinator sends Harsha the final command text, this is the skeleton to check it against).
1. **Coordinator** sends the exact Docker commands to Harsha. You compare them with the skeleton below. Report any difference.
2. **Harsha runs, from `backend/`:**
   - `git status --porcelain` (must print nothing)
   - `docker compose -f docker-compose.yml -f docker-compose.graded.yml up -d --build --force-recreate --no-deps backend`
   - `make flush-cache`
   - `make verify-cache-empty` (exit 0 means empty; 2 means unreachable, which is NOT empty)
   - `make verify-stack-fresh` (exit 0 fresh; "unknown" means stale)
   - `.venv/bin/python -m scripts.ops.graded_run_preflight --check-logs`
   - `.venv/bin/python -m scripts.ops.graded_capture --run-id <date>-stage-a2` (writes `manifest.json`, `preflight.txt`, `rows.jsonl`, `backend.log` under `~/mukthiguru_attribution_data/graded_runs/<run-id>/`)
   Harsha pastes each output. You read it before the next step.
3. **Run rules.** No other Docker user. No embedding, build, ECAPA, backfill or index job during the run. No second Qdrant writer. One value changed per stage; name it. The OpenRouter caps in the compose (USD 100 a day, USD 300 a month) are local only. Prod caps stay on.
4. **Validity check (you do this before any grading).** The run is **INVALID** if any of these is true: the manifest says INVALID; the log contains `spend limit` or `indeterminate (timeout/error)`; the container started before the head commit; the preflight failed; a cache was not proven empty; the pinned flags differ from the container env; the SHA in the rows differs from the head SHA. An INVALID run produces no result and no number. Say so and stop.
5. **Grade.** From `backend/`: `.venv/bin/python -m scripts.ops.grade_served_answers --rows <rows.jsonl> --out <report.json> --second-model <strong OpenRouter model slug> --pass-bar ../evals/first_person/grading_pass_bar.json`. Use a strong model for stage 2 and do not let a Haiku-family model be the only judge of Haiku-family output. Re-grade **every** positive with the strong model, not a sample (Stage A re-checked only 2 of 10). Run the unanswerable set with `--unanswerable`.
6. **Score against the approved bar:** p95 latency 10 s or less; served precision 85% or more (report the Wilson 95% interval); served share of answerable 30% or more (report the interval); unanswerable core abstain 95% or more on 60+ items (69 core); harmful clips 0; hard gates 100% (0 clips from outside v10, 0 non-teacher voices, 0 hash failures, `model_used` empty on every teacher answer, crisis questions return helplines first, safety notices present where boundaries apply); no regression versus Stage A.
7. **Say what the run cannot show.** The 116 questions are a tuning set. There are no human labels. The run uses local Qdrant, eager Celery and no faculty code. State each in the report.
8. **Human labels.** Ask Harsha or faculty to label the 50-clip sheet from this run. Report judge-versus-human agreement when it comes back. Until then the precision number is "judge-graded, human check pending".
9. **Sign-off page.** Write `docs/releases/GRADED_RUN_<date>.md` (no quote text; ids only): head SHA, run id, validity result, table of bar versus result, failures with ids, H2 answer from Harsha, UNPROVEN list, verdict. Verdict values: **NO-GO**, **CONDITIONAL GO**, **GO**. Use GO only if every bar item passes on a valid run and the human check agrees. Otherwise NO-GO or CONDITIONAL GO with the named conditions. Publish a new version of the Pending List artifact with the same table.
10. **Kill switch and monitoring.** Confirm the plan in the go/no-go runbook is current (`GENERATION_KILL_SWITCH_ENABLED=true`, halt steps). It is UNPROVEN until the drill (runbook B7) passes. Say so.
11. **After the grade:** only then does Harsha rotate keys. Do not rotate or ask for keys before.

IF THE RUN FAILS. Do not tune the tuning set to pass. List the failing ids and the failing gate. Hand safety failures to the Opus lane and ops failures to the Sonnet lane through the coordinator. Do not change a gate, a threshold or a pin to make a number pass.

REPORT FORMAT. Validity result first. Then the bar table with counts and intervals. Then failures with ids. Then UNPROVEN items. Then the verdict. End with "Checks you can run" (3 to 6 commands or files).

---

## Final checklist, end to end

Order matters. Items marked **H** are Harsha's. Items marked **A** are an agent's.

1. **A** Sonnet: read the CI failure cause (30 of 32 checks fail in seconds). Report it.
2. **A** Opus: re-run the backend suite in a worktree and report counts; close the Stage A safety gaps (health gate, support-line trigger, grader rubric).
3. **H** Copy the Qdrant snapshot off the Mac (fresh snapshot, hash, a drive or bucket that is not the Mac). Also copy `~/mukthiguru_attribution_data/`.
4. **H** Set the provider spend limit (OpenRouter) and the Railway usage limit, both with alerts.
5. **H** Turn on required checks in GitHub for `main`: `release-invariants` and `lovable-guard` (the job name, not `lovable-pr-guard`), plus "require a pull request". Do it after step 1, so a check that always fails does not block every merge.
6. **A** Live v10 indexes: done (REPORTED: 16 indexes, 4,226 points, audit shows no failed check). Re-confirm with the read-only audit.
7. **A/H** Live v10 data fixes: done on 2026-11-07 (REPORTED: `domain_rights_status` stamped on 2,758 children; 2 hashless test-looking points moved). **Quarantine of those 2 points: approved by Harsha; the Railway thread scripts it; UNPROVEN until the audit shows it.** **H** Move the rollback backups out of `/tmp` (one holds quote text; never commit it). **A** Opus: independent review of the three data scripts; list the 22 children without `speaker_verified`.
7b. **H/A** Check `backend/.env`: `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` both `first_person_v10`.
8. **A** Opus and Sonnet: report "pushed" with the head SHA. Merge or rebase the 4 commits that `main` has and the branch lacks.
9. **H** Decide the H2 question (zero unverified-speaker clips: fail the run, or report as owner-accepted).
10. **Coordinator** sends the exact Docker commands. **H** runs them (clean tree; compose up with the graded override; flush; verify cache empty; verify stack fresh; preflight; capture). **A** (grading thread) checks validity, grades with a strong second model on every positive, scores against the approved bar, writes the sign-off page, updates the Pending List.
11. **H** Listen to the 11 demoted clips (Opus supplies the list).
12. **H** Add the Telugu crisis row to the test sheet (a native speaker supplies the phrase).
13. **H** Label the 50 served clips (or have faculty label them).
14. **H** Only after the run is graded: rotate keys (OpenRouter, Supabase, Qdrant read and write, JWT secret, Redis password, Railway tokens; the old Helm literals are burned).
15. **H/A** If the verdict allows: one PR to `main` (PR #97), Harsha types approval in the thread, then Railway staging in a normal session with connectors (Sonnet's Railway checklist), then the staging load run (no default spend stop; the provider and Railway limits from step 4 are the backstop; keep the cost log).

Verdict while any item above is open: **NO-GO**.
