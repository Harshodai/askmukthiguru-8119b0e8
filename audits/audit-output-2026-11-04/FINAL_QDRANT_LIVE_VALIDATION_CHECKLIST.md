# Final Qdrant live validation checklist (owner-run)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Give the owner one ordered list of read-only steps that turns every `[LIVE-Q]` and `[LIVE-L]` claim about Qdrant into evidence. |
| Status | **owner-run, NOT RUN.** No agent has contacted the owner's Qdrant. Every result below is unknown until the owner files evidence. |
| Date / head | 2026-11-05 / `c9b42d3e` |
| Relation to `22` | `22` holds the full query code for R-1 to R-18. This file gives the consolidated order and only the additions: snapshot off-host copy, scratch restore, collection naming, rights stamp, key enforcement, retrieval bank, evidence filing. Where `22` has the code, this file names the R-number and the data spec check (`specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` §5.2, C-L1 to C-L16). |
| Decisions | D-14 (served collection), D-15 (Qdrant writers and keys), D-08 (off-host storage), D-26 (Qdrant hosting) |
| Findings it clears or confirms | DATA-01, DATA-06, DATA-13, DATA-14, DATA-15, DATA-16, DATA-20 (proposed), RET-07, RET-08, SYS-012 |

## 1. Rules (read first)

1. Read-only first. Steps V-1 to V-2 and V-4 to V-13 use only `GET`, `count`, `scroll`, `retrieve`, `facet` and snapshot listing. Do not call `upsert`, `set_payload`, `delete`, `create_snapshot`, `update_collection` or any alias operation against the live instance.
2. Do the content checks on a scratch restore (V-3) when you can. A scratch restore cannot change live data.
3. Warning: a snapshot file holds every `verbatim_text` in the collection. It is teaching content. Store it only in private storage. Never place it in this repository, which is public today (`14c` IP-001, D-01). Check D-08 for the approved location.
4. Warning: `restore_drill.py --apply` creates a snapshot on the live Qdrant. That is a write. Use V-3 (manual REST restore from an existing snapshot) instead, unless you accept that write.
5. If Qdrant has an API key, use the read-only key. Never paste a key into a file under `audits/`.
6. Result files must contain counts, IDs and hashes only. Never write `verbatim_text`. The guard rejects that key in tracked files (`scripts/guards/lesson_guards.py:40-53`).
7. Stop at the first step that fails a **stop** condition and file the failure. Do not repair data in this checklist.

Set once:

```bash
export QDRANT_URL=http://localhost:6333     # live; scratch uses http://localhost:6335
export QDRANT_API_KEY=                      # read-only key if keys are on
export H="api-key: ${QDRANT_API_KEY}"
export OUT=audits/evidence/qdrant_validation_$(date +%F)   # create locally; see V-18
mkdir -p "$OUT"
```

The Python snippets use the header in the data spec §5 (`C`, `scroll_all`, `CHILD`). Run them with `backend/.venv/bin/python3 -I` from the repo root. Qdrant server is `v1.18.0` and `qdrant-client==1.18.0` (`backend/docker-compose.yml`, `22` §2).

## 2. Consolidated order

| Step | What | `22` / spec link | Type |
|---|---|---|---|
| V-1 | Collection naming and effective serving posture | R-2 | read |
| V-2 | List snapshots; copy the latest off the Mac | DATA-01, SYS-012 | read + file copy |
| V-3 | Restore into a scratch Qdrant and a scratch collection | `22` §1 item 1 | scratch write only |
| V-4 | Inventory | R-1, C-L1 | read |
| V-5 | Vector configuration and dimension check | R-3, C-L2 | read |
| V-6 | Encoder fingerprint | R-4 | read |
| V-7 | Hash integrity sample on `source_text_hash` | R-7, C-L3, C-L4 | read |
| V-8 | Point-ID recomputation | R-8, C-L5 | read |
| V-9 | Collection digest baseline | R-16, C-L11 | read |
| V-10 | Teacher and speaker distributions | R-6, C-L6 | read |
| V-11 | Rights stamp and register match | R-10, R-11, C-L7, C-L10 | read |
| V-12 | Orphans against the source registry and archive | R-10, C-L10 | read |
| V-13 | Contained-clip duplicates | C-L9 | read |
| V-14 | Deletion verification for one chosen video (scratch) | R-14 | scratch |
| V-15 | API-key enforcement | DATA-06 | read |
| V-16 | Drift digest against the sign-off digest | R-16 | read |
| V-17 | Retrieval bank against the collection | R-12, T2-02 | read |
| V-18 | Record results | `22` §1 item 5 | file |

