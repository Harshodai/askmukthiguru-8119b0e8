# Operational Runbooks & Troubleshooting Guide

This guide compiles standard operational runbooks, disaster recovery procedures, and verified incident diagnostics for AskMukthiGuru engineers and SREs.

---

## Runbook Index

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               OPERATIONAL RUNBOOKS MATRIX                                        │
├───────────┬─────────────────────────────────────────────────┬────────────────────────────────────┤
│ Runbook   │ Target Subsystem                                │ Primary Incident or Procedure      │
├───────────┼─────────────────────────────────────────────────┼────────────────────────────────────┤
│ RB-01     │ Qdrant Vector Store                             │ Zero-Downtime Corpus Reindexing    │
│ RB-02     │ Frontend & Nginx Media Serving                  │ YouTube Embed Error 153 Resolution │
│ RB-03     │ Supabase Postgres Security                      │ Cross-User RLS Policy Verification │
│ RB-04     │ Docker Engine (macOS Desktop)                   │ Keychain Helper -25293 Resolution  │
│ RB-05     │ Celery Distributed Workers                      │ Async Event Loop Collision Fix     │
│ RB-06     │ Neo4j Knowledge Graph & Repo Trees              │ Backup, Restore & Cross-Tree Drift │
└───────────┴─────────────────────────────────────────────────┴────────────────────────────────────┘
```

---

## Runbook 1: Zero-Downtime Qdrant Reindexing

### Objective
Reindex the production vector collection (`corpus_vN`) with new embeddings or updated chunker schemas, validate all contract gates, and atomically swap the serving alias without dropping queries.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           ZERO-DOWNTIME REINDEXING WORKFLOW                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [Live Traffic] ───► (Alias: spiritual_wisdom_contextual) ───► [Active Collection: v1]          │
│                                                                                                  │
│   1. Reindex Ingest ──────────────────────────────────────────► [New Collection: v2]            │
│   2. Audit Health & MRR Gates                                            │                       │
│   3. Atomic Alias Switch                                                 ▼                       │
│   [Live Traffic] ───► (Alias: spiritual_wisdom_contextual) ───► [Active Collection: v2]          │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Inspection & Planning
Check active aliases and point counts in Qdrant:
```bash
curl -s http://localhost:6333/aliases | jq .
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --plan-only
```

### Step 2: Dry-Run Simulation
Simulate the batch transformation without mutating Qdrant:
```bash
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --dry-run
```

### Step 3: Execute Reindexing
Build target collection `spiritual_wisdom_contextual_v2` with scalar int8 quantization and configured BGE-M3 dimensions:
```bash
python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --version 2
```

### Step 4: Quality & Retrieval Gate Audit
Before promoting the new collection, verify health and retrieval metrics:
```bash
# Verify optimizer state and memory footprint
python -m scripts.ops.export_qdrant_health --collection spiritual_wisdom_contextual_v2

