# 00 — Executive diagnosis and six-pillar scorecard

Owner: lead. Audit of `origin/main@46b808fb` (2026-11-04), read-only. 153 findings: 2 P0, 47 P1, 81 P2, 22 P3, plus one recorded strength (`findings-index.md`). The independent review (`26`) verified 16 critical claims: 10 confirmed, 5 partly confirmed, 1 refuted. All findings are corrected accordingly.

## 1. Verdict

**Not ready for users.** The product is not ready for internal testing either, because nothing is deployed and `main` is red. The way out is short at the start (owner actions and small PRs) and long at the end (human labelling, clinician and native review, written rights approvals).

## 2. The diagnosis in plain words

Ask Mukti Guru has a serious engineering core. It has a safety-first request pipeline, a fail-closed integrity gate that serves only exact recorded words, a strict data contract for the newest corpus, and a culture of guards and tests (about 12,500 backend tests in CI). But it does not yet do what it is for:

1. **The most common spiritual-emotional questions never reach a teaching.** "What is the cause of my anxiety?" matches a distress keyword, and the seeker receives a meditation template and helplines (`10` ANS-001, confirmed). Three topic questions in a row can trigger crisis pre-emption (SAFE-002). The safety instinct is right; the classifier confuses talking *about* anxiety with *being* in crisis.
2. **A good answer is at most one clip.** The architecture forbids any explanation, synthesis or reflection (invariants 15/21). About 3 in 4 on-topic questions abstain, and about 11% end useful [DOC-CLAIM]. Multi-video synthesis is impossible on the live path.
3. **The data ceiling is low.** The newest corpus fails its own quality scorecard (13/26 checks; 39.9% strict-clean) [DOC-CLAIM]. Identity, versioning, write control and takedown are not governed across stores.
4. **Status claims are not computed.** On 2026-11-04 the release gate was recorded as "24/24 PASS". On a clean checkout it reports `OWNER_ACTION_REQUIRED`, and CI on `main` fails on exactly that test. The "human gold labels" describe themselves as `independent_review:false`.
5. **The public repository publishes the teaching corpus** (2,737 verbatim spans) and teacher voice audio, with no filed written permission. This is the only P0.
6. **Operations were never exercised.** No deploy since August, no staging, spend cap off by default, an unauthenticated LLM route, failing backups, a deletion flow wrapped in a churn funnel, and scheduled deletions that never run.

These come from nine root causes (`16` §2). The biggest are: claims decoupled from computation (RC-2); three products living in one code path (RC-3); ungoverned data identity (RC-4); topic-versus-state confusion in safety (RC-5); and a "one clip or abstain" answer model (RC-6).

## 3. The ultimate questions, answered

| Question | Today | Evidence | Fix |
|---|---|---|---|
| Does it understand what the seeker is seeking? | Partly. Most questions reach the teaching lane, but emotional topics are read as distress states | ANS-001, ANS-002 | T4-04 (clinician) |
| Does it understand the context behind the question? | No. Follow-up is string concatenation; consented memory is read and ignored | ANS-007, MEM-002 | T5-05, T6-02 |
| Does it retrieve the relevant teaching? | Sometimes. Top-1 0.43 [DOC-CLAIM]; dedup before gates; dense-only on v10 | RET-01, RET-02 | T4-01, T4-02 |
| Does it distinguish a teaching from an AI interpretation? | On the chat path, yes: only verbatim spans. Elsewhere, no: unsourced attributions, unlabelled quote translation, and a kill switch that falls back to generation | GURU-012, ADV-05, ADV-03 | T1-03, T5-06, T1-05 |
| Does it communicate the teaching properly? | No. One clip, no explanation, no depth control | ANS-004, ANS-006 | ADR-001, T5-01…T5-04 |
| Does it respond with emotional sensitivity? | Over-sensitively: care templates replace teachings, and helplines are shown that were never call-verified | SAFE-002, SAFE-004 | T4-04, T4-07 |
| Does it remember relevant context, with consent? | It reads memory it does not use, and acts on emotional history without the consent gate | MEM-002, MEM-003 | T1-10, T6-02 |
| Is it worth returning to? | Not yet. A signed-in seeker's history is wiped on sign-out and lives in one browser; the landing page promises a conversational companion the product does not provide; there is no user research; deletion is wrapped in a funnel | UX-006, PRD-010, PRD-008, UX-001 | T6-09, T6-10, T2-07, T1-12 |
| Is it safe when things fail? | Partly. Server-side crisis routing is safety-first, but most client error states show no helpline, and an interrupted stream can leave unlabelled teacher text | UX-007, UX-005 | T1-17, T1-18 |

