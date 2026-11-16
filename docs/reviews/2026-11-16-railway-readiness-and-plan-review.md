# Railway staging readiness and mission-plan review (2026-11-16)

Written by an AI agent on local evidence. Production is unmeasured. This document
reviews `docs/plans/ENGINEERING_MISSION_PLAN_2026-11-16.md` using the
loop-design-check frame:

- a goal must be machine-decidable;
- the verifier must not be gameable;
- a loop must stop.

## 1. Router and crisis: what is live

1. **Crisis detection is three layers, and the last one is an LLM.**
   - The layers:
     - an intake kernel (a fixed phrase list);
     - the engine's rules (`assess_distress`);
     - a Claude Haiku 5.5 escalation on every message (commit 89128ddd), which can raise a verdict to SEVERE or CRISIS but never lower one.
   - On 24 crisis paraphrases, the rules caught 4.
   - Haiku caught all 20 that the rules missed.
   - Haiku raised 0 false alarms on 116 ordinary questions.
   - Haiku's median time was 1.1 s.
2. **The question router is mostly rules, not Jev.**
   - `OffTopicStage`, `CasualShortCircuit` and the bridge make their decisions with rules.
   - Jev (`JevRouterService`) is called only for "ambiguous-domain" questions, and it has a **0.45 s** timeout (`intent_router_ambiguous_domain_timeout_s`).
   - An OpenRouter call rarely returns that fast, so these questions fall back to the neutral lane.
   - The backend log shows 0 Jev lines in the last 48 h.
   - The Jev in `rag/nodes/intent.py` is enabled (`intent_router_jev_enabled=True`, checked in the live container), but the worker logged 0 Jev decisions in 24 h: the first-person module claims the turn first. The ambiguous-domain branch is off live (`intent_router_ambiguous_domain_enabled=False`).
   - **Verdict:** the router is not "top notch". It is a regex router with an LLM that almost never gets to answer.
3. **The router is not what protects the user today.** That job is done by the gates that run after retrieval:
   - answerability (Llama 3.1 8B);
   - the relevance judge (Haiku, minimum score 3);
   - the per-clip judge.

   A wrong route ends in an abstain, not a wrong teaching.
4. **Fix, if wanted.** This changes which answers are served, so it needs a registered run.
   - Option: raise the ambiguous-domain budget to about 2 s.
   - Option: send every non-crisis turn through one Haiku classifier.
   - Either way, measure it on the 116-question set plus the negative controls before switching it on.

## 2. Data quality: are we good?

**No. Data, not code, is what blocks "the best answer to every question".**

1. **Integrity is good.** The serving collection `first_person_v10` holds 4,224 points. Of these, 2,758 have text, and the hash matches on all 2,758.
2. **Graded-9 (the latest registered run) fails.** The showable share was 0.45. The bar is 0.85 (as a Wilson lower bound).
3. **Coverage is low.** 31 of 89 answerable questions were never served a clip in any run.
4. **Answers are not stable.**
   - Only 58% of clips stay the same across runs.
   - HyDE timed out on 71 of 160 calls.
   - So the same question can get a different clip.
5. **The ceiling is segmentation, not selection.** Judge replay:
   - the v1 rubric keeps 34 clips at a precision of 0.50;
   - the v2 rubric keeps 20 clips at a precision of 0.75.

   Neither passes bars 1 and 2.
6. **EM-03b.** 6 stored clips are not a fixed point of the cleaner, which breaks invariant 13. Fixing them is a store write.
7. **One clip serves too many questions:** `UlOt31lBhLY@101`, the hub clip.

## 3. Resegmentation: honest status

1. **The dry run proves little.**
   - The results are in `audits/evidence/dry_run_resegmentation_results.json`: 3 cases, reported as "PASS 3/3".
   - The cases were picked by hand because they could be fixed, and an AI judged the result.
   - It shows the idea can work, not that it does.
2. **Ruthless problem: the new clips are too long.**
   - They are 455-630 words, about 3-4.5 minutes each. Invariant 11 says 18-25 s.
   - The playback window plays the whole span, so a faculty viewer who asks a question gets a 4-minute clip.
   - The old 15-word fragment and a 630-word block are both wrong.
   - The fix needs a cap on words or seconds. Proposal: at most about 90 s or 250 words. This is an owner decision.
