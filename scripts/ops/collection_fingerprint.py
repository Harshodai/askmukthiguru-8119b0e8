#!/usr/bin/env python3
"""Read-only collection fingerprint for a graded run manifest (open-work row T-E10).

Why this exists
---------------
``scripts/ops/graded_capture.py`` writes ``"collection_fingerprint": None`` and
``graded_registered_report.py`` marks any manifest whose fingerprint is ``None``
as an **invalid run**. With no producer, that pair makes the registered bar
unmeetable: every capture is invalid by construction and no report can ever be
a verdict in either direction.

The capture author's reason for the null stands and is respected here: a capture
"has no Qdrant client (only Redis and docker), and a new client would change what
a capture touches". So the fingerprint is produced by this separate, read-only
step instead, against the served collection, and recorded in the manifest.

What it computes (the criteria's ``{points, ids_sha256}``)
----------------------------------------------------------
* ``points``      -- number of point ids scrolled from the collection.
* ``ids_sha256``  -- sha256 over the ids sorted as strings and newline-joined,
                     so the value depends on the id set, not on scroll order.

Usage
-----
    # print only (default; touches nothing)
    python3 scripts/ops/collection_fingerprint.py --collection first_person_v10

    # record it in a run manifest (refuses after a report exists)
    python3 scripts/ops/collection_fingerprint.py --collection first_person_v10 \\
        --run-dir ~/mukthiguru_attribution_data/graded_runs/<run-id> --write

Exit status is the contract (L-OPS-EXIT-STATUS-1):
    0  fingerprint computed (and written, if asked)
    1  refused -- the run already has a report, so writing would retro-fit
       evidence onto a finished run
    2  Qdrant unreachable, collection missing, or the manifest is unusable

Config: QDRANT_URL (default http://localhost:6333), QDRANT_API_KEY or
QDRANT_READ_ONLY_API_KEY (either is accepted; this never writes).

A failed read is never a fingerprint: unreachable is exit 2, never ``{points: 0}``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCROLL_PAGE = 256


def fingerprint_from_ids(ids: Iterable[str | int]) -> dict[str, Any]:
    """``{points, ids_sha256}`` for a collection's point ids.

    Pure, so the arithmetic that decides a run's validity is testable without a
    Qdrant instance. Sorting is by the string form: Qdrant ids may be ints or
    UUIDs, and mixed types are not orderable in Python 3.
    """
    as_strings = sorted(str(i) for i in ids)
    digest = hashlib.sha256("\n".join(as_strings).encode("utf-8")).hexdigest()
    return {"points": len(as_strings), "ids_sha256": digest}


class QdrantError(RuntimeError):
    """Qdrant could not answer. Never converted into an empty fingerprint."""


def _request(url: str, api_key: str | None, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    if api_key:
        # Header, never a query parameter: a key in a URL ends up in logs.
        req.add_header("api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise QdrantError(f"HTTP {exc.code} from {url.split('?')[0]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise QdrantError(f"Qdrant unreachable at {url.split('?')[0]}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise QdrantError(f"non-JSON reply from {url.split('?')[0]}") from exc


def collection_ids(base_url: str, api_key: str | None, collection: str) -> list[str]:
    """Every point id in ``collection``, via scroll pagination. Read-only."""
    base = base_url.rstrip("/")
    ids: list[str] = []
    offset: str | int | None = None
    while True:
        body: dict[str, Any] = {
            "limit": SCROLL_PAGE,
            "with_payload": False,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        reply = _request(f"{base}/collections/{collection}/points/scroll", api_key, body)
        result = reply.get("result") or {}
        points = result.get("points") or []
        ids.extend(str(p["id"]) for p in points if "id" in p)
        offset = result.get("next_page_offset")
        if not points or offset is None:
            return ids


def _manifest_path(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def write_fingerprint(run_dir: Path, fingerprint: dict[str, Any]) -> Path:
    """Record the fingerprint in ``manifest.json``.

    Refuses when the run already has a report: patching a finished run would let
    an invalid capture become valid after the fact, which is retro-fitted
    evidence. A finished run stays invalid and is re-run instead.
    """
    if (run_dir / "registered_report.json").exists() or (run_dir / "registered_report.md").exists():
        raise ValueError(
            f"{run_dir} already has a registered report; refusing to retro-fit a fingerprint "
            "onto a finished run. Re-run the capture instead."
        )
    path = _manifest_path(run_dir)
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["collection_fingerprint"] = fingerprint
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only graded-run collection fingerprint")
    parser.add_argument("--collection", required=True, help="Served collection name")
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Graded run directory; only read (and written to) when --write is given",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Record the fingerprint in the run manifest (refused after a report exists)",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("QDRANT_API_KEY") or os.environ.get("QDRANT_READ_ONLY_API_KEY") or None
    try:
        ids = collection_ids(args.qdrant_url, api_key, args.collection)
    except QdrantError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    fingerprint = fingerprint_from_ids(ids)
    fingerprint["collection"] = args.collection
    print(json.dumps(fingerprint, indent=2))

    if args.write:
        if args.run_dir is None:
            print("FAILED: --write needs --run-dir", file=sys.stderr)
            return 2
        try:
            written = write_fingerprint(args.run_dir, fingerprint)
        except ValueError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Self-check: the pure part must be stable and order-independent.
        a = fingerprint_from_ids([3, 1, 2])
        b = fingerprint_from_ids(["2", "3", "1"])
        assert a == b, (a, b)
        assert a["points"] == 3 and len(a["ids_sha256"]) == 64
        assert fingerprint_from_ids([])["ids_sha256"] == hashlib.sha256(b"").hexdigest()
        print("self-check ok:", a)
        raise SystemExit(0)
    raise SystemExit(main())