## 3. Steps

### V-1 Collection naming and effective posture

Why: three sources disagree, and the answer decides which collection every other step checks.

| Source | What it says | Citation |
|---|---|---|
| Root `CLAUDE.md` invariant 23 | Serving collection is `first_person_v8`; rollback is `first_person_v7` | root `CLAUDE.md` |
| Root `CLAUDE.md` invariant 25 | v10-only serving: `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` may be `first_person_v10` only with harness and terminal flags both true | root `CLAUDE.md` |
| `backend/app/config.py:205` | `first_person_active_collection` defaults to `first_person_v10` | code |
| `backend/app/config.py:282`, `:298` | harness and terminal flags default `False` | code |
| `backend/app/config.py:2323-2326` | With both flags off, the legacy slot becomes `first_person_v8`; the context slot becomes the active name | code |
| `backend/.env.example:207-213`, `backend/docker-compose.yml:311` | Default active name `first_person_v10` | code |

Code wins. With the shipped defaults, users reach `first_person_v8` through the legacy path, and `first_person_v10` is only the named active collection. Invariant 23 describes that default. Invariant 25 describes the owner's v10-only choice, which needs the two flags. Which one runs on your host depends on your local `.env` (unknown, `[LIVE-L]`).

Command (from `backend/`; prints only the listed names, not secrets):

```bash
docker compose -p backend exec backend printenv | grep -E '^FIRST_PERSON_(ACTIVE_COLLECTION|COLLECTION|CONTEXT_COLLECTION|CONTEXT_HARNESS_ENABLED|CONTEXT_TERMINAL_ENABLED|ROUTE_ENABLED)=' | tee "$OUT/V-1_env.txt"
```

Pass: you can state one effective serving collection and path. Set `COLL` to it for the steps that follow, and `LEG=first_person_v8`.
Stop: the slots and flags contradict each other (for example, v10 in a slot with the flags off). File it under D-14.

### V-2 List snapshots and copy the latest off the Mac (DATA-01, SYS-012)

```bash
for c in first_person_v8 first_person_v10 spiritual_wisdom_contextual; do
  echo "== $c"; curl -s -H "$H" "$QDRANT_URL/collections/$c/snapshots" | tee "$OUT/V-2_snapshots_$c.json"
done
```

Pass: each collection you intend to keep has at least one snapshot with a recent `creation_time` and a `size`.
Fail: none exists. File it. Do not create one here (rule 1). Ask for owner approval to run `build_first_person_index.py` or the drill later.

Copy off-host (decision D-08 names the destination):

```bash
SNAP=<name from the listing>
curl -s -H "$H" -o "/private/dest/${SNAP}" "$QDRANT_URL/collections/first_person_v10/snapshots/${SNAP}"
shasum -a 256 "/private/dest/${SNAP}" | tee "$OUT/V-2_sha256_${SNAP}.txt"
```

Pass: the file is in off-host private storage, and its SHA-256 is recorded. The recorded hash is the only item that goes in `audits/`.
Also copy `~/mukthiguru_attribution_data/audio_archive/manifest.json` and run `python3 scripts/ops/audio_archive.py verify` (exists, `scripts/ops/audio_archive.py:339-423`). Record only the pass or fail count.

### V-3 Restore into a scratch Qdrant (restore test)

```bash
docker run -d --name qdrant-scratch -p 127.0.0.1:6335:6333 \
  -v "$PWD/.scratch_qdrant:/qdrant/storage" qdrant/qdrant:v1.18.0
curl -s -X POST "http://localhost:6335/collections/scratch_v10/snapshots/upload?priority=snapshot" \
  -H "Content-Type:multipart/form-data" -F "snapshot=@/private/dest/${SNAP}" | tee "$OUT/V-3_restore.json"
curl -s http://localhost:6335/collections/scratch_v10 | tee "$OUT/V-3_scratch_info.json"
```

