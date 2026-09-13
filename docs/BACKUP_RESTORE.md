# Backup & Restore — Qdrant + Neo4j (local disk)

Schedule: `infrastructure/cron/mukthiguru-backup` (02:00 Qdrant, 02:30 Neo4j, retention 7, disk only — no S3 per policy). Install note lives in that file's header.

Scripts (existing, unmodified): `scripts/ops/backup_qdrant.py`, `scripts/ops/backup_neo4j.py`. Both write a `.sha256` sidecar per artifact and prune beyond retention.

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

## R5 load attempt — 2026-09-13 (20 concurrent users)

Nightly workflow path (`.github/workflows/nightly-load.yml`, locust chat sweep
at `-u 20`): **BLOCKED** — `locust` module absent in both `backend/.venv` and
system python, and package installs are forbidden in this sandbox, so the exact
workflow sweep could not run here. Next step: run it in CI or a dependency-
complete image where `requirements-dev.txt` installs locust.

Substitute transport-only evidence (NOT load proof): 20-way stdlib concurrent
`GET /api/healthz` against the live compose backend (`ready=true`,
`status=healthy`): `n=20 ok=20 fail=0 wall=0.04s min=16ms p50=20ms max=22ms`.
Chat-path p95 at 20 users remains unmeasured.
