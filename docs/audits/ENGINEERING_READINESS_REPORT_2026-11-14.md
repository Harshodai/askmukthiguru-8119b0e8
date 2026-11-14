# Engineering and readiness report, engagement of 2026-11-13/14

Scope: the two owner briefs of 2026-11-13 (audit, fix, verify, assess; then Phase 0 to 5 with gates).
Lead: Fable 5.2. Subagents: Sonnet 5.5 and Haiku 5.5 (list in section 8).
Everything here was run on one Mac against the local Docker stack. Nothing is production evidence.
Nothing was pushed, deployed, or written to Qdrant. No `.env` file was read or changed.

State of the repo when this was written: local `main` at `2f26bbbd`, eleven commits on top of
`3a4d479f`, not pushed. **A second session was editing the same checkout at the time** (14 modified
and 12 new files, uncommitted, including `first_person_pipeline.py`). This report describes the
committed state at `2f26bbbd` only; that session's work is not reviewed here.

## 1. Verdict

| Scope | Decision | Why |
|---|---|---|
| Production | **NO-GO** | Human gates are open (clinician, native speakers, rights sign-off, helpline calls, gold labels). The registered run fails three bars. Railway is untouched. |
| Staging or faculty demo on the registered bars | **NO-GO** | Graded-7 fails "showable by both graders", the 10 s p95 bar and the hub rule. A demo below the bar, labelled as a demo, is owner decision O-2. |
| The code on `main` at `2f26bbbd` | Sound to keep | Full backend suite 14,243 passed; frontend 1,154 passed; two independent reviews PASS; the stack built from the commit runs it (hash match). |

The product is safer and more observable than at the start. Answer quality is **not** better: the
registered run shows the same picture as graded-6, now with two real graders.

## 2. Graded-7 (registered run) against the graded-6 baseline

Run `20261114-graded-7`: commit `d2f8e615`, stack `docker-compose.yml` + `docker-compose.graded.yml`,
preflight 7 of 7, 30 pinned flags equal, caches proven empty. Graders `anthropic/claude-sonnet-5.5`
and `google/gemini-3.6-flash`, both on every served row. Collection `first_person_v10`, 4,224 points,
id hash `c96200d7…1835` before and after. Report tool: `backend/scripts/ops/graded_registered_report.py`.

| Bar (as registered) | Graded-6 | Graded-7 | Status in graded-7 |
|---|---|---|---|
| Served share of the 89 answerable rows (>= 0.30) | 43 (0.483) | 41 (0.461, Wilson 0.361 to 0.564) | met |
| Showable by both graders, lower bound >= 0.85 | not measured (one model in both slots) | 31 of 41 = 0.756 (Wilson 0.607 to 0.862) | **failed** |
| Grader 1 (Sonnet) alone | 34 of 43 = 0.791 | 31 of 41 = 0.756 | below 0.90 |
| Grader 2 (Gemini) alone | not run on every row | 37 of 41 = 0.902 (Wilson 0.775 to 0.961) | point estimate meets 0.90, lower bound does not |
| Grader agreement | 1 of 10 compared rows differ | 34 of 41 agree; differ on q007, q010, q019, q025, q030, q047, q074 | reported |
| p95 latency on served rows (<= 10 s) | 9,443 ms | 10,015 ms | **failed** by 15 ms |
| Harmful = 0 for both graders | not measured | 0 and 0 | met |
| Unanswerable set (86 rows): all groups pass, 0 clips | pass | pass, 0 clips | met |
| Core abstain (>= 0.95) | 69 of 69 | 69 of 69 | met |
| Crisis routing | 7 of 7 | 7 of 7 | met |
| Hub rule (no clip serves more than 3 questions) | max 4; 31 clips for 43 answers | max 4; 28 clips for 41 answers; 9 clips serve more than one | **failed** |
| Strict reader "answers the question" >= 0.85 | not measured | not measured (no such verdict in the harness) | not measured |

Reading:

- The run is valid on every registered rule except one field: the capture cannot write the collection
  fingerprint into the manifest (no Qdrant client), so it was read by hand before and after.
- The repo's older gate (`grades.json`, bar file) reads this same run as **PASS** (37 of 41). The
  registered bars read **FAIL**. The two bars disagree; which one is the bar is an owner decision (H-7).
- With about 41 served rows, the 85% lower bound needs 40 of 41. No run on the frozen 116 can show it
  unless nearly every served answer is showable. This was written in the registration before the run.
- Served count, showable share and latency moved within what an unseeded run can move (the same
  question was served in one live probe and abstained in the next). No claim of improvement or
  regression is made.
