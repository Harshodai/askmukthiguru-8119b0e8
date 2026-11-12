# 22 — Qdrant and graph deferred-validation runbook (read-only)

> **2026-11-06:** Superseded in part by `specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (static fixture equivalents, SQL and Redis checks, rights-stamp check (§5)). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: Specialist S2. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Railway readiness is in S1 `22b-railway-deployment-readiness-runbook.md`.

> **Status: NOT RUN.** This audit had no access to the owner's Qdrant, Memgraph or host data. Every check below is a procedure for the owner (or an agent on the owner's machine). All statements about live contents in `06`/`08` stay `[LIVE-Q]` until this runbook produces evidence.

## 1. Safety rules for the operator

1. **Preferred:** restore the latest snapshot of each collection into a scratch Qdrant (`docker run qdrant/qdrant:v1.18.0` on another port) and run the checks there. This guarantees read-only behaviour against production data.
2. If you run against the live instance, use only the calls listed here: `GET` collection info, `count`, `scroll`, `retrieve`, `query_points`, `facet`, and list snapshots. Do not call `upsert`, `set_payload`, `delete`, `create_snapshot`, `update_collection` or any alias operation.
3. If Qdrant has an API key, use a read-only key (`QDRANT__SERVICE__READ_ONLY_API_KEY`). Today no key is configured by default (`config.py:710`), so the rule in item 2 is the only protection.
4. For Memgraph, run only `MATCH … RETURN` and `SHOW …` statements. Use a session with `default_access_mode=READ`.
5. Save every output under `audits/evidence/qdrant_validation_<date>/` with the command, timestamp, collection digest and operator.

## 2. Setup

Versions pinned in the repository: Qdrant server `v1.18.0` (`backend/docker-compose.yml:152`), `qdrant-client==1.18.0`, `neo4j==6.3.1`, `lightrag-hku==1.5.7` (`backend/requirements.lock`). Memgraph is `memgraph-mage:latest` (not pinned).

```bash
export QDRANT_URL=http://localhost:6333        # or the scratch restore port
export QDRANT_API_KEY=                         # read-only key if one exists
cd backend && .venv/bin/python3 -I -c "import qdrant_client; print(qdrant_client.__version__)"
```

Common Python header (save as a scratch file outside the repo, run with `backend/.venv/bin/python3 -I`):

```python
import hashlib, json, os, uuid, collections
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
C = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60)
def scroll_all(coll, flt=None, fields=True, vectors=False, page=512):
    off = None
    while True:
        pts, off = C.scroll(coll, scroll_filter=flt, with_payload=fields, with_vectors=vectors, limit=page, offset=off)
        yield from pts
        if off is None:
            break
FP_NS = uuid.UUID("b3f9479e-4e67-4a0b-9d48-6a5814e5f7a2")           # first_person_store.py:56
CTX_NS = uuid.uuid5(uuid.NAMESPACE_URL, "askmukthiguru/fp-context/v1")  # first_person_context_store.py:246
```

## 3. Checks

Each check has a **command**, a **pass criterion** and the **finding it confirms or clears**.

### R-1 Collection inventory
```python
for c in C.get_collections().collections:
    info = C.get_collection(c.name)
    print(c.name, info.points_count, info.status, json.dumps(info.config.params.model_dump(), default=str)[:400])
```
Pass: the list includes exactly the collections named in `backend/config/first_person_serving_contract.json` that are in use, plus `spiritual_wisdom_contextual`, the memory collections, and (if kept) `lightrag_vdb_*`. Record every collection that is not referenced by code (candidates for deletion).
Confirms: `06` §2 inventory.

### R-2 Serving posture
Read the live backend environment (not Qdrant): `FIRST_PERSON_ACTIVE_COLLECTION`, `FIRST_PERSON_COLLECTION`, `FIRST_PERSON_CONTEXT_COLLECTION`, `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`, `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED`.
Pass: the effective serving collection is the one the release record names.
Confirms: which engine users reach (`08` §1).

### R-3 Vector configuration
```python
for name in ["first_person_v8", "first_person_v10", "spiritual_wisdom_contextual"]:
    p = C.get_collection(name).config.params
    print(name, p.vectors, p.sparse_vectors, C.get_collection(name).config.quantization_config)
