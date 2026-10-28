# Runbook: Instant Feature Flag Toggle Procedure (DE-6.3)

## Objective
Safely and instantly toggle off (or on) experimental retrieval features and serving gates without full redeployment or code alterations.

---

## Controlled Feature Flags
The following feature flags govern experimental retrieval and serving behavior:

| Environment Variable | Default | Purpose |
|----------------------|---------|---------|
| `CORPUS_PUBLICATION_ENFORCEMENT_ENABLED` | `false` | Gate requiring Qdrant points to have active release in `source_releases`. |
| `FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED` | `false` | Expand retrieved parent units to surrounding spans (RAG-2). |
| `FIRST_PERSON_GRAPH_EXPANSION_ENABLED` | `false` | Append concept-filtered graph retrieval after vector search (RAG-2). |
| `RETRIEVAL_FEEDBACK_LOOP_ENABLED` | `false` | Suppress negative-feedback chunks and boost positive feedback (RAG-1). |
| `HYBRID_SEARCH_ENABLED` | `true` | Combine dense vector and sparse BM25 retrieval with RRF. |
| `FIRST_PERSON_LOCAL_REVIEW_ENABLED` | `false` | Enable local-review endpoints for first-person candidate inspection. |

---

## Step 1: Update Environment Variable
Edit `backend/.env` (or set via Railway/Docker environment):
```bash
# Example: Disable retrieval feedback loop immediately
sed -i '' 's/RETRIEVAL_FEEDBACK_LOOP_ENABLED=true/RETRIEVAL_FEEDBACK_LOOP_ENABLED=false/' backend/.env
```
Or if adding flag:
```bash
echo "RETRIEVAL_FEEDBACK_LOOP_ENABLED=false" >> backend/.env
```

---

## Step 2: Apply to Docker Runtime
In Docker Compose environments, reload the container with the updated env file:
```bash
docker compose up -d --no-deps backend
```
*Note per AGENTS.md X25: A simple `docker compose restart` does NOT reread `.env` files; `docker compose up -d --no-deps` is required.*

---

## Step 3: Clear Serving Policy Fingerprint & Exact Cache
Because `_serving_policy_fingerprint` in `backend/app/pipeline/stages/first_person_bridge.py` includes active feature flags, changing flags automatically causes cache misses for new fingerprint combinations. To flush existing entries immediately:
```bash
cd backend && .venv/bin/python -c "
import redis, os
r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
count = 0
for k in r.scan_iter(match='exact_cache:*'):
    r.delete(k)
    count += 1
print(f'Cleared {count} exact cache keys.')
"
```

---

## Step 4: Verification
1. Query backend health endpoint to confirm settings:
   ```bash
   curl -s http://localhost:8000/api/health | jq .
   ```
2. Send test chat query:
   ```bash
   curl -s -X POST http://localhost:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What is enlightenment?", "session_id": "flag-check"}' | jq .
   ```
3. Check Prometheus metrics to verify metric generation reflects the updated posture (e.g. `retrieval_feedback_suppressions_total` stops incrementing).
