# Lovable sync path review

## 0. Header

| Field | Value |
|---|---|
| Status | Proposal. Review only. No branch was changed. |
| Date | 2026-11-06 |
| Reviewed head | `004f3cf5` (`feature/audit-strengthen-rag-qdrant`) |
| Compared refs | `origin/lovable-sync` = `bb043ae8`; `origin/main` = `46b808fb` (fetched 2026-11-06) |
| Decision | D-24: "What is Lovable's role? Merge or delete `lovable-sync`?" (`unresolved-questions.md:34`) |
| Method | Read-only Git (`git log`, `git diff`, `git show`, `git ls-remote`). No Lovable tool, no Lovable account, no external service. Conventions: `CONVENTIONS.md`. |

Evidence labels follow `CONVENTIONS.md` §3. `[V-GIT]` = verified in Git data now. `[V-STATIC]` = verified in files at the named ref. `[INF]` = inference. `[HUMAN]` = owner decision.

## 1. Existing coverage

| Source | What it says | Gap |
|---|---|---|
| `01-repository-git-history-and-pr-investigation.md:21` | Lists `lovable-sync` (`bb043ae8`) as one of 3 remote branches. | No content review. |
| `01-...:62,68` | `gpt-engineer-app[bot]` has 1,312 commits (about 37%). "The frontend has two writers." | No write-path analysis. |
| `01-...:298-309` (X-05) | `lovable-sync` has 4 commits not in `main`, lacks 113 commits of `main`. Remedy: "Either merge or delete". | No diff review, no rule conflicts, no options. |
| `unresolved-questions.md:34` (D-24) | Open. Target: "One PR-based path". Linked task: T0-07. | No recommendation. |
| `20-ordered-engineering-roadmap.md:35,77-81,148` | Lists T1-16, T1-17, T1-19, T6-10 as frontend tasks. | Does not state which Lovable-touched files they share. |

This document adds the missing evaluation. It does not replace X-05.

## 2. Facts about the branch and the write path

### 2.1 The branch `origin/lovable-sync`

| Item | Value | Label |
|---|---|---|
| Tip | `bb043ae8` "Fixed edge function types", 2026-10-23 19:13:21 +0000 | [V-GIT] |
| Merge base with `main` | `fbbd96fe` (2026-10-24 00:36 +0530) | [V-GIT] |
| Merge base with audit branch `004f3cf5` | `fbbd96fe` (same commit) | [V-GIT] |
| Ahead / behind `main` | 4 ahead, 113 behind | [V-GIT] `git rev-list --left-right --count` |
| Ahead / behind audit branch | 4 ahead, 210 behind | [V-GIT] |
| Age of last commit | 14 days before 2026-11-06 | [V-GIT] |
| Authors | 4 of 4 commits by `gpt-engineer-app[bot]` (`159125892+gpt-engineer-app[bot]@users.noreply.github.com`) | [V-GIT] |

The 4 commits:

| Commit | Time (UTC, 2026-10-23) | Message | Files |
|---|---|---|---|
| `d6e0203f` | 19:09:04 | Work in progress | `src/integrations/supabase/previewAuthStorage.ts`, `src/integrations/supabase/types.ts` |
| `f877dfa8` | 19:09:56 | Changes | `supabase/functions/memory-extract-drain/index.ts` |
| `d1b6c3bf` | 19:11:43 | Changes | `src/components/landing/HeroSection.tsx` |
| `bb043ae8` | 19:13:21 | Fixed edge function types | (merge-base to tip: the 4 files below) |

Net change from merge base to tip: 4 files, +144 / -66. [V-GIT]

