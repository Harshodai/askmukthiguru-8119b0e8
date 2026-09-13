# Deep Research 1/5: Multi-Tenant Scale (teachers as tenants)

Date: 2026-09-13. Lane 1/5. Today one tenant ("sri preethaji + sri krishnaji"); future adds tenants like "sri amma bhagavan", then many users per tenant.

Verified repo paths (read 2026-09-13): `backend/services/tenant_context.py`, `backend/rag/corpus_scope.py`, `backend/rag/nodes/retrieval.py:279,307,803,873,1129`, `backend/services/qdrant/searcher.py`+`filters.py`+`multitenancy_guard.py`, `backend/app/config.py:905 default_tenant_id="oneness",897 default_corpus_id="askmukthiguru",908 require_licensed_domain_reads`, `memory/okf/{sri-preethaji/,sri-krishnaji/,shared/,staging/,compiled.json}`, `backend/services/anon_quota_{service,redis,memory,port}.py`, `backend/app/api/memory.py:345 purge`, `canonical_memory.py:export/forget`, `compliance.py:247 deletion-ticket`, `backend/domain/spiritual_ontology.py:TeacherDomain.rollout_enabled`, `app/assistant_registry.py`+`assistant_authorization.py`.

Current state: ContextVar tenant (`TenantContext.get()`, default `oneness`), soft-migration `get_tenant_collection()` for legacy tenant keeps base name. Retrieval uses `CorpusScope.to_qdrant_filter()` must `{tenant_id,corpus_id,optional teacher_id,domain_rights_status}` + Neo4j `coalesce(r.tenant_id,"oneness")=$tenant_id`. Cache keys tenant-prefixed (`mukthiguru:cache:{tenant}:`). Quota is NOT per-tenant today (global `anon_quota_messages=5/24h`). OKF already teacher-subdir (`rglob` + `_excluded_parts` keeps `staging/` out).

## 1. Qdrant isolation: payload-filter vs collection-per-tenant vs cluster-per-tenant

Qdrant official doctrine: collection-per-tenant "rarely most efficient", 1000-collection/cluster cap, each collection has HNSW/WAL/optimizer overhead. Default = single collection + payload partition (`tenant_id` keyword index with `is_tenant=true`, v1.11+, co-locates tenant vectors → sequential reads). Custom sharding = dedicated shard per large tenant. Tiered (v1.16, Dec 2025) = fallback shared shard + promoted dedicated shards, threshold ~20k points; don't exceed ~1000 dedicated shards. Indexing bottleneck fix: `m=0, payload_m=16` (per-tenant HNSW only). Sparse IDF is shard-global by default — needs explicit `idf` filter scoping. Pinecone/Weaviate/Milvus offer namespace/collection equivalents; OWASP RAG mandates pre-retrieval filtering, never post-filter.
Who uses what: 100s–1000s small tenants → payload-filter; few large/regulated → tiered/custom-shard; different embedding dim/model → collection-per-tenant only.

Recommendation: KEEP `CorpusScope.to_qdrant_filter()` payload model as primary; DO NOT adopt `get_tenant_collection() __tenant_` split for tenant 2. Reasons: dim identical (BGE-M3 1024), size similar (~89k pts), avoids migration + 2x snapshot/backup + cache-key fanout. Concrete: (a) add `is_tenant=true` keyword index on `tenant_id` (+`corpus_id`,`teacher_id`) at collection creation in `services/qdrant/indexer.py`; (b) enforce `multitenancy_guard.py` decorator on every search/upsert (fail-closed if no tenant filter); (c) create collection with `sharding_method=CUSTOM` now with single fallback shard so future promotion needs no rebuild; (d) `payload_m=16,m=0` only when indexing throughput proves bottleneck. Collection-per-tenant only as escape hatch for a different embedding model per teacher.

## 2. Neo4j multi-tenancy: labels/props vs separate DBs