Pass: the scratch collection reports `points_count` equal to the live count (V-4) and `status` "green". Re-run V-4 to V-16 against `http://localhost:6335` and `scratch_v10` where the step says "scratch".
Stop: the count differs or the upload fails. A backup that does not restore is a finding (SYS-012).
Clean up: `docker rm -f qdrant-scratch` and delete `.scratch_qdrant` (it holds teaching text).

### V-4 Inventory (R-1, C-L1)

```bash
curl -s -H "$H" "$QDRANT_URL/collections" | tee "$OUT/V-4_collections.json"
for c in $(curl -s -H "$H" "$QDRANT_URL/collections" | python3 -c "import sys,json;print(' '.join(x['name'] for x in json.load(sys.stdin)['result']['collections']))"); do
  curl -s -H "$H" -X POST "$QDRANT_URL/collections/$c/points/count" -H 'Content-Type: application/json' -d '{"exact":true}' ;
  echo " $c"; done | tee "$OUT/V-4_counts.txt"
```

Pass: every collection in `backend/config/first_person_serving_contract.json` that you use exists. List every other collection as "not referenced by code".
Record: counts. Do not quote any count from a document as current (`CONVENTIONS.md` §7).

### V-5 Vector configuration and dimension check (R-3, C-L2, T3-12)

Run the R-3 snippet in `22`. Then compare to the serving encoder: `settings.embedding_dimension` and `settings.embedding_model`.
Pass: `passage_dense` size 1024, cosine, `passage_sparse` present; v8 also has `question_dense` 1024; the size equals `settings.embedding_dimension`.
Stop: a size mismatch. The backend raises at startup on such a pair (`22` R-3), but the contract declares no encoder, so the check is inactive (`FINAL_PENDING_WORK_REGISTER.md` RET-07 Partial).

### V-6 Encoder fingerprint (R-4)

Run R-4 from `22` on `COLL`.
Pass: one `(embedding_model, embedding_revision)` pair, equal to the serving backend values. Record the pair so the owner can write it into the contract (D-14).

### V-7 Integrity hash sample on `source_text_hash` (R-7, C-L3, C-L4)

```python
mm = collections.Counter()
for p in scroll_all(COLL, CHILD, fields=["verbatim_text","source_text_hash","span_text_sha256","transcript_hash"]):
    h = hashlib.sha256(p.payload["verbatim_text"].encode("utf-8")).hexdigest()
    mm["source_ok" if h == p.payload.get("source_text_hash") else "source_BAD"] += 1
    if p.payload.get("span_text_sha256"):
        mm["span_ok" if h == p.payload["span_text_sha256"] else "span_BAD"] += 1
    mm["transcript_eq_clip" if h == p.payload.get("transcript_hash") else "transcript_is_video_level"] += 1
json.dump(dict(mm), open(os.environ["OUT"] + "/V-7_hash.json", "w"))
print(mm)
```

Pass: `source_BAD == 0` and `span_BAD` absent or 0. The `transcript_is_video_level` count is informational (root `CLAUDE.md` invariant 2).
For the legacy collection, hash `transcript_hash` instead (R-7, second loop); pass `v8_BAD == 0`.
Stop: any BAD. Do not fix. File with the point IDs only.
Sample note: the collection is small (a few thousand points), so scan all points. If you must sample, scroll every Nth page and record N.

### V-8 Point-ID recomputation (R-8, C-L5)

Run R-8 from `22`. Pass: `id_mismatch = 0` and `v8_id_mismatch = 0`. Report duplicate-text groups.

### V-9 Collection digest baseline (C-L11)

```python
import sys; sys.path.insert(0, "backend")
from services.first_person_serving_contract import compute_collection_digest
d = compute_collection_digest(scroll_all(COLL, None, fields=True))
print(d); open(os.environ["OUT"] + "/V-9_digest.txt", "w").write(d + "\n")
```

Pass: the digest is recorded. The contract holds no `collection_digest` today, so there is nothing to equal. Record it as the baseline the owner may sign (T3-02). Note: this snippet hashes the Qdrant point UUID plus the span hash. The nightly audit script uses another identity basis (ingestion spec DATA-27). Do not compare values from the two.

### V-10 Teacher and speaker distributions (R-6, C-L6)

