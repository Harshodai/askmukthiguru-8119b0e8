# Review: plan to take PR #68 green, and the profile/pipeline "master plan"

Checked 2026-10-16 19:3x UTC against: PR #68 head `d4d638b` on GitHub, CI check runs on that head, the Mac working tree (`feat/clip-quality-grading`), `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` (A1–A24), CLAUDE.md invariants. Read-only: nothing edited, committed or pushed.

## Ranked problems

1. **The master plan file must not be executed.** `.claude/tasks/profile_redesign_chat_declutter_pipeline_plan.md` (untracked, Mac only) reverses owner decisions and safety invariants:
   - Task 1.1 sets `first_person_llm_fallback_enabled=True` (owner decision 2026-10-11 is `false`, invariant 21) and `first_person_uncalibrated_direct_enabled=True` with the 0.45 calibration file. 0.45 is the threshold that served "capital of France" as teacher discourse (Audit D P0, invariant 16); invariant 3 forbids hand-picked thresholds.
   - Task 1.3 sends every first-person abstain into the generating graph. That is the "AI improvises a teaching" path the owner turned off.
   - Task 2.1 strips "Yes," / "So," and adds bracketed clarifiers inside quotes. That edits served verbatim text (A20 rejected exactly this; invariant 13 hash).
   - Task 2.4 replaces the LLM relevance gate with a cross-encoder and lowers `crag_skip_confidence` 0.75 → 0.58 by hand. The relevance gate is what took the judge's DON'T-SHOW share from 42% to 12% (invariant 24).
   - Task 2.3 rewrites `GURU_SYSTEM_PROMPT`; the anti-impersonation clause lives there (`test_guru_voice_langhanam.py`).
   - Task 3.1 drops `require_aal2` on `/api/kg/personal-subgraph` (`backend/app/api/kg.py:393`), a step-down in protection for personal memory data.
   - Section 4's sample "verbatim" quotes (e.g. "40,000 neurons of your heart", "Fortune favors the connected consciousness") are not shown to come from any transcript. A plan that models invented teacher quotes breaks L-NO-INVENTED-CREDIT-1 on its own page.
   - Several root-cause claims are stale or by design: `_first_person_claims` returning True is the registry design (`backend/rag/pipeline_registry.py`), the v8 404 is already overridden locally (see 4), and the graph is Memgraph and does not reach answers (CLAUDE.md "Knowledge graph").
   - Safe to keep, as separate small PRs: web-search domain firewall (1.5), profile UI items not already in `b1ab5ca`/`74e51b1`.

2. **CI on the current head is already red, and both reds are caused by this PR.**
   - *Pre-Launch Security Checklist*: gitleaks fails to load `.gitleaks.toml` ("'Allowlist' expected a map, got 'slice'"). The PR changed `[allowlist]` to two `[[allowlist]]` tables. Net effect: **no secret scan ran on this PR at all.** Fix the config (one `[allowlist]` with both regexes, or the array form your gitleaks version supports; verify with gitleaks 8.24.3 locally) — never relax the check.
   - *Frontend build/lint/typecheck/unit* and *Frontend quality gates*: `src/test/personalizeTeaching.test.ts:49` imports `chatStorage` → `src/integrations/supabase/client.ts:10` throws without `VITE_SUPABASE_*`. Mock the client in the test; do not put keys in CI.
   - About 12 other checks were still running when read.

3. **Step 2 of the Mac prompt is stale, and the tree has unplanned work.** A22, the profile cards and the ruff format are already committed and pushed (`28f2f55`, `74e51b1`, `d4d638b` = PR head). Meanwhile the Mac tree holds 24 modified + 3 untracked files that no plan mentions: a new admin `ClipReportsPage`, Auth/MFA/AgeConfirm/ResetPassword pages, all 15 locale files, `scripts/i18n/source-hashes.json`, and `docs/reviews/A12_*`, `A24_*`. "Commit in three pieces" will either sweep these in unreviewed or leave them dangling. Auth and MFA page changes need their own review. Commits by author `opencode` (e.g. `f0964cf`) are also on the branch; it is unclear which session made the uncommitted edits.

4. **Local serves v7, prod config serves v8.** `f0964cf` makes `backend/docker-compose.yml` default `FIRST_PERSON_COLLECTION=first_person_v7` ("no v8 snapshot on this machine"), while `config.py:183` and CLAUDE.md invariant 23 say v8 serves. So "frozen-29 serves 9", the clip-cap numbers and any graded clean-Docker run may measure a different corpus than faculty would get. CLAUDE.md also says v8 was built on the Mac on 2026-10-11; if it is gone, that is a data/backup question too. Decide the faculty collection before measuring anything, and record collection name + point count in every run.

5. **"Served count" is the wrong headline.** Step 6 reports only served (last 9/29). Pushing that number up rewards loosening gates. Every run should report served, out-of-corpus leaks (32/32 abstain), indeterminate count (must be 0, A3), and the independent judge's DON'T-SHOW share, plus `evals/run_safety_scenarios.py` (0 crisis misses, control false positives) after any change touching gates or safety.

6. **A24 is missing from the Mac prompt.** Self-injury ("scratching my arms till they bleed") and disordered eating ("starving myself") get no topic rail, no distress level and no helpline today. It is filed under "humans", but it is a live safety gap that needs your decision, not just a reviewer.

7. **`/code-review max --fix` after CI is green is the wrong order.** Auto-fix across an 80-commit PR touches gate and verbatim code and turns CI red again. Review without `--fix`, triage, fix valid findings, run the safety evals and suites, then push once.

8. **Status claims in the pending list are off.**
   - A22 is not "not done": code and tests are committed (`28f2f55`). What is missing is the evidence the task list asks for (a two-tenant Memgraph run); the commit message says "checked against live Memgraph" with no artifact.
   - Item 4 (delete `claude/project-thread-3cymsm`): already gone; `git ls-remote` shows only main, feat/clip-quality-grading, claude/repeat-lessons-guards and two 2026-10-11 branches.
   - A23 and the frozen-29 re-run are paid live calls (A4 says ~120 calls need the owner's word).

9. **Stall risks.** Every commit/push from the Mac needs Harsha in a Mac terminal; batch them into one sitting. Merges go through the audit thread only (memory rule), so "merge #69" is the audit thread's step, not Harsha's alone.

## Corrected plan

1. Shelve the master-plan file. Triage the 27 uncommitted files: move them to a separate branch/PR (auth pages reviewed on their own) or drop them. Nothing new joins #68.
2. Fix the two PR-caused reds (gitleaks config, Supabase mock in the test). Run full backend + frontend suites locally. Harsha pushes once.
3. Wait for every check on that head; fix remaining reds without skipping tests.
4. Code review without auto-fix; fix valid findings; run crisis tests + `evals/run_safety_scenarios.py` + suites; one push.
5. Decide the faculty collection (v7 or v8). Then, with Harsha's OK for paid calls: A23 compare on the frozen 29, and the frozen-29 re-run reporting served, leaks, indeterminate, judge DON'T-SHOW, collection + point count.
6. File the A22 two-tenant Memgraph evidence.
7. Update the runbook artifact with run ids and evidence per item.
8. Audit thread merges #68 and #69; then the clean-Docker run on final main with caches verified empty (`make verify-cache-empty`), graded by the audit thread.
9. Human gates stay open: clinician + native speakers (A12, A24, A7), listening audit (A11), Supabase key, Railway login and go. Verdict stays NO-GO.