Neo4j multi-DB (one DB per tenant) is Enterprise-only; Community = single DB (confirmed Issue #12920, maintainer: "no plans to move multi-DB to CE"). Community pattern = property `tenant_id` + composite index, or label-per-tenant (dynamic labels frustrate OGMs). Enterprise ADR pattern observed: Phase 1 shared-graph + strict tenant predicates + regression suite → Phase 2 graph-per-tenant on regulatory/perf triggers.

Recommendation: KEEP shared-graph + `tenant_id/corpus_id` edge properties (repo already does `coalesce(r.tenant_id)=$tenant_id` + bound params, never interpolated). Add: (a) composite range index on `(tenant_id,corpus_id,entity_id)` via offline maintenance job only — never app startup; (b) extend `to_neo4j_params` gate to 2-hop traversals; (c) separate DBs only if contract demands physical separation — requires Enterprise/Aura + per-DB backup/restore runbook.

## 3. Per-tenant corpora ingestion + per-tenant OKF bundles

Repo has per-teacher OKF dirs + `OKFStore.list_entries()` gate (type∈doctrine set, non-empty source, quality-filter), `compiler.py` embeds title+description, `_OKF_CACHE` keyed on `compiled.json` mtime. `seed_ontology.py` MERGE carries `tenant_id`. Ingestion checkpoint layers (Redis + `ingestion_state.json`) must be cleared on wipe or phantom success.

Recommendation: `memory/okf/sri-amma-bhagavan/` + `shared/` stays shared; compile to `compiled.json` with mandatory `tenant_id,corpus_id,teacher_id,licensed_domain` per entry; ingestion stamps same fields into Qdrant payload + Neo4j edge (`ontology_writer.py:162 licensed_domain`). Reuse `extract_okf(auto_approve=False)→staging/` review gate; keep twin-copy invariant (guarded by `test_okf_pipeline_integrity.py`). Add `tenant_id` to `IngestionCheckpoint` key (today URL+hash only → cross-tenant re-skip risk).

## 4. Tenant-aware routing + per-tenant eval

Routing today = `set_tenant_from_request` (JWT `tenant_id`/`app_metadata.tenant_id` → ContextVar; refuses `user.id` fallback — guarded by `test_tenant_identity_guard.py`). Licensed-domain read gate (`require_licensed_domain_reads`, `resolve_teacher_domain().rollout_enabled`). Eval: `scripts/eval/run_ragas_eval.py` (`--ci --threshold 0.6`), `test_qdrant_search_quality.py` NDCG. Papers: SlugRAG/SemEval-2026 — domain fine-tune +44.3% Recall@10 / +47.8% NDCG@10 (BGE-large best nDCG 0.51); RAGAS faithfulness = supported-claims/total, WikiEval human agreement 0.95 faith / 0.78 ans-rel.

Recommendation: (a) Route = `assistant_id → AssistantScope(...)` via `assistant_registry/authorization.py` + `CorpusScope` injection; unknown teacher → default-deny. (b) Golden set per teacher: 50–100 Q with per-tenant NDCG@10/recall + RAGAS faithfulness + abstention rate; CI-gate per tenant (`run_ragas_eval.py --tenant`). Do NOT share one golden set across teachers.

## 5. Per-tenant cost attribution/metering

Repo has Sarvam budget guard + OpenRouter accounting groundwork (`34c98a5`: provider `usage.cost` vs fallback estimates vs unknown-cost separated). OpenRouter returns per-response `usage{prompt_tokens,completion_tokens,cost,upstream_inference_cost,cached_tokens}` + Activity/Analytics API. Pattern: gateway computes realized USD per request, tags `tenant_id,user_id,model`, PromQL/OTel aggregation, per-team budgets.

Recommendation: middleware logging `{tenant_id, user_id, model, prompt/comp/reasoning/cache tokens, cost}` to telemetry DB (key = `TenantContext.get()`); per-tenant Redis quota extension `anon_quota:{tenant}:{session}` + per-tenant limit/window settings (today global only). Dashboard: per-tenant spend, cost/successful-grounded-answer, cache-hit rate. Alert on spike.

## 6. Tenant onboarding runbook (`docs/TENANT_ONBOARDING.md`, 30-min)

1. Register `TeacherDomain(domain_id, rollout_enabled=False)` + `assistant_registry` scope (rights pending). 2. Create `memory/okf/<tenant>/` + ingest corpus with stamped fields; verify Qdrant payload index + Neo4j index hit. 3. Add golden set `evals/golden/<tenant>.jsonl`; run `run_ragas_eval.py --tenant <id> --ci`. 4. Set quota/cost tags + cache prefix isolation test. 5. Legal sign-off → flip `rollout_enabled=True`. 6. Rollback: flip flag off (default-deny reads), no data delete.

## 7. GDPR per-tenant purge

`DELETE /account/purge-memory → purge_all_user_data(user_id)` covers backend planes; `canonical_memory.py` forget/export; `second_brain.py` forget/export. `compliance.py:247` is TICKET-ONLY — not a purge. Qdrant supports filtered delete (`tenant_id=X AND user_id=Y`).

Recommendation: (a) `DELETE /compliance/tenant/{tenant_id}` (admin, dual-confirm): Qdrant filtered delete + Neo4j `DETACH DELETE WHERE tenant_id` + Redis prefix scan + Postgres rows + snapshot tombstone; return deletion report. (b) Wire ticket → Celery purge job instead of manual script note. (c) Per-tenant crypto-erase option: per-tenant KEK for Second Brain vault → offboard = key destroy.

## 8. Cross-tenant leakage vectors

Ungated retrieval leaks 98–100% probes; ABAC-gated → 0%. Hybrid vector→graph pivot: RPR≈0.95, amplification 160–194× via shared entities, 95.4% benign queries leak with zero injection. Same-index collusion scales Θ(√k·ε). OWASP: pre-retrieval filter mandatory; never rely on LLM for ACL; log identity + chunk ACL.

Repo vectors: (1) missing `must tenant_id` on any Qdrant path (`QdrantFilterBuilder` has no tenant method — easy to forget); (2) graph expansion without tenant predicate on 2nd hop (shared concept "suffering" pivots); (3) cache cross-serve (tenant-prefixed — keep; add tenant into semantic-cache key + OKF cache); (4) ContextVar leak across tasks (`reset()` on teardown); (5) `user.id`-as-tenant regression (test-guarded — keep); (6) translation/history re-injection without scope; (7) logs echoing other-tenant evidence.

Recommendation: enforce `CorpusScope` at vector AND every graph hop; cross-tenant probe suite (RPR=0 CI gate); per-turn re-validation for multi-turn; strip ACL metadata from prompts; audit-log retrieval identity.

## Sources

- https://qdrant.tech/documentation/manage-data/multitenancy
- https://qdrant.tech/documentation/manage-data/multitenancy/index.md
- https://qdrant.tech/articles/multitenancy
- https://skills.qdrant.tech/qdrant-multitenancy/SKILL.md
- https://www.infoworld.com/article/4099002/qdrant-vector-database-adds-tiered-multitenancy.html
- https://neo4j.com/product/neo4j-graph-database/flexibility
- https://assets.neo4j.com/Official-Materials/Multi+DB+Considerations.pdf
- https://github.com/neo4j/neo4j/issues/12920
- https://community.neo4j.com/t/proper-way-to-implement-multi-tenancy-on-neo4j/625
- https://github.com/samishekhalard/Enterprise-AI-Platform/blob/main/docs/adr/ADR-003-database-per-tenant.md
- https://arxiv.org/html/2602.08668v3 (Retrieval Pivot Attacks)
- https://arxiv.org/html/2605.05287 (ABAC gating 98–100%→0%)
- https://arxiv.org/html/2605.19847v2 (collusion Θ(√k·ε))
- https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/RAG_Security_Cheat_Sheet.md
- https://blogs.oracle.com/developers/secure-enterprise-rag-acls-tenant-filters-provenance-and-oracle-deep-data-security
- https://aclanthology.org/2026.semeval-1.135/ (SlugRAG +44.3%/+47.8%)
- http://arxiv.org/html/2309.15217v2 (RAGAS)
- https://openrouter.ai/docs/use-cases/usage-accounting
- https://openrouter.ai/blog/announcements/activity-dashboard
- https://api.qdrant.tech/api-reference/points/delete-vectors