Run R-6 from `22`.
Pass: every `guru_id` is one of the IDs in `backend/config/gurus.yaml` (`ekam`, `preethaji`, `krishnaji`); zero spans with `speaker_verified=True` and no `voice_verification_method`. Record the counts. On the legacy collection, record `teacher_id` and `speaker` values. On the chat corpus, record `teacher_id` values (root `CLAUDE.md` says they are mixed).

### V-11 Rights stamp and register match (C-L7, R-11)

```python
n_child = C.count(COLL, count_filter=CHILD, exact=True).count
n_lic = C.count(COLL, count_filter=Filter(must=[
    FieldCondition(key="record_type", match=MatchValue(value="retrieval_child")),
    FieldCondition(key="domain_rights_status", match=MatchValue(value="licensed"))]), exact=True).count
print(n_child, n_lic)
```

Pass: `n_lic == n_child`. Retrieval filters on `licensed` (`first_person_context_store.py:464`), so any shortfall means spans that can never be served. A low `n_lic` confirms the proposed DATA-20 (the builder does not stamp the field, `build_full_corpus_v10.py`, no reference to `domain_rights_status`).
Also: `curl -s http://localhost:8000/api/health` and record the rights-register block (count and digest prefix, `backend/app/api/health.py:228-235`). Pass: a count above 0.

### V-12 Orphans against the source registry and archive (R-10, C-L10)

Run R-10 from `22`. Adapt the manifest key path: the manifest keeps entries under `videos` (`audio_archive.py:565`), so the R-10 fallback logic reads them. Use only `status == "archived"` entries.
Pass: `served_without_audio` and `served_not_cleared` are both empty.
Note: there is no source registry yet (ADR-007). The "registry" for this step is the rights register file plus the audio manifest.

### V-13 Contained-clip duplicates (C-L9)

```python
by_vid = collections.defaultdict(list)
for p in scroll_all(COLL, CHILD, fields=["video_id","start_ms","end_ms"]):
    by_vid[p.payload["video_id"]].append((p.payload["start_ms"], -p.payload["end_ms"], str(p.id)))
contained = total = 0
for vid, rows in by_vid.items():
    rows.sort(); best_end = None
    for s, ne, pid in rows:
        total += 1; e = -ne
        if best_end is not None and e <= best_end: contained += 1
        best_end = e if best_end is None else max(best_end, e)
print(contained, total, contained / max(total, 1))
```

Pass: report the rate. It is a measurement, not a gate, until D-DQ2 sets a threshold. Record `contained`, `total`. Do the same on the legacy collection.

### V-14 Deletion verification for one chosen video (R-14), scratch only

Pick one `video_id` X from the scratch collection. Do not delete anything on live.

```python
# scratch only: QDRANT_URL points at http://localhost:6335
flt = Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=X))])
before = C.count("scratch_v10", count_filter=flt, exact=True).count
C.delete("scratch_v10", points_selector=flt, wait=True)          # scratch write
after = C.count("scratch_v10", count_filter=flt, exact=True).count
print(before, after)
```

Pass: `before > 0` and `after == 0`. Then on live, run the R-14 count loop (read-only) to list every collection that still holds X. That list is the withdrawal scope for the takedown design (ingestion spec §6.2). Also check Redis: `redis-cli --scan --pattern 'cache:first_person_exact:*' | wc -l` (informational) and `grep -rl X memory/okf | head`.

### V-15 API-key enforcement (DATA-06, D-15)

```bash
# 1. No key: must be rejected if keys are on
curl -s -o /dev/null -w "no_key=%{http_code}\n" "$QDRANT_URL/collections"
# 2. Read-only key: a write must be rejected. This probe cannot change data:
#    the target collection does not exist, so a permitted call returns 404, not 403.
curl -s -o /dev/null -w "ro_key_delete=%{http_code}\n" -H "api-key: $QDRANT_READ_ONLY_API_KEY" \
  -X DELETE "$QDRANT_URL/collections/zz_probe_does_not_exist"
# 3. Is the port reachable from outside the host? Run from another machine.
curl -s -o /dev/null -w "remote=%{http_code}\n" "http://<host-ip>:6333/collections"
```

