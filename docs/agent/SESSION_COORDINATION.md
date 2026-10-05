# Session coordination (shared working tree)

Several Claude sessions edit this one checkout at the same time. Every session
follows this file. Edit it only to change your own lane. Message the other
sessions when you do.

## Lanes (who may edit what)

| Lane | Owner session | Files |
|---|---|---|
| Crisis / safety | **AskMukthiGuru engineering W0–W6** | `services/serene_mind_engine.py`, `app/pipeline/stages/{distress,guardrail}_stage.py`, `guardrails/lightweight_handler.py`, `services/crisis_helplines.py`, `config/helplines.yaml` (read-only: owner-approved), `evals/`, `tests/test_{crisis*,serene_mind,self_harm*,distress*,pipeline_stages}.py` |
| First-person data (boundaries, speakers, questions, Qdrant shadow builds) | **First-person production hardening plan** | `ingest/verbatim/`, `scripts/ops/{audit_first_person_boundaries,measure_first_person_boundary_repair,generate_first_person_questions}.py`, `services/text_quality_filter.py`, `evaluation/gold/`, `tests/test_verbatim_*`, `tests/test_{audit,generate}_first_person_*`; the only lane that runs `build_first_person_index --apply` (after owner approval) |
| Commits + handoff docs | **Session handoff and warning remediation** | git writes, `lessons.md`, `docs/agent/SESSION_HANDOFF_*` |

Anything not listed: announce the edit to the other sessions first.

## Rules

1. **Stay in your lane.** Re-read a file before every edit. Never revert, reformat or "fix" another lane's code. Report the failure to its owner, with the exact lines.
2. **One committer.** Only the handoff session runs git writes. A lane owner says "done", with the full backend suite count + `evals/run_safety_scenarios.py` result + an exact file list. The committer then commits only those files. Never commit another lane's mid-edit files.
3. **Shared runtime.** `mukthiguru-backend` bind-mounts `app/`, `services/`, `guardrails/`, `rag/` from this tree, so a restart loads whatever is on disk — including another lane's mid-edit files. Before restarting, message the other sessions and say why; don't restart while any lane has mid-edit code in those directories. Never restart during another session's live eval. Anon `/api/chat` probes are rate-limited: pace them ≥12 s.
4. **Qdrant.** Only the first-person lane writes, and only new shadow collections after a dry run plus owner approval. No aliases, no `FIRST_PERSON_COLLECTION` change, no deletes.
5. **Never edit `.env`** without the owner's explicit approval, and announce it when done (the 2026-09-28 translation change set a precedent; don't repeat it silently).
6. **Measurements.** Put numbers in `docs/agent/EXPERIMENT_LEDGER_2026-09-27.md` with the command that produced them. A number from a mid-edit tree is not a result.

## Current state (update when it changes)

**Re-dated 2026-10-03 (Q6 / audit G.4 #3).** This block had gone stale (it still said `first_person_v2`), and `docs/agent/*` "current state" blocks are what other sessions read first. It is now pointer-only — deep truth lives in `.claude/tasks/abstention_gate_and_index_hygiene_plan.md` and `HANDOFF_2026_10_03.md`; do not treat counts here as measured unless the command is shown.

- **Branch:** `fix/first-person-harness-translation-crisis-2026-09-28` (working tree dirty, 1400+ pre-existing uncommitted files; owner does the pushes — committer `git push` is permission-denied).
- **First-person pipeline (mechanism only; no final numbers yet):**
  - Phase 1 index hygiene **done** — stale-embedding re-key/re-embed + `is_verbatim`/`rights_cleared` indexes + post-write vector validation (plan execution log, 2026-09-30).
  - Phase 2 answerability gate **landed** — `first_person_answerability_check_enabled` (code default `True`), single wire point in `FirstPersonPipeline.execute()` immediately before `is_direct=True`; the LLM classifies the *question only* as exact `YES`/`NO`, and `NO`/indeterminate/timeout all fall through to honest abstention with zero citations (fail toward honesty). Validation runs are **in flight** — leak/false-refusal numbers are not final; do not quote them.
  - Phase 3 quote gate **32/32 verbatim, 0 not_found** after the transcript-projection fallback fix (`HANDOFF_2026_10_03.md` §F).
  - Chat bridge kill-switch **OFF**: `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` in root `.env`; re-enable only after owner sees final Phase 2 validation numbers.
- **Live collection:** `FIRST_PERSON_COLLECTION=first_person_v7` (root `.env`), **144 points** measured `curl -s localhost:6333/collections/first_person_v7` on 2026-10-03 — pending mass ingest (target ~2,500 clips / 634 rights-cleared videos per `HANDOFF_2026_10_03.md`, owner fork pending).
- **Pre-2026-10-03 bullets (v2 "pinned-harness winner", crisis-lane uncommitted state, commit chain) are superseded** — recoverable from git history and `handoff.md`.
