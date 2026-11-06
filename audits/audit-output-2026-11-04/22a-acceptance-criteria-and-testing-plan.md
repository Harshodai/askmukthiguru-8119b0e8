# 22a — Acceptance criteria and testing plan

> **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (testing methodology by component (§8) and data-integrity invariants as executable checks (§6)). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: lead. Purpose: tell the implementation agent exactly how to prove each change works, and tell a reviewer how to tell that it does not. Task acceptance criteria: `20` (short) and `21` (P0/P1 detail). Metrics: `04`. Datasets: `18`.

## 1. Principles

1. **Behaviour over source text.** A test asserts what the system does, never that a string appears in a source file. The repository has 112 source-text tests (CQ-008). Do not add more. Replace them in the areas you touch.
2. **Real stores in CI.** Retrieval, cache and isolation behaviour runs against fixture Qdrant and Redis containers (T2-05), not against mocks only.
3. **Measure before and after.** Any retrieval, routing, gate or prompt change posts a before/after delta from the frozen retrieval bank (T2-02) and the PR suite (T2-01).
4. **No self-grading.** The same model must not produce and judge an answer (ADV-04). AI-written labels are never gold (invariant 3).
5. **Gates are computed.** A gate status is whatever the gate computes on a clean checkout. Never edit a test, threshold or evidence file to change a status (X-01).
6. **Safety sets are human-owned.** Crisis items become blocking only after clinician review. Multilingual items become blocking only after native review.

## 2. Test layers

| Layer | What it proves | Where | Runs | Blocking? |
|---|---|---|---|---|
| Unit | Pure functions: routing pre-filter, distress discriminator, hash checks, gate rules, settings validators | `backend/tests/`, `src/test/` | Every PR | Yes |
| Contract | Response schema (`layers[]`, `citations[]`, `verification`), writer contract for spans (T3-03), API error shapes | `backend/tests/contract/` (new) | Every PR | Yes |
| Integration (fixture stores) | Hybrid retrieval, gate-then-dedup, cache isolation, takedown, RLS, erasure queue | CI job with Qdrant + Redis + Postgres containers (T2-05) | Every PR touching those areas | Yes |
| Retrieval evaluation | Recall@1/5/10, Precision@5, MRR, nDCG@10 on the frozen bank | `evals/retrieval_bank/` (T2-02) | Every retrieval PR; nightly | Yes on regression beyond CI |
| PR answer suite (offline) | Routing, distress benign/crisis/multi-turn, quote integrity, voice lint, abstain set | `evals/pr_suite/` (T2-01) | Every PR | Yes |
| Held-out human evaluation | Usefulness, faithfulness, attribution, emotional appropriateness | `evals/golden_v2/` (T2-04) | Per release candidate | Release gate |
| Security | Auth on every LLM-spending route, RLS, injection fixtures, secrets scan, dependency CVEs | `backend/tests/security/`, CodeQL, gitleaks | Every PR / nightly | Yes |
| Data quality | Scorecard blockers, hash and ID recomputation, teacher-ID vocabulary, verified-without-method | `scripts/ops/data_quality_audit.py` (T3-05) | Before promotion; daily | Promotion gate |
| Performance | p50/p95/p99 per lane; LLM calls per turn; tokens and cost per turn | `gate1_load_test.py` on staging (T9-02) | Per release candidate | Release gate |
| End-to-end | Seeker journeys on Chromium, Firefox, WebKit, mobile viewports | `tests/e2e/` | Every PR (smoke); nightly (matrix) | Smoke yes |
| Chaos | Redis down, Qdrant down, backend down during deletion, LLM timeouts | staging scripts | Monthly; before release | Release gate |
| Migration | Forward migration on a copy; no automatic down migration (existing check) | `supabase/`, CI | Every migration PR | Yes |

## 3. Retrieval and answer metrics (definitions)

