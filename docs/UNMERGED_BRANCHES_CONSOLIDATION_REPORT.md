# Consolidated Unmerged Branches Report
**Base Commit**: `6bbf7802` (`main`)
**Audit Disposition**: The 18 historical branches were audited against `main`. All functional capabilities (WhatsApp bot, crisis helplines, translations, ops scripts, and quote attribution tools) were already previously landed on `main` via squashed PRs (#45, #50, #53, #59). PR #75 was closed without merging to prevent merge collisions, and the valuable research notes (now at `docs/research/notes/`) were brought directly into `main`.

---

## 1. Overview

This branch combines the clean production codebase of `main` with the full history and content of all 18 previously unmerged branches. Every commit, feature, script, research note, and test fixture from those branches is now reachable and preserved in this single branch.

---

## 2. Integrated Branches Summary

| # | Branch Name | Original Commit | Description of Incorporated Work |
|---|---|---|---|
| 1 | `claude/fix-quote-audio-fidelity-ixdgsu` | `b50ad438` | Hardened quote verification for renderer gate; verifies rendered quotes against stored sources. |
| 2 | `fix/redaction-verification-details` | `8f540f5d` | Redaction and verification details in chat responses. |
| 3 | `fix/npm-audit-prod-build-plugin-classification` | `9fb265e7` | Dependency reclassification (`tailwindcss-animate` moved to devDependencies). |
| 4 | `claude/dep-security-fixes` | `86a8575a` | Dependency check workflow updates and package-lock reconciliations. |
| 5 | `test-pr50-rebase` | `477a9f44` | Crisis helpline numbers alignment (AASRA 022-27546669, call-verified lines). |
| 6 | `fix/prelaunch-gate-local-supabase` | `7e0ecf52` | Gitleaks scanning configuration and local Supabase prelaunch gate tests. |
| 7 | `claude/project-thread-nqifjf` | `52ec1dd9` | Helpline entry-count guard alignment (14 entries following KIRAN removal). |
| 8 | `claude/project-thread-d0vgrx` | `fa308b4a` | Provider outage `system_error` alignment; Guru registry and mode tests. |
| 9 | `claude/project-thread-tucvr3` | `e653c59e` | Faculty access gate, head fragment repair previews, OpenRouter monthly limit. |
| 10 | `fix/go-report-work` | `930632a1` | Complete WhatsApp Bot integration (`whatsapp_bot/`), `quarantine_promise_clips.py`, `repair_first_person_head_fragments.py`, clinical safety dossier. |
| 11 | `feat/speaker-attribution-verbatim` | `7698d92b` | Speaker attribution pipeline research (`research_notes/`), pilot scripts (`docs/attribution/pilot/`), diarization models. |
| 12 | `feat/first-person-verbatim` | `a8ae5e4e` | Verbatim quote baseline handoff, evaluation harness, silver sheets. |
| 13 | `feat/ruthless-e2e-ux-hardening-2026-09-local` | `071e4d04` | Wisdom Reflection practice localizations, E2E regression sweeps. |
| 14 | `fix/first-person-harness-translation-crisis-2026-09-28` | `bd41c948` | OKF graduation, entity linking pre-pass hooks, translation stability probes. |
| 15 | `snapshot/mac-local-2026-10-06` | `06169ed4` | Mac local working tree snapshot from Oct 6 (`audit_results.json`, `audit_script.py`, cleaner utilities). |
| 16 | `snapshot/mac-local-2026-10-07` | `67b8b5d7` | Mac local working tree snapshot from Oct 7. |
| 17 | `snapshot/mac-local-2026-10-06-curated` | `f0ff8b59` | Curated Mac-local work: offline tokenizer loading, boundary tests, snapshot manager utilities. |
| 18 | `fix/first-person-only-quality-2026-10-11` | `c9fc8ad2` | Sound first-person serving quality gates. |
| 19 | `fix/i18n-sync-stale-keys` | `2237af69` | Synced 15 keys across all 13 supported Indic locales. |

---

## 3. Notable Artifacts & Directories Brought Together

1. **`whatsapp_bot/`**: Full WhatsApp companion integration (`wa_bot.py`, Dockerfile, environment configurations).
2. **`scripts/ops/quarantine_promise_clips.py`**: Identifies and quarantines clips promising specific future outcomes.
3. **`scripts/ops/repair_first_person_head_fragments.py`**: Heuristic repair for fragmentary clip openings.
4. **`docs/research/notes/Speaker attribution pipeline for teachings/`**: Detailed research on diarization, calibration certification, word boundary quoting, and production efficiency.
   *Path correction (2026-10-22):* these notes were landed at `research_notes/` and have since been relocated to `docs/research/notes/`, per the repository-consolidation plan. The root-level `research_notes/` copy was removed as a byte-identical duplicate.
5. **`docs/attribution/pilot/`**: Prototype scripts for speaker enrollment, leave-one-out cross-validation, and embedding scanning.
6. **`audit_results.json` & `audit_script.py`**: Historical forensic audit logs of corpus and clip boundaries.

---

## 4. How to Inspect & Compare Against Main

To see the full diff of everything added/changed compared to `main`:
```bash
git diff --stat main..consolidated/unmerged-branches
```

To view changes in a specific subsystem:
```bash
# WhatsApp bot
git diff main..consolidated/unmerged-branches -- whatsapp_bot/

# Ops scripts
git diff main..consolidated/unmerged-branches -- scripts/ops/

# Research notes
git diff main..consolidated/unmerged-branches -- research_notes/
```
