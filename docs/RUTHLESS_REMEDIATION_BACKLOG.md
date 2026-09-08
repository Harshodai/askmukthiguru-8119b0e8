# AskMukthiGuru — Ruthless Remediation Backlog

> This is an implementation backlog derived from the current source architecture. It is intentionally stricter than a conventional architecture review.
>
> **Important:** repository inspection cannot prove live-system correctness. Runtime changes must be accompanied by executable tests and release-like evidence.

## 0. Stop-the-line gates

Do not declare production-ready until these are proven in a disposable release-like environment:

- Real provider round-trip succeeds.
- Streaming completes with terminal `done` and handles provider/network interruption correctly.
- Supabase RLS blocks cross-user reads/writes.
- Anonymous quota cannot be raced around.
- Qdrant index fingerprint matches the active embedding model/configuration.
- Neo4j/LightRAG graph workspace is populated, current and tenant-safe.
- Vector and graph corpus manifests agree with the intended publication version.
- Provider fallback is observable and quality-evaluated.
- Worker restart/recovery works.
- Backup/restore has been executed, not merely documented.
- Migration rollback has been executed.
- Browser E2E passes against release-like infrastructure.
- Retrieval/answer evaluation passes a held-out regression corpus.

## 1. P0 — Retrieval correctness before optimization

### 1.1 Index fingerprinting

Persist and validate, per published corpus/index:

- embedding model identifier and revision;
- dense dimension;
- pooling configuration;
- sparse encoder configuration;
- chunking version;
- metadata/filter schema version;
- RAPTOR configuration/version;
- reranker version;
- corpus/source manifest version.

Fail closed on incompatible combinations. A healthy Qdrant HTTP response is not sufficient evidence that retrieval is healthy.

### 1.2 Vector/graph publication consistency

Introduce a publication manifest that identifies the exact corpus version represented in Qdrant and Neo4j/LightRAG. Publication must be atomic from the application's perspective: expose only a fully validated version.

Detect:

- missing vector records;
- missing graph entities/edges;
- stale workspaces;
- partial ingestion;
- orphaned records;
- duplicate IDs;
- source-rights mismatches.

### 1.3 Retrieval regression corpus

Maintain a versioned held-out corpus covering:

- factual;
- semantic paraphrase;
- relational;
- multi-hop;
- comparative;
- multilingual;
- follow-up;
- doctrinally sensitive;
- adversarial/prompt injection;
- attachment-grounded;
- unknown-answer/abstention.

Gate changes on retrieval recall/precision, MRR/nDCG where applicable, citation correctness, groundedness, unsupported-claim rate and abstention behavior.

## 2. P0 — Security and isolation

Run adversarial integration tests against two independent users for every durable surface:

- conversations;
- messages;
- profile;
- memory;
- Second Brain;
- notebooks;
- graph-backed memory;
- Qdrant-backed memory;
- admin endpoints;
- telemetry containing user-linked data.

Test both API authorization and direct database/RLS enforcement.

Test cache keys for user/tenant isolation. Never allow a shared response cache to become an authorization boundary.

## 3. P1 — Query-adaptive retrieval

Complete and validate the existing cheap retrieval planner before adding new routing layers. Current source already has bounded 1/2-hop context-graph planning, async retrieval fan-out and graph-plan telemetry; the remaining work is evidence/latency thresholds and held-out evaluation.

### Fast lane

Use for simple/high-confidence semantic/casual questions:

`intent -> Qdrant hybrid -> answer -> lightweight deterministic checks`

Avoid unnecessary:

- graph traversal;
- HyDE;
- decomposition;
- reranking;
- CRAG loops;
- reflection;
- LLM verification.

### Relational lane

Use when entity relationships, multi-hop reasoning or graph semantics are actually required:

`intent -> Qdrant + bounded Neo4j/context graph in parallel -> bounded graph expansion -> rerank/evidence gate -> answer`

### Deep lane

Use only when complexity/confidence signals justify it:

`decompose -> hybrid retrieval -> graph reasoning -> rerank -> evidence grading -> generation -> verification`

Every lane must have explicit latency and token budgets.

## 4. P1 — Graph retrieval must earn its latency

Do not maximize graph usage for its own sake. Standard live chat currently does not invoke LightRAG (`lightrag=None`); treat LightRAG as an ingestion/administrative/operational service unless and until a separately benchmarked live-chat integration is approved.

Measure per query class:

- graph invocation rate;
- graph latency;
- nodes/edges traversed;
- useful-edge rate;
- unique evidence contribution;
- answer quality delta vs no-graph baseline;
- citation delta;
- unsupported-claim delta;
- timeout/error rate.

Make graph retrieval mandatory for query classes where it materially improves quality and optional elsewhere.

Bound traversal by:

- maximum hops;
- node/edge budget;
- result count;
- time budget;
- evidence relevance threshold.

Never permit an unbounded graph expansion to dominate p95/p99 latency.

## 5. P1 — Parallelize independent work

Audit every LangGraph node dependency.

Where operations are independent, execute concurrently:

- Qdrant retrieval and graph retrieval;
- independent query decompositions;
- independent metadata lookups;
- safe evidence preparation;
- non-dependent telemetry preparation.

Do not parallelize blindly when it increases memory pressure, provider contention or duplicate work.

Every async node must be audited for blocking CPU/network operations.

## 6. P1 — Global latency budget

Introduce a request deadline propagated through every child operation.

Conceptually:

