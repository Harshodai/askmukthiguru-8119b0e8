# Session coordination (shared working tree)

Several Claude sessions edit this one checkout at the same time. Every session
follows this file. Edit it only to change your own lane. Message the other
sessions when you do.

## Lanes (who may edit what)

| Lane | Owner session | Files |
|---|---|---|
| Crisis / safety | **AskMukthiGuru engineering W0–W6** | `services/serene_mind_engine.py`, `app/pipeline/stages/{distress,guardrail}_stage.py`, `guardrails/lightweight_handler.py`, `services/crisis_helplines.py`, `config/helplines.yaml` (read-only: owner-approved), `evals/`, `tests/test_{crisis*,serene_mind,self_harm*,distress*,pipeline_stages}.py` |
| First-person build + serve | **First-person production hardening plan** | `ingest/verbatim/`, `scripts/ops/*first_person*`, `services/first_person_*.py`, `services/text_quality_filter.py`, `app/api/first_person.py`, `evaluation/first_person_harness.py`, `evaluation/gold/`, `tests/test_*first_person*`, `tests/test_verbatim_*` |
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

- Branch `fix/first-person-harness-translation-crisis-2026-09-28`: `d1e9d019` → `fc100964` (B2/B4/PCS) → `c1ccd2b8` (dangling conjunction per clip) → `011fc135` (boundaries module, audit, question generator). The owner has pushed up to `d1e9d019`; the committer session's `git push` is denied by permission settings, so the owner pushes.
- Live backend: `FIRST_PERSON_COLLECTION=first_person_v2` (pinned-harness winner), running code from before the crisis lane's current edits.
- Crisis lane: escalate-only LLM + re-tier task **in progress**. Its files are uncommitted and must not be committed yet.
- First-person lane: B2 sentence snapping / B4 guard committed in `fc100964`. Next steps are that lane's call.
