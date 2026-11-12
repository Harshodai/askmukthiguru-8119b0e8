# Handoff: first-person verbatim route, readiness goal (2026-11-13)

Repo: /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8, branch feature/audit-strengthen-rag-qdrant.
Head 11dbfa9a is pushed to origin (confirmed by git fetch). Working tree: one untracked file, backend/tests/test_standalone_perturbations.py (intentionally uncommitted, awaiting owner call).
main = 46b808fb, 0 commits ahead of the feature branch. Merge would be a fast-forward of 329 commits. NOT merged.

## Goal status
Goal: "complete everything, make ready for Railway deployment, apply the Medium article, use Opus as a subagent, leave nothing".
NOT complete. Reasons, all verified:
- Not merged to main (owner decision pending).
- Graded-7 not run. Needs owner spend approval and a clean image build from 11dbfa9a.
- Second-grader evaluation not done (planned: google/gemini-3.6-flash, configured in backend/app/config.py gemini_model; slug not verified live).
- Strict end-to-end reader: 7 of 43 served graded-6 answers answer the question (ANSWERS 7, PARTIAL 24, MISSES 12). Automated judge said 34 showable. Both readers are AI.
- Same-clip defect unfixed: 43 served answers use 31 distinct clips; 9 clips serve 21 answers. The scorer gave clips 3 to questions they do not answer.
- Standalone gate gaps (deterministic, measured 2026-11-13): truncated clips refused 14 of 40; "So " prefix refused 0 of 40. Recorded as strict xfail in backend/tests/test_standalone_perturbations.py, not fixed.
- Negative-control set (question paired with a clip from another question) only proposed, not built.
- Railway readiness not established. Staging/demo blockers are listed below.

## What was done (committed in 11dbfa9a)
- Redis URL password masked in coalescer success and failure logs (backend/app/sanitization.py redact_url_credentials). Tests: backend/tests/test_log_redaction.py.
- Anonymous user ids logged as hash (pseudonymize_identity) in pipeline_coordinator PERSONALIZATION_PROBE and related logs.
- Harness abstain log now gives judge per-clip reasons (first_person_judge.rejection_reason). The old "(< min)" label was wrong: the judge serve rule also needs answers/standalone/complete/safe. Tests: backend/tests/test_fp_judge_rejection_reason.py.
- Orchestrators reuse container.telemetry_sink (app/orchestrator.py, app/stream_orchestrator.py). Test doubles fixed (spec mock needed telemetry_sink).
- Standalone gate: three anaphoric openers added (here you receive / since your X is / when this X breaks down) in backend/services/first_person_evidence_policy.py. Clip-specific patterns removed as overfit. Tests: backend/tests/test_standalone_openers.py.
- Graded compose pins: FIRST_PERSON_JUDGE_MODEL and FIRST_PERSON_CONTEXT_USE_SPARSE=false in backend/docker-compose.graded.yml. Graded-6 sparse=false had lived only in an override outside the repo; the code default is True (app/config.py:333).
- CLAUDE.md invariant 22: gate budget 6 s corrected to 12 s (_ANSWERABILITY_TIMEOUT_S = 12.0). Note: an Opus review claims graded-6 ran with the answerability gate OFF; config defaults it ON and the graded compose does not pin it. UNVERIFIED. Check the graded-6 manifest/logs before trusting the CLAUDE.md edit.
- lessons.md: Nov 13 entries added at top (overfitting, judge serve rules, unpinned config, n=43 bounds, second grader at 1%, URL secrets in logs, unrecorded v11, mock spec attrs, claims from config memory, native BM25 vs learned sparse).
- Full backend suite on final edits: 14,095 passed, 0 failed, 22 skipped.