| File | Net change | Already on `main`? | Differs on audit branch? |
|---|---|---|---|
| `src/integrations/supabase/types.ts` | +100 / -100 (reorder one table, add `tenant_id` columns, add `claim_pending_extractions`, `has_active_memory_consent`, drop `p_tenant_id` args) | Yes. `git diff origin/lovable-sync origin/main` is empty for this file. `main` has `646b8bfa` (2026-10-23 19:15:42) "Work in progress". | No. Empty diff to `HEAD`. |
| `src/integrations/supabase/previewAuthStorage.ts` | +101 / -... (typed broker, `PreviewAuthStorage` interface) | Yes. Empty diff to `main`. | No. |
| `src/components/landing/HeroSection.tsx` | removes `fetchPriority="high"` (1 line) | No. `main` and `HEAD` keep it (`HeroSection.tsx:89`). | Yes. |
| `supabase/functions/memory-extract-drain/index.ts` | imports `type SupabaseClient`, replaces `ReturnType<typeof createClient>` 4 times | No. `HEAD` has no `SupabaseClient` (grep). `main` instead adds `sourceConversationId` and `memorySource.ts` import. | Yes. |

[V-GIT] for all rows.

Reading: two of four files are already identical on `main`. The branch holds two small changes not on `main`: one hero-image priority removal and one type-only edge-function refactor. [INF] The branch is a stale copy of a Lovable change set that `main` took through another path (see 2.2).

### 2.2 How Lovable writes

| Item | Value | Label |
|---|---|---|
| Bot identity | `gpt-engineer-app[bot]`, 1,316 commits across all refs (`git log --all --format='%an|%ae'`); 1,312 on `main` | [V-GIT] |
| Bot commits on `main` after the merge base `fbbd96fe` | 36; last one `9e50fe56` "Lovable update", 2026-10-31 | [V-GIT] |
| Bot-authored merge commits on `main` | 202. Example: `9e50fe56` has parents `311a8cf3` and `b54b02d2`; committer is the bot. | [V-GIT] |
| Write mode | The bot creates commits and merge commits whose committer is the bot. [INF] Lovable pushes to `main` directly (or via its own sync branch that it merges itself). No PR is needed in this history. The exact GitHub setting (branch protection, direct push right) is not visible from Git. | [INF] |
| Files the bot touched on `main` (all history) | `.lovable/plan.md` 58 times; `package.json` 12; `package-lock.json` 7; `vite.config.ts` 3; `.env.example` 2; `.env.production` 1; `bun.lock` 16 (last 2026-07-27, since removed); many root-level `.md` files | [V-GIT] |
| `.lovable/` in tree | `.lovable/plan.md` and 5 files in `.lovable/plan/`; 6 tracked files. Last change to `plan.md`: `b8b7604b` by Harshodai, 2026-11-01 | [V-GIT] |
| Workflow or bot that syncs | None found in `.github/workflows/` (24 files). Only 2 workflows mention Lovable: `build-deploy.yml:138` (comment: "The frontend is hosted on Lovable") and `eval-gate.yml:81` (`LOVABLE_API_KEY` secret passed to the golden eval). | [V-STATIC] grep |
| Sync is done by | Lovable's own GitHub integration (outside this repo). [INF] Rests on bot-committed merges and no workflow in the repo. | [INF] |
| Check on bot pushes | `main-hard-gates.yml` runs on `push` to `main` and on `pull_request` to `main`. On a direct bot push it runs after the code has landed. | [V-STATIC] |

### 2.3 Frontend deploy and backend URL

| Build | Backend URL it calls | Evidence |
|---|---|---|
| Vercel build | `VITE_BACKEND_URL=https://askmukthiguru-8119b0e8-production.up.railway.app`, set in `vercel.json` `env` | [V-STATIC] `vercel.json:2-4` |
| Build that reads `.env.production` | Same Railway URL; also real `VITE_SUPABASE_URL` and publishable key | [V-STATIC] `.env.production` |
| Lovable preview / Lovable hosting | Not in repo. `src/lib/domain.ts:13` says "a Lovable build must set VITE_BACKEND_URL". `src/lib/backendUrl.ts:34` reads `VITE_BACKEND_URL` or empty. `vite.config.ts:41` falls back to `http://localhost:8000` for the dev proxy. If Lovable sets no value, the call target is empty or local. Value in the Lovable project settings is unknown. | [V-STATIC] + [HUMAN] |
| CI image | `frontend/Dockerfile` with mock Supabase values; scan only, not deployed (`build-deploy.yml:136-141`) | [V-STATIC] |
| Railway | `.railwayignore` hides `src/`, `package.json`, `vite.config.ts`, `.lovable/`, `*.tsx`, `*.ts`; Railway builds only `backend/` | [V-STATIC] |

