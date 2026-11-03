# ADR 0001: Publication Model — Release Table vs Alias Swap & Shadow Mode Rollout

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Data Engineering, Architecture Governance, Security Team
- **Consulted:** Master Plan DE-0.1, DE-0.3, DE-0.4, D1

---

## Context
Prior to this architecture, content ingestion directly wrote vector points into production collections in Qdrant with no logical release boundaries. Once a chunk was embedded, it became immediately retrievable. Removing defective doctrine or revoking copyright-withdrawn material required either manual point deletion across multiple stores or a costly, unversioned collection re-creation.

Two distinct publication paradigms were considered:
1. **Whole-Index Alias Swapping:** Ingesting everything into a new collection (`corpus_vN`) and flipping a Qdrant alias.
2. **Fine-Grained Relational Publication Registry:** Tracking publication states per source in a Supabase table (`source_releases`) and filtering retrieval queries at serve time.

## Decision
We adopt a **hybrid two-tier publication model**:

1. **Macro Lifecycle (Physical Indexing):**
   - Major schema shifts, embedding model upgrades, or re-chunking use versioned collections (`spiritual_wisdom_contextual_vN`) and atomic Qdrant alias swapping (`QdrantAliasManager`).
2. **Micro Lifecycle (Granular Publication & Governance — D1):**
   - A relational registry table `public.source_releases` in Supabase serves as the single source of truth for whether a source URL and version is `active`, `superseded`, `quarantined`, or `revoked`.
   - Vector points carry immutable `source_release_version` and `source_url` attributes.
   - Retrieval queries join or filter against approved source releases.
3. **Shadow-Mode Rollout (DE-0.4):**
   - The release filter is the tri-state setting `release_filter_mode` (`off` | `shadow` | `enforce`, default `off`; `RELEASE_FILTER_MODE`). `corpus_publication_enforcement_enabled` is a different gate (manifest presence at startup/ingest) and is **not** the shadow/enforce switch.
   - In `shadow`, points that would have been excluded are logged and metered via Prometheus (`retrieval_release_shadow_exclusions_total`), proving no unexpected retrieval dropouts before moving to `enforce`.
   - In `enforce`, a point is served only if its `source_release_version` equals the source's active release. Missing or non-numeric versions are dropped (fail closed), and an unreadable release registry makes retrieval abstain rather than guess a version.

## Consequences
- **Positive:** Granular instant rollback of defective talks without touching Qdrant; zero downtime index migrations; comprehensive auditability of what was published when.
- **Negative:** Requires vector payloads to be stamped with release versions; requires low-latency caching of active source release lists during query processing.
- **Mitigation:** Active release IDs/versions are cached in Redis with a 5-minute TTL.
