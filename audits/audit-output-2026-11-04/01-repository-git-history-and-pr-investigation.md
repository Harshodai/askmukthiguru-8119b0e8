# 01 — Repository, Git history and PR investigation

Owner: lead. Pillars: P1, P3, P4. Conventions: `CONVENTIONS.md`.

## 1. Summary

1. The audit target is `origin/main` @ `46b808fb`, not the session checkout. [V-GIT]
2. `main` is red at its head. One backend test fails, and it is the release-gate test. [V-GIT]
3. The "gate 24/24 PASS / READY_FOR_PUBLIC_RELEASE_REVIEW" result recorded on 2026-11-04 does not reproduce on a clean CI checkout. CI reports `OWNER_ACTION_REQUIRED`. [V-GIT]
4. `main` has no branch protection. Large changes reach `main` before CI finishes, or without a PR. [V-GIT]
5. The repository is public. That fact changes the risk of every tracked teaching text, data backup and environment file (see `14c`, `14`). [V-GIT]

## 2. Repository identity

| Fact | Value | Label |
|---|---|---|
| Remote | `https://github.com/Harshodai/askmukthiguru-8119b0e8` | [V-GIT] |
| Visibility | public (`private=false`, `visibility=public`) via the GitHub REST API, 2026-11-04 | [V-GIT] |
| Created | 2026-02-05 (first commit is a 2025-01-01 Lovable template) | [V-GIT] |
| Default branch | `main` | [V-GIT] |
| Remote branches | 3: `main` (`46b808fb`), `feature/audit-strengthen-rag-qdrant` (`9e17370d`), `lovable-sync` (`bb043ae8`) | [V-GIT] |
| Branch protection | `protected: false` on all 3 branches | [V-GIT] |
| Tracked files on `main` | 5,499 | [V-GIT] |
| Size by type (tracked, `memory/` and lockfiles excluded) | Python 1,847 files / 531,156 lines; TSX 358 / 67,060; TS 245 / 33,553; SQL 147 / 9,537; Markdown 628 / 128,455; JSON 242 / 788,688 | [V-STATIC] |

## 3. Session checkout versus `main`

| Fact | Value | Label |
|---|---|---|
| Session branch | `feature/audit-strengthen-rag-qdrant` @ `c905ab3` | [V-GIT] |
| Clone type | shallow (`git rev-parse --is-shallow-repository` = true; 47 commits visible before fetch) | [V-GIT] |
| Relation to `main` | 0 ahead, 5 behind. `merge-base(HEAD, main) = c905ab3` | [V-GIT] |
| Delta `c905ab3..main` | 82 files, +3,751 / −486. Includes `9e17370d` "first-person v10 harness, graph expansion, rights isolation & complete test suite" and `26209a3b` "record owner decisions — gate 24/24" | [V-GIT] |
| Remote copy of the session branch | `9e17370d` (ahead of the local checkout) | [V-GIT] |
| Working tree at start | clean (`git status --short` empty) | [V-GIT] |

