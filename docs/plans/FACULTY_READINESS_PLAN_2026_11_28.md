# Faculty readiness: live eval, findings, fixes and acceptance criteria (2026-11-28)

Scope: the production backend `https://askmukthiguru-8119b0e8-production.up.railway.app` (deployment `c2ccbe86`, JSON logs and per-turn trace on) and the frontend on `https://askmukthiguru.lovable.app`. Faculty sign in with Google; there is no access code and no custom domain yet. Numbers are tagged **measured**, **modelled** or **unverified**.

## What was run (measured)
- Live battery against production, anonymous sessions: `frozen29` (29 on-topic), `ooc13`, `compound10`, `unanswerable38_draft`, the 25-row `conversation_cases_draft` (multi-turn, ambiguous, apparent-contradiction, plain-fact). The runner was ad hoc (see `L-LIVE-EVAL-1`); the repo batteries `scripts/ops/first_person_live_matrix.py` and `live_smoke_battery.py` should be preferred next time.
- 5,000 Railway log lines read; 81 `answer_outcome` records aggregated.

## Results (measured)
| Set | Result |
|---|---|
| frozen29 on-topic | 16 served a clip, 12 abstained, 1 meditation short-circuit |
| out-of-corpus (13) | 0 leaks: 4 blocked, 4 boundary, 4 abstain, 1 live-info |
| unanswerable (38 draft) | 0 served: 26 abstain, 7 blocked, 5 boundary |
| compound (10) | 6 served, 3 abstained, 1 HTTP 429 (rate limit) |
| multi-turn (6 pairs) | 7 of 12 turns served; 1 turn returned LLM prose (the leak, fixed below) |
| ambiguous (6) | 2 served a clip without clarifying, 2 returned the crisis helpline for "how do i get rid of it?" and "should i leave it or hold on?", 2 abstained |
| apparent contradiction (6) | 1 served, 5 abstained |
| plain-fact (6) | 6 abstained with the generic text (no logistics pointer) |
| latency | p50 4.0 s, p95 12.4 s, max 24.7 s |
| log outcomes (81) | 26 `answerability_withheld`, 17 `no_verified_clips`, 16 served, 11 boundary, 10 other abstains |

## Defects found and what this PR does about them
| # | Defect | Evidence | Fix in this PR | Acceptance criterion |
|---|---|---|---|---|
| 1 | LLM prose on the general lane with fallback off | mantra-vs-prayer turn, `route=general_knowledge_unverified` | `intent.py` coerces Jev general/live_research to the teaching lane when fail-closed; bridge difference carve-out removed | `tests/test_fp_only_no_generated_comparison_2026_11_28.py` green; live re-run of the 2-turn case returns `first_person_abstain` |
| 2 | Serial Qdrant enrichment, slow tail | 15 `enrichment window timed out after 1.50s` warns; modelled up to N x 1.5 s | `_widen` runs concurrently, same deadline and order | live p95 below 10 s on a 40-question rerun (**unverified until redeploy**) |
| 3 | Gate rejections unexplained (`integrity` 4-5 per question) | one counter bundles about 13 checks | `integrity_<reason>` and `abstain_<reason>` counters, failing gate names in the warn line | rerun the eval; read the reason distribution from `fp.rejected`; root cause stays **unproven** until then (suspect: YouTube oEmbed from a datacenter IP) |
| 4 | Duplicate nodes in the personal graph | one node per memory row, id-only dedupe, no `created_at` | server merge by (type, normalised label) with `merged_count`, client dedupe, layout and overlap pass | A: no duplicate (type,label); B: no dangling edge; C: nodes <= limit; E: 5 identical memories -> 1 node with `merged_count` 5 (backend and vitest tests) |
| 5 | Faculty gate dead code and stale packet | gate off in prod but boot guard kept; packet quoted 63.1 percent and a dead domain | gate, guards, tests removed; packet rewritten | repo grep for `FACULTY_ACCESS_CODE` clean except history; packet URL returns 200 |
| 6 | Secret printed in a tool listing | `ANON_SESSION_HMAC_SECRET` | rotated on backend and celery (takes effect at redeploy) | old anon tokens return 400 and the frontend re-mints one |