```
Pass:
- v8: dense `passage_dense` and `question_dense` of size 1024, cosine; sparse `passage_sparse`.
- v10: dense `passage_dense` of size 1024; sparse `passage_sparse` present.
- Chat: `dense` 1024 + `sparse`; INT8 scalar quantisation.
Confirms: RET-02 prerequisite (sparse vectors exist on v10); dimension pin.

### R-4 Encoder fingerprint (v10)
```python
fp = collections.Counter((p.payload.get("embedding_model"), p.payload.get("embedding_revision"))
    for p in scroll_all("first_person_v10", Filter(must=[FieldCondition(key="record_type", match=MatchValue(value="retrieval_child"))]), fields=["embedding_model","embedding_revision"]))
print(fp)
```
Pass: one `(model, revision)` pair, equal to `settings.embedding_model` / `embedding_model_revision` of the serving backend. Also record the serving backend's `EMBEDDING_BACKEND`.
Confirms: RET-07.

### R-5 Payload schema validation (v10)
```python
import sys; sys.path.insert(0, "backend")
from domain.first_person_context import SourceSpan, ParentUnit
bad = collections.Counter()
for p in scroll_all("first_person_v10"):
    pl = dict(p.payload); rt = pl.pop("record_type", None)
    try:
        (SourceSpan if rt == "retrieval_child" else ParentUnit).model_validate(pl)
    except Exception as e:
        bad[(rt, type(e).__name__, str(e).splitlines()[0][:80])] += 1
print(bad.most_common(20))
```
Note: the store strips its own operational fields before validation (`_strip_record_type`, `first_person_context_store.py:259`). If many failures name extra keys, compare with that function before you conclude a defect.
Pass: 0 failures, or only failures explained by documented operational fields.
Confirms: schema validity (`06` §7); RET-06 (count points that carry `rights_status`).

### R-6 Teacher and speaker distributions
```python
for coll, key in [("first_person_v10","guru_id"),("first_person_v8","teacher_id"),("spiritual_wisdom_contextual","teacher_id")]:
    print(coll, C.facet(coll, key=key, limit=50))
print(C.facet("first_person_v10", key="speaker_verified", limit=5))
print(C.facet("first_person_v10", key="voice_verification_method", limit=20))
```
A facet needs a payload index on the key. If the call fails, use `scroll_all` with a `Counter`.
Pass: every teacher value exists in `backend/config/gurus.yaml`. No `speaker_verified=True` without `voice_verification_method` (except the documented legacy `centroid_v1` exemption).
Confirms: DATA-13; provenance (`06` §7); the 2026-10-31 backfill result.

### R-7 Hash integrity (v10 and v8)
```python
mm = collections.Counter()
for p in scroll_all("first_person_v10", Filter(must=[FieldCondition(key="record_type", match=MatchValue(value="retrieval_child"))]),
                    fields=["verbatim_text","source_text_hash","transcript_hash"]):
    h = hashlib.sha256(p.payload["verbatim_text"].encode("utf-8")).hexdigest()
    mm["source_ok" if h == p.payload.get("source_text_hash") else "source_BAD"] += 1
    mm["transcript_eq_clip" if h == p.payload.get("transcript_hash") else "transcript_is_video_level"] += 1
print(mm)
for p in scroll_all("first_person_v8", fields=["verbatim_text","transcript_hash"]):
    h = hashlib.sha256(p.payload["verbatim_text"].encode("utf-8")).hexdigest()
    mm["v8_ok" if h == p.payload.get("transcript_hash") else "v8_BAD"] += 1
