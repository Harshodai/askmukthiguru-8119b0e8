# Handoff 2026-11-26: PR queue cleared, CI gates live, evidence and consent hardening

Read `docs/architecture/2026-11-26-verified-audit-findings.md` (sections 7 to 9) for the finding-by-finding status and
`lessons.md` (top section) for the rules learned. This file is the short "where things stand".

## What is on `main` (merged this session)
PRs 110, 111, 112, 113 (reviewed, two fixed), 114 (CI gates now run on PRs and main), 117 (evidence platform, editorial
workbench, bereavement SEVERE-downgrade removal), 118 (v13 gap clips fail closed), 119 (ruff backlog and formatter, CI-pinned ruff 0.15.13).
PR 120 carries the rest: Node 24 in CI and `frontend/Dockerfile`, editorial hardening (server-side evidence, persistence flag,
author/approver separation), consent-gated seeker comprehension (flag), registry-based teacher aliases, test fixes, this documentation,
and the recorded Memgraph build manifest.

## CI facts to know
- `lint-test.yml` runs on PRs and main pushes. Backend job order: ruff check, `ruff format --check` (ruff **0.15.13**; local venvs have newer versions that format differently; a 0.15.13 binary is in the uv cache), Bandit, pytest with a coverage floor, safety scenarios, quote verification.
- Guards that fail a PR: `guru_literal_guard.py` (no teacher-name literals in runtime code; use `services/guru_registry.py`), exception ratchet (ceiling now **759**, raised from 754 on 2026-11-26 with the owner's approval; new code catches specific types), pipeline order guard, migration lint.
- Formatting can break source-text assertions and move `# noqa` comments: re-run ruff check after format. Keep `scripts/` mirrors byte-identical to `backend/scripts/` (`tests/test_repo_layout.py`).
- Node: CI and the frontend image use 24. Local tooling that uses tree-sitter/WASM stays on Node 22; no CI job uses it.

## Flags and migrations (nothing flipped, nothing applied)
- `editorial_persistence_enabled` (default false) needs migration `supabase/migrations/20261126120000_editorial_persistence.sql`.
- `seeker_comprehension_recovery_enabled` (default false) needs migration `20261126000100_seeker_comprehension_consent_binding.sql`; the earlier `20261126000000_teaching_editorial_intelligence.sql` must exist first. Revocation tolerates a missing signals table.
- `FIRST_PERSON_LLM_FALLBACK_ENABLED` stays false (binding owner directive). `FIRST_PERSON_CONTEXT_USE_SPARSE` stays false (measured, no human labels).

## Data state (local stack)
- `first_person_v13_shadow`: 4,730 points; 13 `passage` points demoted to `pending_voice_check`; snapshot `first_person_v13_shadow-1111874297854021-2026-11-26-05-52-22-7.snapshot` is the rollback.
- Memgraph TU layer rebuilt: 2,999 of 2,999 spans resolve; snapshot copy in `~/mukthiguru_attribution_data/memgraph_snapshot_pre_tu_rebuild_20261126/` (restore untested). Build with the `backend/scripts/ops` copy of `build_teaching_unit_graph.py` (the root copy resolves paths wrongly); the builder only MERGEs, so delete `TU*` labels first with the `drop_projection` query.
- Railway untouched and still stopped. The running Memgraph image is `memgraph-mage:latest`, not the 2.20.1 pinned in docs.

## Known gaps, none blocking
- Editorial: Supabase adapter errors other than a missing client surface as 500, not 503; service_role can still edit the audit table; the adapter and both migrations have never run against a real database.
- Consent: revocation now returns 503 if Redis is configured but unreachable, even with both flags off; two consent lookups per turn when a flag is on; seen-clip tenant (`ctx.tenant_id or "default"`) can differ from `TenantContext`.
- Evidence: the claim verifier also matches quotes against `surrounding_context`, which may lie outside the speaker-verified span (pre-existing).
- Not traced: whether serving reads the 13 demoted `passage` records.

## Human-only gates (still pending; agents never fake-close them)
Clinician and native-speaker review of distress detection (first-turn paraphrases are still rated NONE), 299-pair gold labels (the
`evals/gold_set_v1` annotator CSVs are template-filled, not human labels), faculty invitations, speaker gate sign-off, rights sign-off,
helpline confirmation calls.
