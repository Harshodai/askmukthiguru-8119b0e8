#!/usr/bin/env python3
"""
scripts/ops/reconcile_first_person_v7.py — deterministic-ID + vector reconciliation
for Qdrant `first_person_v7` (plan Phase 1, 2026-09-30).

Root cause (audit A-1/A-2/A-10): two in-place mutation episodes changed
`verbatim_text` AFTER the point IDs were first written, leaving
    id != uuid5(FIRST_PERSON_NAMESPACE, f"{sha256(verbatim_text)}:{start_ms}:{end_ms}")
on 52/144 points, with `passage_dense`/`passage_sparse` embedding the OLD text.

Fix per mismatched point: re-embed the CURRENT verbatim_text (dense+sparse),
upsert under the recomputed UUID, VERIFY the read-back (vector names, dense
dim, payload intact), only then delete the stale UUID.

Safety:
  * default mode is DRY-RUN (prints old_id -> expected_id, no writes)
  * `--apply` refuses to delete a stale point until its replacement read-back
    verifies; payload is copied verbatim from the stored point (zero payload loss)
  * idempotent + resumable: correct points are skipped; a crash between upsert
    and delete heals on rerun (stale twin detected as identical -> delete-only)
  * every operation logged to a JSONL audit file next to the backup

Usage (host):   cd backend && .venv/bin/python ../scripts/ops/reconcile_first_person_v7.py
                (add --apply / --ensure-indexes)
Usage (container, repo-root scripts/ is bind-mounted at /app/scripts):
                docker exec -w /app mukthiguru-backend \
                  python /app/scripts/ops/reconcile_first_person_v7.py --apply

DECISION (recorded): `scripts/ingestion/repair_v7_clips.py` does NOT cover this —
it only snaps boundaries via payload surgery and never re-embeds or re-keys IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Path setup: resolve `services.*` whether run from backend/ (host), /app
# (container cwd), from anywhere on host (via repo_root/backend), or by a
# docker-cp'd /tmp copy (cwd covers it).
_self = Path(__file__).resolve()
_HERE_BACKEND = _self.parents[2] / "backend" if len(_self.parents) > 2 else _self.parent
for _cand in (Path.cwd(), Path("/app"), _HERE_BACKEND):
    if (_cand / "services" / "first_person_store.py").exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

from qdrant_client import QdrantClient  # noqa: E402
from services.first_person_store import (  # noqa: E402
    make_first_person_point_id,
    validate_clip_entry,
)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "first_person_v7"
EMBED_BATCH = 64  # matches build_first_person_index._BATCH_SIZE
_HOST_LOG = Path(
    "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/"
    ".claude/tasks/audit_2026-09-29/reconcile_first_person_v7_log_2026-09-30.jsonl"
)
# Container runs (docker cp to /tmp) cannot see the host .claude dir — fall back
# to /tmp and `docker cp` the log back next to the backup after --apply.
LOG_PATH = (
    _HOST_LOG
    if _HOST_LOG.parent.exists()
    else Path("/tmp/reconcile_first_person_v7_log_2026-09-30.jsonl")
)
# Vector set every re-embedded point must carry (no colbert; question_dense is
# dead schema written on 0/144 points — see audit A-5).
REQUIRED_VECTORS = ("passage_dense", "passage_sparse")


def scroll_all(client: QdrantClient, collection: str) -> list[Any]:
    """Paginated scroll with payload + vectors (never a single 500-limit page)."""
    out: list[Any] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=200,
            with_payload=True,
            with_vectors=True,
        )
        out.extend(points)
        if offset is None:
            return out


def expected_id_for(payload: dict[str, Any]) -> tuple[str, str]:
    """(expected UUID, sha256 hex) recomputed from CURRENT verbatim_text.
    Binding contract: first_person_store.make_first_person_point_id with
    transcript_hash == sha256(verbatim_text)."""
    text = str(payload.get("verbatim_text", ""))
    hash_hex = hashlib.sha256(text.encode("utf-8")).hexdigest()
    stored_hash = str(payload.get("transcript_hash", ""))
    if stored_hash.casefold() != hash_hex:
        raise ValueError(
            f"hash drift: stored transcript_hash {stored_hash[:12]} != sha256(text) {hash_hex[:12]} "
            "(reconcile expects text/hash already consistent; fix hash first)"
        )
    return make_first_person_point_id(
        hash_hex, int(payload["start_ms"]), int(payload["end_ms"])
    ), hash_hex


def find_mismatches(points: Iterable[Any]) -> list[dict[str, Any]]:
    """Points with id != uuid5(hash,start,end). Pure — testable without Qdrant."""
    mismatches = []
    for p in points:
        payload = p.payload or {}
        if not payload.get("verbatim_text"):
            raise ValueError(f"point {p.id}: missing verbatim_text")
        expected_id, hash_hex = expected_id_for(payload)
        if str(p.id) != expected_id:
            mismatches.append(
                {
                    "old_id": str(p.id),
                    "expected_id": expected_id,
                    "hash_prefix": hash_hex[:12],
                    "start_ms": payload["start_ms"],
                    "end_ms": payload["end_ms"],
                    "video_id": payload.get("video_id"),
                    "text_len": len(str(payload["verbatim_text"])),
                }
            )
    return mismatches


def ensure_indexes(client: QdrantClient, collection: str) -> list[dict[str, Any]]:
    """Idempotently create keyword payload indexes (R1 + A-5 is_verbatim gap)."""
    info = client.get_collection(collection)
    # payload_schema is a dict-like {field: PayloadSchemaInfo}
    try:
        present = {k: str(getattr(v, "data_type", v)) for k, v in dict(info.payload_schema).items()}
    except Exception:  # noqa: BLE001 — None schema means no indexes yet
        present = {}
    created = []
    for field in ("is_verbatim", "rights_cleared"):
        if field in present:
            print(f"  index {field}: already present ({present[field]})")
            continue
        res = client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema="keyword",
            wait=True,
        )
        created.append({"field": field, "schema": "keyword", "result": str(res.operation_id)})
        print(f"  index {field}: CREATED (operation_id={res.operation_id}, status={res.status})")
    return created


def _log(op: dict[str, Any]) -> None:
    rec = {"ts": datetime.now(UTC).isoformat(), **op}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _vector_names(v: Any) -> set[str]:
    return set(v.keys()) if isinstance(v, dict) else set()


def apply(client: QdrantClient, collection: str) -> int:
    """Re-embed + re-key every mismatched point. Returns mismatches handled."""
    points = scroll_all(client, collection)
    mismatches = find_mismatches(points)
    by_id = {str(p.id): p for p in points}
    if not mismatches:
        print("nothing to reconcile (0 mismatches)")
        return 0

    # Fail-closed guard: this script only ever repairs the known stale-vector
    # vector set. question_dense (never written) or unknown names abort.
    for m in mismatches:
        names = _vector_names(by_id[m["old_id"]].vector)
        unexpected = names - set(REQUIRED_VECTORS)
        if unexpected:
            raise RuntimeError(
                f"{m['old_id']}: unexpected vector names {sorted(unexpected)} — abort, hand-review"
            )

    # Planned actions. to_delete excludes any ID that is also a target (chain guard).
    existing_ids = set(by_id)
    todo = []  # (mismatch, needs_embed)
    delete_only = []  # stale ids whose correct twin already exists & is identical
    for m in mismatches:
        if m["expected_id"] in existing_ids:
            twin = by_id[m["expected_id"]]
            src = by_id[m["old_id"]].payload or {}
            twin_pl = twin.payload or {}
            same = (
                str(twin_pl.get("verbatim_text")) == str(src.get("verbatim_text"))
                and int(twin_pl.get("start_ms", -1)) == int(src.get("start_ms", -2))
                and int(twin_pl.get("end_ms", -1)) == int(src.get("end_ms", -2))
                and str(twin.id) == m["expected_id"]
                and find_mismatches([twin]) == []
            )
            if not same:
                raise RuntimeError(
                    f"conflict: expected id {m['expected_id']} exists with different content — abort"
                )
            delete_only.append(m)
        else:
            todo.append(m)

    print(f"reconcile plan: embed+upsert={len(todo)}, delete-only(twin exists)={len(delete_only)}")

    # Re-embed CURRENT text for every point that needs a new key.
    embedded: dict[str, dict[str, Any]] = {}
    if todo:
        from services.embedding_service import EmbeddingService
        from services.qdrant.utils import QdrantUtils

        embedder = EmbeddingService()
        for i in range(0, len(todo), EMBED_BATCH):
            batch = todo[i : i + EMBED_BATCH]
            texts = [str(by_id[m["old_id"]].payload["verbatim_text"]) for m in batch]
            enc = embedder.encode_batch(texts)
            for m, dense, sparse_dict in zip(batch, enc["dense"], enc["sparse"]):
                sv = QdrantUtils.sparse_dict_to_vector(sparse_dict)
                embedded[m["old_id"]] = {
                    "passage_dense": dense,
                    "passage_sparse": {"indices": list(sv.indices), "values": list(sv.values)},
                }
            print(
                f"  embedded batch {i // EMBED_BATCH + 1}/{(len(todo) + EMBED_BATCH - 1) // EMBED_BATCH}"
            )

        from qdrant_client.http.models import PointStruct, SparseVector

        dim = len(embedded[todo[0]["old_id"]]["passage_dense"])
        new_points = []
        for m in todo:
            payload = dict(by_id[m["old_id"]].payload)  # verbatim payload copy
            validate_clip_entry(payload)  # all store invariants, fail-closed
            vec = embedded[m["old_id"]]
            if len(vec["passage_dense"]) != dim:
                raise RuntimeError(
                    f"{m['old_id']}: dense dim drift {len(vec['passage_dense'])} != {dim}"
                )
            new_points.append(
                PointStruct(
                    id=m["expected_id"],
                    vector={
                        "passage_dense": vec["passage_dense"],
                        "passage_sparse": SparseVector(
                            indices=vec["passage_sparse"]["indices"],
                            values=vec["passage_sparse"]["values"],
                        ),
                    },
                    payload=payload,
                )
            )
        client.upsert(collection_name=collection, points=new_points, wait=True)
        print(f"  upserted {len(new_points)} points under corrected UUIDs")

        # --- READ-BACK VERIFY (before any delete) ---
        verify_ids = [m["expected_id"] for m in todo]
        got = client.retrieve(
            collection_name=collection,
            ids=verify_ids,
            with_payload=True,
            with_vectors=True,
        )
        got_by_id = {str(g.id): g for g in got}
        for m in todo:
            g = got_by_id.get(m["expected_id"])
            if g is None:
                raise RuntimeError(f"read-back failed: {m['expected_id']} missing after upsert")
            names = _vector_names(g.vector)
            if names != set(REQUIRED_VECTORS):
                raise RuntimeError(f"read-back failed: {m['expected_id']} vectors {sorted(names)}")
            if len(g.vector["passage_dense"]) != dim:
                raise RuntimeError(f"read-back failed: {m['expected_id']} dense dim != {dim}")
            src_pl = by_id[m["old_id"]].payload
            if (g.payload or {}).get("verbatim_text") != src_pl.get("verbatim_text"):
                raise RuntimeError(f"read-back failed: {m['expected_id']} payload text mismatch")
            if (g.payload or {}).get("transcript_hash") != src_pl.get("transcript_hash"):
                raise RuntimeError(f"read-back failed: {m['expected_id']} payload hash mismatch")
        print(
            f"  read-back verified {len(verify_ids)}/{len(verify_ids)} (vectors + payload intact)"
        )

    # --- DELETE stale IDs (only after verification; never a target ID) ---
    targets = {m["expected_id"] for m in todo}
    stale = [m for m in mismatches if m["old_id"] not in targets]
    if stale:
        client.delete(
            collection_name=collection,
            points_selector=[m["old_id"] for m in stale],
            wait=True,
        )
        print(f"  deleted {len(stale)} stale points")

    for m in mismatches:
        action = (
            "upsert_corrected+delete_stale"
            if m["old_id"] in {x["old_id"] for x in todo}
            else "delete_stale_twin_identical"
        )
        _log(
            {
                "action": action,
                "old_id": m["old_id"],
                "new_id": m["expected_id"],
                "hash_prefix": m["hash_prefix"],
                "video_id": m["video_id"],
                "start_ms": m["start_ms"],
                "end_ms": m["end_ms"],
            }
        )
    print(f"  logged {len(mismatches)} operations to {LOG_PATH.name}")
    return len(mismatches)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument(
        "--ensure-indexes", action="store_true", help="create is_verbatim/rights_cleared indexes"
    )
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--qdrant-url", default=QDRANT_URL)
    args = ap.parse_args(argv)

    client = QdrantClient(url=args.qdrant_url, timeout=60)
    info = client.get_collection(args.collection)
    names = set(dict(info.config.params.vectors)) | set(
        dict(info.config.params.sparse_vectors or {})
    )
    print(f"collection={args.collection} schema_vectors={sorted(names)}")

    if args.ensure_indexes:
        ensure_indexes(client, args.collection)

    points = scroll_all(client, args.collection)
    mismatches = find_mismatches(points)
    payload_keys = sorted({k for p in points for k in (p.payload or {})})
    print(f"points={len(points)} mismatches={len(mismatches)} payload_keys={payload_keys}")

    if not args.apply:
        print("DRY-RUN (no writes). old_id -> expected_id:")
        for m in mismatches:
            print(
                f"  {m['old_id']} -> {m['expected_id']}  [{m['video_id']} {m['start_ms']}-{m['end_ms']} h={m['hash_prefix']}]"
            )
        print(f"mismatch count: {len(mismatches)}")
        return 0

    handled = apply(client, args.collection)
    final = find_mismatches(scroll_all(client, args.collection))
    print(f"handled={handled} remaining_mismatches={len(final)}")
    return 0 if not final else 1


if __name__ == "__main__":
    sys.exit(main())
