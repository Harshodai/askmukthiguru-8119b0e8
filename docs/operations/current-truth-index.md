# Current truth index

**Reviewed:** 2026-11-25

This page is the short navigation layer for release decisions. It does not replace the
binding repository instructions, source configuration, evidence manifests, or human review
packets. Historical reports remain historical; they must not be read as current production
proof.

## Current release posture

**Production is NO-GO.** Code changes can improve controls and make evidence reproducible,
but they cannot manufacture rights approval, speaker certification, clinical review, native-
speaker review, authorized provider spend, hosted operational evidence, or deployment approval.
First-person public release and first-person generation fallback remain disabled.

## What is agent-verifiable in this repository

| Control | Current authority | What a code/CI run can establish |
|---|---|---|
| Script-tree parity | `AGENTS.md`, `backend/tests/test_repo_layout.py` | Shared root/backend scripts are byte-identical, except the declared RAGAS exception. |
| Release fingerprint integrity | `scripts/ops/collection_fingerprint.py`, `scripts/ops/graded_registered_report.py` | A run has a complete collection name, non-negative point count, SHA-256 id-set digest, matching active collection, and no conflicting restamp. |
| Prompt-data isolation | `backend/services/untrusted.py` and focused prompt tests | Attachment, retrieved, memory, summary, and research fields are fenced as data and cannot close their own fence. |
| Readiness scope semantics | `scripts/ops/predeployment_checklist.py` | A staging pass cannot return a production-scoped success without explicit owner authorization. |
| Memory-plane lifecycle inventory | [`docs/operations/memory-plane-inventory.json`](memory-plane-inventory.json), `backend/tasks/retention_tasks.py` | Scheduled retention names every purge surface, its window, executor, result key, and protected ledger; it does not prove a hosted run occurred. |
| Safety and serving contracts | Focused backend tests and startup gates | Deterministic safety, rights, speaker, integrity, relevance, and serving-contract behavior remains fail-closed in the tested paths. |

## What remains open and cannot be closed by code alone

- Rights/licensing approval and the signed content-rights decision.
- Human speaker-attribution certification, native-speaker review, clinician review, and helpline verification.
- Gold labels, calibration decisions, independent answer review, and unsigned human-gate packets.
- Authorized provider credentials and a valid, graded, collection-fingerprinted release run.
- Hosted staging/production smoke, load, soak, degradation-recovery, backup-restore, and alert-delivery evidence.
- Railway promotion, alias changes, corpus writes, and production deployment approval.

## Evidence boundary

Local, mocked, offline, or dependency-limited runs are diagnostic only. They must not be
reported as hosted or production evidence. A release report is valid only when its manifest,
input hashes, evaluator revision, collection fingerprint, grades, and validity state are
joined immutably and the applicable human and operational gates are signed off.

Use the authoritative runbooks for action:

- [Release evidence pack](release-evidence-pack.md)
- [Production deployment runbook](production-deployment-runbook.md)
- [Human-gate packets](../reviews/2026-11-14-human-gates/README.md)
- [Content rights register](../rights/CONTENT-RIGHTS.md)
- [First-person public-release status](../FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md)