# Audit lineage completeness ratio (must be >= 99%)
python -m scripts.ops.audit_lineage_completeness --collection spiritual_wisdom_contextual_v2 --dry-run
```

### Step 5: Atomic Alias Promotion
Promote the collection instantaneously via Qdrant's atomic alias API:
```bash
python -c "
from services.qdrant_aliases import QdrantAliasManager
mgr = QdrantAliasManager()
mgr.switch_alias('spiritual_wisdom_contextual', 'spiritual_wisdom_contextual_v2')
print('Production alias promoted successfully.')
"
```

---

## Runbook 2: YouTube Embed Error 153 Resolution

### Symptom
When seekers click *"Play source clip"* or toggle the discourse video player in `DiscourseAudioStrip.tsx` or `CitationCard.tsx`, the embedded YouTube iframe fails with `Video player configuration error (Error 153)`.

### Root Cause (L-YOUTUBE-EMBED-ERROR-153-1)
Nginx previously served `Referrer-Policy: "same-origin"`. When embedding YouTube iframes (`https://www.youtube.com/embed/...`), modern browsers stripped the HTTP `Referer` header on all cross-origin requests. Because YouTube's embed player requires a valid cross-origin referrer and authorized origin to prevent unauthorized scraping, stripping the header triggers a fatal Error 153.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            YOUTUBE EMBED ERROR 153 FIX                                           │
├───────────────────────────────────┬──────────────────────────────────────────────────────────────┤
│ Broken Configuration              │ Corrected Production Architecture                            │
├───────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ • Referrer-Policy: same-origin    │ • Referrer-Policy: strict-origin-when-cross-origin           │
│ • www.youtube.com/embed/{id}      │ • www.youtube-nocookie.com/embed/{id}                        │
│ • No origin query parameter       │ • &origin=${encodeURIComponent(window.location.origin)}      │
│ • Stripped Referer header         │ • Browser transmits origin; YouTube authorizes playback      │
└───────────────────────────────────┴──────────────────────────────────────────────────────────────┘
```

### Resolution Steps
1. **Nginx Security Header Update**:
   Verify `nginx.conf` and `frontend/nginx.conf` declare:
   ```nginx
   add_header Referrer-Policy "strict-origin-when-cross-origin" always;
   ```
2. **HTML Meta Tag**:
   Confirm `frontend/index.html` specifies:
   ```html
   <meta name="referrer" content="strict-origin-when-cross-origin" />
   ```
3. **Iframe Component Parameters**:
   Ensure all player iframes in `DiscourseAudioStrip.tsx` and `CitationCard.tsx` point to `youtube-nocookie.com` with explicit origin encoding:
   ```typescript
   const embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}`;
   ```

---

## Runbook 3: Supabase RLS Policy Verification

### Objective
Ensure that multi-tenant isolation and Row-Level Security (RLS) policies prevent cross-user data leakage across private spiritual conversations, meditation logs, and journal entries.

### Execution
Run the automated multi-user probe (`scripts/verify_rls_policies.py`):
```bash
cd backend
SUPABASE_URL=http://localhost:54321 \
SUPABASE_SERVICE_ROLE_KEY=<local-service-role-key> \
SUPABASE_ANON_KEY=<local-anon-key> \
.venv/bin/python scripts/verify_rls_policies.py
```

### What the Probe Verifies:
```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              CROSS-USER RLS AUDIT MATRIX                                         │
├───────────────────────────────┬──────────────────────────────────┬───────────────────────────────┤
│ Target Table                  │ Security Assertion               │ Test Methodology              │
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ `conversations`               │ Bob cannot read Alice's threads  │ Alice seeds row; Bob selects  │
│ `chat_messages`               │ Bob cannot inspect Alice's turns │ Bob queries by Alice's ID     │
│ `meditation_sessions`         │ Bob cannot view Alice's practice │ Bob attempts cross-read       │
│ `user_profiles`               │ Bob cannot update Alice's state  │ Bob sends UPDATE payload      │
│ `canonical_memories`          │ Anonymous users cannot dump mem  │ Unauthenticated query probe   │
└───────────────────────────────┴──────────────────────────────────┴───────────────────────────────┘
```
**Acceptance Criteria**: The script must report `100% PROBED TABLES PASSED` with zero policy bypasses.

---

## Runbook 4: Docker Safe Execution & macOS Keychain Helper -25293 Bypasses

### Symptom
When executing Docker commands on macOS (e.g., `docker compose up`), the CLI hangs or crashes with:
```text
error getting credentials - err: exit status 1, out: `Cannot autolaunch D-Bus without X11 $DISPLAY`
or:
keychain credentials helper error -25293
```

### Root Cause
Docker Desktop for macOS attempts to read cached registry credentials from the locked macOS Keychain (`docker-credential-osxkeychain`). When the keychain helper times out or lacks desktop session permissions, all Docker Compose and build actions fail.