Pass:
- `no_key` is 401 or 403 (keys are on). A 200 means no authentication. File it under DATA-06 and D-15.
- `ro_key_delete` is 403 (the read-only key cannot write). A 404 means the key can write: stop and file it.
- `remote` fails to connect (compose binds `127.0.0.1`, `backend/docker-compose.yml:156`).
Also confirm the backend uses the read-only key: V-1 style `printenv | grep -c QDRANT_READ_ONLY_API_KEY` returns 1 (compose `:302-303`). Print the count only, never the value.

### V-16 Drift digest (R-16)

Compare the V-9 digest with the signed digest, once the owner records one (T3-02). Also compute the R-16 protected-field digest in `22` and compare it with the sign-off value.
Pass: identical, unless a documented build ran.
Today: no signed digest exists, so record "baseline established" and the date.

### V-17 Retrieval bank against the collection (T2-02, R-12)

Facts, verified at `c9b42d3e`:
- `evals/retrieval_bank/bank.jsonl` has 8 queries. Their `relevant_ids` are placeholders such as `sp_bs_001`, not real `source_span_id` values (`bank.jsonl`, read).
- `evals/retrieval_bank/harness.py` has no command-line entry. It exposes `load_retrieval_bank()` and `evaluate_retrieval_system(queries, retrieve_fn, k_values=(1, 5, 10))`, which returns Recall@k, MRR and nDCG@k with 95% intervals (`harness.py:37-96`).

So the bank cannot produce a meaningful live result yet. Do these in order:
1. A human labels real `source_span_id`s for each query, from the scratch restore. AI-authored labels are not allowed (root `CLAUDE.md` invariant 3). This is part of T2-04.
2. Save the labelled bank outside the repo (it names clip IDs, not text, but keep it private until D-01).
3. Write a `retrieve_fn(query, teacher) -> list[str]` that embeds the query host-side (`backend/.venv/bin/python3`, invariant 18), calls `FirstPersonContextStore(C, COLL).retrieve(query_dense, query_sparse=..., guru_id=...)`, and returns the `source_span_id`s from the returned parent contexts (read `ParentContext` in `backend/domain/first_person_context.py` for the field names).
4. Run `evaluate_retrieval_system(load_retrieval_bank(path), retrieve_fn)` and save the summary JSON.

Pass: a summary with `num_queries` equal to the labelled count. No threshold is set before the baseline exists. Record the numbers as the baseline only.

### V-18 Record results

Where: `audits/evidence/qdrant_validation_<date>/` (the path `22` §1 item 5 names). Today `audits/evidence/` is tracked and not ignored.
For every step file: step ID, exact command, timestamp, operator, collection name, collection digest, pass or fail.
Warnings:
- Keep the directory local until you decide D-01 (repository visibility). Do not commit it without owner approval.
- Run this before filing, and expect no output:

```bash
grep -rlE '"verbatim_text"|"source_transcript_text"|"live_verbatim_text"' "$OUT" || echo "clean"
```

Then fill the summary table:

| Step | Result | Pass | Finding filed |
|---|---|---|---|
| V-1 | | | |
| V-2 | | | |
| V-3 | | | |
| V-4 to V-16 | | | |
| V-17 | | | |

## 4. What this checklist does not prove

- It does not show that answers are good. That needs human labels (`18`).
- It does not measure latency or cost. That needs the deployed stack (`22b`).
- It does not show that rights are legally sufficient (`14c`) [HUMAN].
- It does not check Memgraph, LightRAG or Postgres beyond what `22` R-17, R-18 and the data spec SQL checks cover.

## 5. Verified, assumptions, unknowns

**Verified** [V-STATIC]: the flag defaults and slot resolution (`config.py:41`, `:205`, `:282`, `:298`, `:2309-2326`); compose port binding and key variables (`docker-compose.yml:156`, `:162-163`, `:302-303`); health rights block; bank and harness contents; the contract has no digest or encoder fields; `restore_drill.py` writes a snapshot with `--apply`.

**Assumptions** [INF]: Qdrant REST paths follow the documented API for `v1.18.0` (snapshot upload with `priority=snapshot`, `DELETE` on a missing collection returns 404 when authorised). I did not call Qdrant to confirm.

**Unknowns** [LIVE-Q, LIVE-L]: every count, hash result, key state and snapshot age on the owner's host; the owner's effective flags (V-1).
