# First-Person v5 Serving Path Review

## Executive finding

The serving route is deliberately conservative and has strong local integrity behavior. The API performs safety pre-emption, embedding, dedicated retrieval, pipeline execution, optional translation glosses, and response validation. The route is not yet a calibrated production answer system because the live profile is absent, tenant/guru boundaries are incomplete, and promotion/rollback is collection-name based.

## End-to-end path

1. `backend/app/api/first_person.py:query_first_person_teaching()` checks `first_person_route_enabled` and `first_person_mode`.
2. `_english_query()` translates for retrieval while preserving the raw query for safety.
3. `container.embedding.encode_single_full_async()` creates dense/sparse vectors.
4. `_pipeline()` creates a cached process-local `FirstPersonPipeline` and optional reranker adapter.
5. `backend/services/first_person_pipeline.py:execute()` runs distress checks, exact cache lookup, hybrid retrieval, integrity gates, decision logic, citation formatting, and cache population.
6. `backend/services/first_person_store.py` performs named dense/sparse Qdrant retrieval and one-clip-per-video deduplication.
7. Non-English requests receive `translated_text` glosses while `verbatim_text` remains unchanged.
8. `src/components/chat/CitationCard.tsx` handles timestamp playback and speaker display.

## Correctness strengths

- Crisis pre-emption runs before retrieval and returns helplines with no citations.
- Exact cache is used instead of semantic cache for the first-person path.
- Cached citations are revalidated for hash, speaker, an- Cached citations are revalidated for hash, speaker, an- Cached citations are revalidapeakers, artifact detection, and trailing conjunctions.
- The API does not expose raw pipeline exceptions.
- Store IDs are deterministic UUIDv5 values.
- The 85-test Docker suite covers - The 85-test Docker suite covers - The 85-test Docker suite covers - The 85-test Docker suite covers - The 85-test Docker suite covers - The 85-test Docker suite covers - The 85-test Dockerty in the live container. `backend/services/first_person_pipeline.py` therefore loads no profile and documents that non-empty answers are `weak_match`. A healthy route and passing unit tests do not prove direct-answer precision or coverage.

**Remediation:** require a profile tied to collection/build ID, encoder/reranker hashes, dataset hash, fitted threshold, sample count, and one-sided risk bound. Refuse direct-answer mode when the profile is absent or mismatched.

### Retrieval and relevance

The route performs hybrid retrieval and optional reranking, but the current live probes returned abstain/weak-match for ordinary topical queries. The reconciliation notes report top-1 scores around 0.4 on the bake-off and warn that v4/v5 vector reproducibility is unresolved.

**Remediation:** use a frozen embedding/runtime manifest; report retrieval recall@k and MRR separately from direct-answer precision; add per-guru, language, topic-density, and no-answer slices.

### Tenant/guru isolation

The request accepts `teacher_id`, and the store supports teacher payloads, but the contract is not a general `guru_id` isolation layer. There is no demonstrated mandatory caller-independent tenant filter on every cache/search path. `FIRST_PERSON_COLLECTION` is configuration-selected, and no aliases exist.

**Remediation:** derive a server-side policy object from authenticated tenant/guru context. Require `guru_id`, `rights_cleared`, `first_person_eligible`, policy version, and active build in every Qdrant filter. Include them in cache keys. Add cross-guru leak probes under concurrency.

### Cache and concurrency

`_pipeline` is process-local and lru-cached. The reranker adapter schedules work back onto the request loop from a worker thread with a 5-second timeout. This is workable for one process but requires load tests for multiple workers, cancellation, thread starvation, and cache coherence after collection promotion.

Redis exact-cache entries have a 24-hour TTL and point-servability checks, but revocatioRedis exact-cache entries have a 24-hour TTL and point-servability checks, but revocatioRedis exact-cache entries have a 24-hour TTL and point-servability checks, but revocatioRedis exact-cache entries have a 24-hour TTL and point-servability checks, but revocatioRedis exact-cache entries have a 24-houry-sensitive and require human/clinical review. Translation timeout falls back to raw multilingual embedding, which is safe but may reduce retrieval quality.

**Remediation:** maintain a native-speaker/clinician-reviewed crisis set, require zero unsafe downgrade errors, and expose safety decision telemetry without logging user text.

### Citation/rendering

Backend citations preserve exact text and timestamps. Frontend citation-contract tests pass, but the build emits Radix accessibility warnings for missing dialog titles/descriptions. Speaker naming must remain conditional on verified speaker status; current payload labels alone should not imply voice verification.

### Operational behavior

Live health reports dependencies healthy, but health does not test calibrated profile validity, active collection/alias integrity, rights policy, or retrieval quality. `IS_PRODUCTION=false` and `FIRST_PERSON_SERVE_UNREGISTERED=true` are active locally.

## Recommended serving contract

```text
Request -> authenticated guru policy -> crisis check -> exact cache
-> hybrid retrieval with mandatory guru/rights/build filter
-> rerank -> calibrated decision
-> exact substring/hash/speaker/timestamp validation
-> response + audit event
```

Every response should contain a non-user-visible trace with request ID, guru ID, build ID, policy version, retrieval candidate IDs, gate results, decision, latency, and cache status.

## Release gates

- Valid calibration profile present and bound to active build.
- No unsafe runtime flags.
- Alias points to immutable validated collection.
- Zero cross-guru leakage under deterministic and load tests.
- 100% hash/citation/timestamp checks on gold/adversarial sets.
- Crisis and rights revocation tests pass.
- P95/P99 latency and timeout SLOs pass under expected concurrency.

## Production gate addendum

The internal design review (`docs/agent/research/FIRST_PERSON_DESIGN_REVIEW_2026-09-27.md`) confirms that v5 ranking is hybrid RRF but confidence is a separately recomputed raw dense cosine; the route currently has no reranker; `question_dense` is absent on all 260 v5 points; and hub-like clips recur for unrelated, multilingual, and gibberish queries. Therefore the current threshold cannot support a world-class coverage/precision claim.

The release gate must require a calibrated score that includes reranker score, dense/sparse evidence, top-1/top-2 margin, language, speaker/dispute status, and build/model lineage. Until human-gold calibration exists, the only safe production label is related/abstained, never direct answer.
