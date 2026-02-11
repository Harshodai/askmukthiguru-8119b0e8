---
description: Ralph — Autonomous PRD-driven agent loop (adapted from snarktank/ralph)
---

# Ralph Workflow

Ralph is an autonomous loop that iterates until all PRD items are complete. Each iteration = fresh context, one story, quality checks, commit, repeat.

## Setup
1. Create a PRD for the feature (use the `SPEC_DEV.md` as input)
2. Convert the PRD into a structured JSON format (`prd.json`)
3. Switch to (or create) the git branch specified in `branchName`:
   ```bash
   # Try to switch to an existing branch first (supports resuming).
   # If the branch doesn't exist yet, create it.
   git checkout <branchName> || git checkout -b <branchName>
   ```
4. **Validate dependencies** before the first iteration:
   - Verify every ID in every story's `dependencies` array references a valid story `id` in the same `prd.json`. Fail with: `"INVALID_DEP: Story #X references non-existent dependency #Y"`
   - Run a topological sort / cycle detection (DFS with coloring) across all `dependencies` edges. If a cycle is found, fail with: `"CIRCULAR_DEP: Cycle detected involving stories [#A → #B → #C → #A]"` and list all offending IDs.
   - Both checks must pass before any iteration begins.

## PRD Format (`prd.json`)
```json
{
  "projectName": "Feature Name",
  "branchName": "feature/name",
  "failurePolicy": "reduce",
  "stories": [
    {
      "id": 1,
      "title": "Story title",
      "description": "What to implement",
      "acceptanceCriteria": ["Criterion 1", "Criterion 2"],
      "priority": 1,
      "passes": false,
      "dependencies": []
    }
  ]
}
```

### Schema Notes
- **`priority`**: Lower numbers = higher priority. `priority: 1` is the highest priority and is selected first.
- **`branchName`**: The git branch for all work. Created during setup, verified at each iteration start.
- **`dependencies`**: Optional array of story `id`s that must have `passes: true` before this story can be selected. Dependency satisfaction is checked at **story-selection time** (step 2), not at quality-check time.
- **`passes`**: Allowed values: `true` | `false` | `"skipped"` | `"escalated"`.
  - `false` — initial state; story has not yet passed quality checks.
  - `true` — set **immediately** after quality checks pass (step 4), in the quality-check handler, **before** the commit step. Dependency satisfaction is not part of `passes`; it is enforced separately at selection time.
  - `"skipped"` — story was skipped by failure policy (Option B). Story-selection logic treats `"skipped"` as a terminal state (does not re-process).
  - `"escalated"` — story was escalated for human review (Option C). Treated as terminal.
- **`failurePolicy`**: Top-level or per-story. Accepted values: `"reduce"` (default) | `"skip"` | `"escalate"`. Controls behavior when quality checks fail after all retries are exhausted (see step 5).

## Execution Loop (for each iteration)

### 1. Verify Branch
Confirm the current git branch matches `branchName`. If not, run `git checkout <branchName>` (do **not** create — it should already exist from setup). Abort if checkout fails.

### 2. Select Story
Read `prd.json` — find the lowest `priority` number story where `passes === false` AND all `dependencies` have `passes === true`.

**Per-story skip**: If a story has unsatisfied dependencies, skip it and log: `"BLOCKED: Story #{id} — waiting on dependencies #{dep_ids}"`.

**Deadlock detection**: After scanning all stories, if **no** eligible story is found (every remaining story with `passes === false` has unsatisfied dependencies), this is a deadlock:
1. Write to `progress.txt`: `"DEADLOCK: No eligible stories. Blocked: [storyId -> blockingDeps]"` listing each blocked story ID and its unsatisfied dependency IDs.
2. Exit with a non-zero error code so the workflow fails fast and requires human intervention.

Select the next eligible story if one exists.

### 3. Implement
Implement that single story (one story per iteration).

### 4. Run Quality Checks
- **Type checking** — Run for typed languages (TypeScript, Java, Python projects with mypy/pyright). Skip for untyped languages.
- **Run tests** — Run all unit/integration tests by default. For large repos, run only tests affected by the change, but ensure CI runs the full suite.
- **Lint checks** — Run linter for the project's configured tool.

### 5. Handle Results
**On success:**
- Step 5a: Set `passes: true` in `prd.json` immediately (this is the quality-check handler — passes reflects that checks passed, NOT that dependencies are satisfied).
- Step 5b: Commit the implementation with a descriptive message referencing the story ID: `feat(story-#): <description>`
- Step 5c: In a separate commit, update `prd.json`: `prd.json: mark story-# passes`
- Push both commits in the same PR.

**On failure:**
Retry quality checks up to `max_retries` times (default: 2). Log each attempt's test/lint output to `progress.txt` for auditing. If all retries are exhausted, apply the `failurePolicy` (per-story override or top-level default):

- **Option A — `"reduce"` (default)**: Identify the failing component (specific failing test, lint rule, or type error from the last retry output). Reduce scope to fix it — simplify or remove the failing part. Re-run quality checks. Limit scope-reduction attempts to **2**. If reductions still fail, escalate automatically (fall through to Option C).
- **Option B — `"skip"`**: Mark the story as `"passes": "skipped"` in `prd.json`. Log full diagnostics (failing test names, error output) to `progress.txt`. The story will not be re-processed.
- **Option C — `"escalate"`**: Mark the story as `"passes": "escalated"` in `prd.json`. Create a `REVIEW_NEEDED.md` with: story ID/title, failing test/lint/type-check output, attempted retries and scope reductions, and a suggested remediation. The story will not be re-processed.

### 6. Record Learnings
Append learnings to `progress.txt`.

### 7. Repeat
Repeat until all stories have `passes` set to `true`, `"skipped"`, or `"escalated"`.

## Merge Policy
After the final iteration with all stories resolved:
1. Ensure CI is green on the `branchName` branch
2. Create a PR from `branchName` → `main`
3. Merge after review (or auto-merge if configured)

## Critical Rules
- **Each Iteration = Fresh Context**: Only memory between iterations is git history, `progress.txt`, and `prd.json`
- **Small Tasks**: Each story must be completable in one session. Split big stories.
- **Feedback Loops**: Tests verify behavior. Type checks catch errors. CI stays green.
- **Right-sized stories**: Add a component, update an action, add a migration. NOT "build the dashboard."
- **Stop Condition**: When all stories have `passes` resolved (true/skipped/escalated), output COMPLETE.

## After Each Iteration
Update any relevant documentation with learnings:
- Patterns discovered ("this codebase uses X for Y")
- Gotchas ("do not forget to update Z when changing W")
- Useful context ("the settings panel is in component X")