## Measured facts for decisions
- Graded-6 (sparse off, min 3, judge on, single judge Sonnet 5.5 both slots, 1% second-slot sample): 43 of 89 answerable served (48.3%); automated showable 35/43 (81.4%); p95 8.07 s; harmful 0; unanswerable 69/69 pass; core abstain 1.0.
- Graded-5 (sparse on): 26 served, showable 20/26 (76.9%), p95 12.7 s.
- Wilson 95% interval for 35/43: roughly 67% to 91%. A run at n=43 cannot show the 85% bar.
- Opener patterns: 7 of 43 graded-6 served clips would be refused by the earlier, broader set; 8 of 2,758 v10 children match the final patterns (blast radius).
- Collection first_person_v10: 4,224 points, green. first_person_v11 also exists (4,360 points): stale fork, 2,885 of 2,887 children lack domain_rights_status, two points from a removed video. Contract entry in backend/config/first_person_serving_contract.json. Do not build v11/v12 before deciding its status.
- Qdrant v1.20 article (Medium copy in ~/Downloads): native BM25 on the full-text index does not apply to our BGE-M3 learned sparse vectors. Code tokenizer, nested indexes, turbo8/16 skipped. Upgrade from qdrant 1.18.0 not now.
- Answer-level claim: with one verbatim clip per answer, "85% answers the question" is not reachable on this corpus (Opus). "85% showable" is reachable mainly by abstaining more.

## Opus reviews (read-only, reports in the session scratchpad)
- /private/tmp/claude-501/-Users-harshodaikolluru-Public-askmukthiguru-8119b0e8/5c36588b-cf62-4ca3-a82b-aa9385738020/scratchpad/opus_plan.md (article fit, fix plan)
- .../scratchpad/opus_prerun_review.md (pre-run review: verdict RUN AFTER ITEMS 1-6; items 1-3 now done)
- .../scratchpad/pre_run_criteria.md (pre-registered criteria with amendments)
- .../scratchpad/graded6_answer_review.md (strict reader, 43 rows)

## Pre-registered criteria (scratchpad/pre_run_criteria.md)
Both graders >= 90% showable, lower bound >= 85%; strict ANSWERS >= 85% (not reachable now, so the AI stage will fail until selection/corpus changes); served share >= 30%; p95 <= 10 s; harmful 0; unanswerable 100%; abstain >= 0.95; crisis 7/7; hub rule (no clip serving more than 3 questions); invalid-run rules. Human sample of 50 is a separate later stage.

## Blocked on owner (not doable by agents)
1. Merge to main: fast-forward of 329 commits. Owner decision after graded numbers.
2. Graded-7 spend and second-grader spend approval.
3. Sparse default on/off (Settings default is True).
4. Budget reservation policy: calls with no provider response keep their reserve (backend/services/llm_budget_guard.py settle()). Fail-closed by design; a stall can exhaust the daily cap.
5. Demo scope: may the demo serve below the 85% bar, labelled as demo.
6. v11 status: keep, rebuild as v12, or remove.
7. Human-only gates (production, not staging/demo): native-speaker review, clinician review, helpline phone verification, rights sign-off, 299-item gold batch, human answer sample.
8. Demo UI: frontend src/lib/answerAnnouncement.ts says "no close match" for groundingState 'abstained'; served clips carry 'abstained' by design (verification.passed false). Screen-reader users hear the wrong announcement over a clip. Decide the contract before demo.

## Agent-owned next work (in order)
1. Build negative-control set: pair each question with a clip answering another question; the gate should abstain on nearly all. Building the set costs no spend; running it calls the scorer.
2. Fix standalone gate gaps: truncation (ends mid-clause without terminal punctuation) and "So " prefix. Convert the two xfail tests to passing tests once fixed. Any change to served answers needs a graded run to count.
3. Same-clip defect: the root is scorer leniency, not retrieval order. Options: negative-control-driven scorer rubric, abstain when the best clip is reused across unrelated questions, or a judge that compares candidates. Re-ranking by score alone is not a fix.
4. Second grader from another family on the same rows (every row, not 1%). Verify slug live first.
5. Graded-7 on committed code only after owner spend approval. Use the pre-registered criteria and do not re-run to pass.
6. Commit the untracked perturbation test file if owner agrees.
7. Railway staging: the staging env file, clean-Docker proof for invariant 25 (CLAUDE.md), grounding label decision, demo labels ("Related, not a direct answer"). Resuming Railway is owner-only.

