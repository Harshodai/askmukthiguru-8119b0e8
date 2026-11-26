# Handoff 2026-11-26: PR queue cleared, CI gates live, evidence and consent hardening

Read `docs/architecture/2026-11-26-verified-audit-findings.md` (sections 7 to 11) for the finding-by-finding status and
`lessons.md` (top section) for the rules learned. This file is the short "where things stand".

## What is on `main` (merged this session)
PRs 110, 111, 112, 113 (reviewed, two fixed), 114 (CI gates now run on PRs and main), 117 (evidence platform, editorial
workbench, bereavement SEVERE-downgrade removal), 118 (v13 gap clips fail closed), 119 (ruff backlog and formatter, CI-pinned ruff 0.15.13).
PR 120 merged at `21202303f` (head `0f8731efa`): Node 24 in CI and both frontend Dockerfiles (root
`frontend.Dockerfile` plus `frontend/Dockerfile`), editorial hardening (server-side evidence, persistence flag,
author/approver separation), consent-gated seeker comprehension (flag), registry-based teacher aliases, test fixes, this
documentation, the recorded Memgraph build manifest, and the trailing-newline fix for
`backend/config/teaching_unit_graph_manifest.json` (its writer now emits one too).

## CI facts to know
- `lint-test.yml` runs on PRs and main pushes. Backend job order: ruff check, `ruff format --check` (ruff **0.15.13**; local venvs have newer versions that format differently; a 0.15.13 binary is in the uv cache), Bandit, pytest with a coverage floor, safety scenarios, quote verification. Ruff CI runs with `working-directory: backend`; repo-root ruff errors are pre-existing debt not checked by CI.
- `Validate Pre-commit Hooks` checks `end-of-file-fixer` (e.g., generated JSON manifests must end with a trailing newline).
- Guards that fail a PR: `guru_literal_guard.py` (no teacher-name literals in runtime code; use `services/guru_registry.py`), exception ratchet (ceiling now **759**, raised from 754 on 2026-11-26 with the owner's approval; new code catches specific types), pipeline order guard, migration lint.
- Formatting can break source-text assertions and move `# noqa` comments: re-run ruff check after format. Keep `scripts/` mirrors byte-identical to `backend/scripts/` (`tests/test_repo_layout.py`).
- Node: CI and the frontend image use 24. Local tooling that uses tree-sitter/WASM stays on Node 22; no CI job uses it.

## Flags and migrations (nothing flipped, nothing applied)
- `editorial_persistence_enabled` (default false) needs migration `supabase/migrations/20261126120000_editorial_persistence.sql`.
- `seeker_comprehension_recovery_enabled` (default false) needs migration `20261126000100_seeker_comprehension_consent_binding.sql`; the earlier `20261126000000_teaching_editorial_intelligence.sql` must exist first. Revocation tolerates a missing signals table.
- `FIRST_PERSON_LLM_FALLBACK_ENABLED` stays false (binding owner directive). `FIRST_PERSON_CONTEXT_USE_SPARSE` stays false (measured, no human labels).

## Data state (local stack)
- `first_person_v13_shadow`: 4,730 points; 13 `passage` points demoted to `pending_voice_check`; snapshot `first_person_v13_shadow-1111874297854021-2026-11-26-05-52-22-7.snapshot` is the rollback.
- Memgraph TU layer rebuilt: 2,999 of 2,999 spans resolve; snapshot copy in `~/mukthiguru_attribution_data/memgraph_snapshot_pre_tu_rebuild_20261126/` (restore verified in a scratch Memgraph with `RECOVER SNAPSHOT`). Build with the `backend/scripts/ops` copy of `build_teaching_unit_graph.py` (the root copy resolves paths wrongly); the builder only MERGEs, so delete `TU*` labels first with the `drop_projection` query.
- Railway untouched and still stopped. The running Memgraph image is `memgraph-mage:latest`, not the 2.20.1 pinned in docs.

## Known gaps, none blocking
- Editorial: Supabase adapter errors other than a missing client currently surface as 500, not 503 (being fixed in an uncommitted follow-up); `service_role` can still edit the audit table. The migrations were applied to a scratch Supabase Postgres and their policies tested (audit doc section 10); the adapter's HTTP path and a real Supabase project were not (real-Supabase apply deferred by owner: "ignore supabase").
- Consent: decided to keep 503 on revocation when Redis cache invalidation fails (revocation receipt is persisted first so retry is safe, and 200 would leave `mukthiguru:cache:*` stale). Correction: `container.redis_client` is never assigned in production (only in one test), so the 503 comes from exact-cache invalidation at `backend/app/api/memory.py:1018`, not `services/seeker/consent.py`. Two consent lookups per turn when a flag is on; seen-clip tenant (`ctx.tenant_id or "default"`) can differ from `TenantContext`.
- Evidence: an unreachable Qdrant raises `ResponseHandlingException` and escapes as HTTP 500 instead of 503 (being fixed in an uncommitted follow-up); the claim verifier also matches quotes against `surrounding_context`, which may lie outside the speaker-verified span (pre-existing).
- Traced and closed: serving never reads `passage` records; the 13 demotions changed no served answer.

## Human-only gates (still pending; agents never fake-close them)
Clinician and native-speaker review of distress detection (first-turn paraphrases are still rated NONE), 299-pair gold labels (the
`evals/gold_set_v1` annotator CSVs are template-filled, not human labels), faculty invitations, speaker gate sign-off, rights sign-off,
helpline confirmation calls.

## End of 2026-11-26 (later session): verification, cleanup, follow-ups
- **Verification (local runs on merged head `0f8731efa`):**
  - Backend pytest: **15,648 passed, 65 skipped, 2 deselected, 1 xfailed, 0 failed** (333 s).
  - Frontend: `npm run lint` 0 errors (69 warnings), `npm run typecheck` 0 errors, `npx vitest run` 213 files / **1,331 passed, 6 skipped, 0 failed**.
  - CI-equivalent `ruff check .` and `ruff format --check .` from `backend/`: clean (1,938 files formatted).
  - `fetch_by_ids` verified read-only against live local Qdrant (`first_person_v13_shadow`, 4,730 points).
- **Cleanup:** removed and pruned worktrees `wcomb`, `wnode`, and three `agent-*` worktrees; deleted their five merged branches. Scratch containers `scratch-pg`/`scratch-mg` were already gone. Untouched: the two other sessions' worktrees under `/private/tmp/askmukthiguru-*`.
- **Backups:** the two files that blocked the `main` pull (local manifest change and stale untracked copy of this handoff) were backed up byte-for-byte to `<scratchpad>/pre_pull_backup_20261126/` before removal.
- **Uncommitted follow-ups:** unreachable-Qdrant 503 handling and Supabase adapter 503 error mapping (being fixed); `src/integrations/supabase/client.ts` (`VITE_ALLOWED_EMAIL_DOMAINS` override) also remains uncommitted in the working tree.
