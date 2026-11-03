# First-person local validation — 2026-11-02

## Bottom line

The shared first-person policy/harness changes pass the focused regression suite and the full default backend suite: **12,256 passed, 21 skipped, 3 deselected, 1 xfailed** in the final run. The cold local chat request did **not** produce a teaching answer: it reached the first-person route and abstained because the fail-closed OpenRouter budget guard rejected the answerability check. This validates the tested gates, not the requested “best answer” experience.

There is no saved pre-change response for this question, so this is not an A/B quality comparison. The only observed response is the post-change run.

## What was exercised

The local frontend/backend had been rebuilt with the no-data-loss Make target. Runtime inspection showed `FIRST_PERSON_ROUTE_ENABLED=true`, `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, `FIRST_PERSON_MODE=retrieval_only`, and the context harness/terminal/enrichment/graph-expansion flags off. Therefore the live sample exercised the user-facing first-person bridge and legacy retrieval policy; it did not exercise the context harness as a serving path. The harness policy itself was covered by unit tests.

One question was posted to local `POST /api/chat` with a newly signed anonymous-session token in `session_id`, `cache_bypass=true`, and `incognito=true`. No cached answer was reused, and incognito prevented conversational persistence/memory. The question was: **“What is love according to Krishnaji and Preethaji?”**

## Test results

The focused run used the repository Python 3.12 virtual environment and ran sequentially. It covered:

- shared evidence-policy decisions;
- first-person context harness and red-team cases;
- first-person serving/cache fingerprint cases;
- compound-query assembly, speaker-verification, and relevance-off regressions;
- standalone/showability, relevance, and unverified-clip gates.

Focused result: **209 passed, 1 deselected in 1.62 seconds**. The deselected case was `test_live_qdrant_fp_context_serving`; the unrelated early-abstention E6C case was not selected. A later full default run completed with **12,256 passed, 21 skipped, 3 deselected, 1 xfailed in 257.52 seconds**. The three deselections were the two repository-default `slow` cases and the live-Qdrant/provider integration. The first full attempt exposed a 256-file-descriptor limit and one test using `monkeypatch.undo()` to remove autouse fixture settings; the patch was scoped with `monkeypatch.context()`, and the rerun used a process-local 4096 descriptor limit plus task-local DSPy/SQLite paths. The previously failing cases were separately rerun: **743 passed**.

The full suite used a synthetic invalid OpenRouter credential, `A28_LIVE_PROBES=0`, and `UPDATE_QDRANT_BASELINE=0`; it made no paid inference call. The tracked Qdrant quality-baseline SHA-256 was identical before and after. The live-Qdrant/provider test and the pre/post answer comparison remain pending because the current configured key has a $50 cap rather than the approved dedicated $0.25 test cap.

Pytest’s test fixture confines its Redis flushes to dedicated test DB 15. No Qdrant points, aliases, or corpus data were modified.

## Live sample result

- HTTP: `200`
- Intent: `QUERY`
- Route: `first_person_abstain`
- Grounding: `abstained`
- Cache hit: `false`
- Citations: `0`
- Latency: `341 ms`

The response was:

> I don't have a verified verbatim teaching that directly answers this, and I'd rather say so than improvise one. Try rephrasing, or ask about a specific teaching or practice.

This is an abstention, not a partial answer and not a teaching from either guru.

## Why it abstained

The post-request backend log gives the specific cause:

1. The answerability check became indeterminate with `OpenRouter daily or monthly spend limit reached`.
2. The pipeline recorded `reason=answerability_withheld` and **discarded retrieved candidates**, then skipped reranking and the relevance scorer.
3. The bridge returned an abstention rather than serving unchecked or synthesized teacher speech.

This message originates from the application’s `OpenRouterBudgetGuard` reservation path, which is configured fail-closed. Runtime settings were: guard enabled, daily ceiling **$25**, monthly ceiling **$100**, and per-request reservation cap **$0.03**. A later read-only preflight found **$38.43** reserved in the UTC-day ledger (above the daily cap) and **$38.43** in the monthly ledger (below the monthly cap). The configured provider key was read-only verified at a **$50** limit with **$47.47** remaining; it is not the approved dedicated $0.25 test key and was not used for inference or modified. No budget counter was reset, raised, or bypassed.

Read-only Qdrant metadata showed the legacy retrieval collection `first_person_v8` was `green` with **1,801 points**. That proves the collection is present, not that it contains a directly answerable love passage. The pipeline’s own log says candidates were retrieved and then discarded when answerability could not be established.

## Docker log review

The backend startup log reported application startup complete and Uvicorn running. The captured startup logs contained no `ERROR`, `CRITICAL`, or traceback. Nonfatal warnings included inability to `chown /app/model_cache`, deprecated Hugging Face download arguments, and an OpenTelemetry tracer-provider override. After the sample, the first-person pipeline and bridge logs recorded the budget-related abstention above; there was no Qdrant connection failure in those lines.

## What this proves—and does not prove

The focused and full suites establish that the tested policy paths behave as expected under fixtures, including the harness and compound-path safety fixes. The live request demonstrates fail-closed behavior when answerability cannot be checked because of the application budget guard. It does **not** demonstrate a relevant multi-video answer, correct clip-set selection, grammatical editorial stitching, or improved answer quality against a pre-change baseline. The live diagnostic remains blocked until a dedicated provider key with a hard $0.25 cap and a separate local app/Redis budget store are configured.

The immediate blocker to observing a real clip answer is available, authorized OpenRouter budget headroom. Do not disable answerability or reset the spend ledger merely to force an answer. Once the budget issue is resolved through the project’s approved process, rerun the same cold question and inspect the returned clips and citations. The larger editor-like workflow—cross-video evidence-set selection, sufficiency checking, and a reviewable edit decision list—remains future work in the [implementation plan](../.claude/tasks/editorial_teaching_evidence_engine_plan.md). The broader current-state and research explanation is [here](editorial_teaching_existing_vs_target.md).