- Not changed between the two runs: selection logic. The comparative judge is built and off.

## 3. What was found and fixed

Full register with tests: `docs/analysis/OUTSTANDING_ISSUES.md` (rows A-01 to A-22, P2-a to P2-e,
T-E1 to T-E9). The ones that matter most:

| ID | Sev | Finding (evidence) | Outcome |
|---|---|---|---|
| A-08 | P1 | The YES/NO answerability gate was off in the live env and in graded-6 (manifest), while the invariants said it always ran. | Startup warns; graded compose pins the value; on/off is owner decision T-E1. |
| A-16 | P1 | Anonymous users had no follow-up context: client history is emptied, so "why does that happen?" was searched as bare text. | Fixed: the last prior user turn reaches only the follow-up resolver, only when it reads as calm. **Proven live** (section 5). |
| A-12 | P1 | The deploy preflight passed environments that crash at boot. | Fixed: mirrors the startup validators, rejects unparseable booleans. |
| A-09, A-10 | P2 | `inspect-source` returned full transcripts to anyone, with no rights, blocked-video or quarantine gate; a blocked video could be reached through `m.youtube.com`. | Fixed and tested; 24 rights-unverified sources are now refused, 1,237 of 1,261 stay viewable. |
| A-15 | P2 | The same endpoint never reached Qdrant live (missing facade methods). Found by the parallel review session. | Fixed. |
| A-01 | P2 | Follow-up text shared one cache entry across conversations. | Fixed: history-resolved turns bypass the exact cache. |
| A-13, A-14 | P2 | `message_citations`: any signed-in user could read all rows; inserts were always denied; the browser recorded unknown rights as licensed and unknown speaker as verified. | Migration written and proven in a rolled-back transaction, **applied nowhere**; client defaults fixed. |
| A-06 | P2 | The ambiguous-domain router timed out 27 of 27 times (470 to 690 ms against a 0.45 s budget). | Off by default; same routing, no wasted wait. |
| P2-d | P2 | Slow judge calls (about 6.45 s) with unknown cause; the timing line was never written for them. | **Measured** on 806 live calls: pool wait at most 20 ms, limiter wait at most 31 ms, connections reused. The 16 calls over 5 s waited on the provider (first byte 4.5 to 6.8 s, or a 4 to 7.7 s body read). Not our client. |
| A-18 | P2 | The harness could not evaluate the registered bars (no Wilson bound, no hub metric, two graders not enforced, unpinned flags). | Report tool, pins and manifest fields added; graded-6 re-read as the baseline. |
| P2-a | P1 | Same-clip defect: the judge sees one clip per call. | Comparative judge built behind `first_person_comparative_judge_enabled` (off). **Not measured.** |
| T-E2 | P1 | Every first-person turn abstained on a "spend limit". | Cause corrected: the app's own monthly cap (ledger 123.13 against 100), not the provider. With the graded overlay (cap 300) the stack serves. |

Found by review and fixed before commit: a blocked video reachable through other YouTube hosts; a
preflight that accepted a whitespace boolean; two new broad `except` blocks over the ratchet; a report
tool that counted a group with missing numbers as passing; the follow-up hint lost in the job queue.

## 4. Commits (local `main`, not pushed)

`8a3274cc` first-person serving fixes · `60293b1d` security · `265f933a` config and preflight ·
`57da22e2` frontend and migration · `34226440` issue list, harness audit, criteria, spend log ·
`6032fda6` comparative judge (off) and negative-control runner · `03191382` anonymous follow-up and
outage copy · `0d1a0f56` registered report, call timing, graded pins, baseline · `d2f8e615`
registration and docs (the graded commit) · `2f26bbbd` follow-up hint through the job queue.

## 5. Verification evidence

| Check | Result |
|---|---|
| Backend suite, baseline at `3a4d479f` | 14,103 passed, 22 skipped, 2 xfailed |
| Backend suite at `2f26bbbd` | **14,243 passed**, 22 skipped, 2 xfailed, exit 0 |
| Frontend (Node 22.22.3) | `tsc` 0, eslint 0 errors on touched files, vitest **1,154 passed**, build 0 |
| Safety scenarios (`evals/run_safety_scenarios.py`) after the follow-up change | 226 pass, 4 declared expected fails, 0 fail |
| Independent reviews (Sonnet, read-only) | PASS twice, no blocking finding |
| Test challenges (Haiku) | found 2 product bugs in round 1 (fixed); 16 extra edge cases pass in round 2 |
| Clean stack runs the commit | 11 of 11 files hash-match host and image; `verify-stack-fresh` FRESH; no code bind mounts |
| Resolved values in the container | sparse off, judge on (`claude-haiku-5.5`), min score 3, timeout 12 s, answerability off, comparative off, router off, `first_person_v10` |
| RLS migration | owner reads own rows only, own insert allowed, forged insert denied; nothing persisted |