print(mm)
```
Pass: `source_BAD = 0` and `v8_BAD = 0`. Record the `transcript_hash` split to confirm DATA-03 (root `CLAUDE.md` reports 1,839 of 2,758 equal on v10).
Confirms: DATA-03; invariant 2.

### R-8 Point-ID recomputation and duplicates
```python
# v10: point id = uuid5(CTX_NS, source_span_id); span id = sha256(guru|video|corpus_version|word_start|word_end|transcript_hash)
bad = 0; seen_text = collections.defaultdict(list)
for p in scroll_all("first_person_v10", Filter(must=[FieldCondition(key="record_type", match=MatchValue(value="retrieval_child"))])):
    pl = p.payload
    sid = hashlib.sha256(f'{pl["guru_id"]}|{pl["video_id"]}|{pl["corpus_version"]}|{pl["word_start"]}|{pl["word_end"]}|{pl["transcript_hash"]}'.encode()).hexdigest()
    if sid != pl["source_span_id"] or str(uuid.uuid5(CTX_NS, sid)) != str(p.id):
        bad += 1
    seen_text[pl["source_text_hash"]].append(str(p.id))
print("id_mismatch", bad, "dup_text_groups", sum(1 for v in seen_text.values() if len(v) > 1))
# v8: point id = uuid5(FP_NS, f"{transcript_hash}:{start_ms}:{end_ms}")
bad8 = sum(1 for p in scroll_all("first_person_v8", fields=["transcript_hash","start_ms","end_ms"])
           if str(uuid.uuid5(FP_NS, f'{p.payload["transcript_hash"]}:{p.payload["start_ms"]}:{p.payload["end_ms"]}')) != str(p.id))
print("v8_id_mismatch", bad8)
```
Pass: `id_mismatch = 0`; `v8_id_mismatch = 0`. Duplicate-text groups are reported (target ≤ 0.5% of spans, per the project scorecard).
Confirms: uniqueness (`06` §7); writer drift after the v11 incident (DATA-06).

### R-9 Chat-corpus duplicates by URL form
```python
by_vid = collections.defaultdict(set)
for p in scroll_all("spiritual_wisdom_contextual", fields=["video_id","source_url"]):
    if p.payload.get("video_id"):
        by_vid[p.payload["video_id"]].add(p.payload.get("source_url"))
print(sum(1 for v in by_vid.values() if len(v) > 1), "video_ids with >1 source_url")
```
Pass: 0.
Confirms or clears: DATA-10.

### R-10 Orphans against the source of truth
Inputs: `~/mukthiguru_attribution_data/audio_archive/manifest.json`, the transcript directory, and the rights manifest `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json`.
```python
served_vids = {p.payload["video_id"] for p in scroll_all("first_person_v10", fields=["video_id"])}
manifest = json.load(open(os.path.expanduser("~/mukthiguru_attribution_data/audio_archive/manifest.json")))
archived = set(manifest.get("videos", manifest).keys()) if isinstance(manifest, dict) else set()
rights = {a["video_id"]: a["rights_status"] for a in json.load(open("audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json"))["assets"] if a.get("video_id")}
print("served_without_audio", sorted(served_vids - archived)[:50])
print("served_not_cleared", sorted(v for v in served_vids if rights.get(v) not in ("confirmed_channel_owner","confirmed_video_owner")))
```
Adapt the manifest key path to its real structure (not verified in this audit).
Pass: both lists are empty.
Confirms: DATA-01 (source coverage); rights coverage (`06` §7).

### R-11 Rights fail-closed behaviour in the deployed image
Run inside the container that serves users:
```bash
python -c "from services.qdrant.indexer import _load_rights_register as L; m=L(); print(len(m), sum(m.values()))"
```
Pass: about 751 keys with about 704 cleared. A result of `0 0` means every clip will abstain.
Confirms: DATA-02.

### R-12 Sample retrieval quality (no generation)
For 30 questions from the frozen bank (S3 `18`), run both engines read-only and store the top 10 with point IDs:
```python
from services.embedding_service import EmbeddingService
E = EmbeddingService(); enc = E.encode_batch([q])   # dense + sparse; confirm the return keys in embedding_service.py:987
# legacy: FirstPersonStore(...).search_hybrid(...)   v10: FirstPersonContextStore(C, "first_person_v10").retrieve(...)
```
Pass: results are archived with collection digests. Human labels (not AI labels) decide relevance (root `CLAUDE.md` invariant 3).
Confirms: RET-01, RET-02 and RET-08 baselines.

### R-13 Index consistency
```python
info = C.get_collection("first_person_v10")
print(info.payload_schema.keys(), info.indexed_vectors_count, info.points_count, info.segments_count)
```
Pass: payload indexes exist for every filter key used at serve time (`record_type`, `rights_cleared`, `domain_rights_status`, `speaker_verified`, `guru_id`, `video_id`, `parent_unit_id`, `topic_ids`, `entity_ids`, `tags`). `indexed_vectors_count` is close to the vector count (HNSW built).
Confirms: retrieval performance assumptions.

### R-14 Deletion verification (after any takedown)
For a `video_id` X:
```python
for coll in [c.name for c in C.get_collections().collections]:
    try:
        n = C.count(coll, count_filter=Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=X))]), exact=True).count
        print(coll, n)
    except Exception as e:
        print(coll, "no video_id index or field", type(e).__name__)
