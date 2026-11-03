# Runbook: Cross-Store Drift Detection and Repair (DE-6.3)

## Objective
Detect, investigate, and repair state drift across primary knowledge stores:
- Qdrant (vector embeddings and chunk metadata)
- Supabase (source releases, quality queues, and canonical memories)
- Neo4j / Memgraph (knowledge graph entities and relationships)

---

## Observability & Alerts
- **Prometheus Metric:** `corpus_drift_points_total{store_pair="..."}`
- **Alert:** `CorpusStoreDriftDetected` fires when drift > 0 for > 15 minutes.

---

## Step 1: Run Cross-Store Audit
Execute the automated cross-store audit tool:
```bash
python -m scripts.ops.cross_store_audit --json reports/drift_report.json
```
Review output metrics:
- Points in Qdrant missing from Supabase `source_releases`.
- Sources in Supabase missing Qdrant points.
- Entities in Neo4j with no corresponding Qdrant vectors.

---

## Step 2: Classify Drift Pattern

### Pattern A: Orphan Qdrant Points
Points exist in Qdrant whose `source_url` was deleted or purged from Supabase.
**Repair:**
1. Dry-run orphan detection:
   ```bash
   python -m scripts.ops.reconcile_orphans --dry-run
   ```
2. Reconcile and purge orphan points:
   ```bash
   python -m scripts.ops.reconcile_orphans
   ```

### Pattern B: Missing Vectors in Qdrant
A valid approved source in `source_releases` has zero points in Qdrant (failed ingest or interrupted sync).
**Repair:**
1. Re-ingest the specific missing source URL:
   ```bash
   python -m scripts.ingestion.bulk_ingest_video --url "https://www.youtube.com/watch?v=..."
   ```

### Pattern C: Neo4j Graph Disconnect
Nodes or relationships exist for entities whose chunks were modified or removed.
**Repair:**
1. Run graph alignment check:
   ```bash
   python -m scripts.ops.launch_gate_kg_readiness
   ```
2. Sync or prune stale graph triples as instructed by audit report.

---

## Step 3: Verification
Re-run the audit and check that the gauge returns to zero:
```bash
python -m scripts.ops.cross_store_audit
```
Confirm `corpus_drift_points_total` is 0.
