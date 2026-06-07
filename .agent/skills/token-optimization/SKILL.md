---
name: token-optimization
description: Habits and tactics to reduce token usage during agent work — when to spawn subagents, batch tool calls, prefer graph/search over reads, and compact context at safe breakpoints.
---

# Token Optimization

Apply on every non-trivial task to extend session quality within token limits.

## Core habits

1. **Batch parallel tool calls.** Independent reads, searches, edits, and deploys MUST go in one tool block. Sequential calls without dependency = wasted tokens.
2. **Prefer narrow tools over file reads.**
   - `rg -n` / `rg -l` before `code--view`.
   - `code--view` with specific `lines` ranges, never full file by default.
   - `code-review-graph` MCP (`semantic_search_nodes`, `query_graph`, `get_impact_radius`) before grep when available.
3. **Spawn subagents for high-output exploration.** Use `acp_subagent--explore` or `acp_subagent--spawn_agent` for "trace this", "find all usages", "audit X" — they read many files and return a summary, keeping main context clean.
4. **Use `code--line_replace` (with `...` ellipsis on >6-line ranges) instead of `code--write`** unless creating a new file.
5. **Skip recap prose.** One short closing sentence. No "Files changed" lists, no third-person past-tense summaries.
6. **Reuse `<codebase-context>` files already in prompt** — never re-read them.
7. **Verify with the cheapest signal.** `tsc`/build output > targeted test > full test run > preview screenshot. Don't screenshot for logic bugs; don't run tests for pure type changes.

## Sprint / multi-step work

- Use `task_tracking--create_task` only when ≥2 meaningful steps. Don't narrate task management.
- For "continue the plan" requests: read `.lovable/plan.md` / `next_steps.md` once, then act. Don't re-summarize the plan.
- At logical breakpoints, drop intermediate context by closing out completed tasks before starting the next.

## Model selection (Lovable AI Gateway in edge functions)

| Task | Model |
|---|---|
| Chat / streaming / agent loops | `google/gemini-2.5-flash` (default, free until Oct 13 2025) |
| Cheap classification, summarization, embedding-style | `google/gemini-2.5-flash-lite` |
| Hard reasoning, structured extraction, code synthesis | `google/gemini-2.5-pro` |
| Image gen | `google/gemini-2.5-flash-image` (Nano Banana) |

Never default to GPT-5 for routine generation — Gemini Flash is 5–10× cheaper for equivalent quality on this stack.

## Anti-patterns to refuse

- Reading entire files just to find one symbol → use `rg -n "symbol" path`.
- Re-running the same failed command 3+ times → change approach.
- `cat` / `ls` / `find /` in bash → use `code--view`, `code--list_dir`, scoped `rg`.
- `cd /dev-server && ...` as first call (CWD already there) → wasted call.
- Standalone shell comments (`# note`) as commands → no-ops.
- Asking the user to confirm obvious next steps when the request was "continue" or "yes".

## Quick checklist before sending a response

- [ ] Did I batch independent tool calls?
- [ ] Did I use ranged `code--view` or `rg`, not full reads?
- [ ] Could a subagent have produced this exploration?
- [ ] Is my prose under 2 lines (excluding code/tool output)?
- [ ] Did I avoid re-reading files already in `<codebase-context>`?
