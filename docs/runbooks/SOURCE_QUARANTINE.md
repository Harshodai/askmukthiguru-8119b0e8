# Source Quarantine and Legacy-Vector Cleanup

## Incident

On 2026-08-21, a production generic-practice request exposed `The_Four_Sacred_Secrets.pdf` in the provenance evidence returned from the legacy Qdrant collection. The repository history had already been scrubbed of that source, but stale vector payloads remained in the serving collection.

This is a **rights and retrieval-boundary incident**. A source that is not currently approved must not reach user-facing context, citations, provenance, GraphRAG summaries, or generation merely because a legacy vector point exists.

## Immediate serving control

Commit `8971162` adds `backend/services/qdrant/source_policy.py`. The policy matches only the quarantined source identity and is applied in two places:

1. `QdrantSearcher` drops the source before converting Qdrant payloads into retrieval documents.
2. `retrieve_documents` applies a final pass after vector, fallback, GraphRAG, OKF, and web documents are merged.

The second pass is required because not every candidate channel originates in Qdrant. The policy is fail-closed for the named source and does not modify `scripts/ingestion/corpus/`.

## Permanent cleanup procedure

A separate maintenance operation must enumerate the exact Qdrant point IDs whose payload `source_url`, `title`, or source identity matches the quarantine identity, export a bounded manifest, verify its count and hashes, and delete only those IDs with an audited operation. The operation must be tenant/corpus scoped, resumable, dry-run capable, and protected by a maintenance lock. Do not use `FLUSHALL`, delete the whole collection, or edit immutable corpus packages as a substitute.

After cleanup, run a bounded Qdrant verification that searches representative queries and asserts no returned payload or provenance item contains the quarantined identity. Keep the serving denylist permanently unless a rights owner explicitly re-authorizes the source through the governed release registry.

## Verification contract

A production release is not rights-clean until all of the following hold:

- `/api/health` is ready and healthy.
- Direct and fallback vector retrieval exclude the quarantined identity.
- GraphRAG and provenance manifests contain no quarantined source.
- Generic, comparative, and multilingual smoke tests return no quarantined citation.
- The exact cache namespace has been invalidated after rollout; global Redis eviction is forbidden.