## 4. Six-pillar scorecard

| Pillar | Status | Why | Top findings | First tasks |
|---|---|---|---|---|
| P1 Stability, architecture, cost | Red | Never deployed; sync pipeline wedges threads; spend cap off; 3 sequential LLM gates; ≥8 caches, ~14 LLM modules | SYS-003, SYS-004, SYS-006, SYS-007, SEC-001 | T1-07, T1-08, T3-01, T9-01, T4-06, T7-02 |
| P2 Spiritual answer intelligence | Red | Template instead of teaching for emotional topics; one clip; no synthesis; no depth control | ANS-001, ANS-004, RET-03, ANS-006 | T4-04, T2-01, T5-01…T5-04 |
| P3 Code and data quality, wiring | Amber/Red | Strong contracts in places; ungoverned data identity; 2,145-line sync function; docs drift from code; `main` red | DATA-01…07, CQ-001, X-01, X-07 | T0-04, T3-*, T7-01 |
| P4 Spiritual integrity, guru confidence, release | Red | Public corpus; unfiled rights; non-reproducible release record; unsourced attributions; kill switch falls back to generation | X-06, IP-001, X-01, GURU-002, GURU-012, ADV-03 | T0-01, T0-02, T0-04, T1-03, T1-05, T1-11 |
| P5 Mentor and returning user | Red | Memory unused or used without consent; churn funnel at deletion; streaks tied to progress; no user research | MEM-002, MEM-003, UX-001, UX-002, PRD-008 | T1-10, T1-12, T6-02, T2-07 |
| P6 FRs and NFRs | Amber | 32 FRs specified with status (`03`); NFRs specified with baselines and provisional targets (`04`); most baselines unmeasured | SYS-011, EVAL-002, EVAL-003 | T2-01, T2-03, T9-02 |

## 5. What to do this week

**Owner (minutes to hours each):**
1. Make the repository private (D-01). This stops the only P0 today.
2. Turn on branch protection for `main` with required checks (T0-03).
3. Correct the release-authorisation scopes to "owner-only local review" (D-11, T0-04).
4. Decide ADR-002 (no general-assistant lane for review and beta) and ADR-005 (retire the graph stack) (D-04, D-05).
5. Engage a clinician for the topic-versus-state discriminator and test sets (D-06).
6. Decide where private evidence and the source bundle live (D-08).

**Implementation agent (small PRs, in parallel; prompts in `25`):**
T0-06 revalidation → T0-04 honest gate test → T1-05 fail-closed teaching route → T1-02 latent-P0 removal → T1-01 voice governance → T1-07 spend caps → T1-08 endpoint auth → T1-12 direct deletion flow → T1-10 consent gate → T3-01 rights register in the image.

## 6. Key numbers (with labels)

| Number | Value | Label |
|---|---|---|
| Tracked files / Python lines | 5,499 / ~531K | [V-STATIC] |
| Backend tests in CI on `main@46b808fb` | 12,478 passed, 1 failed (release gate), 52 skipped | [V-GIT] |
| LLM calls per in-domain turn (defaults) | 3 (rerank, answerability, relevance) | [V-STATIC] |
| Uncached first-person latency, local | p50 6.8–7.6 s, p95 12.3–13.9 s | [DOC-CLAIM] |
| On-topic questions served | ~24–31% | [DOC-CLAIM] |
| Benign on-topic questions routed to distress | 17/150 | [DOC-CLAIM] |
| v10 scorecard | 13/26 checks; strict clean 39.9% | [DOC-CLAIM] |
| Helplines call-verified | 1/15 | [V-STATIC] |
| Independent human gold labels | 0 confirmed independent (303 rows self-described `independent_review:false`; 0/300 tracked packets filled) | [V-STATIC] |
| Verbatim spans in the public repository | 2,737 | [V-STATIC] |

## 7. Where to go next

- Root causes and failure modes: `16`. Target architecture and decisions: `17`. Roadmap: `20`. Specs: `21`. Testing: `22a`.
- Readiness scorecard and guru-review recommendation: `23` (final sections).
- Implementation: `24` and `IMPLEMENTATION-AGENT-PROMPT.md`.
- Owner decisions: `unresolved-questions.md`.
