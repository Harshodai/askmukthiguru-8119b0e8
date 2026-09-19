# Backup & Restore — Qdrant, Postgres (Supabase), Graph (local & cloud)

Schedule:
- **Linux host**: `infrastructure/cron/mukthiguru-backup` (02:00 Qdrant, 02:30 Neo4j, retention 7, disk only).
- **macOS host**: `infrastructure/launchd/com.mukthiguru.backup-qdrant.plist` (02:00 daily Qdrant snapshot).
- **Supabase Postgres (Free Path)**: `.github/workflows/backup.yml` (03:00 UTC daily cron via Supabase CLI).

Scripts:
- Qdrant: `scripts/ops/backup_qdrant.py` (REST API snapshots, SHA-256 sidecars, retention pruning).
- Graph: `backend/scripts/ops/migrate_neo4j_to_memgraph.py` (Bolt-based export/import/verify for Neo4j 5.x & Memgraph 3.x).
  *Note on `scripts/ops/backup_neo4j.py`*: Uses `docker exec` + `neo4j-admin`/APOC. It works against **neither Memgraph nor Railway**. Do NOT rely on it for graph coverage in cloud or Memgraph deployments.
- Supabase: `.github/workflows/backup.yml` (Supabase CLI dumps: roles, schema, data).

## Qdrant restore

Per upstream snapshots docs, a collection snapshot restores via upload with
`priority=snapshot` (snapshot wins over existing data), or via
`PUT /collections/{name}/snapshots/recover` with `{"location": ..., "priority": "snapshot"}`.
Snapshot and server must share the minor version (here: snapshot predates server 1.18.0, restore accepted).

```bash
# 1. Create the target collection matching the SNAPSHOT's vector config
curl -X PUT http://localhost:6333/collections/<name> \
  -H 'Content-Type: application/json' \
  -d '{"vectors": {"size": 1024, "distance": "Cosine"}}'
# 2. Upload with snapshot priority
curl -X POST 'http://localhost:6333/collections/<name>/snapshots/upload?priority=snapshot' \
  -H 'Content-Type: multipart/form-data' \
  -F 'snapshot=@/var/backups/mukthiguru/qdrant/<collection>_<ts>.snapshot'
# 3. Poll until status == green, confirm points_count, drop scratch on success
```

Gotcha (found 2026-09-13): `backup_qdrant.py --verify-only` mirrors the *live*
source collection's config (`on_disk: true`) for its temp collection, but the
2026-08-01 snapshot stores `on_disk: null` — Qdrant 400s the upload as
"Snapshot is not compatible with existing collection". Workaround for old
snapshots: create the scratch collection without `on_disk` (step 1 above).
Do not "fix" by editing the snapshot; fix belongs in the verify helper, out of scope here.

## Neo4j restore

Per upstream ops manual, Community restores offline via `neo4j-admin database load`
(the dump equivalent of `neo4j-admin database dump`), Enterprise additionally via
`neo4j-admin database restore`. Replacing a database requires it stopped first plus
`--overwrite-destination=true`; dump/load round-trips data only (users/roles metadata excluded).

```bash
# Offline load of a .dump artifact (stop the DB first when replacing):
neo4j-admin database load neo4j --from-path=/var/backups/mukthiguru/neo4j --overwrite-destination=true
# Cypher-format backups replay through cypher-shell against a running instance.
```

## Scratch-restore proof — 2026-09-13 (local stack, Qdrant 1.18.0)

Qdrant — real artifact `backups/qdrant/guru_tone_podcast_20260801_094334.snapshot`
(+ valid `.sha256` sidecar) restored to scratch collection `_dbg_restore`:

```
$ backend/.venv/bin/python scripts/ops/backup_qdrant.py --verify-only \
    backups/qdrant/guru_tone_podcast_20260801_094334.snapshot --source-collection guru_tone_podcast
[Verify] Checking guru_tone_podcast_20260801_094334.snapshot ...
  [+] Checksum OK
  [+] Archive OK (12 entries)
  [*] Running test-restore to temporary collection ...
  [-] FAIL: Test-restore exception: HTTP Error 400: Bad Request
```