3. **Before resegmented clips can serve:**
   1. Run it on the whole corpus into a shadow collection. The script `build_shadow_resegmented_index.py` exists; it is untracked and belongs to the other session.
   2. Compute the embeddings host-side (invariant 18).
   3. Set the hash fields.
   4. Do a registered graded run against v10.
   5. Switch `FIRST_PERSON_COLLECTION`, and keep v10 for rollback.
4. Until then, the demo serves v10, as measured in graded-9.

## 4. Mission-plan review (ruthless)

1. **The header is stale.**
   - Section 0 says EM-01 and EM-02 are "uncommitted".
   - EM-01 (S-01) is in fact committed, in 89128ddd.
   - EM-02 (`first_person_bridge.py`) is still uncommitted, and it is the other session's.
   - Update section 0 before anyone acts on it.
2. **EM-05 is not a defect on any live path.**
   - `validate_session_id`, `validate_correlation_id`, `validate_iso_date` and `validate_user_id` all call `.strip()` before they match.
   - Probe on 2026-11-16: input `'abc\n'` came back as `'abc'`.
   - Downgrade it to a cosmetic `fullmatch` cleanup, and don't spend a slice on it.
3. **EM-07 is now covered on the chat route.**
   - EM-07 is the prerouter missing "suicidal"; the Haiku escalation now covers it on the chat route.
   - Keep it open only for channels that do not run `DistressStage`. WhatsApp needs checking (mission area D).
4. **The plan is too big for a deploy decision.**
   - Phases 1-9 are a multi-week refactor: regex moved to data, plus 12 audit areas.
   - None of it is needed for a staging demo.
   - Loop-design-check: areas A-L have no machine-decidable stop. "Honest readiness statement" cannot be decided by a machine.
   - Either give each area one pass/fail check, or treat the areas as a backlog rather than a loop.
5. **The plan is missing the two things that actually move answer quality:**
   - resegmentation with a length cap (section 3);
   - retrieval determinism (the HyDE timeouts, and clip stability at 58%).

   Both have decidable goals:
   - a showable share of at least 0.85;
   - the same clip for the same question in at least 95% of reruns.
6. **The R2 golden snapshot is the right first move.** It makes every later refactor decidable ("the snapshot is identical"). Keep it.
7. **The verifier can be gamed.**
   - The graded run uses LLM graders.
   - The judge rubric was tuned on the same 116 questions (the owner has said 116 is the tuning set).
   - A loop that iterates until graded PASS on that set will overfit.
   - A held-out set is needed before any autonomous loop is pointed at the bar.

## 5. What is pending before Railway staging (numbered, decidable)

| # | Item | Owner | Done when |
|---|---|---|---|
| 1 | Merge `origin/main` (4 frontend UX commits made by Lovable) into local `main`, then push the 13 local commits | Harsha | `main` is level with `origin/main` |
| 2 | CI runs only by hand (EM-10). Run `lint-test` once on the pushed sha | Harsha | Workflow is green on that sha |
| 3 | Railway Qdrant has `first_person_v10` (4,224 points) and server v1.20 | Harsha, or an agent with Railway auth | A count query on Railway returns 4,224 |
| 4 | Railway variables match the local posture: `FIRST_PERSON_SERVING_POSTURE=v10_only`; harness and terminal `true`; both collections `first_person_v10`; bridge on; fallback off; `DISTRESS_LLM_ESCALATION_ENABLED=true`; Haiku slug allowed in `OPENROUTER_EXTRA_ALLOWED_MODELS` | Harsha | Startup log shows `v10_only_mode_active` and no B4 error |
| 5 | Deploy settings: health gate `/api/healthz`; `FORWARDED_ALLOW_IPS=10.0.0.0/8`; `PYTHON_MEMORY_LIMIT_MB=0`; memory at least 4 GB (2.6 GB measured locally after the in-process warm-cache fix) | Harsha | Deploy is healthy, with no exit 137 |
| 6 | Demo quota: sign in for the demo, or raise `ANON_QUOTA_MESSAGES` | Harsha | 10 demo questions are answered with no 429 |
| 7 | Smoke test on Railway: the 3 runbook questions, 1 crisis phrase (expects 14416), and 1 out-of-corpus question (expects an abstain) | Agent | All 5 behave as expected |
| 8 | Clinician signature on three notes: 429 helplines, phrase gap, LLM escalation | Clinician | Signed. Per CLAUDE.md, not a staging blocker |
| 9 | Pass the registered bar | Blocked on resegmentation | Cannot be reached on v10. Do not promise it at the demo |

Items 1-7 are enough for a faculty **staging** demo, with one known limit: only about
half of the clips shown are rated showable by both graders.
