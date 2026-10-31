# Runbook: Qdrant Snapshot Restore Drill (DE-6.3)

## Objective
Execute an emergency snapshot restore or periodic disaster recovery drill for Qdrant vector collections with measurable RPO and RTO.

---

## SLOs & Targets
- **RPO (Recovery Point Objective):** < 24 hours. Daily automated snapshots generated via cron/Celery Beat.
- **RTO (Recovery Time Objective):** < 30 minutes. Full restore and validation into scratch collection before alias swap.

---

## Step 1: Discover Available Snapshots
List collection snapshots stored on Qdrant and check snapshot age:
```bash
python -m scripts.ops.snapshot_qdrant --collection spiritual_wisdom_contextual --list
```
Identify the newest verified snapshot (e.g. `spiritual_wisdom_contextual-1111874297854021-2026-10-27-20-08-11.snapshot`).

---

## Step 2: Dry-Run Restore Simulation
Simulate the restore to ensure network and parameters are valid:
```bash
python -m scripts.ops.snapshot_qdrant \
  --collection spiritual_wisdom_contextual \
  --restore spiritual_wisdom_contextual-1111874297854021-2026-10-27-20-08-11.snapshot \
  --into-collection scratch_restore_test \
  --dry-run
```

---

## Step 3: Execute Live Restore to Scratch Collection
Always restore into an isolated scratch collection first:
```bash
python -m scripts.ops.snapshot_qdrant \
  --collection spiritual_wisdom_contextual \
  --restore spiritual_wisdom_contextual-1111874297854021-2026-10-27-20-08-11.snapshot \
  --into-collection scratch_restore_test
```

---

## Step 4: Validate Restored Collection
1. **Health and Segment Verification:**
   ```bash
   python -m scripts.ops.export_qdrant_health --collection scratch_restore_test
   ```
   Confirm:
   - `status`: `green`
   - `optimizer_status`: `ok`
   - `points_count` matches snapshot expectation (e.g. ~14,033 points).

2. **Lineage Audit:**
   ```bash
   python -m scripts.ops.audit_lineage_completeness --collection scratch_restore_test --limit 100 --dry-run
   ```

3. **Sample Retrieval Test:**
   ```bash
   cd backend && .venv/bin/python -c "
   from services.qdrant.client import QdrantClient
   c = QdrantClient('http://localhost:6333')
   pts = c.scroll('scratch_restore_test', limit=1, with_payload=True)[0]
   assert len(pts) > 0, 'No points restored'
   print('Verification passed:', pts[0].id)
   "
   ```

---

## Step 5: Promotion (Disaster Recovery only, never in a drill)
Promotion serves the restored data to users. Do it only when **all** hold:
- Step 4 passed on the scratch collection: lineage audit clean, point count equals the snapshot manifest, sample retrieval returns expected points.
- The release filter and rights stamps on the restored points were checked (`RELEASE_FILTER_MODE`, `domain_rights_status`), so a rolled-back or revoked source cannot reappear.
- The owner (Harshodai) approved the promotion in writing.

Record the alias target you are replacing so the swap can be reverted (`mgr.rollback_alias('spiritual_wisdom_contextual')`), then switch:
```bash
cd backend && .venv/bin/python -c "
from services.qdrant_aliases import QdrantAliasManager
mgr = QdrantAliasManager()
print('previous target:', mgr.get_alias_target('spiritual_wisdom_contextual'))
print(mgr.atomic_alias_swap('spiritual_wisdom_contextual', 'scratch_restore_test'))
"
```
After promotion run `make flush-cache` and `make verify-cache-empty`.

---

## Step 6: Post-Restore Cleanup (In Drill)
If this was a drill, clean up the scratch collection:
```bash
curl -s -X DELETE http://localhost:6333/collections/scratch_restore_test
```
Record drill completion time, restored point count, and observed RTO in the incident/drill ledger.