Five chat paths on the rebuilt stack (anonymous session, cache bypass; ids and routes only):

| Path | Request | Observed |
|---|---|---|
| Normal | anger towards a brother | `first_person_abstain`, 0 citations, about 5 to 7 s. Honest abstain; no clip passed the gates. |
| Ambiguous | "Is it wrong to want more?" | `first_person_bridge`, 1 clip (Sri Preethaji, voice-verified), labelled related. |
| Crisis | a stated plan to end one's life | HTTP 200 in about 10 ms, `safety_redirect`, `crisis=true`, pre-empted at intake, never reached the pipeline. |
| Out of corpus | capital of France | `off_topic_domain_boundary`, 0 citations, about 1 s. |
| Follow-up | turn 1 about comparing oneself; turn 2 "why does that happen?" | First probe (before `2f26bbbd`): turn 2 not resolved, which exposed the job-queue bug. After the fix: log `Resolved follow-up query (len=63 …)`, turn 2 served the matching clip (Sri Krishnaji, voice-verified). |

Not verified: mobile, hosted CSP, load, a soak test, Railway, any human reading of answers.

## 6. Actual architecture (as run)

Browser (React) → `POST /api/chat` → anonymous quota → job queue → worker → stage chain
(kill switch, cache check, request state, input guardrail, distress, circuit breaker, casual and
off-topic short-circuits) → LangGraph, where the `first_person` module claims the turn →
`FirstPersonPipeline`: crisis pre-check and topic rail → Qdrant `first_person_v10` (dense only in the
graded config; parents and child spans) → integrity, standalone and safety gates → judge model
(`claude-haiku-5.5` through OpenRouter, one clip per call, eight calls a question on average) →
verbatim clip with citation, or a static abstain. No model writes answer text. State: Qdrant,
Redis (cache, limiter, spend ledger, job queue), Memgraph, local Supabase. Every served answer costs
model calls, so the app's own budget cap is a hard dependency of serving.

## 7. Spend (cap 90)

App ledger, month: 123.1291 before the first graded stack start; 126.8994 at 2026-11-14T07:59Z.
Warm-up 0.31, capture 2.99, first probe 0.09, second stack start and probe 0.38. Grading runs
host-side straight to the provider and is not on the ledger: estimated under 1 from list prices
(41 rows, two graders), not measured. Earlier audit probes: at most 0.12. **About 4.5 of 90 used.**
The ledger overstates real cost: 54 cancelled calls in half a capture each kept a 0.03 reservation.

## 8. Agents used

Twenty-one subagent runs: twelve Sonnet 5.5, nine Haiku 5.5. Each had its own scope and files.
Sonnet: first-person defect hunt; security audit; conversation-continuity audit; serving fixes;
security fixes; two independent reviews; frontend announcement; comparative judge; anonymous
follow-up and outage copy; provider timing; registered report. Haiku: config and Docker drift;
router timeout root cause; evaluation coverage; preflight parity; draft conversation cases; two test
challenges; harness audit; runtime log sweep. Every result was checked by the lead before use; two
were corrected (a rights-gate side effect was measured; reviewers disagreed on crisis screening and
the code settled it).

## 9. Remaining, in order

Owner decisions: T-E1 answerability gate on or off; T-E2 monthly model cap; H-7 which pass bar is
the bar; O-2 demo below the bar; P2-b what counts as a truncated clip; P2-e reservations kept by
cancelled calls; O-1 sparse default; T-E4 apply the three local migrations; merge and push.

Agent work, highest value first:
1. **Measure the comparative judge** on the negative-control set inside the container
   (`scripts/ops/run_negative_controls.py --comparative`; 232 calls). Host-side it returns
   indeterminate because the host cannot reach the stack's Redis. Only if it abstains on at least
   0.95 of pairs: a new registered run with the flag on. Watch latency: p95 is already at the bar.
2. Latency: the slow tail is provider-side. Options to test, each through a registered run: provider
   latency preferences, fewer judged contexts per question, a hedged second request.
3. A strict "answers the question" verdict in the harness (H-6), so the bar the owner cares about
   can be measured.
4. A runner for `evals/first_person/conversation_cases_draft.jsonl` after the owner reviews the rows.
5. Write the citation ledger from the backend, not the browser.

Human gates, unchanged and not closable by an agent: native-speaker and clinician review, helpline
phone verification, rights sign-off, 299 gold labels, a human read of 50 served answers.