Unknown: which host serves the public frontend today (Vercel, Lovable hosting, or both). `vercel.json` and the build-deploy comment disagree. See Unknowns.

## 3. Findings

### LOV-01 — Lovable writes to `main` without a PR (P1)

| Field | Value |
|---|---|
| Severity | P1 (architectural risk) |
| Evidence | 36 bot commits on `main` since `fbbd96fe`, 202 bot-authored merges overall, last `9e50fe56` on 2026-10-31 [V-GIT]. No PR path in history for those commits. [INF] |
| Impact | Unreviewed code reaches `main`. Hard gates (`main-hard-gates.yml`) run after the push. Guards that run only in pre-commit (`scripts/guards/lesson_guards.py`) never run on the bot's commits. [INF] The bot has no local hook. |
| Fix | NEW-LOV-01, NEW-LOV-02. |

### LOV-02 — Two writers touch the same frontend files (P1)

| Field | Value |
|---|---|
| Severity | P1 (architectural risk) |
| Evidence | Bot commits on `main` after the merge base touched 26 distinct paths. The audit branch (`004f3cf5` vs `46b808fb`) changes 33 files in `src/`. They share `src/components/chat/ChatInterface.tsx` [V-GIT]. T1-16, T1-19 and T1-10 all list that file (`20-ordered-engineering-roadmap.md:215`). |
| Impact | Merge conflict risk on the main chat component. Lovable regenerates whole files; a Lovable edit can undo T1-16 (relative `/api` calls replaced by `BACKEND_URL`), T1-19 (no summary call), or T1-17 (helpline on error cards). A conflict resolved in the Lovable editor is not reviewed by the audit tests. [INF] |
| Fix | NEW-LOV-02, NEW-LOV-03. |

### LOV-03 — Lovable can regenerate DB types and edge functions from its own Supabase view (P1)

| Field | Value |
|---|---|
| Severity | P1 (architectural risk) |
| Evidence | `src/integrations/supabase/types.ts` and `previewAuthStorage.ts` carry the header "This file is automatically generated. Do not edit it directly." [V-STATIC]. The Lovable commit `d6e0203f` changed RPC signatures (`p_tenant_id` dropped from `create_compaction_snapshot` and two other RPCs; `claim_pending_extractions` added). `memory-extract-drain/index.ts` is a consent-critical edge function (receipt checks, claim ownership). |
| Impact | A regenerated `types.ts` can disagree with the migrations in `supabase/migrations/` and with the consent and memory UI. The memory consent invariants (CLAUDE.md "Memory Consent & SQL Deletion Cascade") live in SQL and in this edge function. A type-only edit looks harmless but ships a function body that the audit tests do not cover. [INF] |
| Fix | NEW-LOV-02 (path filter), NEW-LOV-04. |

### LOV-04 — `lovable-sync` is stale and carries 2 small unmerged changes (P2)

| Field | Value |
|---|---|
| Severity | P2 (maintainability) |
| Evidence | 4 ahead, 113 behind `main`; last commit 2026-10-23 [V-GIT]. Section 2.1 table. |
| Impact | The branch looks like pending work. A person who merges it can (a) drop `fetchPriority="high"` from the hero image, a likely Largest Contentful Paint regression [INF, not measured], and (b) revert nothing else, because `types.ts` and `previewAuthStorage.ts` already match `main`. Merging it into `main` now would add a conflict with the `memory-extract-drain` change that `main` has (`sourceConversationId`). [INF] A textual merge test was not run (see Unknowns). |
| Fix | NEW-LOV-05. |

### LOV-05 — Lovable edits repo-root and doc files that repo rules reserve (P2)

