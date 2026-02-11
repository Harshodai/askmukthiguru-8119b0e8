---
description: GET SHIT DONE — Spec-driven development workflow (adapted from gsd-build/get-shit-done)
---

# GET SHIT DONE (GSD) Workflow

Complexity is in the system, not the workflow. Every step produces a markdown artifact that drives the next step. Context engineering → XML-structured plans → atomic execution → verification.

## Special Directives
- `// turbo` — Placed above a phase step to indicate that `run_command` tool calls in that step can be auto-run (`SafeToAutoRun: true`). Applies only to the single step immediately following it.
- `// turbo-all` — Placed anywhere within a phase to indicate that ALL `run_command` tool calls in that entire phase can be auto-run (`SafeToAutoRun: true`). Applies to every step in the phase.

These are instructions for the Antigravity AI agent's workflow runner, not code comments.

## Phase 0: Map Existing Codebase (Brownfield only)
// turbo
1. Analyze the existing codebase structure, tech stack, conventions, and patterns
2. Document findings in `.planning/CODEBASE_MAP.md`
3. This feeds all subsequent phases with existing context

## Phase 1: Initialize Project
1. Ask the user clarifying questions until the idea is fully understood (goals, constraints, tech preferences, edge cases)
2. Research the domain — investigate best practices, libraries, patterns
3. Extract requirements — what's v1, v2, and out of scope
4. Create a phased roadmap mapped to requirements
5. Save artifacts:
   - `SPEC_DEV.md` — Source of truth (the "what")
   - `ROADMAP.md` — Execution strategy (the "how")
   - `STATE.md` — Current phase/status tracker
6. Get user approval on the roadmap before proceeding

## Phase 2: Discuss Phase
1. For each phase in the roadmap, analyze gray areas:
   - APIs → error handling, response format, edge cases
   - UI → layout, interactions, empty states
   - Data → schema, validation, transformations
2. Ask the user to clarify preferences for each gray area
3. Save as `.planning/{phase}-CONTEXT.md`

## Phase 3: Plan Phase
1. Research how to implement the phase, guided by CONTEXT decisions
2. Create 2-3 atomic task plans (small enough for a single focused session)
3. Verify plans against requirements
4. Each task must specify:
   - **Files** to create/modify
   - **Action** with precise instructions
   - **Verify** how to confirm correctness
   - **Done** criteria
5. Save as `.planning/{phase}-{N}-PLAN.md`

## Phase 4: Execute Phase
// turbo-all
1. Execute plans one at a time in clean context
2. After each task: run tests, verify, commit atomically
3. Commit format: `feat({phase}): {description}` or `fix({phase}): {description}`
4. Save execution summary as `.planning/{phase}-{N}-SUMMARY.md`

## Phase 5: Verify Work
1. Extract testable deliverables from the phase
2. Walk user through each one for confirmation
3. If issues found → diagnose → create fix plan → re-execute
4. Document results in `.planning/{phase}-VERIFICATION.md`

## Phase 6: Repeat → Complete → Next Milestone
1. Loop Phase 2-5 for each phase in the roadmap
2. When all phases done → archive milestone, tag release
3. Start next milestone with fresh roadmap cycle

## Quick Mode (for small tasks)
For bug fixes, config changes, or one-off tasks that don't need full planning:
1. Ask what needs to be done
2. Create a quick plan
3. Execute and commit
4. Save to `.planning/quick/{NNN}-{description}/`

## Key Principles
- **Context Engineering**: Every artifact feeds the next step — nothing exists in isolation
- **Atomic Commits**: Every task = one commit. Traceable. Revertable. Clean history.
- **Fresh Context**: Each execution step starts clean. No accumulated garbage.
- **Verify Everything**: Automated tests + human verification for every phase.