## Not fixed here (owner decision or measured experiment first)
1. **Answerability gate abstains on simple questions** ("Is it okay to cry?"). It is a single question-only YES/NO LLM call; threshold and gate semantics are owner decision T-E1. Experiment, shadow only: human-label showable vs not on frozen29 and the 116 bank (check kappa), log the answerability verdict and gate chain without blocking, report the false-abstain rate on showable items and the wrong-serve rate on out-of-corpus items, split `indeterminate` (plumbing) from `no` (judgement), oversample abstained cases because a 50-item set gives wide intervals. Sources: MLflow LLM-judge calibration (opened); arXiv 2411.06037 and others (search snippets only).
2. **Ambiguous questions** are served a clip or the crisis line with no clarifying question. Product decision on a clarify turn.
3. **Crisis helpline on ambiguous phrases** is the conservative design; false positives are accepted, loosening needs the clinician gate.
4. **Plain-fact questions** ("what time does satsang start?") get the generic abstain; a logistics pointer needs owner copy.
5. **Human gates unchanged:** native-speaker and clinician reviews, 299 gold labels, rights sign-off, helpline calls, 50-row speaker sign-off.
6. **Data:** no full re-ingest. A shadow-only top-up for the 123 audio files with no points, the 303 clips over 120 words and the 461 `ecapa_failed` speaker rechecks, into a new collection, run at low priority on the host (one worker, `nice`, resumable). Not started; needs approval.
7. **Monitoring:** no uptime alert, no rehearsed rollback, backup cron not installed. Owner items.

## Pre-invite checks (agent-checkable after redeploy; UNPROVEN until run)
1. `/api/healthz` 200 and `/api/capabilities` `ready: true`.
2. CORS preflight with Origin `https://askmukthiguru.lovable.app` returns 200 with that origin.
3. Smoke chat served in under 10 s; the mantra-vs-prayer 2-turn case returns the static abstain.
4. Log severities are real; `answer_outcome` carries `fp.rejected` with `integrity_<reason>` names; no question or clip text in logs.
5. Graph page with a seeded account shows no duplicate labels (screenshot).
6. 12 sign-ins from one network: 3 questions each in 60 s produce no HTTP 429 (per-identity limit is 20/min; the anonymous per-IP limit is the one to watch).

