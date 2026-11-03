# Runbook: Instant Feature Flag Toggle Procedure (DE-6.3)

## Objective
Safely and instantly toggle off (or on) experimental retrieval features and serving gates without full redeployment or code alterations.

---

## Controlled Feature Flags
The following feature flags govern experimental retrieval and serving behavior:

| Environment Variable | Default | Purpose |
|----------------------|---------|---------|
| `RELEASE_FILTER_MODE` | `off` | `off` / `shadow` / `enforce`: requires points to carry the active `source_release_version`. |
| `CORPUS_PUBLICATION_ENFORCEMENT_ENABLED` | `false` | Separate manifest-presence gate (not the release filter). |
| `FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED` | `false` | Expand retrieved parent units to surrounding spans (RAG-2). |
| `FIRST_PERSON_GRAPH_EXPANSION_ENABLED` | `false` | Append concept-filtered graph retrieval after vector search (RAG-2). |
| `RETRIEVAL_FEEDBACK_ENABLED` | `false` | Suppression-only, TTL-bounded feedback loop (RAG-1). It never boosts and never writes to Qdrant. |
| `HYBRID_SEARCH_ENABLED` | `true` | Combine dense vector and sparse BM25 retrieval with RRF. |
| `FIRST_PERSON_LOCAL_REVIEW_ENABLED` | `false` | Enable local-review endpoints for first-person candidate inspection. |

---

## Step 1: Update Environment Variable
Edit `backend/.env` (or set via Railway/Docker environment):
```bash
# Example: Disable retrieval feedback loop immediately
sed -i '' 's/RETRIEVAL_FEEDBACK_ENABLED=true/RETRIEVAL_FEEDBACK_ENABLED=false/' backend/.env
```
Or if adding flag:
```bash
echo "RETRIEVAL_FEEDBACK_ENABLED=false" >> backend/.env
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
`_serving_policy_fingerprint` in `backend/app/pipeline/stages/first_person_bridge.py` includes active feature flags, so changing a flag already causes cache misses for new fingerprints. To flush existing entries immediately:
```bash
make flush-cache          # Redis mukthiguru:cache, mukthiguru:semcache, cache:first_person_exact + Qdrant semantic cache
make verify-cache-empty   # exit 0 = empty; 1 = still cached; 2 = unreachable (NOT empty)
```
Never use `FLUSHALL`. Do not hand-roll `scan_iter` patterns: the real namespaces
are `mukthiguru:cache`, `mukthiguru:semcache` and `cache:first_person_exact`
(`backend/app/constants.py`, `scripts/ops/flush_cache.py`); patterns such as
`exact_cache:*` match zero keys, so revoked content would keep serving from cache
for the 24 h TTL.

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
