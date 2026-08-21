# Redis Namespace Budget and Telemetry Runbook

**Owner:** AskMukthiGuru platform  
**Scope:** Query-cache cost control only  
**Last reviewed:** 2026-08-21

## Policy

AskMukthiGuru uses Redis for more than response caching. Queue jobs, anonymous quota reservations, sessions, rate limits, telemetry, and Second Brain state are correctness-sensitive. Therefore, no global Redis eviction or `FLUSHALL` is an acceptable response-cache policy.

`REDIS_CACHE_MAX_KEYS` applies only to the exact-query namespace matching `mukthiguru:cache:*`. When the ceiling is reached, new exact-query writes are skipped while existing keys remain refreshable. `REDIS_CACHE_MAX_KEYS=0` disables the ceiling for rollback. The default is `10,000`. Namespace metrics use the fixed label `exact_query` and are sampled no more often than `REDIS_CACHE_TELEMETRY_INTERVAL_SECONDS`.

## Read-only production measurement

Run the report inside the backend or worker container. It reads key names and TTL metadata only; it does not read values or delete keys.

```bash
railway ssh \
  -p 7cbd5f8c-2bb1-4ba8-8de9-8bc36a14e137 \
  -s 18690f24-5e2d-4fdb-95f6-42142111df7e \
  -e production \
  -i ~/.ssh/id_ed25519 \
  'cd /app && python3 scripts/ops/redis_namespace_report.py --scan-limit 100000'
```

Record the JSON output in the dated scalability audit. Treat `truncated=true` as an incomplete measurement, not as a zero or a pass. Do not copy Redis URLs, passwords, or key values into reports.

## Activation and rollback

The default ceiling is intentionally conservative. Activate or adjust it only after observing exact-query cache hit rate, namespace growth, non-expiring key count, and Redis memory over at least one normal serving window. If cache rejections appear while hit rate or response latency regresses, set `REDIS_CACHE_MAX_KEYS=0`, redeploy the backend and worker, and investigate namespace growth before changing any global Redis policy.

The setting is safe to roll back because it controls admission to new query-cache writes, not deletion. Existing cache entries expire by their normal TTL or are removed by the targeted flush utility.

## Targeted flush

Use `scripts/ops/flush_cache.py` for cache invalidation. It deletes only the known Qdrant semantic-cache collections and Redis patterns `mukthiguru:cache:*` and `mukthiguru:semcache:*`. It never runs `FLUSHALL`. After a flush, verify that queue, session, quota, telemetry, rate-limit, and Second Brain namespaces remain present and operational.

## Release gate

A release is not complete until the following are true:

| Gate | Evidence | Stop condition |
|---|---|---|
| Scope | Diff contains only query-cache metrics, adapter, settings, tests, docs, and ops tooling | Any corpus or private-memory plaintext change |
| Safety | ReDoS scanner passes; Python compilation passes | Scanner failure or syntax failure |
| Tests | Focused Redis budget tests pass in the dependency-complete Railway image/CI | Any regression or missing locked dependency |
| Runtime | `/api/healthz` and `/api/health` ready; worker healthy | Any readiness failure |
| Cost | Namespace report shows bounded exact-cache growth and no unexpected non-expiring query-cache keys | Unbounded growth, unexpected TTL absence, or memory alarm |
| Quality | ONNX shadow validator passes on complete corpus and held-out faithfulness/NDCG | Any missing corpus source or category regression |

## Evidence basis

Qdrant describes semantic caching as a separate, smaller vector collection that stores question embeddings and associated answers, and recommends it for repeated question-answering workloads where reuse is appropriate [1]. Qdrant also emphasizes simple evaluation metrics such as hit rate and retrieval quality rather than relying on intuition alone [2]. Redis recommends monitoring memory utilization, latency, cache hit rate, and evictions; its operational guidance uses 80% as an alert point for non-caching workloads and warns that a mixed Redis instance should not be treated as a disposable cache [3]. These principles support the namespace-specific budget and the requirement to measure hit rate before splitting or changing retention.

## References

[1]: https://qdrant.tech/articles/semantic-cache-ai-data-retrieval/ "Qdrant: Semantic Caching for RAG: Cut LLM Cost and Latency"
[2]: https://qdrant.tech/blog/hitchhikers-guide/ "Qdrant: The Hitchhiker's Guide to Vector Search"
[3]: https://redis.io/tutorials/redis-software-observability-playbook/ "Redis: Redis Software Developer Observability Playbook"