```
Also check Redis (`SCAN MATCH cache:first_person_exact:*`, then inspect payloads for X), the OKF files (`rg X memory/okf`), and Memgraph (R-17).
Pass: 0 in every collection, or a recorded serve block for collections that are intentionally kept.
Confirms: DATA-07.

### R-15 Re-ingestion verification
After a rebuild of one video: compare the before and after point-ID sets for that `video_id`. Pass: no IDs from the old set remain unless they are unchanged spans. No other video's points changed.
Confirms: DATA-05.

### R-16 Post-sign-off drift
Compute a digest of sorted `(point_id, source_text_hash, speaker_verified, voice_verification_method, domain_rights_status)` for the serving collection. Compare it with the digest recorded at sign-off.
Pass: identical, unless a documented build ran.
Confirms: DATA-06.

### R-17 Memgraph read-only checks
```cypher
SHOW STORAGE INFO;
MATCH (n) RETURN labels(n) AS l, count(*) AS c ORDER BY c DESC LIMIT 30;
MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC LIMIT 30;
MATCH ()-[r]->() WHERE r.tenant_id IS NULL RETURN count(r);            // backfill needed?
MATCH (n:base) WHERE n.source_doc_id IS NULL RETURN count(n);          // provenance gaps
MATCH (c:__Chunk__) RETURN count(c);                                    // name-keyed chunk nodes
MATCH (t) WHERE any(l IN labels(t) WHERE l STARTS WITH 'TU_') RETURN count(t);  // TeachingUnit projection
```
Pass: edges without `tenant_id` = 0. Report the provenance gap counts as DATA-08 evidence.

### R-18 LightRAG stores
```python
for n in ["lightrag_vdb_entities_baai_bge_m3_1024d", "lightrag_vdb_relationships_baai_bge_m3_1024d", "lightrag_vdb_chunks_baai_bge_m3_1024d"]:
    try:
        print(n, C.count(n, exact=True).count)
    except Exception as e:
        print(n, "absent", type(e).__name__)
```
Then run the project's artifact gate (`find_artifact`) over a sample of 500 chunk payloads.
Pass: either the collections are retired (RET-05) or contamination is below 1%.

## 4. Mapping to findings

| Check | Findings |
|---|---|
| R-1, R-2 | Inventory (`06` §2); `08` §1 |
| R-3, R-13 | RET-02; performance |
| R-4 | RET-07 |
| R-5 | `06` §7 validity; RET-06 |
| R-6 | DATA-13; provenance |
| R-7 | DATA-03; invariant 2 |
| R-8, R-16 | Uniqueness; DATA-06 |
| R-9 | DATA-10 |
| R-10 | DATA-01; rights coverage |
| R-11 | DATA-02 |
| R-12 | RET-01, RET-02, RET-08 |
| R-14 | DATA-07 |
| R-15 | DATA-05 |
| R-17 | DATA-08 |
| R-18 | RET-05; DATA-08 |

## 5. What stays unverified after this runbook

- Whether answers are good. That needs human labels (S3 `18`).
- Production latency. That needs the deployed stack (S1 `22b`).
- Legal sufficiency of the rights basis (S4 `14c`) `[HUMAN]`.