Consequence: the designated branch is already merged into `main` (PR #86 and the direct merge `46b808fb`). Under the session's Git rules, any later implementation work restarts the branch from the latest `main`. It must not stack on merged history.

## 4. History profile (`origin/main`, 3,524 commits)

### 4.1 Commits per month

| Month | Commits |
|---|---|
| 2025-01 | 1 (template) |
| 2026-02 | 31 |
| 2026-03 | 1 |
| 2026-04 | 88 |
| 2026-05 | 495 |
| 2026-06 | 480 |
| 2026-07 | 836 |
| 2026-08 | 518 |
| 2026-09 | 731 |
| 2026-10 | 291 |
| 2026-11 (to 04) | 52 |

### 4.2 Authors and AI involvement [V-GIT]

| Author (git name) | Commits |
|---|---|
| Harshodai | 2,156 |
| gpt-engineer-app[bot] (Lovable) | 1,312 |
| opencode / OpenCode | 20 |
| Harshodai Kolluru | 18 |
| Claude | 11 |
| Others (Railway Agent, Jules, emergent-agent, railway-app) | 7 |

- About 37% of commits come from the Lovable bot. The frontend has two writers: Lovable and local agent sessions. [V-GIT] [INF]
- `Co-Authored-By: Claude ...` trailers appear on at least 450 commits (Sonnet 5/5.5 about 326, Opus 5/5.5 about 60, Fable 5 15, others). Most backend work is agent-authored. [V-GIT]

### 4.3 Commit types [V-GIT]

| Type | Count |
|---|---|
| fix | 759 |
| feat | 467 |
| docs | 217 |
| chore | 81 |
| merge | 65 |
| test | 63 |
| refactor | 41 |
| perf | 38 |
| other / unprefixed (mostly Lovable "Changes") | 1,703 |

- The fix-to-feat ratio is about 1.6. [V-GIT]
- 93 commit subjects mention `lessons`. Agents use documentation as working memory. [V-GIT] [INF]
- Only 4 reverts exist. Defects are fixed forward, not rolled back. [V-GIT]

### 4.4 Churn hotspots since 2026-07-01 [V-GIT]

| File | Changes |
|---|---|
| `lessons.md` | 297 |
| `src/components/chat/ChatInterface.tsx` | 167 |
| `backend/app/config.py` | 165 |
| `backend/rag/nodes/generation.py` | 123 |
| `src/components/chat/ChatMessage.tsx` | 112 |
| `handoff.md` | 87 |
| `backend/rag/nodes/retrieval.py` | 80 |
| `src/pages/ProfilePage.tsx` | 79 |
| `backend/app/api/chat.py` | 75 |
| `backend/app/main.py` | 72 |
| `backend/ingest/pipeline.py` | 70 |
| `CLAUDE.md` | 67 |
| `AGENTS.md` | 64 |
| `backend/services/first_person_pipeline.py` | 50 |

Reading: the configuration file, the chat UI, the generation node and the agent instruction files change most often. Core contracts were not stable during the period. [INF]

## 5. Product-definition history (from repository records)

| Date | Change | Evidence |
|---|---|---|
| Jul–Sep 2026 | A 20-node LLM RAG pipeline (CRAG, CoVe, HyDE, GraphRAG, LightRAG, OKF, memory) is built and tuned. | [DOC-CLAIM] `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` §1 |
| 2026-09-24 | Priority changes to verbatim first-person clips. | [DOC-CLAIM] same §1; root `CLAUDE.md` "#1 priority" |
| 2026-09-26 | ADR-FP-1..3 accepted ("Closest teaching" v1; separate ship gates; chat feature freeze). | [DOC-CLAIM] `docs/architecture/first-person-path-to-prod.md` §4 |
| 2026-10-11 | Chat becomes first-person-only: a teacher clip or a static abstain. | [DOC-CLAIM] root `CLAUDE.md` invariant 21 |
| 2026-10-23 | PR #76 adds a neutral general-assistant persona for non-doctrinal questions. | [V-GIT] PR #76 body |
| 2026-10-30 | v10-only serving decision. | [DOC-CLAIM] root `CLAUDE.md` invariant 25 |
| 2026-11-03 | PR #86 merges "Ralph Hardening + Master Plan" (1,034 files). | [V-GIT] |
| 2026-11-04 | Owner decisions recorded as "gate 24/24 PASS"; `main` turns red the same day. | [V-GIT] |

The product changed direction three times in about ten weeks. Large parts of the July–September generation stack now sit off the serving path (see `05`, `09`). [INF]

## 6. PR #76 (the historical PR named in the mission)

| Field | Value [V-GIT] |
|---|---|
| Title | Improve general chat routing, latency, memory consent, and safety |
| Branch | `fix/chat-latency-memory-robustness` → `main` |
| State | merged 2026-10-23T14:50:38Z by the owner |
| Size | 140 files, +10,016 / −3,118, **488 commits**, 11 comments |
| CI at merge | 23 checks green; UI device matrix (firefox, webkit) cancelled at 14:54Z, after the merge |

What PR #76 states it changed (from its body; behaviour is verified by S1/S3 in `05` and `09`, not here):

1. Teaching-domain questions keep the first-person route. General and non-doctrinal questions go to a neutral assistant persona, which need not cite teacher clips.
2. Greetings bypass cache and memory I/O. General graph turns skip HyDE, rerank and grading.
3. General-mode retrieval avoids the teaching corpus. Temporal questions can use bounded live web search from a domain allowlist. Answers with no approved source are labelled `unverified`.
4. Authenticated memory uses the server-side consent receipt and fails closed.
5. Unverified client-supplied history is dropped. Shared caches are bypassed after recent distress.
6. The optional LLM crisis escalation flag stays off pending clinical sign-off.
7. CI fixes (lint, Python 3.12 lock, load-test concurrency).

PR #76's own "Not claimed as complete" list: no live production credentials used; CI, load-test evidence and post-deploy p95/p99 still required; backup destination gate unresolved; crisis policy needs clinician review. Those items remain open at `main@46b808fb` per the task list. [DOC-CLAIM]

Tension recorded for the lead synthesis: PR #76 introduces a general-assistant answer mode. Root `CLAUDE.md` invariant 21 describes chat as first-person-only (clip or static abstain). Both are on `main`. Whether general mode is reachable under the documented local `.env` is traced in `05` and `09`.

## 7. PRs after #76

| PR | Title (short) | Base | Merged | Label |
|---|---|---|---|---|
| #77 | Stability: green CI plus three crash fixes | main | 2026-10-23 | [V-GIT] |
| #78 | Honest fallback for empty general answers | main | 2026-10-23 | [V-GIT] |
| #79 | Docs: v10 collection config bug, compose drift | main | 2026-10-23 | [V-GIT] |
| #80 | FP harness: dedupe overlapping spans | main | 2026-10-23 | [V-GIT] |
| #81 | Score v10 clips with no voice check (read-only) | main | 2026-10-23 | [V-GIT] |
| #82 | Plan: v10 path to public GO | main | 2026-10-23 | [V-GIT] |
| #83 | Relevance scorer budget, gate input, follow-ups | main | 2026-10-25 | [V-GIT] |
| #84 | First-person corpus remediation D1–D25 | main | 2026-10-26 | [V-GIT] |
| #86 | Ralph Hardening + Master Plan | main | 2026-11-03 | [V-GIT] |
| #87, #88, #91 | CI green, finish prompt, WhatsApp webhook | main | closed, not merged | [V-GIT] |
| #89 | Serve-time garbage gate gaps | main | 2026-10-28 | [V-GIT] |
| #90 | Video approval page | feature branch | 2026-10-30 | [V-GIT] |
| #92 | Allow v10-only serving config | feature branch | 2026-10-31 | [V-GIT] |

## 8. PR #86 and the last two commits on `main`

### 8.1 PR #86 [V-GIT]

| Field | Value |
|---|---|
| Size | 1,034 files, +87,409 / −92,640, 165 commits, 2 comments |
| Body claim | "All 564 tests across the affected suites pass" |
| Merged | 2026-11-03T18:59:08Z |
| Checks still running at merge | Backend Lint & Test (finished 19:09:54Z), Backend regression gates (19:07:35Z), Golden-25 (19:01:01Z) |
| Checks failed after merge | UI device matrix firefox (19:06:57Z), Mobile Safari (19:07:19Z), webkit (19:18:08Z) |
| Checks cancelled | build + unit + e2e (19:37:45Z), chromium, Mobile Chrome |
| Post-merge on `main` (`99d09c14`) | Lint & Test success; Production Readiness success; Pre-launch gate **failure**; Build & Deploy **failure** |

The PR body cites 564 tests. The full backend suite is about 12,500 tests. The PR's evidence is a subset. [V-GIT]

### 8.2 Direct pushes without a PR [V-GIT]

| Commit | Content | PR |
|---|---|---|
| `26209a3b` | Records five owner decisions; "Gate: 24/24 PASS" | none |
| `9e17370d` | 72 files, +3,698 / −353 (v10 harness, graph expansion, rights isolation, tests) | none |
| `46b808fb` | Merge of the feature branch into `main` | none |

### 8.3 CI on `main@46b808fb` (2026-11-04) [V-GIT]

| Workflow | Result |
|---|---|
| Lint & Test | **failure** (Backend Lint & Test → pytest step) |
| Production Readiness | **failure** (Backend regression gates → Pytest: 1 failed, 12,478 passed, 52 skipped) |
| Pre-launch gate | **failure** |
| Build & Deploy | skipped |
| Main Hard Gates, Security Audit, CodeQL | success |

The failing test, from the job log (job 126691871430):

```
FAILED tests/test_first_person_public_release_gate.py::test_the_repository_gate_reports_owner_action_required
  assert report["status"] == gate.STATUS_READY
  AssertionError: 'OWNER_ACTION_REQUIRED' == 'READY_FOR_PUBLIC_RELEASE_REVIEW'
```

The test sets `config["env_file"] = "backend/.env.example"` (the tracked default) and then asserts READY. The test name still says "reports owner action required". The assertion was changed to READY, and the gate does not agree on a clean checkout. [V-GIT] [V-STATIC]

### 8.4 Scheduled workflows on `main` (last run on 2026-11-04) [V-GIT]

| Workflow | Result |
|---|---|
| Supabase Database Backup (Free Path) | failure |
| Hallucination Anomaly Detection | failure |
| Nightly Load Test (OPS-7) | failure |
| Golden-25 First-Person Attribution Gate, Eval Gate, Nightly Staging RLS, Nightly Eval, Nightly Corpus Audit, Nightly Cache Warm | success |

The backup failure means no automated database backup ran (cause per `[DOC-CLAIM]` task list §2 N2: the workflow refuses to upload dumps from a public repository). See `15`.

## 9. Findings

### X-01 — Release-gate claim is not reproducible on a clean checkout; `main` is red
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Release integrity |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Production Readiness run 41863600903, job 126691871430; `backend/tests/test_first_person_public_release_gate.py:924`; commit `26209a3b` message "Gate: 24/24 PASS" |
| Actual behaviour | The tracked repository state yields `OWNER_ACTION_REQUIRED`. The owner's local state yields READY. The test was edited to expect READY and fails. |
| Expected behaviour | A release state is computed from tracked, reviewable evidence, and CI reproduces it. |
| Root cause | The gate depends on local, untracked files or `.env` values. The test was changed to match the desired status, not the computed one. |
| User impact | Reviewers and teachers could be told the product is "ready for review" on evidence that nobody else can reproduce. |
| Downstream impact | Repeats the pattern in task list §1 item 5 ("readiness declared before it was measured"). |
| Dependencies | Gate script and its config (traced by S4 in `23`). |
| Remediation | Restore the honest assertion. Make the gate read only tracked evidence, or record a signed evidence manifest. Never edit a gate test to match a desired status. |
| Acceptance criteria | The gate status in CI equals the status on the owner's machine for the same commit. `main` is green. |
| Regression test | A CI job that runs the gate on a clean checkout and posts the status as an artifact. |
| Implementation risk | Low. |
| Verification | [V-GIT] [V-STATIC] |

### X-02 — `main` is unprotected; merges precede CI; large changes land without review
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Category | Engineering process |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `list_branches`: `protected: false`. PR #86 merged 18:59:08Z; backend checks finished 19:07–19:09Z; device-matrix jobs failed after merge. `9e17370d` (72 files) and `26209a3b` pushed with no PR. |
| Actual behaviour | Red and unfinished checks do not block `main`. |
| Expected behaviour | Required checks pass before any change reaches `main`. |
| Root cause | No branch protection; solo owner plus many agent sessions. |
| User impact | Regressions can reach the branch that a deploy would use. |
| Downstream impact | Every "verified" claim in docs can be invalidated by the next push. |
| Dependencies | GitHub settings (owner only). |
| Remediation | Turn on branch protection: required checks (Lint & Test, Production Readiness, Golden-25), PR required, no force push. Keep the required set small and fast. |
| Acceptance criteria | A push with a failing required check cannot reach `main`. |
| Regression test | Attempt a PR with a deliberately failing test in a sandbox branch; confirm the merge is blocked. |
| Implementation risk | Low. Slower merges. |
| Verification | [V-GIT] |

### X-03 — PR size makes review impossible
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Engineering process |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | PR #86: 1,034 files, +87,409 / −92,640, 2 comments. PR #76: 488 commits, 140 files. |
| Actual behaviour | Multi-workstream PRs merge as one unit. |
| Expected behaviour | PR-sized units with one objective each (see `20`). |
| Root cause | Agent sessions batch whole plans into one branch. |
| User impact | Indirect: defects hide inside large merges. |
| Remediation | Cap PRs (for example ≤ 400 changed lines of application code, excluding generated files). One task ID per PR. |
| Acceptance criteria | Roadmap PRs in `20` each map to one task ID. |
| Regression test | A CI check that warns above the size cap. |
| Implementation risk | Low. |
| Verification | [V-GIT] |

### X-04 — The designated work branch is already merged; the session checkout is stale and shallow
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Repository hygiene |
| Severity | P3 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | §3 of this document |
| Remediation | Before implementation, run `git fetch origin main && git checkout -B feature/audit-strengthen-rag-qdrant origin/main`, then revalidate this audit against the new head (see `25`, first-task prompt). |
| Acceptance criteria | The coding agent records the `main` SHA it starts from. |
| Verification | [V-GIT] |

### X-05 — Two writers on the frontend (Lovable bot and agent sessions); `lovable-sync` has diverged
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Repository hygiene |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | 1,312 commits by `gpt-engineer-app[bot]`. `lovable-sync` has 4 commits not in `main` ("Fixed edge function types", "Changes") and lacks 113 commits of `main`. |
| Actual behaviour | Frontend and Supabase edge-function edits can arrive from Lovable outside the agent workflow and its guards. |
| Expected behaviour | One integration path for frontend changes, with the same CI gates. |
| Remediation | Decide the role of Lovable. Either merge or delete `lovable-sync`. Route Lovable edits through PRs with required checks. |
| Acceptance criteria | No branch with unique, unreviewed commits older than 7 days. |
| Verification | [V-GIT] [HUMAN] |

### X-06 — Public repository holds teaching content and operational data
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Category | Content rights / security |
| Severity | P1 |
| Type | Confirmed defect (exposure is confirmed; the rights impact is for the owner and rights holders to judge) |
| Confidence | High for visibility |
| Evidence | GitHub API `visibility=public`; 1,553 tracked files under `memory/`; tracked `data/*.json` graph and Qdrant backups; tracked `.env.production`, `.env.mobile`. Content detail in `14c`; secrets and data detail in `14`. |
| Remediation | Owner decision: make the repository private, or remove teaching text and data from the tracked tree and history. See `14c` register. |
| Acceptance criteria | No verbatim teaching text, transcript, or data backup is reachable in a public repository without written permission. |
| Verification | [V-GIT] [HUMAN] |

### X-07 — Agents use documents as the system's memory, which costs every session
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Maintainability |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `lessons.md` 1,993,523 bytes and 297 edits since July; `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` 408,329 bytes; root `CLAUDE.md` 48,529 bytes; `AGENTS.md` 57,746 bytes; loose root files (`handoff.md`, `roadmap.md`, `FIRST_PERSON_CONTEXT_HARNESS_AND_TAGGING_PLAN_2026-10-20.md`, two `video_*_analysis_*.md`) despite the clean-root rule. |
| Actual behaviour | Each session reconciles conflicting dated documents before work. The task list itself says sessions "spend their first hour reconciling them". |
| Expected behaviour | Executable guards and a short, current status file. History lives in Git. |
| Remediation | Freeze `lessons.md` and archive it. Keep one status file under 30 KB. Convert repeated rules into guards (the repo already has `scripts/guards/`). Move loose root files. |
| Acceptance criteria | Root holds no loose plan or analysis files. The status file is under 30 KB and dated. |
| Verification | [V-STATIC] [V-GIT] |

## 10. Not verified here

- `Pre-launch gate` on `46b808fb` (run 41863600883): 3 of 6 jobs fail. They are the Playwright "UI device matrix" jobs for Mobile Safari, firefox and webkit. Each uploads a `playwright-failures-*` artifact (artifacts 13341258070, 13341881915, 13341572949). The failing spec names were not in the log tail and were not read. Cross-browser behaviour is unverified for Safari and Firefox users. [V-GIT]
- The 11 comments on PR #76 and their resolution. Not read.
- The owner's 40 local branches and 10 agent worktrees cited in the task list §1 item 7. [LIVE-L]