## Sources
Opened: Databricks, collect user feedback (https://docs.databricks.com/gcp/mlflow3/genai/human-feedback/user-feedback); "Every LLM feature needs a kill switch" (https://dev.to/zeybek/every-llm-feature-needs-a-kill-switch-3mf7); MLflow LLM-judge calibration (https://mlflow.org/articles/llm-judge-calibration/); OpenRouter limits (https://openrouter.ai/docs/api_reference/limits). Search snippets only, not opened: arXiv 2411.06037, 2601.04525, 2605.05482, 2604.08046.

## Artifact filters + length cap (always on since 2026-11-28, owner decision: no flag for behaviour that should simply be on)
- Inside the content quality gate, clips are rejected with bounded counters in `fp.rejected` (no text): `artifact_asr_restart` (lone lowercase one-word sentence, e.g. "everything. everything."), `artifact_audience_address` ("please be seated", "are you ready", "from today you are/will", "has freed"; applies even to Soul Sync practice clips), `artifact_outcome_promise` ("magic potion", "heal your ... of all", "everything happens. Everything comes."), `artifact_short_question_tail` (ends in a question of 4 words or fewer).
- `FIRST_PERSON_MAX_CONTEXT_WORDS=150` set on Railway (code default 600): the harness drops the span furthest from the hit until a multi-span window fits; a single span already over 150 words cannot be trimmed and is not served (`too_long`).
- Expected effect (modelled from a scroll of `first_person_v13_shadow`, not measured live): about 6 percent of servable spans removed by the filters, 4 videos lose all servable spans; the length cap removes the longest spans (162 spans exceed 140 words). Re-run the independent clip grader after deploy.
- Not shipped (precision risk): spaced-hyphen ASR errors (9.5 percent of spans) and repeated-word and "ends in ?" filters; the spaced hyphen needs a re-ingest with an extended `asr_cleaner` (invariants 2/13).
- `FIRST_PERSON_BOUNDARY_GUARD_ENABLED` is not set anywhere in this repo, so in prod it is the code default `False`: boundary quality rests on the standalone and relevance gates plus the v13 builder's snapping.

## Post-deploy results (2026-11-28, deployment 5e1cdacb of PR 124; measured)
- `/api/healthz` 200, `ready: true`, CORS preflight from `https://askmukthiguru.lovable.app` 200 with that origin.
- Mantra-vs-prayer returns the static abstain (single-turn re-check; the leak was found in a 2-turn session).
- Rotated anon secret: with the published frontend a stale token re-mints and the answer is served (49 of 50 counter). The published bundle did not contain the fix until the owner published the frontend; the backend now returns 401 for a signature mismatch so older clients recover too.
- New counters live: of 19 `decide_abstain` outcomes in the first 40 post-deploy turns, 15 were `abstain_not_standalone`, 3 `abstain_question_only_clip`, 1 `abstain_speaker_unverified_or_no`; only 1 `integrity_speaker_unverified`. The "integrity 4-5 per question" seen before was the old bundled counter, not a corpus defect.
- 12 users, 36 distinct questions: no errors, p50 15.5 s, p95 34 s, wall 75 s; 24 abstained (odd phrasing), 12 served. Same-question burst (cache) p95 5 s: not representative.
- Independent grader on 34 served clips (before deploy; Sonnet, not a human): 65 percent relevance 2 or higher, 35 percent 0-1, 76 percent with a defect. Artifact filters (default off) address part of it; the rest needs re-ingest or the judge.
- Crisis phrases in hi/te/ta/kn return the helpline with no clip.

## Strict first-person release closure added in PR #127

The live audit found that Railway was still running `main` commit `5a244534` from PR #125, not PR #127's answer-window commit `199e569d`. Consequently, no Railway result may be used as evidence for the new range-selection implementation until the owner merges PR #127 and verifies the resulting deployment commit.

This PR now makes the strict source-only contract executable at both the pipeline and API boundaries. A served `answer_text` must equal the exact space-joined `citation.verbatim_text` values; otherwise the route returns the deterministic abstention with zero citations. The dedicated route no longer exposes an LLM-generated `translated_text` gloss alongside teaching citations. Non-English input may still be translated for retrieval, but the served teaching body remains the original source words.

The faculty gate now performs a direct known-teaching provenance check requiring exact reconstruction, `is_verbatim=true`, `speaker_verified=true`, `domain_rights_status=licensed`, and `boundary_status=verified`. It rejects generated gloss fields and malformed citation bodies. It also turns known canonical-memory dreamer errors and OKF/editorial HTTP 499 client-abort activity into hard readiness failures instead of warnings. A clean gate is therefore necessary but not sufficient: native-speaker, clinician, rights, and owner review packets remain human gates.

The post-merge acceptance battery must include one known direct teaching, one contiguous multi-span answer, one out-of-corpus question, one acute-safety question, and one non-English request. The multi-span case must prove that the visible body is reconstructed from the selected verified spans and that an invalid or failed LLM range falls back or abstains without generated text.

## Hardening verification (2026-11-28, PR worktree)

- `python3 -m py_compile` passed for the changed route, pipeline, tests, and faculty gate; `git diff --check` passed.
- Ruff import checks passed for all changed Python files; the isolated new faculty-gate contract test passed **4/4** with `pytest --noconftest`.
- The full focused pytest invocation was attempted from `backend/`, the repository-required dependency path, but the host interpreter is Python 3.9 while the checked-in backend code requires Python 3.12 (`str | Sequence[str]` fails during import). No dependency installation or source workaround was made; the dependency-complete focused suite remains a CI/container gate.
- The earlier repo-root pytest attempt was correctly rejected by the repository’s splitter-shadowing guard; it was not treated as test evidence.

## PR #127 post-join audit and faculty-readiness matrix (2026-11-29)

The cross-video editorial path had a real quality gap: each parent context was gated independently, but the final multi-video body was assembled with a separator that did not match the public citation reconstruction contract, and no final grammar/coherence/relevance evaluator inspected that joined body. PR #127 now reconstructs the body deterministically from the exact citation texts, evaluates the final source-only body through the existing relevance scorer, records bounded evaluator timing, and fails closed on mismatch, disabled evaluation, malformed output, rejection, timeout, or unexpected evaluator failure. The evaluator can return only metadata; it cannot rewrite teaching text. If the composite is rejected or indeterminate, the serving path may fall back only to an already-gated single result, never to an unchecked composite.

| Gate or evidence | Status | Ruthless interpretation |
|---|---|---|
| Exact source-only body at pipeline and API boundaries | **PASS (code/tests)** | Visible teaching must equal the space-joined citation `verbatim_text`; generated gloss fields are rejected. |
| Same-parent contiguous multi-span stitching | **PASS (code/tests)** | Ordered spans are deterministically joined and re-run through the serve-time gates. |
| Cross-video deterministic selection and exact reconstruction | **PASS (code/tests)** | Distinct verified citations are joined only from already-gated results; no LLM-authored body is permitted. |
| Final cross-video grammar/coherence/relevance evaluation | **PASS (code/tests)** | The evaluator sees the final joined body and may only accept/reject/score metadata. |
| Evaluator rejection, indeterminacy, disabled gate, or exception | **PASS (code/tests)** | Composite serving fails closed or falls back to one already-gated result; no composite leak. |
| Railway deployment of PR #127 | **UNPROVEN** | Read-only Railway metadata confirms deployment `17530dcb-e9f8-42e4-993f-ef3c838e9faf` runs `main` commit `5a24453434dbe9d2c67a48925cfebb70d9bf66c5` (PR #125), not PR #127. |
| Production latency, reason distribution, and post-redeploy smoke battery | **UNPROVEN** | Must be measured after merge and deployment, not inferred from local tests. |
| RLS cross-user end-to-end workflow | **UNPROVEN** | No fresh production/test-environment evidence. |
| Supabase backup secret, successful backup, and restore drill | **UNPROVEN** | Operational evidence is absent. |
| Role migration applied and faculty admin access verified | **UNPROVEN** | Migration application/proof is absent. |
| Native-speaker, clinician, helpline, rights, gold-label, and speaker human gates | **HUMAN-PENDING** | Empty or unsigned review packets are not approvals and must remain open. |
| Monitoring, rollback rehearsal, and corpus top-up/re-ingest | **OWNER-PENDING** | No unattended production change is authorized by this PR. |

### Acceptance criteria for the joined-answer evaluator

A multi-video answer is faculty-testable only if its visible body is byte-equivalent after the repository’s whitespace normalization to the ordered citation reconstruction, every citation remains verified and licensed, and the final joined body passes the configured minimum metadata-only relevance/coherence score. The test battery must include a passing join, a below-minimum join, an evaluator transport/exception path, a disabled-gate path, and a deliberately generated/reformatted body. Any failed or indeterminate case must return zero composite citations or a single independently gated fallback; it must never expose an LLM-generated teaching sentence.

### Railway status

**UNPROVEN for PR #127.** Read-only metadata was retrieved from project `resilient-embrace`, production service `askmukthiguru-8119b0e8`: deployment `17530dcb-e9f8-42e4-993f-ef3c838e9faf` is `SUCCESS`, branch `main`, commit `5a24453434dbe9d2c67a48925cfebb70d9bf66c5`, merged PR #125. The captured production logs are therefore pre-PR evidence and cannot certify the joined-answer implementation.

### Live-log triage and PR-scoped fixes (2026-11-29)

- **Rate limiting:** production logged async Redis timeouts followed by “degrading to allow.” The async limiter now enters the same bounded process-local sliding/backoff limiter used during startup, records the current request once, and reconnects through the existing cooldown path. Focused regression coverage passes; no Railway configuration or Redis state was changed.
- **Canonical memory:** production logged rejected audit inserts with actor `dreamer` and a separate string-row `.get` failure in `dream_all`. Dreamer audit events now use the schema-approved `system` actor, and both active-user and active-memory query boundaries reject malformed rows. Focused dreamer and actor-contract tests pass; no Supabase migration was applied remotely.
- **Memgraph/TeachingUnit:** first-person concept/TU expansion remains explicitly off by default. Memgraph sizing is bounded and returns a deterministic heuristic on unavailable/error/timeout; it does not inject text or write graph state. This is an intentional fallback, not evidence that TU retrieval improves answer quality.
- **General RAG faithfulness:** the observed low-faithfulness/no-citation run was fail-closed in the generation/formatting path; no additional source leak was identified. This remains a separate general-RAG quality/latency concern, not evidence for first-person readiness.

After the owner merges and deploys, capture the deployed commit again, run the faculty gate, inspect bounded `fp.rejected` reason counts and rate-limit health, and run the full acceptance battery before inviting faculty.