```text
request deadline
  ├── routing budget
  ├── retrieval budget
  ├── graph budget
  ├── rerank budget
  ├── generation budget
  └── verification budget
```

When the deadline is exhausted, cancel child work rather than allowing background operations to consume capacity after the user has timed out.

Record deadline cancellations explicitly.

## 7. P1 — Reduce model calls

For every model invocation ask:

> If this call is removed, does held-out answer quality materially decrease?

Candidate reductions:

- deterministic intent routing where safe;
- deterministic evidence checks before LLM verification;
- skip reflection on high-confidence answers;
- skip CRAG rewrite loops when retrieval confidence is already high;
- avoid repeated translations;
- avoid generating summaries/titles on the critical chat path;
- batch independent model calls where provider/API semantics allow it.

No reduction should ship without quality regression evidence.

## 8. P1 — Context engineering

Before generation:

1. Deduplicate exact/near-duplicate evidence.
2. Remove low-value chunks.
3. Preserve source diversity.
4. Preserve authority hierarchy.
5. Preserve provenance IDs.
6. Compress redundant context.
7. Order evidence deliberately.
8. Enforce a context budget.

Optimize for **evidence density**, not maximum token count.

## 9. P1 — Reranker economics

Benchmark reranking against a no-rerank baseline.

Use reranking when candidate ambiguity justifies it.

Do not pay reranker latency for queries where hybrid retrieval already produces high-confidence evidence.

If a late-interaction/ColBERT path is enabled, gate it behind held-out quality + latency evidence and a rollback switch.

## 10. P1 — Cache correctness

Every answer-affecting cache key must account for all relevant dimensions, including as applicable:

- user/tenant isolation;
- corpus/index version;
- prompt version;
- model/provider;
- task/strategy;
- language;
- retrieval configuration;
- personalization state;
- safety policy version.

Never trade correctness for a higher cache hit rate.

Track separately:

- true response-cache hits;
- request coalescing hits;
- retrieval-cache hits;
- embedding-cache hits.

Do not label coalescing as a response cache hit.

## 11. P1 — LLM fallback quality

For every fallback event capture:

- primary provider/model;
- fallback provider/model;
- failure reason;
- fallback latency;
- answer quality outcome.

Run quality evaluation separately for fallback traffic.

Availability without quality is not success.

## 12. P1 — Embedding/worker memory

Benchmark resident memory under the exact production worker topology.

Measure:

- cold-start memory;
- warmed model memory;
- per-worker duplication;
- concurrent embedding memory;
- reranker memory;
- graph client memory;
- peak memory during ingestion.

Do not scale workers horizontally until model residency and concurrency are understood.

## 13. P1 — Observability required for optimization

Every chat trace must expose node-level:

- start/end;
- duration;
- timeout;
- retry;
- fallback;
- cache state;
- candidate counts;
- graph counts;
- model/provider;
- token counts;
- quality/evaluation identifiers where available.

Minimum production SLO views:

- TTFT p50/p95/p99;
- total latency p50/p95/p99;
- retrieval latency;
- graph latency;
- reranker latency;
- generation latency;
- verification latency;
- timeout rate;
- fallback rate;
- cache hit rate;
- retrieval regression score.

## 14. P1 — Failure injection

Exercise:

- Qdrant outage;
- Neo4j outage;
- LightRAG failure;
- Redis outage;
- Supabase latency;
- provider timeout;
- provider malformed output;
- provider rate limit;
- circuit open;
- queue saturation;
- worker restart;
- SSE disconnect;
- browser refresh during streaming.

For every failure verify:

1. User-visible behavior is correct.
2. No data corruption occurs.
3. No tenant isolation boundary is weakened.
4. Recovery is automatic where intended.
5. The incident is observable.

## 15. P1 — Ingestion correctness

Treat ingestion as a transaction-like publication process.

Never publish generated artifacts before validation.

Validate:

- source rights;
- extracted text integrity;
- doctrine correction integrity;
- chunk counts;
- embedding dimensions;
- Qdrant writes;
- graph writes;
- manifest/checkpoint consistency.

A checkpoint must never be accepted as proof of success without store-state verification.

## 16. P2 — Simplify the architecture

Continuously identify:

- duplicate services;
- compatibility facades;
- dead providers;
- historical code paths;
- redundant caches;
- unused feature flags;
- duplicate configuration systems;
- unnecessary model calls;
- libraries that provide overlapping functionality.

Do not remove anything solely because it looks complicated. Remove it only when source analysis and tests demonstrate that it is unused or redundant.

## 17. Required before/after benchmark

For every performance change capture:

| Metric | Before | After | Delta | Quality impact |
|---|---:|---:|---:|---|
| TTFT p50 | | | | |
| TTFT p95 | | | | |
| E2E p50 | | | | |
| E2E p95 | | | | |
| E2E p99 | | | | |
| Retrieval p95 | | | | |
| Graph p95 | | | | |
| Generation p95 | | | | |
| Tokens/request | | | | |
| Cost/request | | | | |
| Retrieval recall | | | | |
| Citation correctness | | | | |
| Groundedness | | | | |
| Unsupported claims | | | | |
| Abstention quality | | | | |

A latency win that materially harms quality is a regression.

## 18. Definition of done

A remediation is complete only when:

- implementation exists;
- regression test exists;
- relevant benchmark exists;
- observability exists;
- failure behavior is defined;
- security/isolation impact is tested;
- documentation matches source;
- rollback is possible;
- CI passes;
- release-like validation passes where infrastructure is involved.

**Do not mark a checkbox because code was written. Mark it only because evidence exists.**