Root-caused to the on-disk mismatch above (server error body:
"Snapshot is not compatible with existing collection ... on_disk: Some(true) ...
Snapshot Vectors: ... on_disk: None"). Manual scratch restore with a
snapshot-matching collection:

```
recreated without on_disk
upload: {"result":true,"status":"ok",...}
STATUS green points_count= 157
scratch collection dropped
```

Result: **PASS** — upload accepted, status green, 157 points, scratch collection
dropped, no leftover `_verify_*`/`_dbg_*` collections. Live collections untouched.

Neo4j — real artifact `backups/neo4j/neo4j_20260801_151758.cypher`:

```
$ NEO4J_PASSWORD=dryrun-proof-only backend/.venv/bin/python scripts/ops/backup_neo4j.py \
    --verify-only backups/neo4j/neo4j_20260801_151758.cypher
[Verify] Checking neo4j_20260801_151758.cypher ...
  [+] Checksum OK
  [+] Contains valid Cypher statements.
```

Result: **PASS** (checksum + Cypher content; full `.dump` load stays an offline
maintenance-window operation per the procedure above).

## R5 re-proof — 2026-09-13 (local stack, Qdrant 1.18.0, base bf7ada3d)

Policy: backups STAY local-cron (`infrastructure/cron/mukthiguru-backup`); no
Celery Beat move (`celery_config.py` `beat_schedule` covers win-back/memory
only). Cron install state: `/etc/cron.d/mukthiguru-backup` and
`/etc/mukthiguru/backup.env` both ABSENT on this host — RPO unbounded until
the manual sudo install in the cron header is performed.

Qdrant — same real artifact as above, fresh run into throwaway `_r5_restore`
(created WITHOUT `on_disk` per the gotcha above; live `guru_tone_podcast`
holds 12 pts with `on_disk: true` and was untouched):

```
create (1024/Cosine, no on_disk): {"result":true,"status":"ok"}
upload ?priority=snapshot: {"result":true,"status":"ok"}
status= green points= 157
scroll limit=1: 1 pt, id 00c75bf1-c3d5-5ff4-9a5e-984f17960736
search with that point's vector, limit=1: 1 hit, same id, score= 1.0
DELETE collection: ok; scratch_gone= True
```

Result: **PASS** — green, 157 points, scroll + vector search both hit, scratch
dropped, no leftover collections.

Neo4j — `NEO4J_PASSWORD=dryrun-proof-only ... backup_neo4j.py --verify-only
backups/neo4j/neo4j_20260801_151758.cypher` → Checksum OK + valid Cypher,
exit 0. Full offline `neo4j-admin database load` NOT attempted (live single-DB
Community instance; replacing it is an outage). Next step: replay/load against
a stopped scratch instance in a maintenance window.

## F-BKP-1 fix + restore drill — 2026-09-16 (Phase 0 item 4)

**Bug**: `infrastructure/cron/mukthiguru-backup:22` and `scripts/ops/backup_qdrant.py`'s
`DEFAULT_COLLECTION` both said `spiritual_wisdom` — a collection that no
longer exists on this host (`GET /collections` lists only
`spiritual_wisdom_contextual` and dated `spiritual_wisdom_ingest_backup_*`
snapshots). The nightly cron job was backing up nothing; a restore from it
would have created an empty collection while the actual production data
(`spiritual_wisdom_contextual`, 12,904 points) was never captured. **Fixed**:
both now say `spiritual_wisdom_contextual`.

**Restore drill, run for real against the live local stack** (not the older
`guru_tone_podcast`/2026-08-01 artifacts referenced above — a fresh backup of
the actual live, now-correctly-named collection):

```
$ backend/.venv/bin/python scripts/ops/backup_qdrant.py \
    --collection spiritual_wisdom_contextual --retention 7
[+] Remote snapshot created: spiritual_wisdom_contextual-...-2026-09-16-15-32-41.snapshot
[+] Saved backups/qdrant/spiritual_wisdom_contextual_20260916_153241.snapshot (182.06 MB)
[+] Checksum OK
[+] Archive OK (14 entries)
[+] Test-restore OK
[+] Point count matches: 12904
[✅] Backup verified
```

Then, independently of the script's own internal test-restore, a second
from-scratch restore into a throwaway collection (`_p0_bkp1_restore_drill`,
created only from this artifact — never touching live) proving it can
actually answer a query:

```
upload ?priority=snapshot: {"result": true, "status": "ok"}
status -> green, points_count = 12904 (matches live exactly)
scrolled point 00002161-94f2-515c-906c-ca271e50cd4e:
  payload includes real doctrine text ("[Source: Oneness Abundance
  festival | Riddhi - Siddhi -Buddhi | Ekam | Speaker: Ekam / O&O
  Academy | Topic: Divine Prote...")
query (that point's own dense vector, using=dense, limit=3):
  hit 1: same point id, score=1.0000005
  hit 2: e3d42ff9-..., score=0.890
  hit 3: 3e6c38c1-..., score=0.871
scratch collection dropped; live spiritual_wisdom_contextual points_count
  confirmed unchanged at 12904 afterward.
```

**Result: PASS** — a semantic query was served from data restored from the
cron artifact alone, on the correctly-named live collection. The backup is
no longer a ritual.

Nightly workflow path (`.github/workflows/nightly-load.yml`, locust chat sweep
at `-u 20`): **BLOCKED** — `locust` module absent in both `backend/.venv` and
system python, and package installs are forbidden in this sandbox, so the exact
workflow sweep could not run here. Next step: run it in CI or a dependency-
complete image where `requirements-dev.txt` installs locust.

Substitute transport-only evidence (NOT load proof): 20-way stdlib concurrent
`GET /api/healthz` against the live compose backend (`ready=true`,
`status=healthy`): `n=20 ok=20 fail=0 wall=0.04s min=16ms p50=20ms max=22ms`.
Chat-path p95 at 20 users remains unmeasured.

---

## Graph migration over Bolt — 2026-09-19

`scripts/ops/backup_neo4j.py` covers neither Memgraph nor Railway: it shells out to
`neo4j-admin`/APOC through `docker exec`, so it needs a local Neo4j container and a
writable volume. Neither exists on Railway, and Memgraph has no `neo4j-admin` at all.
That left the graph with no migration or restore path.

`backend/scripts/ops/migrate_neo4j_to_memgraph.py` closes it. It speaks only Bolt, so
it works against Neo4j 5.x and Memgraph 3.x in either direction and needs no container
access, no volume mount, and no server-side tooling.

```bash
cd backend
PY=.venv/bin/python
M="$PY -m scripts.ops.migrate_neo4j_to_memgraph"

$M export   --uri bolt://localhost:7687 --user neo4j --password "$NEO4J_PASSWORD" \
            --output backups/neo4j/graph_dump.json
$M import   --uri bolt://<target>:7687  --user neo4j --password "$TARGET_PASSWORD" \
            --input  backups/neo4j/graph_dump.json
$M verify   --uri bolt://<target>:7687  --user neo4j --password "$TARGET_PASSWORD" \
            --against backups/neo4j/graph_dump.json     # exit 1 on any mismatch
$M finalize --uri bolt://<target>:7687  --user neo4j --password "$TARGET_PASSWORD"
```

Four properties make this safe to run against a remote target over a flaky link:

- **Idempotent.** `import` MERGEs on migration markers rather than CREATEing, so a
  re-run after a partial failure repairs the gap instead of duplicating the graph.
- **Markers survive `import` on purpose.** They are what makes the retry safe, so
  they are stripped by a separate `finalize` step. Run it only after `verify` passes.
- **`verify` can go red.** It compares node count, relationship count, the per-label
  histogram and the per-relationship-type histogram against the dump's manifest, names
  every discrepancy, and exits non-zero. Totals alone would miss a graph that has the
  right number of the wrong things.
- **Edge identity is explicit.** Edges MERGE on their source `elementId`, not on
  `(start, type, end)`. The live graph contains a parallel same-type edge pair that a
  naive MERGE silently collapses into one.

### Railway

Bolt (7687) is not routable from outside Railway's private network, and
`railway run` containers mount volumes read-only — which is why an in-container
restore is not an option either. Create a **TCP proxy** on the graph service's port
7687, run the migration against the `*.proxy.rlwy.net` endpoint it returns, then
**remove the proxy** — while it exists the database is exposed to the internet.

`backend/scripts/ops/railway_graph_migrate.sh` wraps the five steps, refuses a target
that already holds nodes unless `ALLOW_NONEMPTY_TARGET=1`, and will not finalize if
verify fails.

Note the live Railway graph service is `gb-neo4j-railway-template` — **Neo4j**, not
Memgraph, despite what most of this repo's docs assume. The script handles both.

### Drill — 2026-09-19, performed

Source: live local Memgraph 3.13.1, **6,430 nodes / 4,188 relationships**.

| Step | Target | Result |
| :--- | :--- | :--- |
| export | — | 6430 / 4188 in 0.34s, 7.0 MB, all 4,188 `rel_id`s unique |
| import | Memgraph 3.13.1 (scratch, :7690) | 6430 / 4188 in **0.53s** |
| verify | " | PASSED, exit 0 |
| import ×2 | " | still 6430 / 4188 — **not** doubled |
| parallel edges | " | 1 group / 2 edges, matching source exactly |
| *delete 7 nodes + 3 edges* | " | verify **FAILED**, exit 1, named every missing type |
| import (repair) | " | back to 6430 / 4188; verify exit 0 |
| finalize | " | 0 markers left; `Teacher` properties byte-identical to source |
| import | **Neo4j 5.17.0** (scratch, :7691) | 6430 / 4188 in 2.51s |
| verify | " | PASSED, exit 0 |
| indexes | " | all 8 application indexes created with Neo4j DDL, + marker index |
| finalize | " | 0 markers, marker index dropped, 6430 / 4188 intact |

The live source graph was untouched throughout (export is read-only): 6430 / 4188,
0 markers.

Regression tests: `backend/tests/test_graph_migration.py` (15 tests). Negative control
performed — removing the Cypher identifier guard, the edge-identity marker, and the
histogram comparison each failed exactly the test that covers it, and nothing else.

---

## Supabase Postgres Free Path — Daily Dumps via GitHub Actions

Production Supabase is on the **Free tier** and has zero automated platform backups. Upgrading to Pro is explicitly rejected per project constraints. We use the official Supabase CLI database dump workflow:

### Daily Automated Workflow: `.github/workflows/backup.yml`
- **Schedule**: Daily at `03:00 UTC` + manual trigger via `workflow_dispatch`.
- **Secret**: `SUPABASE_DB_URL` (direct/session connection string on port 5432).
- **Privacy Security Gate**: Fails loudly if the repository is public (`github.event.repository.private == false`). Storing unencrypted database dumps in public GitHub workflow artifacts is strictly forbidden.
- **Dumps performed**:
  ```bash
  # 1. Roles dump
  supabase db dump --db-url "$SUPABASE_DB_URL" -f roles.sql --role-only
  # 2. Schema dump
  supabase db dump --db-url "$SUPABASE_DB_URL" -f schema.sql
  # 3. Data dump (using COPY protocol for fast restore)
  supabase db dump --db-url "$SUPABASE_DB_URL" -f data.sql --data-only --use-copy
  ```
- **Packaging**: Produces a timestamped tar archive `supabase_backup_<timestamp>.tar.gz` with a `.sha256` sidecar, retained for 7 days in workflow artifacts.

### Supabase Restore Procedure
To restore into a fresh Supabase or Postgres database:
```bash
# 1. Extract backup
tar -xzf supabase_backup_<timestamp>.tar.gz

# 2. Restore database roles first
psql "$TARGET_DB_URL" -f roles.sql

# 3. Restore schema
psql "$TARGET_DB_URL" -f schema.sql

# 4. Restore data
psql "$TARGET_DB_URL" -f data.sql
```

---

## macOS Host Qdrant Automation: launchd Agent

This host runs macOS, where `/etc/cron.d` is not active. The backup agent is configured as a launchd LaunchAgent:

- **Plist**: `infrastructure/launchd/com.mukthiguru.backup-qdrant.plist`
- **Schedule**: Daily at `02:00` local time.
- **Log output**: `backups/qdrant/backup-qdrant.log` and `backups/qdrant/backup-qdrant-error.log`

### Installation Commands
```bash
# 1. Copy plist to user LaunchAgents directory:
cp infrastructure/launchd/com.mukthiguru.backup-qdrant.plist ~/Library/LaunchAgents/

# 2. Load the agent into launchd:
launchctl load ~/Library/LaunchAgents/com.mukthiguru.backup-qdrant.plist

# 3. Verify agent is loaded:
launchctl list | grep com.mukthiguru.backup-qdrant

# 4. (Optional) Trigger manual run to verify:
launchctl start com.mukthiguru.backup-qdrant
```

---

## Graph Backup Realities: `backup_neo4j.py` vs `migrate_neo4j_to_memgraph.py`

**Crucial Operational Clarification:**
`scripts/ops/backup_neo4j.py` executes `docker exec` against a local Neo4j container to invoke `neo4j-admin database dump` or APOC procedures. It requires:
1. Direct `docker exec` access to a container named `mukthiguru-neo4j`.
2. A writable mounted container volume.

Consequently, `scripts/ops/backup_neo4j.py` works against **neither Memgraph nor Railway**:
- Memgraph does not have `neo4j-admin` CLI.
- Railway container volumes are mounted read-only and do not permit external `docker exec`.

**Do not treat `backup_neo4j.py` as providing graph coverage.**
The true, portable graph backup and migration utility is `backend/scripts/ops/migrate_neo4j_to_memgraph.py`, which operates purely over the Bolt protocol (7687) and is fully verified across both Neo4j 5.x and Memgraph 3.x.

---

## Workstream W4 Qdrant Restore Drill — 2026-09-19 (Local Stack, Qdrant 1.18.0)

Conducted a live from-scratch restore drill of the production snapshot:
`backups/qdrant/spiritual_wisdom_contextual_20260916_153241.snapshot` (182.06 MB)
into an isolated throwaway collection (`_w4_scratch_restore_drill`), without affecting the live collection (`spiritual_wisdom_contextual`, 12,904 points).

### Exact Execution Commands
```bash
# Run scratch restore drill
backend/.venv/bin/python scratch/run_drill.py
```

### Verbatim Drill Output
```
=== Workstream W4 Qdrant Restore Drill ===
Time: 2026-09-19 05:32:05 UTC
Artifact: backups/qdrant/spiritual_wisdom_contextual_20260916_153241.snapshot (182.06 MB)
[1] Live collection 'spiritual_wisdom_contextual' points_count = 12904
[2] Creating scratch collection '_w4_scratch_restore_drill' ...
    Create response: {'result': True, 'status': 'ok', 'time': 0.512563209}
[3] Uploading snapshot to '_w4_scratch_restore_drill' with priority=snapshot ...
    Upload response: {'result': True, 'status': 'ok', 'time': 4.737858752}
[4] Polling collection status ...
    Status reached green after 48s
[5] Restored collection points_count = 12904
    [+] Point count matches live collection exactly: 12904 points
[6] Scrolling 1 point from restored collection ...
    Sample Point ID: 00002161-94f2-515c-906c-ca271e50cd4e
    Payload keys: ['text', 'source_url', 'title', 'speaker', 'topic', 'content_type', 'source_type', 'language', 'tags', 'chunk_index', 'raptor_level', 'source_version', 'corpus_id', 'ingested_at', 'authority_tier', 'assistant_slug', 'assistant_scope_version', 'video_id', 'channel_name', 'published_at', 'duration', 'thumbnail_url', 'view_count', 'parent_id', 'parent_text', 'is_child', 'important_kwd', 'tenant_id', 'domain_rights_status', 'teacher_id', 'teacher_ids', 'provenance', 'provenance_rationale']
    Text snippet: "[Source: Oneness Abundance festival | Riddhi - Siddhi -Buddhi | Ekam | Speaker: Ekam / O&O Academy | Topic: Divine Prote..."
    Topic: "Divine Protection/Guidance"
    Source URL: https://www.youtube.com/watch?v=1e0yk20hF7Y
[7] Querying restored collection with sample dense vector ...
    Vector query returned 3 hits:
      Hit 1: id=00002161-94f2-515c-906c-ca271e50cd4e, score=1.010189
      Hit 2: id=e3d42ff9-d41c-51e2-9732-540521b43781, score=0.8956909
      Hit 3: id=3e6c38c1-5205-5d1a-a459-9adef4e69489, score=0.87399673
    [+] Top hit matches sample point ID with cosine similarity 1.010189
[8] Dropping scratch collection '_w4_scratch_restore_drill' ...
    Delete response: {'result': True, 'status': 'ok', 'time': 0.712938042}
    Scratch collection gone: True
[9] Live collection 'spiritual_wisdom_contextual' points_count after drill = 12904
    [+] Live collection verified completely intact and untouched!

[✅] RESTORE DRILL SUCCESS: Verified 12,904 points restored, queried, and verified.
```

### Result: PASS
1. Snapshot restored 100% of the 12,904 points with green status.
2. Doctrine payload verified intact (`[Source: Oneness Abundance festival ...]`).
3. Dense vector search successfully resolved the target point with cosine score 1.010 (int8 scalar quantization variance).
4. Scratch collection cleanly dropped; live production collection confirmed unchanged at 12,904 points.

---

## Free-Tier Leaked-Password Protection (k-Anonymity)

Supabase Pro includes built-in leaked password checks, but on the Free plan, this feature is unavailable. We implemented client-side k-anonymity breach verification via HaveIBeenPwned's unauthenticated Range API:

- **Endpoint**: `https://api.pwnedpasswords.com/range/{sha1-prefix-5}`
- **Security Invariant**: Neither the password nor the full SHA-1 hash is EVER sent over the network. Only the first 5 hexadecimal characters of the SHA-1 hash are sent. Suffix matching (35 hex chars) occurs locally in memory.
- **Header**: `Add-Padding: true` prevents response-length analysis attacks.
- **Integration**:
  - `src/lib/passwordBreachCheck.ts`: Core k-anonymity utility.
  - `src/pages/AuthPage.tsx`: Invoked before `supabase.auth.signUp()`.
  - `src/pages/ResetPasswordPage.tsx`: Invoked before `supabase.auth.updateUser()`.
- **User Feedback**: If breached, returns:
  > *"This password has appeared in a known data breach. For your security, please choose a stronger, unique password."*
- **Test Coverage**:
  - `src/lib/passwordBreachCheck.test.ts`: 9 unit tests verifying k-anonymity contract, prefix extraction, breach detection on "password123", and clean password acceptance.
  - `src/test/AuthPageBreachCheck.test.tsx`: Component integration tests verifying rejection before signup call.

