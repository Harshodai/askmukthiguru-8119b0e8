#!/usr/bin/env python3
"""Read-only live audit of a first-person Qdrant collection (NEW-DQ-1, DATA-15).

Implements checks C-L1 to C-L9 and the C-L11 digest from
audits/audit-output-2026-11-04/specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md.

Rules:
  * Read only. It calls get_collection, get_collections and scroll. Nothing else.
  * The report holds counts, ratios, point ids and field names. It never holds
    verbatim_text or any other text field. A test enforces this.
  * Exit code 0 when no check failed, 1 when at least one failed, 2 on usage or
    connection errors.
  * The default collection is the serving collection from Settings. It must be
    declared in config/first_person_serving_contract.json, else the script stops.

Not implemented here (need other stores, not Qdrant): C-L10 (register and archive),
C-L12 (chat source URLs), C-L13 (LightRAG), C-L14 (Memgraph), C-L15 (Redis), C-L16 (OKF).
They appear in the report as "not_implemented". The span-id recompute half of C-L5 is
also not implemented; only the point-id recompute is.

Usage (host, backend venv):
    backend/.venv/bin/python scripts/ops/fp_live_audit.py
    backend/.venv/bin/python scripts/ops/fp_live_audit.py --collection first_person_v10 --json out.json
    QDRANT_URL=http://localhost:6333 backend/.venv/bin/python scripts/ops/fp_live_audit.py --skip C-L8

Do not schedule this script by default. Run it by hand after a build or a restore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from services.first_person_context_store import (  # noqa: E402
    RECORD_TYPE_CHILD,
    SPAN_INDEXES,
    point_id_for_record,
)
from services.first_person_serving_contract import (  # noqa: E402
    CONTEXT_SCHEMA,
    compute_collection_digest,
    load_contract_cached,
)
from services.first_person_store import make_first_person_point_id  # noqa: E402
from services.guru_registry import get_gurus  # noqa: E402

NOT_IMPLEMENTED = ("C-L10", "C-L12", "C-L13", "C-L14", "C-L15", "C-L16")
SCROLL_BATCH = 500
#: Payload keys the audit reads. Anything else (above all verbatim text) is never kept.
_FIELDS = (
    "record_type",
    "source_span_id",
    "video_id",
    "guru_id",
    "source_text_hash",
    "transcript_hash",
    "speaker_verified",
    "voice_verification_method",
    "domain_rights_status",
    "start_ms",
    "end_ms",
    "verbatim_text",
)


def default_collection() -> str:
    """The serving collection from Settings; it must be declared in the contract."""
    name = (settings.first_person_context_collection or "").strip()
    contract = load_contract_cached()
    if not name or name not in contract:
        raise SystemExit(
            f"Serving collection {name!r} is not declared in "
            "config/first_person_serving_contract.json. Stop."
        )
    return name


def _connect(url: str, api_key: str | None):
    from qdrant_client import QdrantClient

    return QdrantClient(url=url, api_key=api_key or None, timeout=60)


def _scroll_all(client, collection: str) -> Iterable[Any]:
    offset = None
    while True:
        points, offset = client.scroll(
            collection,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=list(_FIELDS),
            with_vectors=False,
        )
        yield from points
        if offset is None:
            return


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_checks(
    client,
    collection: str,
    *,
    schema: str,
    dim: int,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    """Run the implemented checks. ``schema`` is "v10" (fp-context) or "v8" (legacy clip)."""
    skip = set(skip or ())
    checks: list[dict[str, Any]] = []

    def add(check_id: str, title: str, ok: bool | None, **detail: Any) -> None:
        if check_id in skip:
            return
        status = "INFO" if ok is None else ("PASS" if ok else "FAIL")
        checks.append({"id": check_id, "title": title, "status": status, **detail})

    # C-L1 inventory
    names = sorted(c.name for c in client.get_collections().collections)
    info = client.get_collection(collection)
    add(
        "C-L1",
        "collection exists",
        collection in names,
        points_count=info.points_count,
        collections=len(names),
    )

    # C-L2 dimension and vector names
    vectors = info.config.params.vectors
    dense = vectors.get("passage_dense") if isinstance(vectors, dict) else None
    sparse = info.config.params.sparse_vectors or {}
    dist = str(getattr(getattr(dense, "distance", None), "value", "")).lower()
    add(
        "C-L2",
        "dense size, cosine, sparse vector present",
        bool(dense) and dense.size == dim and dist == "cosine" and "passage_sparse" in sparse,
        dense_size=getattr(dense, "size", None),
        expected_dim=dim,
        distance=dist,
        sparse_present="passage_sparse" in sparse,
    )

    # C-L8 payload indexes (needs a real server; local mode keeps no schema)
    have = set((info.payload_schema or {}).keys())
    missing_idx = sorted({k for k, _ in SPAN_INDEXES} - have)
    add("C-L8", "payload indexes", not missing_idx, missing=missing_idx)

    # Single streaming pass for C-L3, C-L4, C-L5, C-L6, C-L7, C-L9, C-L11.
    hash_key = "source_text_hash" if schema == "v10" else "transcript_hash"
    children = bad_hash = bad_id = 0
    bad_hash_ids: list[str] = []
    bad_id_ids: list[str] = []
    rights_values: dict[str, int] = {}
    record_types: dict[str, int] = {}
    verified_no_method = not_licensed = 0
    bad_guru: set[str] = set()
    by_video: dict[str, list[tuple[int, int]]] = {}
    digest_rows: list[dict[str, Any]] = []
    known_gurus = {g.id for g in get_gurus()}
    for p in _scroll_all(client, collection):
        pl = p.payload or {}
        digest_rows.append(
            {
                "id": str(p.id),
                "payload": {
                    k: pl.get(k)
                    for k in ("span_text_sha256", "source_text_hash", "transcript_hash")
                },
            }
        )
        rt = str(pl.get("record_type") or "<missing>")
        record_types[rt] = record_types.get(rt, 0) + 1
        if schema == "v10" and pl.get("record_type") not in (None, RECORD_TYPE_CHILD):
            continue
        children += 1
        text = pl.get("verbatim_text")
        if not isinstance(text, str) or _sha(text) != pl.get(hash_key):
            bad_hash += 1
            bad_hash_ids.append(str(p.id))
        try:
            if schema == "v10":
                expect = point_id_for_record(str(pl.get("source_span_id")))
            else:
                expect = make_first_person_point_id(
                    str(pl.get("transcript_hash")), int(pl["start_ms"]), int(pl["end_ms"])
                )
        except (KeyError, TypeError, ValueError):
            expect = ""
        if str(uuid.UUID(str(p.id))) != expect:
            bad_id += 1
            bad_id_ids.append(str(p.id))
        guru = str(pl.get("guru_id") or "")
        if guru and guru not in known_gurus:
            bad_guru.add(guru)
        if (
            pl.get("speaker_verified") is True
            and not str(pl.get("voice_verification_method") or "").strip()
        ):
            verified_no_method += 1
        rv = str(pl.get("domain_rights_status") or "<missing>")
        rights_values[rv] = rights_values.get(rv, 0) + 1
        if pl.get("domain_rights_status") != "licensed":
            not_licensed += 1
        try:
            by_video.setdefault(str(pl.get("video_id")), []).append(
                (int(pl["start_ms"]), int(pl["end_ms"]))
            )
        except (KeyError, TypeError, ValueError):
            pass

    hash_id = "C-L3" if schema == "v10" else "C-L4"
    add(
        hash_id,
        f"sha256(verbatim_text) == {hash_key}",
        bad_hash == 0,
        bad=bad_hash,
        bad_point_ids=bad_hash_ids[:20],
        children=children,
    )
    add(
        "C-L5",
        "point id recomputes",
        bad_id == 0,
        bad=bad_id,
        bad_point_ids=bad_id_ids[:20],
        children=children,
    )
    add(
        "C-L6",
        "guru ids in registry; no verified speaker without a method",
        not bad_guru and verified_no_method == 0,
        unknown_guru_ids=sorted(bad_guru),
        verified_without_method=verified_no_method,
    )
    add(
        "C-L7",
        "every child carries domain_rights_status=licensed",
        not_licensed == 0,
        not_licensed=not_licensed,
        status_values=dict(sorted(rights_values.items())),
        children=children,
    )
    for c in checks:
        if c["id"] == "C-L1":
            c["record_types"] = dict(sorted(record_types.items()))

    contained = 0
    for spans in by_video.values():
        kept_start = kept_end = None
        for start, end in sorted(spans, key=lambda s: (s[0], -s[1])):
            if kept_end is not None and start >= kept_start and end <= kept_end:
                contained += 1
            else:
                kept_start, kept_end = start, end
    add(
        "C-L9",
        "contained-span rate (reported, not a failure)",
        None,
        contained=contained,
        total=children,
        rate=round(contained / children, 4) if children else 0.0,
    )
    add(
        "C-L11",
        "collection digest (record as baseline; compare to a signed value later)",
        None,
        digest=compute_collection_digest(digest_rows),
        points=len(digest_rows),
    )

    failed = [c["id"] for c in checks if c["status"] == "FAIL"]
    return {
        "collection": collection,
        "schema": schema,
        "checks": checks,
        "failed": failed,
        "not_implemented": list(NOT_IMPLEMENTED),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", help="default: the serving collection from Settings")
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument(
        "--dim", type=int, default=0, help="default: embedding_dimension in the contract, else 1024"
    )
    ap.add_argument("--skip", action="append", default=[], help="check id to skip, repeatable")
    ap.add_argument("--json", dest="json_out", help="also write the report to this file")
    args = ap.parse_args(argv)

    collection = args.collection or default_collection()
    contract = load_contract_cached().get(collection)
    if contract is None:
        print(
            f"Collection {collection!r} is not declared in the serving contract.", file=sys.stderr
        )
        return 2
    schema = "v10" if contract.schema == CONTEXT_SCHEMA else "v8"
    dim = args.dim or contract.embedding_dimension or 1024
    try:
        client = _connect(args.qdrant_url, os.environ.get("QDRANT_API_KEY"))
        report = run_checks(client, collection, schema=schema, dim=dim, skip=set(args.skip))
    except Exception as exc:  # network or auth: say what failed, keep no payload
        print(f"Audit could not run: {type(exc).__name__}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
