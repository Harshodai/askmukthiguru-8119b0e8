# AskMukthiGuru agent pack

A subagent-driven way to raise the project toward 10/10 without pretending agents can do the human parts.

## What is inside
- `.claude/agents/`: 13 subagents (`repo-auditor`, `safety-engineer`, `eval-engineer`, `red-team-reviewer`, `grounding-engineer`, `retrieval-quality-engineer`, `frontend-engineer`, `practice-engineer`, `privacy-engineer`, `rights-registrar`, `platform-engineer`, `docs-writer`, `independent-reviewer`).
- `docs/agent/`: `NON_NEGOTIABLES.md`, `GATES.md`, `SCORECARD.md`, `RETRIEVAL_QUALITY.md` (LightRAG/Qdrant/ontology/answer-quality/ingestion standard).
- `ORCHESTRATOR_PROMPT.md`: the main prompt.
- `PHASE_PROMPTS.md`: phase prompts P1 to P10 and loops L1 to L7.
- `.claude/settings.snippet.json`: suggested deny rules and a subagent depth limit. Merge it into your own settings after review.

## Install
1. Unzip at your repo root so `.claude/agents/` and `docs/agent/` land in place.
2. Merge `.claude/settings.snippet.json` into `.claude/settings.json` after reviewing it. It blocks pushes, hard resets, history rewriting and `rm -rf` for the whole session, and disables nested subagents.
3. Start Claude Code in the repo. Subagent files are detected automatically; if you add the first `.claude/agents/` directory during a session, restart. In current versions `/agents` no longer opens a creation wizard; edit the files directly or ask Claude.
4. Paste `ORCHESTRATOR_PROMPT.md`. Approve the plan (Gate G0). Then paste one phase prompt at a time.

## How it works
- Only the orchestrator delegates; subagents cannot spawn subagents.
- Subagents start fresh, so every delegation is a self-contained brief.
- Writers run in isolated git worktrees on `agent/<area>/<task>` branches. Nothing merges without you.
- `independent-reviewer` gates every branch. Humans sign the gates in `GATES.md`.

## What agents cannot do
Rights approvals, clinician sign-off, helpline verification, a human red-team, real users, a funding decision and organizational endorsement. Those are in `SCORECARD.md` as "Only humans can do". With agents alone, a realistic estimate is about 6 to 6.5 overall.

## Model strategy: mostly Sonnet, Opus for two roles

11 of 13 subagents run on Sonnet. Only `red-team-reviewer` (needs adversarial creativity to find failure modes) and `independent-reviewer` (the final gate before anything is marked ready to merge) run on Opus. `safety-engineer` runs on Sonnet — the real safety backstop is the human clinician sign-off at Gate G1, not which model wrote the code, and `independent-reviewer` (Opus) plus `red-team-reviewer` (Opus) both check its output before anything reaches that gate.

`.claude/settings.snippet.json` sets the main session to Sonnet with extended thinking on (`alwaysThinkingEnabled: true`, a 32k thinking budget). Extended thinking is a session-level setting — Claude Code does not currently expose a separate "reasoning effort" per subagent, so this applies to the whole session including subagents that inherit it.

**Known risk:** subagent model routing (the `model:` field, per-call overrides, the env var) has open reports of not reliably working — a subagent can silently run on the parent session's model instead of the one specified. Check Claude Code's usage/cost breakdown by model after your first few tasks to confirm Sonnet is actually taking the bulk of the work; if it isn't, switch the main session model manually for the Opus-tier tasks instead of trusting the subagent file.

Want it cheaper still? Tell the orchestrator to also route `red-team-reviewer` to Sonnet, keeping only `independent-reviewer` on Opus as your literal "final review."

## Review before use
Read every subagent file. They are prompts, not guarantees. Keep permission prompts on for writer subagents until you trust the workflow.
