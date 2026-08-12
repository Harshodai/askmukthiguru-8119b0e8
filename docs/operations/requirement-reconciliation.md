# Requirement-to-Implementation Reconciliation

## Scope

This matrix reconciles the inherited user requirements, the 2026-08-12 wide audit, and the current working tree. A feature marked **frozen** is intentionally not production-enabled. A feature marked **partial** is not a release-ready substitute for the full audit requirement.

| Requirement or audit area | Current state | Evidence in code or records | Remaining gate |
|---|---|---|---|
| Stable retrieval identity | Implemented | Deterministic document keys and UUIDv5 memory IDs; focused tests. | Real Qdrant, Neo4j, cache, and citation cross-scope tests. |
| Corpus and tenant containment | Partial | Corpus arguments and relationship provenance exist. | One mandatory `CorpusScope` contract and scoped filter proof on every RAG, graph, cache, memory, and admin path. |
| Knowledge graphs and multi-teacher growth | Frozen | New relationships carry corpus and teacher provenance. | Legacy graph quarantine, rights manifest, backfill, and cross-corpus isolation proof. |
| Ingestion correctness | Partial | Relationship provenance and a dry-run backfill tool exist. | Canonical source/version checkpoints, fail-closed ontology writes, staged cross-store release, and rollback proof. |
| Memory privacy and consent | Safely disabled | Backend and legacy frontend automatic writes default off. | One durable outbox, consent modes, deletion receipts, dedupe, and cross-store erase test. |
| Replica-safe jobs and streams | Partial and frozen | Legacy job lease and stream cancellation tests exist; Redis Streams is off. | One durable work primitive, provider idempotency, global budgets, cursor/reconnect, and two-replica chaos proof. |
| Confidence and capability truth | Partial | No-context support is reduced and UI labels evidence support. | Startup capability manifest and dependency-outage matrix that changes API/UI state. |
| Teacher voice and attribution | Partial | First person is preserved only from context and attributed in the Langhanam prompt. | Governed `TeacherProfile`, rights/source registry, and multilingual attribution benchmark. |
| Indian-language support | Partial | Hinglish/Tanglish detection and answer-language translation direction are tested. | Message-level multilingual evaluation corpus, browser validation, and latency measurement. |
| Trusted live event and booking information | Frozen | Official-domain filtering and result tags exist; search is off by default. | `LIVE_LOGISTICS` intent, typed event fields, verified-at timestamp, expiry, and official booking card. |
| Public ingress and attachments | Frozen | Runtime service-worker cache is static-only; attachments remain frozen. | Attachment quarantine, scanning, safe-view, retention, deletion, and operator controls. |
| Edge-function control plane | Partial | Source-controlled auth manifest is present. | Function inventory, provider/data-flow review, scheduled-job migration, and staging auth matrix. |
| WhatsApp | Frozen | Default 404 and disabled direct startup are tested. | Consent, private identity bridge, replay ledger, durable state, redaction, deletion, budgets, and provider replay proof. |
| Vercel and Railway deployment | Partial | Railway readiness endpoint, root-to-appuser entrypoint, and runbook exist. | Staging deploy, volume-permission proof, dependency health drill, load test, and rollback record. |
| 500 to 1,000 users and waitlist | Not proven | Initial safe one-replica configuration is documented. | Capacity plan, SLOs, cost controls, on-call and incident practice, support workflow, and public waitlist truth review. |
| Latency and TTFT | Partial | Existing cache, ONNX, and reranker work is documented. | Frozen multilingual benchmark, observed per-tier TTFT, dependency budgets, and load/soak evidence. |
| Reproducible release | Partial | Test isolation and Redis range alignment are implemented. | One lock authority, clean CI install, non-skippable integration jobs, immutable artifact/SBOM, and restore drill. |

## Release disposition

The current application is suitable only for internal engineering and supervised non-production validation. It is not cleared for a public waitlist, public live logistics, automatic memory, WhatsApp, public attachments, multi-teacher expansion, or a 500 to 1,000 user rollout. The next work must prioritise the remaining P0 proof gaps over feature activation.

## Reconciliation changes applied

The reconciliation corrected two concrete ingestion defects: playlist checkpoint lookup and persistence now use the same source key, and a Neo4j ontology transaction failure is explicit rather than being converted to a zero-write success. Playlist processing rolls back the re-indexed source and does not checkpoint it when the required graph write fails.

The reconciliation also closes the public support attachment route. The client no longer presents file upload controls, and the backend rejects all attachments before any local persistence or email forwarding. Finally, `GET /api/capabilities` now reports policy-disabled, available, and unavailable features without revealing secrets. These changes do not satisfy the still-outstanding durable outbox, cross-scope integration, multi-replica, typed live-logistics, clean-CI, or public-scale launch proofs.