### Safe Execution Wrapper (`scripts/docker-safe.sh`)
Execute Docker commands using the workspace wrapper:
```bash
# Safe startup
bash scripts/docker-safe.sh docker compose up -d

# Safe backend rebuild
bash scripts/docker-safe.sh docker compose up -d --build --no-deps backend
```

#### How `docker-safe.sh` Works:
1. Creates an isolated temporary directory `.docker_clean/bin/`.
2. Mocks the credential helper binaries (`docker-credential-osxkeychain`, `docker-credential-desktop`) to return empty JSON without querying the keychain.
3. Sets `{"credsStore": ""}` in `.docker_clean/config.json`.
4. Adds the local Docker binary path (`$HOME/.docker/bin` or standard Docker paths) to `PATH`.

---

## Runbook 5: Celery AsyncTask Event Loop Collision Resolution

### Symptom
Celery worker processes executing ingestion or background tasks crash with:
```text
RuntimeError: This event loop is already running
or:
RuntimeError: Cannot run the event loop while another loop is running
```

### Root Cause
When asynchronous Python functions (`asyncio`) are called inside Celery tasks via `asyncio.run()`, collisions occur if Celery's worker thread or parent framework has already initialized an active event loop in that thread context.

### Architectural Solution (`backend/tasks/ingest_tasks.py`)
All Celery tasks inherit from `AsyncTask` and execute coroutines via `self.run_async()`:

```python
class AsyncTask(celery_app.Task):
    _loop = None

    def run_async(self, coro):
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        # If an event loop is already running in this thread, execute
        # the coroutine in an isolated single-worker ThreadPoolExecutor
        if running_loop and running_loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()

        # Otherwise run on the managed instance loop
        return self.loop.run_until_complete(coro)
```

**Rule**: Never call `asyncio.run()` directly inside Celery tasks; always invoke `self.run_async(coro)`.

---

## Runbook 6: Neo4j / Memgraph Backup, Restore & Cross-Tree Drift Checks

### 6.1 Database Backup & Restore

```bash
# --- Neo4j Offline Dump (Host / Local Container) ---
docker exec -it neo4j neo4j-admin database dump neo4j --to-path=/var/backups/mukthiguru/neo4j

# --- Neo4j Offline Load / Restore ---
docker exec -it neo4j neo4j-admin database load neo4j \
  --from-path=/var/backups/mukthiguru/neo4j \
  --overwrite-destination=true

# --- Bolt-Based Migration & Verification (Works with Memgraph & Railway) ---
# Recommended for cloud environments where docker exec is unavailable
python -m scripts.ops.migrate_neo4j_to_memgraph --verify-only
```

### 6.2 Cross-Tree Script Drift Verification (`backend/tests/test_repo_layout.py`)

AskMukthiGuru maintains two separate script trees:
* `scripts/`: Repository-level tooling, operations runbooks, and audit scripts.
* `backend/scripts/`: Backend modules executed with `python -m scripts.<name>` inside `/app`.

Because `docker-compose.yml` mounts root `scripts/` at `/app/scripts`, any file duplicated across both directories must remain **byte-identical** to prevent silent behavior divergence.

```bash
# Run cross-tree drift test
pytest backend/tests/test_repo_layout.py::test_cross_tree_shared_scripts_are_identical
```

If drift is detected:
1. Identify the canonical version in `backend/scripts/`.
2. Synchronize the content to root `scripts/`.
3. Commit both files atomically.

---

## 7. Cross-Reference Navigation

* [Architecture: Overview](Architecture-Overview)
* [Data: Qdrant Vector Store Architecture](Data-Qdrant-Vector-Store)
* [Data: Neo4j Knowledge Graph](Data-Neo4j-Knowledge-Graph)
* [Quality Benchmarks & Evaluation](Quality-Evaluation-and-Benchmarks)
* [Operations, Deployment & CI Gates](Operations-Deployment-and-CI)
