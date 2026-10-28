# Runbook: Corpus Reindexing & Alias Swap (DE-6.3)

## Objective
Reindex the production corpus into an isolated, versioned collection (`corpus_vN`), validate all quality and contract gates, and atomically swap the serving alias without downtime.

---

## Prerequisites
- Working directory: repository root (or `/app` in container).
- Python virtualenv activated (`backend/.venv`).
- Ensure target version number is identified (`N`). Check active alias target:
  ```bash
  curl -s http://localhost:6333/aliases
  ```

---

## Step 1: Planning Phase
Inspect the active alias, discover source collection, calculate target configuration, and generate execution plan:
```bash
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --plan-only
```
Review the output:
- Source collection and current point count.
- Target collection name (`spiritual_wisdom_contextual_v2`).
- Chunker version, parent ID scheme, and embedding dimension.

---

## Step 2: Dry-Run Simulation
Simulate migration without writing points to Qdrant:
```bash
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --dry-run
```
Verify:
- Batch reading succeeds.
- Quality gates and text filters execute without unhandled exceptions.
- Zero mutations occur in Qdrant.

---

## Step 3: Execute Reindex
Build the new versioned collection:
```bash
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --version 2
```
This performs:
1. Target collection creation with scalar int8 quantization and configured vector params.
2. Ingest stream from source collection with transformation and gate enforcement.
3. Payload enrichment (`chunker_version`, `parent_id_scheme`, `source_release_version`).
4. Rejections written to `corpus_gate_rejections` ledger.

---

## Step 4: Verification & Quality Gates
Before swapping the alias, run the validation matrix against the new collection:
```bash
# 1. Check optimizer status and point count
python -m scripts.ops.export_qdrant_health --collection spiritual_wisdom_contextual_v2

# 2. Audit lineage completeness
python -m scripts.ops.audit_lineage_completeness --collection spiritual_wisdom_contextual_v2 --dry-run

# 3. Verify retrieval quality benchmark
python -m scripts.ops.measure_rag_variants --collection spiritual_wisdom_contextual_v2
```
Criteria to proceed:
- `points_count` matches or exceeds target minimum.
- `optimizer_status` is `ok`.
- Lineage completeness ratio >= 99%.
- Retrieval benchmark shows no MRR/NDCG regression.

---

## Step 5: Atomic Alias Swap
Promote the new collection to the active alias atomically:
```bash
python -c "
from services.qdrant_aliases import QdrantAliasManager
mgr = QdrantAliasManager()
mgr.switch_alias('spiritual_wisdom_contextual', 'spiritual_wisdom_contextual_v2')
print('Alias swapped successfully.')
"
```

---

## Step 6: Post-Deployment Smoke Test & Cache Flush
1. Test live retrieval:
   ```bash
   curl -s -X POST http://localhost:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What is the beautiful state?", "session_id": "test-reindex-probe"}' | jq .
   ```
2. Monitor dashboard:
   - Open Grafana dashboard `docs/dashboards/corpus_data_platform_sli.json`.
   - Verify error rates and latency stay within SLOs.

---

## Rollback Procedure
If unexpected regressions occur:
```bash
python -c "
from services.qdrant_aliases import QdrantAliasManager
mgr = QdrantAliasManager()
mgr.switch_alias('spiritual_wisdom_contextual', 'spiritual_wisdom_contextual_v1')
print('Rolled back to v1.')
"
```
The previous collection remains intact and untouched.
