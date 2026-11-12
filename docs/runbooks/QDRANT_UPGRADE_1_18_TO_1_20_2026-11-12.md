# Qdrant upgrade runbook: server 1.18.0 to 1.19.2 to 1.20.0 (2026-11-12)

Status: PLAN ONLY. Nothing here has been run. Verdict stays NO-GO until the clean-Docker run on final main is graded.
Harsha runs every command. No two threads may run Docker at once.

## 1. Versions (verified 2026-11-12 from official pages)

| Item | Repo / live today | Latest stable | Source |
|---|---|---|---|
| Qdrant server | `v1.18.0` live (`GET /` on :6333 returns 1.18.0) | `v1.20.0` (22 Oct 2026, flagged "Latest"); latest 1.19 patch `v1.19.2` (5 Oct); latest 1.18 patch `v1.18.3` (17 Jul) | https://github.com/qdrant/qdrant/releases |
| qdrant-client | pinned `1.18.0` (`backend/requirements.txt:39`, `requirements.lock:697`); host `backend/.venv` has `1.19.1` | `1.20.0` on PyPI (supports server 1.20); 1.19.1 is latest 1.19 | https://pypi.org/project/qdrant-client/ , https://github.com/qdrant/qdrant-client/releases |

Upgrade rules (official, from the 1.19 and 1.20 release posts https://qdrant.tech/blog/qdrant-1.19.x/ and https://qdrant.tech/blog/qdrant-1.20.x/):
- One minor version at a time, via the latest patch of each intermediate minor: 1.18.x to 1.19.2 to 1.20.0. Do not jump 1.18 to 1.20.
- Storage is only compatible across one minor version. Snapshots restore only onto the same or the next minor (https://qdrant.tech/documentation/migration-recovery-options/). Therefore a 1.18 snapshot restores onto 1.18 or 1.19, NOT 1.20.
- Downgrading an image on a migrated volume is not supported. Rollback = restore the pre-upgrade volume copy.
- Client SDK should stay within one minor of the server.

Recommendation: do the upgrade only after the graded run is settled, or accept the baseline change. Safest first step is 1.19.2 (the mature patch), verify, soak, then 1.20.0 (3 weeks old, no patch yet).

## 2. Breaking changes that touch this repo (checked against code)

Server 1.19: legacy REST `/search`, `/recommend`, `/discover` removed. Repo check: no live code calls `client.search`/`recommend`/`search_groups` (only a docstring at `backend/app/tracing.py:69` and `backend/benchmarks/run_ralph.py:106`, a benchmark script; fix that script before using it). Production paths use `query_points`. Per-component `on_disk`/`always_ram`/`on_disk_payload` flags are deprecated but still work; live v10 has `on_disk_payload: true`, no change needed.

Server 1.20: `enforce_internal_auth` and `p2p` changes are cluster-only (this is single node, not affected). Inline-storage memory placement now follows `hnsw_config.memory` (default `cached`); v10 uses plain dense plus sparse with no quantization and no inline storage, so no RAM change expected. UNPROVEN: check `docker stats` after the upgrade; Qdrant container limit is 3 GiB (`backend/docker-compose.yml:152` block).

Client 1.19: `search*`, `recommend*` deprecated; `add`/`query` removed. Client 1.20 (matters for the ops scripts):
- update ops reject an EMPTY points list or empty selector with `ValueError`. Checked and already guarded (no change needed): `backend/tasks/cache_maintenance_tasks.py:55` (`if not points: break` precedes the delete) and `backend/app/api/ingest.py:785` (`if not res.point_ids` precedes `set_payload`). NOT checked: the ops scripts `scripts/ops/backfill_language.py:90`, `corpus_rights_sweep.py:165`, `eu_ai_act_backfill.py`, `repair_*.py`, `fix_teacher_tags.py`; read each for an empty-list path before running it on client 1.20.0 (UNPROVEN).
- uploads raise `ValueError` when `ids`/`payload` are shorter than vectors; `create_payload_index` default text tokenizer is `word` (our indexes are keyword/integer/bool, unaffected).
- Alias, scroll, `create_payload_index`, sparse vectors, collection config: no removal or deprecation listed in client or server notes for 1.19 or 1.20.

Client skew today: the host venv (1.19.1) differs from the container (1.18.0). Lesson from `audits/evidence/first_person_v11_speaker_backfill_and_build_2026-10-31.md`: a second client wrote tags. Make host and container the same version when bumping.

## 3. Files that carry the server tag (bump all together; `backend/tests/test_k8s_reference_drift.py` fails on drift)

```
backend/docker-compose.yml:152
docker-compose.prod.yml:141
backend/infrastructure/k8s.yaml:127
infrastructure/k8s_deployment.yaml:363
infrastructure/k8s/helm/mukthiguru/values.yaml:172   (tag: v1.18.0)
.github/workflows/fixture-stores.yml:37
```

Stale docs, not code: `docs/kubernetes-deployment.md:217` says v1.17.1, `backend/README.md:206-216` says v1.13.2.
Client pin lives in `backend/requirements.txt:39`; regenerate the lock, never hand-edit: `uv pip compile backend/requirements.txt -o backend/requirements.lock --python-version 3.12`.
No pin edits were made: bumping them now would change the stack baseline in the middle of the graded-run prep and the bump is two steps (1.19.2 then 1.20.0).

## 4. Pre-checks (read-only, safe anytime)

```bash
cd ~/Public/askmukthiguru-8119b0e8/backend
export PATH="$HOME/.docker/bin:$PATH"
docker volume ls | grep qdrant                 # expect backend_qdrant_data; use the real name below
curl -s localhost:6333/ ; echo                 # version 1.18.0
curl -s localhost:6333/aliases ; echo          # first_person -> first_person_v10
```
Local Qdrant has no API key set (unauthenticated curl worked). If you set one, add `-H "api-key: $QDRANT_WRITE_API_KEY"` to every curl.

## 5. Backup (do before ANY image change)

5a. Record the baseline manifest (counts for every collection plus the alias).
```bash
mkdir -p ~/qdrant_upgrade_20261112 && cd ~/qdrant_upgrade_20261112
curl -s localhost:6333/aliases > aliases.json
for c in $(curl -s localhost:6333/collections | python3 -c "import sys,json;print(' '.join(x['name'] for x in json.load(sys.stdin)['result']['collections']))"); do
  n=$(curl -s localhost:6333/collections/$c | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['points_count'],len(r['payload_schema']))")
  echo "$c $n"
done | tee baseline_counts.txt
grep -E "^first_person_v10 " baseline_counts.txt   # expect: first_person_v10 4226 24
```

5b. Snapshot the live collections and download them (aliases are not inside collection snapshots; `aliases.json` above is the record).
```bash
cd ~/qdrant_upgrade_20261112
for c in first_person_v10 first_person_v11; do
  name=$(curl -s -X POST "localhost:6333/collections/$c/snapshots?wait=true" | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['name'])")
  curl -s -o "$name" "localhost:6333/collections/$c/snapshots/$name"
  curl -s localhost:6333/collections/$c/snapshots | python3 -c "import sys,json;[print(s['name'],s['checksum']) for s in json.load(sys.stdin)['result'] if s['name']=='$name']"
  shasum -a 256 "$name"; ls -l "$name"
done
```
Check: the checksum Qdrant prints should equal the `shasum -a 256` of the downloaded file. If they differ (UNPROVEN which algorithm Qdrant reports), keep both files and rely on 5c.

5c. Cold copy of the whole volume (the only backup that survives a storage migration; rollback depends on it). Stops Qdrant, so the backend loses vector search for about a minute.
```bash
cd ~/Public/askmukthiguru-8119b0e8/backend
docker compose -p backend stop backend qdrant
docker run --rm -v backend_qdrant_data:/data -v ~/qdrant_upgrade_20261112:/backup alpine \
  sh -c 'tar czf /backup/qdrant_data_v1.18.0.tgz -C /data . && ls -l /backup/qdrant_data_v1.18.0.tgz'
tar tzf ~/qdrant_upgrade_20261112/qdrant_data_v1.18.0.tgz | head -5     # must list files
(cd ~/qdrant_upgrade_20261112 && shasum -a 256 qdrant_data_v1.18.0.tgz | tee qdrant_data_v1.18.0.sha256)
docker compose -p backend up -d --no-deps qdrant backend
```
If `docker volume ls` showed a different volume name, use it in place of `backend_qdrant_data`. Copy the folder off the Mac as well (open item in CLAUDE.md).

## 6. Restore test (scratch Qdrant, separate port, never touches live data)

Prove the snapshot restores on the same minor, then on the next minor (the upgrade path).
```bash
cd ~/qdrant_upgrade_20261112
SNAP=$(ls first_person_v10-*.snapshot | tail -1)
for V in v1.18.0 v1.19.2; do
  rm -rf scratch_$V && mkdir scratch_$V
  docker run -d --name qd_scratch_$V -p 127.0.0.1:6343:6333 -v "$PWD/scratch_$V:/qdrant/storage" qdrant/qdrant:$V
  sleep 8
  curl -s -X POST "localhost:6343/collections/first_person_v10/snapshots/upload?priority=snapshot&wait=true" \
       -H 'Content-Type: multipart/form-data' -F "snapshot=@$SNAP"
  curl -s localhost:6343/collections/first_person_v10 | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print('$V',r['status'],r['points_count'],len(r['payload_schema']))"   # expect green 4226 24
  curl -s -X POST localhost:6343/collections/first_person_v10/points/count -H 'content-type: application/json' \
       -d '{"exact":true,"filter":{"must":[{"key":"record_type","match":{"value":"parent_unit"}}]}}'
  docker rm -f qd_scratch_$V
done
```
Expected: both print `green 4226 24`. Do NOT test a 1.18 snapshot on 1.20: it is documented as unsupported.

## 7. Upgrade (step 1: 1.19.2)

```bash
cd ~/Public/askmukthiguru-8119b0e8
sed -i '' 's#qdrant/qdrant:v1.18.0#qdrant/qdrant:v1.19.2#' backend/docker-compose.yml docker-compose.prod.yml backend/infrastructure/k8s.yaml infrastructure/k8s_deployment.yaml .github/workflows/fixture-stores.yml
sed -i '' '172s#tag: v1.18.0#tag: v1.19.2#' infrastructure/k8s/helm/mukthiguru/values.yaml   # line 172 is the qdrant block
git diff --stat
cd backend && docker compose -p backend pull qdrant
docker compose -p backend up -d --no-deps --force-recreate qdrant
until curl -sf localhost:6333/readyz >/dev/null; do sleep 2; done; curl -s localhost:6333/ ; echo   # version 1.19.2
```
Verify (section 8). Soak, then repeat the same block with `v1.19.2` to `v1.20.0` for step 2. Run `cd backend && .venv/bin/pytest tests/test_k8s_reference_drift.py tests/test_image_pins.py -q` after each tag edit (drift guard).

Client bump (after the server matches): set `qdrant-client==1.19.1` for step 1 or `==1.20.0` for step 2 in `backend/requirements.txt`, regenerate the lock with the uv command in section 3, rebuild the backend image, and install the same version in `backend/.venv` (`backend/.venv/bin/pip install qdrant-client==<ver>`). Guard the empty-list callers first (section 2).

## 8. Verification (after each step)

```bash
cd ~/qdrant_upgrade_20261112
curl -s localhost:6333/ ; echo
curl -s localhost:6333/aliases ; echo     # must equal aliases.json: first_person -> first_person_v10
for c in $(curl -s localhost:6333/collections | python3 -c "import sys,json;print(' '.join(x['name'] for x in json.load(sys.stdin)['result']['collections']))"); do
  n=$(curl -s localhost:6333/collections/$c | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['points_count'],len(r['payload_schema']))"); echo "$c $n"
done > after_counts.txt
diff baseline_counts.txt after_counts.txt && echo COUNTS_IDENTICAL
curl -s localhost:6333/collections/first_person | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['status'],r['points_count'])"   # green 4226 (read through the alias)
cd ~/Public/askmukthiguru-8119b0e8 && make verify-stack-fresh
docker stats --no-stream mukthiguru-qdrant      # RSS vs the 3 GiB limit
```
Pass = `COUNTS_IDENTICAL`, alias unchanged, v10 `green 4226` with 24 indexes, v11 4360, then a real chat round-trip against a first-person question. UNPROVEN until Harsha runs it.

## 9. Rollback

Rollback = old image plus the cold volume copy (a migrated volume cannot be reopened by the older image).
```bash
cd ~/Public/askmukthiguru-8119b0e8
git checkout -- backend/docker-compose.yml docker-compose.prod.yml backend/infrastructure/k8s.yaml infrastructure/k8s_deployment.yaml infrastructure/k8s/helm/mukthiguru/values.yaml .github/workflows/fixture-stores.yml
cd backend
docker compose -p backend stop backend qdrant && docker compose -p backend rm -f qdrant
(cd ~/qdrant_upgrade_20261112 && shasum -a 256 -c qdrant_data_v1.18.0.sha256) || echo "STOP: backup corrupt"
# DESTRUCTIVE: deletes the upgraded volume. Only after the checksum above printed OK.
docker volume rm backend_qdrant_data && docker volume create backend_qdrant_data
docker run --rm -v backend_qdrant_data:/data -v ~/qdrant_upgrade_20261112:/backup alpine sh -c 'tar xzf /backup/qdrant_data_v1.18.0.tgz -C /data'
docker compose -p backend up -d --no-deps qdrant backend
```
Then repeat section 8 against `baseline_counts.txt`. Second-line fallback if the volume copy is unusable: start a clean 1.18.0 volume and upload the downloaded snapshots via `.../snapshots/upload?priority=snapshot`, then recreate the alias: `curl -X POST localhost:6333/collections/aliases -H 'content-type: application/json' -d '{"actions":[{"create_alias":{"collection_name":"first_person_v10","alias_name":"first_person"}}]}'`.

## 10. One-time payload index: `embedding_model_family` (keyword)

Live state read 2026-11-12: the index ALREADY EXISTS on `first_person_v10` (data_type keyword) but covers 0 points, because no v10 point carries that payload field (count with `must_not is_empty` = 0 of 4,226). `first_person_v11` (4,360 points) does NOT have the index. Index creation is idempotent and does not touch points. For v11:
```bash
curl -s -X PUT "localhost:6333/collections/first_person_v11/index?wait=true" \
  -H 'content-type: application/json' \
  -d '{"field_name":"embedding_model_family","field_schema":"keyword"}'
curl -s localhost:6333/collections/first_person_v11 | python3 -c "import sys,json;r=json.load(sys.stdin)['result']['payload_schema'];print(r.get('embedding_model_family'))"   # keyword, points: <populated count>
```
Same command with `first_person_v10` is a no-op. Rollback of an index: `curl -X DELETE localhost:6333/collections/first_person_v11/index/embedding_model_family`. Note: an index on an unpopulated field has no effect until a rebuild writes the field (`build_fp_context_from_v9.py:1020` writes `unknown_legacy_carried` only on carried rows).
