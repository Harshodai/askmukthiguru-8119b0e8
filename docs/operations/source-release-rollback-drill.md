# Source-release rollback drill

The code now supports a controlled source-release rollback. Migration `20260805000004_source_release_rollback.sql` allows a **superseded** release to return to `approved` only through an explicit service-role approval. The existing activation transaction then atomically makes it active and supersedes its currently active peer in the same `(corpus_id, source_identity)` scope.

| Step | Expected governed state | Required evidence |
|---|---|---|
| Register release A | `pending` | Release ID, checksum, scoped corpus/source identity. |
| Approve and activate A | `active` | Reviewer ID, activation timestamp, source-scope canary. |
| Register, approve, activate B | A is `superseded`; B is `active` | Both release IDs and active version B from Qdrant, Neo4j, and LightRAG checks. |
| Re-approve and reactivate A | A is `active`; B is `superseded` | Reviewer ID, restored active version A, and fresh retrieval/citation canaries. |

Run the deterministic repository regression before any environment drill:

```bash
cd backend
.venv/bin/pytest -q tests/test_corpus_release_registry.py
```

The physical drill remains a **launch blocker** while Railway and the staging data stores are offline. Before increasing traffic, apply both source-release migrations to staging, then attach dated evidence showing the four state transitions and the same scoped release version in Qdrant, Neo4j, LightRAG, and the `/api/admin/operations` release snapshot. Do not treat local test success as proof that an environment migration has been applied.