## Operational notes
- The stop hook checks only the goal text, not the owner's decisions. Clear it with /goal clear if the loop continues.
- The sandbox denied push from the agent; the owner pushed by hand.
- Graded run command shape (from the graded runbook): backend/.venv/bin/python -m scripts.ops.graded_capture --run-id <id>; then scripts.ops.grade_served_answers (3a with --unanswerable; 3b with --first-model/--second-model and --sample-fraction 1.0 for the criteria).
- The backend container runs a graded-6 config from an earlier recreate, not 11dbfa9a. Rebuild a clean image before graded-7.
- Health and redis samplers from graded-6 are finished or dead; check before reuse.

## Update 2026-11-13 (later): agent-owned work round 2 (uncommitted at time of writing; see commit note)

Done, tested, no paid calls, no Qdrant writes, no push:
1. Negative-control set: `evals/first_person/build_negative_controls.py` (seeded, seed 20261113, no LLM) writes `evals/first_person/negative_controls.jsonl` (116 pairs, question paired with a clip from another question; only ids and 12-char clip hashes, no clip text). Schema and pairing tests: `backend/tests/test_negative_controls.py` (7 pass). Caveat: the pairing assumes the pair should abstain; some clips are on-topic for both questions. Review served pairs before trusting the abstain rate.
2. Standalone gate:
   - "So " opener: a narrowed resumptive rule (So + what/how/why/when/where/who/generally/basically/now/then/this/that/these/those) in `services/first_person_evidence_policy.py`. Refuses 3 served clips (q004, q071, q084). A broader "any So" rule broke the existing test `test_so_opener_is_a_fine_opener` (which keeps "So both …" valid), so it was narrowed rather than overriding the test. Converted to a passing test in `backend/tests/test_standalone_perturbations.py`.
   - Truncation: NOT fixed. The xfail stays strict, because a punctuation-free ending is a judge-approved valid ending in this repo (see the `_ends_on_dangling_word` docstring and lesson L-XFAIL-PREMISE-CAN-CONFLICT-WITH-INVARIANT-1). It needs an owner decision about what counts as a cut, not a rule change by an agent.
3. Same-clip defect: analysis only, `docs/analysis/SAME_CLIP_DEFECT_2026-11-13.md`. Recommends a comparative judge (candidate A) measured on the negative-control set first; then a rubric change. No scorer or serve-rule change made.
4. Graded-7 runbook: `docs/runbooks/GRADED_7_RUNBOOK.md`. Not executed. Paid and write steps are marked. Grader slugs verified live by a read-only model-list call: google/gemini-3.6-flash, anthropic/claude-sonnet-5.5, anthropic/claude-haiku-5.5 are all listed (listed is not proof of a working call under budget policy).
5. Lessons: round 2 entries added at the top of lessons.md (L-SO-RULE-MUST-RESPECT-EXISTING-TEST-1, L-XFAIL-PREMISE-CAN-CONFLICT-WITH-INVARIANT-1, L-NEGATIVE-CONTROL-IS-AN-ASSUMPTION-1, L-RUNBOOK-IS-NOT-A-RUN-1, L-PROMPT-OPTIMIZER-IS-ADVISORY-1).

Served-answer impact of the gate change (deterministic, no LLM): 6 of 43 graded-6 served clips now refused (q004, q029, q043, q071, q081, q084). The strict reader had marked q004, q071 and q081 as MISS or PARTIAL; q084 was PARTIAL; q029 and q043 were judged MISS or PARTIAL too. No graded run has measured this effect yet.

Still owner-only: merge to main; graded-7 and second-grader spend; sparse default; budget-reservation policy; demo bar; v11 status; truncation definition; demo "no close match" announcement; production gates.
