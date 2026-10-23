# First-Person Context Harness: Operator Write-Command Proposal

> [!CAUTION]
> **STATUS: NOT RUN — OWNER APPROVAL REQUIRED BEFORE EXECUTION**
> No command in this document has been executed. No collection has been created or mutated. No alias has been switched.
> Execution of any step below requires:
> 1. Owner review and explicit sign-off of candidate dry-run reports and checksums.
> 2. Owner-provided concrete values for every `<PLACEHOLDER>` field.
> 3. Verified full snapshot backup of Qdrant state prior to any write.
> 4. Execution only within an approved maintenance window by the named operator.

---

## 1. Prerequisites Checklist

Before executing Step 1, verify that all prerequisites are satisfied:

- [ ] ASR manifest containing word-level start/end timestamps and engine/version metadata has been delivered and verified by the data steward.
- [ ] Documentary rights manifest has been approved by the legal/content owner.
- [ ] Speaker review of the 1,202 legacy unverified clips (and provenance of 779 verified clips) is complete and recorded in `speaker_manifest.json`.
- [ ] Dry-run candidate validation passes with zero unhandled errors (`validate_fp_context_candidate.py`).
- [ ] Qdrant snapshot backup verified with readable test restore in an isolated container.

---

## 2. Step-by-Step Operator Runbook

### STEP 1: Strict Dry-Run Candidate Validation & Quarantine Split

```bash
# Target: local/staging operator workstation
python backend/scripts/ops/validate_fp_context_candidate.py \
  --asr-manifest "<APPROVED_ASR_MANIFEST_PATH>" \
  --rights-manifest "<APPROVED_RIGHTS_MANIFEST_PATH>" \
  --speaker-manifest "<APPROVED_SPEAKER_REVIEW_PATH>" \
  --source-spans "<APPROVED_SOURCE_SPANS_JSONL_PATH>" \
  --candidate-out "/tmp/fp_candidate_<VERSION>_<TIMESTAMP>.jsonl" \
  --quarantine-out "/tmp/fp_quarantine_<VERSION>_<TIMESTAMP>.jsonl"

# Output inspection
sha256sum "/tmp/fp_candidate_<VERSION>_<TIMESTAMP>.jsonl"
sha256sum "/tmp/fp_quarantine_<VERSION>_<TIMESTAMP>.jsonl"
```

**Verification Gate:**
- Confirm Candidate count matches `<APPROVED_CANDIDATE_COUNT>`.
- Confirm Quarantine count matches `<EXPECTED_QUARANTINE_COUNT>`.
- Candidate SHA-256 matches `<APPROVED_CANDIDATE_SHA256>`.

---

### STEP 2: Pre-Write Qdrant Snapshot Creation & Hash Verification

```bash
# Create snapshot of live first_person collections
curl -X POST "http://<QDRANT_HOST>:6333/collections/first_person_v9/snapshots" \
  -H "api-key: <QDRANT_API_KEY>"

# Verify snapshot file on storage and record checksum
sha256sum "/qdrant/storage/snapshots/first_person_v9/<SNAPSHOT_NAME>.snapshot"
```

**Verification Gate:**
- Snapshot creation returns HTTP 200 with status `ok`.
- Snapshot hash is recorded in ops log book.

---

### STEP 3: Create Dedicated New Versioned Collection (Never Mutate In-Place)

> [!IMPORTANT]
> The target collection MUST be a brand new versioned name (e.g., `first_person_context_v1`).
> Never write directly to `first_person_v9` or alias `first_person`.

```bash
curl -X PUT "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{
    "vectors": {
      "passage_dense": {
        "size": 1024,
        "distance": "Cosine"
      }
    },
    "optimizers_config": {
      "default_segment_number": 2
    }
  }'
```

---

### STEP 4: Create Required Payload Indexes

```bash
# Tenant / Guru ID (keyword index for partitioned retrieval)
curl -X PUT "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>/index" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{"field_name": "guru_id", "field_schema": "keyword"}'

# Parent Unit ID (grouping index)
curl -X PUT "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>/index" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{"field_name": "parent_unit_id", "field_schema": "keyword"}'

# Speaker verification status
curl -X PUT "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>/index" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{"field_name": "speaker_verified", "field_schema": "bool"}'

# Rights clearance status
curl -X PUT "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>/index" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{"field_name": "rights_cleared", "field_schema": "bool"}'
```

---

### STEP 5: Idempotent Batch Upsert with Strict Deterministic UUIDv5 Point IDs

```bash
# Execute candidate index builder in upsert mode (requires explicit flag)
python backend/scripts/ops/build_first_person_context_index.py \
  --input-jsonl "/tmp/fp_candidate_<VERSION>_<TIMESTAMP>.jsonl" \
  --qdrant-url "http://<QDRANT_HOST>:6333" \
  --collection "<NEW_COLLECTION_NAME>" \
  --batch-size 100 \
  --upsert
```

---

### STEP 6: Post-Upsert Contract & Completeness Audit

```bash
# Run readiness auditor against new collection
docker exec mukthiguru-backend python /opt/audit_first_person_readiness.py \
  --qdrant-url "http://qdrant:6333" \
  --collection "<NEW_COLLECTION_NAME>" \
  --alias "first_person" \
  --context-collection "<NEW_COLLECTION_NAME>"
```

**Verification Gate:**
- Post-write count matches `<APPROVED_CANDIDATE_COUNT>` exactly.
- All 18 fp-context fields present on 100% of points.
- 0 duplicate IDs.
- `speaker_verified=true` on 100% of servable candidate points.

---

### STEP 7: Rollback Procedure (If Audit Fails Any Gate)

If any check in Step 6 fails:

```bash
# 1. Delete failed candidate collection immediately
curl -X DELETE "http://<QDRANT_HOST>:6333/collections/<NEW_COLLECTION_NAME>" \
  -H "api-key: <QDRANT_API_KEY>"

# 2. Verify live collection and alias are unchanged
curl "http://<QDRANT_HOST>:6333/collections/first_person_v9" \
  -H "api-key: <QDRANT_API_KEY>"
curl "http://<QDRANT_HOST>:6333/aliases" \
  -H "api-key: <QDRANT_API_KEY>"

# 3. If live collection was somehow touched, restore snapshot
curl -X POST "http://<QDRANT_HOST>:6333/collections/first_person_v9/snapshots/recover" \
  -H "Content-Type: application/json" \
  -H "api-key: <QDRANT_API_KEY>" \
  -d '{"location": "file:///qdrant/storage/snapshots/first_person_v9/<SNAPSHOT_NAME>.snapshot"}'
```

---

## 3. Metadata & Approvals Registry

| Parameter | Required Specification | Status |
|---|---|---|
| Target Collection Name | `<NEW_COLLECTION_NAME>` | Pending Approval |
| Approved Manifest SHA-256 | `<APPROVED_CANDIDATE_SHA256>` | Pending Delivery |
| Approved Point Count | `<APPROVED_CANDIDATE_COUNT>` | Pending Delivery |
| Executing Operator | `<OPERATOR_NAME>` | Pending Assignment |
| Execution Maintenance Window | `<SCHEDULED_WINDOW_UTC>` | Pending Schedule |
| Reversible Snapshot Target | `<SNAPSHOT_NAME>` | Pending Pre-Write |