| Metric | Definition | Source of truth |
|---|---|---|
| Recall@k | Share of items where ≥1 human-labelled relevant span is in the top k | Frozen bank labels (human) |
| Precision@k | Relevant spans in top k ÷ k | Same |
| MRR | Mean of 1/rank of the first relevant span | Same |
| nDCG@10 | Graded relevance (0–3) discounted by rank | Same |
| Served share | Served answers ÷ answerable items | Held-out set |
| Usefulness | Human rating ≥4 on the 5-point rubric (`18` §6.3) | Held-out set |
| Faithfulness (L3) | Explanation sentences entailed by cited spans ÷ all explanation sentences | Verifier + human audit sample |
| Attribution accuracy | Spans whose displayed speaker matches the verified speaker | Data audit + human sample |
| Quote integrity | Verbatim layers that are exact substrings of stored span text | Deterministic |
| Voice violations | Assistant sentences in a teacher's first person, or teacher-voice labels on generated text | Voice lint + human sample |
| Emotional appropriateness | Rubric dimension; clinician-defined anchors | Held-out set |
| Continuity | Follow-up items resolved to the correct prior spans | Multi-turn stratum |
| Latency | p50/p95/p99 per lane; time to first visible content | Outcome events |
| Cost | Tokens and USD per turn; per useful answer | Outcome events (T2-03) |

## 4. Per-change verification checklist (the agent runs this for every PR)

1. Re-locate every symbol you change (`rg -n`). Note any drift from `21`.
2. Write or update behaviour tests first. Watch them fail on the old code.
3. Make the change behind a flag if it changes behaviour.
4. Run the affected unit and contract tests: `cd backend && .venv/bin/pytest tests/<files> -q`.
5. Run the fixture-store integration job locally or in CI if retrieval, cache, RLS or erasure is touched.
6. Run the PR answer suite and the retrieval bank if routing, retrieval, gates, prompts or safety code is touched. Paste both deltas into the PR.
7. Run the frontend checks if `src/` is touched: `npm run lint`, `npm test`, and the e2e smoke spec.
8. Run the guards: `python3 scripts/guards/lesson_guards.py` (publication, voice, literal names when added).
9. Confirm no secret, teaching text, transcript or teacher audio was added (`git diff --stat`, publication guard).
10. Write the PR body: task ID; findings closed; files; tests with real output; acceptance checklist; rollback note.

## 5. Acceptance criteria index

| Scope | Where the criteria live |
|---|---|
| P0 and P1 tasks | `21` (each spec's "Acceptance") |
| P2 and P3 tasks | The finding record's "Acceptance criteria" field in the owning document (`findings-index.md` → Doc) |
| Phases | `20` §7 "Completion evidence" |
| NFRs | `04` (each table's Target column) |
| Release scopes | `23` "Release-readiness scorecard" (exit conditions) |

Every criterion must be measurable. If a criterion cannot be measured yet (for example, it needs the held-out set), the PR states "measurement pending T2-04" and the task stays open.

## 6. Regression protection by root cause

| Root cause | Regression it must catch | Test |
|---|---|---|
| RC-1 single source of truth | A second definition of scope, teacher, cache or LLM client appears | Guard: one scope file; literal-name ratchet; import-linter contracts |
| RC-2 computed claims | A gate passes on missing or non-independent evidence | Gate fixtures (T1-11); clean-checkout gate job |
| RC-3 one product | Generated text reaches a teaching answer | Fault-injection and kill-switch tests (T1-05); voice lint |
| RC-4 data identity | Stale or duplicate points after a rebuild; hash mismatch served | Rebuild fixture; daily audit |
| RC-5 topic vs state | A topic question routes to distress; a crisis is missed | Benign, crisis and multi-turn sets |
| RC-6 answer model | A layered answer contains an unsupported sentence or merges teachers | Entailment check; cross-teacher stratum |
| RC-7 rights | Teaching text or audio enters the public tree; a span without `permission_ref` is served | Publication guard; serving filter test |
| RC-8 process | Merge without required checks | Branch protection (owner) |
| RC-9 operations | Spend cap off; register missing; deletion fails with the backend down | Settings validator; startup check; erasure drill |

## 7. Known weaknesses of this plan

- Until T2-04 exists, quality claims rest on small or AI-written sets. Label such results "provisional".
- LLM-dependent items in the PR suite are recorded as "requires live" and cannot block. Live evaluation runs only on staging.
- The e2e matrix is red today on Firefox, WebKit and Mobile Safari (`01` §10). Fix it before it can protect anything.
- Nothing here measures user wellbeing. The user study (T2-07) and the outcome metrics (T2-03) are the only proxies.
