# Qdrant Vault Runbook

Runbook for the Qdrant collections that hold user-personal data: `second_brain_vault` and `guru_memories`-related vector storage. Doctrine collection configuration lives in `services/qdrant/client.py`.

## `second_brain_vault`

Shared multi-tenant collection used by `services/second_brain/second_brain_service.py`. Plaintext notes remain encrypted in Postgres (`user_brain_nodes`); only anonymous item IDs and tiny filter payloads live in Qdrant.

### Current configuration

| Parameter | Value | Notes |
| --- | --- | --- |
| Collection name | `second_brain_vault` | Hardcoded in `services/second_brain/vault_index.py`. |
| Vector size | `settings.embedding_dimension` (default `1024`) | Must match the active encoder (`BAAI/bge-m3`). |
| Distance | Cosine | `Distance.COSINE`. |
| Vectors on disk | `True` | `on_disk=True`. |
| Payload on disk | `True` | `on_disk_payload=True`. |
| HNSW `m` | `32` | Doctrine-matching connectivity. |
| HNSW `ef_construct` | `200` | Doctrine-matching build-time beam width. |
| HNSW `full_scan_threshold` | `10000` | Linear scan below 10 k points. |
| Quantization | Scalar INT8, `always_ram=True` | Matches `spiritual_wisdom` default. |
| Payload indexes | `user_id` keyword, `kind` keyword | Tenant isolation + future faceting. |

### Recreate procedure

Use only when the collection is empty or after a backup. This deletes all vector data in the collection; encrypted notes in Postgres survive and can be re-vectorized.

```bash
# From backend/ with Qdrant reachable and the app env loaded.
export QDRANT_URL=http://localhost:6333
export QDRANT_API_KEY=your-key-if-required
backend/.venv/bin/python - <<'PY'
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from services.second_brain.vault_index import VaultIndex

async def main():
    idx = VaultIndex()
    idx._client.delete_collection(idx._collection)
    idx.ensure_collection()
    print(f"Recreated {idx._collection}")

asyncio.run(main())
PY
```

After recreation, re-vectorize from Postgres:

```bash
backend/.venv/bin/python - <<'PY'
# Trigger SecondBrainService to re-embed all user_brain_nodes rows.
# Implementation depends on the existing re-index admin path; ensure
# plaintext is never written to Qdrant payload.
PY
```

## `guru_memories` (pgvector)

Episodic memory vectors live in Postgres (`public.guru_memories.embedding`) using the `pgvector` extension, not Qdrant. HNSW build parameters are aligned to the doctrine/Qdrant HNSW contract where the names map as follows:

| Qdrant name | pgvector name | Value |
| --- | --- | --- |
| `m` | `m` | `32` |
| `ef_construct` | `ef_construction` | `200` |

Current migration: `supabase/migrations/20260618044620_58e0642d-38c0-469d-9bd5-b6e91fc32297.sql`.

### Index definition

```sql
CREATE INDEX IF NOT EXISTS guru_memories_embedding_idx
  ON public.guru_memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 32, ef_construction = 200);
```

### Re-vector / reindex procedure

If the embedding dimension or HNSW parameters change, the safest approach is:

1. Back up the table:
   ```sql
   CREATE TABLE public.guru_memories_backup AS TABLE public.guru_memories;
   ```
2. Drop and recreate the index (requires `ACCESS EXCLUSIVE` lock; brief on small tables):
   ```sql
   DROP INDEX IF EXISTS public.guru_memories_embedding_idx;
   CREATE INDEX guru_memories_embedding_idx
     ON public.guru_memories
     USING hnsw (embedding vector_cosine_ops)
     WITH (m = 32, ef_construction = 200);
   ```
3. If the dimension changed, recreate the `embedding` column and re-embed all rows via the backend embedding service. Do not truncate user data without a verified backup.

On a live system with many rows, prefer building the new index concurrently and swapping with `REINDEX INDEX CONCURRENTLY` after testing on a replica.

### Dimension note

The current migration defines `embedding vector(384)`. The live encoder (`BAAI/bge-m3`) produces 1024-dim dense vectors. Writing 1024-element arrays into a `vector(384)` column will fail at insert time. Before enabling semantic memory writes, either:

- Recreate the column as `vector(1024)` and re-embed all existing rows, or
- Change the active embedding model to a 384-dim model.

Because this is data-destructive if done wrong, the migration does not auto-alter the column here; follow the re-vector procedure above after backing up the table.

## Tech debt: `user_profiles` timestamp columns

Some historical migrations define `public.user_profiles.created_at` / `updated_at` as `float8` instead of `timestamptz`. The service currently treats them as opaque numeric timestamps. A hot migration to `timestamptz` is intentionally **not** applied here because:

- The table may be large and live-queried by the orchestrator hot path.
- Conversion requires downtime or a generated-column/swap strategy that must be verified against the actual schema and query patterns first.
- No production incident has been tied to the float8 representation.

Safe path when prioritized:

1. Audit all readers/writers of `user_profiles.created_at` / `updated_at` for expected `timestamptz` behavior.
2. Add generated columns `_created_at_ts` / `_updated_at_ts` as `timestamptz` populated from the float8 values, or perform a zero-downtime column swap behind a feature flag.
3. Remove the old float8 columns only after all code paths consume the new `timestamptz` columns and a rollback window has passed.