| Field | Value |
|---|---|
| Severity | P2 |
| Evidence | The bot touched root-level `.md` files (`roadmap.md` 12 times, `handoff.md` 8, `RELEASE_CHECKLIST.md` 3, others once), `.env.production`, `.env.example`, `package.json` (12) and `package-lock.json` (7) [V-GIT]. `CLAUDE.md` "Project constraints": clean root; plans in `docs/`; secrets stay in env vars. |
| Impact | Violates "clean root" (loose markdown at the repo root). The `.env.production` edit is a public-bundle file (publishable keys only today), but a bot that can edit it can edit any value in it. `package.json` edits by Lovable can add dependencies without the licence review (`LICENSE-EXCEPTIONS.md`). [INF] |
| bun.lockb | No `bun.lockb` or `bun.lock` is tracked now (`git ls-files`). The bot edited `bun.lock` 16 times, last on 2026-07-27, and it was later removed. Rule "do not touch `bun.lockb`" is met at this head. The risk is that Lovable's tooling re-creates a Bun lockfile. [V-GIT] + [INF] |
| Fix | NEW-LOV-02, NEW-LOV-03. |

### LOV-06 — Voice and storage rules have no gate against Lovable UI edits (P2)

| Field | Value |
|---|---|
| Severity | P2 |
| Evidence | Voice rules: `CLAUDE.md` "Voice Governance" (assistant never speaks in a teacher's first person; clips only verbatim). Storage contracts: `src/CLAUDE.md:31,38-39` (localStorage stores, `askmukthiguru_stream_checkpoint` in `sessionStorage`, `clearProfile()` on sign-out). Lovable prompts in `.lovable/plan.md` describe UI and journey changes (e.g. "Personalize action", "daily journey"). [V-STATIC] |
| Impact | Lovable copy edits can reintroduce claims that T6-10 removed (landing copy that promises more than the product does) or text that reads as teacher speech. No automated check reads UI copy for voice. [INF] A Lovable change to chat streaming can drop the checkpoint contract. |
| Fix | NEW-LOV-03, NEW-LOV-06. |

### LOV-07 — Frontend host and `VITE_BACKEND_URL` for Lovable builds are undocumented (P2)

| Field | Value |
|---|---|
| Severity | P2 |
| Evidence | Section 2.3. `vercel.json` hard-codes the Railway URL; `build-deploy.yml:138` says the frontend is hosted on Lovable; `src/lib/domain.ts:13` says a Lovable build must set the variable. |
| Impact | A Lovable preview with no variable calls an empty or local URL, and a Lovable publish could call a different backend than Vercel does. Railway is stopped by owner decision (`CLAUDE.md` Gotchas), so the Railway URL in `vercel.json` may point to a stopped service. [INF] |
| Fix | NEW-LOV-07. |

### LOV-08 — `LOVABLE_API_KEY` secret in the eval workflow (P3)

| Field | Value |
|---|---|
| Severity | P3 |
| Evidence | `eval-gate.yml:81` passes `secrets.LOVABLE_API_KEY` to `run_golden_eval.py`. `AGENTS.md:187` cites a "Lovable key hard-dependency" lesson. [V-STATIC] |
| Impact | A secret tied to a vendor that D-24 may retire. If option A is chosen, the secret may be unused. Not verified whether the eval script reads it. |
| Fix | NEW-LOV-08. |

## 4. Options and recommendation

All items below are proposals. The decision belongs to the owner [HUMAN].

| | A. Retire Lovable writes, delete the branch | B. Lovable only through PRs with required checks | C. Design sandbox that never merges |
|---|---|---|---|
| What changes | Disconnect the Lovable GitHub integration. Delete `lovable-sync`. Remove `.lovable/` and the `.railwayignore` line. | Keep the integration. Lovable pushes to a feature branch only. `main` requires a PR, `main-hard-gates`, and a path-filtered review. | Keep Lovable on a separate repo or fork. Humans port wanted ideas by hand. |
| Writers on frontend | 1 | 2, but one gate | 1 in this repo |
| Guard coverage | Full | Full for PRs; bot has no pre-commit hook, so CI must run the guards (NEW-LOV-02) | Full |
| Review load | Lowest | Medium. Every Lovable change needs a human review. | Low, but copy-paste cost |
| Loss | Lovable's visual editor and preview for this repo | None, but slower | Live link between editor and repo |
| Risk | Owner may still want visual edits; Lovable-generated Supabase types stop (can come from `supabase gen types` instead) | Lovable regenerates large files, so PRs are noisy and conflict with audit work | Drift between two code bases |
| Rollback | Re-connect the integration (account-side, not in Git) | Remove branch protection | Re-connect |
| Fit with D-24 target "One PR-based path" | Yes (zero Lovable path) | Yes | Partly |

### Recommendation (proposal)

Choose B now. Treat A as the end state if the owner stops using the Lovable editor.

Reasons:
1. `main` already contains the Lovable work that matters: the 2 generated files match, and 36 more bot commits landed after the branch forked. Deleting `lovable-sync` loses 2 small changes only (hero `fetchPriority`, a type-only refactor). [V-GIT]
2. The owner's own files reference Lovable as a host (`build-deploy.yml:138`, `src/lib/domain.ts:13`). Option A needs an owner answer on hosting first (Unknown U-1).
3. B closes LOV-01 and LOV-02 without removing a tool the owner may still use.
4. C does not fix the existing `main` write path, because Lovable already writes to `main`.

Order: delete the stale branch (NEW-LOV-05) first; it is independent of the choice. Then gate `main` (NEW-LOV-01, -02). Revisit A after 30 days if no Lovable PR is opened. [INF]

## 5. Tasks

Task IDs are `NEW-LOV-n`. They are not yet in `20-ordered-engineering-roadmap.md`. Link to T0-07 (D-24 task).

| ID | Task | Files | Non-goals | Rollback |
|---|---|---|---|---|
| NEW-LOV-01 | Owner step: in GitHub settings, require a PR and the `main-hard-gates` check on `main`; remove direct-push right of `gpt-engineer-app[bot]`. Then confirm Lovable pushes to a branch. | None in repo (GitHub settings). Record the result in `docs/`. | Do not change CI jobs. Do not contact Lovable. | Untick the rule in GitHub settings. |
| NEW-LOV-02 | Add a CI job on `pull_request` that runs `scripts/guards/lesson_guards.py` and fails if a PR by `gpt-engineer-app[bot]` changes `bun.lock*`, root `*.md`, `.env*`, `package.json`, `package-lock.json`, `supabase/migrations/**`, `supabase/functions/**` or `src/integrations/supabase/**` without a label `lovable-reviewed`. Add `.github/CODEOWNERS` for the same paths. | `.github/workflows/lovable-pr-guard.yml` (new), `.github/CODEOWNERS` (new), a test under `scripts/guards/tests/` or `backend/tests/` | No change to existing guards. No auto-merge. | Delete the new workflow and CODEOWNERS file. |
| NEW-LOV-03 | Add a UI-copy voice check: a test that scans `src/locales/*.json` and landing components for first-person teacher phrasing ("I invite you", "When I speak of") and for the T6-10 claims list. Extend the ESLint rule for relative `/api` (already in `eslint.config.js:65-74`) to cover Lovable-created files. | `src/__tests__/voice-copy.test.ts` (new), `eslint.config.js` | No copy rewrite. No translation review (needs native speakers, a separate human gate). | Remove the test file. |
| NEW-LOV-04 | Add a CI check that `src/integrations/supabase/types.ts` equals the output of `supabase gen types` against the repo migrations, or at least that RPC names in `types.ts` exist in `supabase/migrations/`. Mark the files "do not edit by hand" in CODEOWNERS. | `.github/workflows/supabase-schema-snapshot.yml` (extend) or a new script in `scripts/guards/` | Do not run against a live Supabase project in this task. | Revert the workflow edit. |
| NEW-LOV-05 | Delete `origin/lovable-sync` after the owner confirms (D-24). Before deleting, record `bb043ae8` in `docs/` so the tip can be restored. Owner decides whether to port `fetchPriority` removal and the `SupabaseClient` type refactor by a normal PR. | Remote branch ref; one note in `docs/` | Do not merge the branch. Do not rebase it. | `git push origin bb043ae8:refs/heads/lovable-sync` (owner action). |
| NEW-LOV-06 | Add a short rule to `src/CLAUDE.md`: Lovable edits must keep `chatStorage`, `profileStorage`, `askmukthiguru_stream_checkpoint` contracts; list the audit tasks T1-16, T1-17, T1-19, T6-10 as "do not revert". Add Lovable "Project knowledge" text from the same rule (owner step, in the Lovable account, not done here). | `src/CLAUDE.md` | No change to `CLAUDE.md` root. | Revert the edit. |
| NEW-LOV-07 | Write the frontend hosting fact sheet: which host serves production, the `VITE_BACKEND_URL` of each build (Vercel, Lovable preview, Lovable publish, native), and that Railway is stopped. Resolve the `build-deploy.yml:138` comment. | `docs/operations/frontend-hosting.md` (new), `.github/workflows/build-deploy.yml:138` (comment only) | No deploy. No change to `vercel.json` values. | Delete the doc; revert the comment. |
| NEW-LOV-08 | Check if `backend/evaluation/run_golden_eval.py` reads `LOVABLE_API_KEY`. If not, remove it from `eval-gate.yml:81`. | `.github/workflows/eval-gate.yml` | Do not remove the secret from GitHub settings in the same task. | Restore the line. |

## 6. Verified / Assumptions / Unknowns

### Verified

- `origin/lovable-sync` = `bb043ae8`, 4 ahead and 113 behind `main`, 4 ahead and 210 behind `004f3cf5`; merge base `fbbd96fe` for both. [V-GIT]
- All 4 branch commits are by `gpt-engineer-app[bot]`, 2026-10-23 19:09 to 19:13 UTC. [V-GIT]
- The branch changes 4 files (+144 / -66). `types.ts` and `previewAuthStorage.ts` are identical to `main` and to the audit head. [V-GIT]
- `main` has 36 bot commits after the merge base; the last is `9e50fe56`, 2026-10-31. Bot-authored merge commits on `main`: 202. [V-GIT]
- No workflow in `.github/workflows/` syncs Lovable. Two workflows mention it (`build-deploy.yml:138`, `eval-gate.yml:81`). [V-STATIC]
- `.lovable/` has 6 tracked files. No `bun.lock` or `bun.lockb` is tracked now. [V-GIT]
- `vercel.json` sets `VITE_BACKEND_URL` to the Railway URL. `.railwayignore` hides the frontend from Railway. [V-STATIC]
- Bot commits and the audit branch both change `src/components/chat/ChatInterface.tsx`. [V-GIT]

### Assumptions

- A1. Lovable writes to `main` by direct push or self-merge through its GitHub integration. Rests on bot-committed merges and no repo workflow. [INF]
- A2. Removing `fetchPriority="high"` lowers hero-image load priority and may hurt LCP. Not measured. [INF]
- A3. A bot push does not run local pre-commit hooks, so `lesson_guards.py` does not run on it. [INF]
- A4. Recommendation B is a proposal; A and C remain valid. [HUMAN]

### Unknowns

- U-1. Which host serves the public frontend now (Vercel, Lovable, both). Needs the owner. [HUMAN]
- U-2. GitHub branch protection on `main` and the bot's push right. Not visible from Git; needs repo settings. [HUMAN]
- U-3. The `VITE_BACKEND_URL` set inside the Lovable project. Not in the repo; not read (no Lovable access used). [HUMAN]
- U-4. Whether `lovable-sync` is created by Lovable's integration or by hand. The name is not in any repo file. [HUMAN]
- U-5. A textual merge of `lovable-sync` into `main` or into `004f3cf5` was not run (`git merge-tree` can write objects, so it was skipped under the no-write rule). Conflict in `memory-extract-drain/index.ts` and `HeroSection.tsx` is expected only by inference.
- U-6. Whether `run_golden_eval.py` reads `LOVABLE_API_KEY`. Not checked.
- U-7. The Lovable GitHub integration state (connected or not). Needs the owner's Lovable account; not used here.
