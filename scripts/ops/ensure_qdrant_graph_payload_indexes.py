"""Ensure Qdrant payload indexes required by graph-linked retrieval.

Dry-run by default. ``--apply`` creates only keyword indexes and never deletes
or rewrites points. The rollback is to stop using the optional graph-linked
filters; removing an index is intentionally a separate, explicit operation.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.http.models import PayloadSchemaType

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger("ensure_qdrant_graph_payload_indexes")
DEFAULT_LOCK = "/tmp/askmukthiguru_qdrant_payload_indexes.lock"
INDEX_FIELDS = (
    "entity_ids",
    "graph_node_ids",
    "teacher_id",
    "language",
    "ontology_version",
    "context_cluster_ids",
)


def acquire_lock(path: Path):
    handle = path.open("a+", encoding="utf-8")
    if fcntl is None:
        return handle
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"Another Qdrant index maintenance job holds {path}") from exc
    return handle


def _schema_name(schema: Any) -> str:
    if isinstance(schema, dict):
        return str(schema.get("data_type") or schema.get("type") or "unknown")
    return str(getattr(schema, "data_type", schema))


def inspect_indexes(client: QdrantClient, collection: str) -> Dict[str, str]:
    info = client.get_collection(collection)
    payload_schema = getattr(getattr(info, "payload_schema", None), "items", lambda: [])()
    return {str(field): _schema_name(schema) for field, schema in payload_schema}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create missing indexes")
    parser.add_argument("--url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom"))
    parser.add_argument("--lock-file", default=DEFAULT_LOCK)
    args = parser.parse_args()

    lock_handle = acquire_lock(Path(args.lock_file))
    try:
        client = QdrantClient(
            url=args.url,
            api_key=args.api_key or None,
            check_compatibility=False,
        )
        info = client.get_collection(args.collection)
        before = inspect_indexes(client, args.collection)
        missing = [field for field in INDEX_FIELDS if field not in before]
        result: Dict[str, Any] = {
            "collection": args.collection,
            "points_count": getattr(info, "points_count", None),
            "apply": bool(args.apply),
            "before": before,
            "missing": missing,
            "created": [],
            "rollback": "Disable optional graph-linked filters; do not delete indexes during incident response.",
        }
        if args.apply:
            for field in missing:
                client.create_payload_index(
                    collection_name=args.collection,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                result["created"].append(field)
            result["after"] = inspect_indexes(client, args.collection)
        else:
            result["after"] = before
            result["message"] = "Dry run only; no payload indexes were changed. Re-run with --apply after review."
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    raise SystemExit(main())
