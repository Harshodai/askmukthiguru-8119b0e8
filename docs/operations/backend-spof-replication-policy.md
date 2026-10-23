# Backend SPOF & replication policy

Status: reference (content dated, moved verbatim, not re-verified). Owner: project owner. Last verified: not re-verified as of 2026-10-22.

Moved verbatim from `backend/CLAUDE.md` (token-optimizer pass, 2026-10-22).

## SPOF & Replication Policy (P2-2)

Official architecture, disaster recovery, and high availability policy across stateful components (Redis, Neo4j, Qdrant) across growth tiers (1k, 10k, 100k users).

| User Tier | Target QPS (p95) | Redis Policy | Neo4j Policy | Qdrant Policy | Target SLA / RTO / RPO |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1k Tier** (Pilot / MVP) | 5-15 QPS | **Single Node**: Standalone Docker/Railway container with AOF persistence. Local in-memory TTL fallback on network disconnect. | **Single Instance**: Community edition with local persistent volume. Nightly automated dump (`neo4j-admin dump`). | **Single Node**: Local storage volume with automated nightly snapshot backup to S3 (`scripts/ops/qdrant_backup.py`). | **99.0% SLA**<br>RTO < 15 min<br>RPO < 24 hrs |
| **10k Tier** (Production HA) | 50-150 QPS | **Primary + Read Replica**: Master-replica with automated Sentinel failover (<5s). Read queries load-balanced across replicas; rate limits & anonymous quota use Redis ZADD sliding window. | **Causal Cluster**: 1 Core Leader + 2 Read Replicas (or Neo4j AuraDB HA). Asynchronous read-scaling with transactional causal chaining. | **Distributed 3-Node Cluster**: `replication_factor=2`, `write_consistency_factor=1`. Sharded collections across nodes with dynamic consensus routing. | **99.9% SLA**<br>RTO < 30 sec<br>RPO < 1 min |
| **100k Tier** (Enterprise Multi-AZ) | 500-1500+ QPS | **Multi-AZ Redis Cluster**: Multi-region Redis Cluster with active-passive read-replicas, segregated tiers (Session/RateLimit vs. Semantic/Doctrine Cache), Envoy L7 proxy. | **Enterprise Multi-AZ Cluster**: Multi-region Core Cluster + edge read replicas co-located with API pods. Dedicated read routing and Cypher connection poolers. | **Multi-AZ Sharded Qdrant Cluster**: `replication_factor=3`, `write_consistency_factor=2` across 3 AZs. HNSW scalar/binary quantization, collection tenant partitioning, zero-downtime rolling upgrades. | **99.99% SLA**<br>RTO ~ 0 (transp. failover)<br>RPO = 0 (quorum writes) |

### Failover & Degradation Invariants
1. **Redis Degradation**: If Redis drops, `AnonQuotaRedisAdapter` and `RedisBackedRateLimiter` degrade gracefully to in-process memory caches; search queries bypass semantic cache and proceed directly to vector/graph retrieval without failing requests with HTTP 500.
2. **Neo4j Degradation**: If Neo4j becomes unreachable, GraphRAG retrieval gracefully falls back to pure Qdrant dense vector search + BM25 keyword retrieval; OKF static teachings remain operable.
3. **Qdrant Degradation**: If Qdrant cluster is degraded, exact-match and hot doctrine caches serve answers; fallback returns honest zero-source abstention (`grounding_state=abstained`) rather than fabricating ungrounded teachings.

### Backup caveat (P6, verified 2026-09-13)
Backups stay local-cron per policy (`infrastructure/cron/mukthiguru-backup`: 02:00 Qdrant, 02:30 Neo4j, retention 7, disk-only) — deliberately NOT Celery Beat (`celery_config.py` `beat_schedule` covers win-back/memory only). The cron needs manual sudo install (`/etc/cron.d/` + `/etc/mukthiguru/backup.env`); it was absent on this host, so RPO is unbounded until installed. Qdrant scratch-restore is proven queryable (157 pts + search hit); Neo4j `.dump` load stays an offline maintenance-window op — queryable replay unproven.
