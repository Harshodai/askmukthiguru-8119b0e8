"""Backfill deterministic ontology links into existing Qdrant payloads.

The job is deliberately payload-only and never reads, writes, stages, or uploads
``scripts/ingestion/corpus/``. It is dry-run by default, scoped to one tenant and
corpus, resumable through a JSON cursor, and protected by a process lock.

Use ``--apply`` only after reviewing the dry-run sample and collection scope.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from rag.kg_expansion import resolve_concepts_in_query

try:
    import fcntl
except ImportError:  # pragma: no cover - production runs on Unix
    fcntl = None


logger = logging.getLogger("backfill_qdrant_graph_links")
DEFAULT_ONTOLOGY_VERSION = "seeded-ontology-v1"
DEFAULT_STATE_PATH = "/tmp/askmukthiguru_qdrant_graph_links.json"
DEFAULT_LOCK_PATH = "/tmp/askmukthiguru_qdrant_graph_links.lock"
GRAPH_FIELDS = (
    "entity_ids",
    "graph_node_ids",
    "source_segment_ids",
    "ontology_version",
    "entity_resolution_confidence",
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _load_state(path: Path, reset: bool) -> Dict[str, Any]:
    if reset or not path.exists():
        return {"next_offset": None, "processed": 0, "patched": 0, "skipped": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable state file %s: %s", path, exc)
        return {"next_offset": None, "processed": 0, "patched": 0, "skipped": 0}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_json_safe(state), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _lock(path: Path):
    handle = path.open("a+", encoding="utf-8")
    if fcntl is None:
        return handle
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"Another graph-link backfill holds {path}") from exc
    return handle


def _scope_filter(tenant_id: str, corpus_id: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(key="corpus_id", match=MatchValue(value=corpus_id)),
        ]
    )


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _source_segment_id(payload: Dict[str, Any], point_id: Any) -> str:
    explicit = payload.get("source_segment_id") or payload.get("chunk_id")
    if explicit:
        return str(explicit)
    source = str(payload.get("source_url") or payload.get("source") or "unknown")
    chunk_index = payload.get("chunk_index", point_id)
    return f"{source}#segment:{chunk_index}"


def build_graph_patch(
    payload: Dict[str, Any],
    point_id: Any,
    ontology_version: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Return only missing graph metadata and the deterministic entity matches."""
    text = str(payload.get("text") or "")
    title = str(payload.get("title") or "")
    topic = str(payload.get("topic") or "")
    entities = resolve_concepts_in_query(" ".join(part for part in (title, topic, text) if part))
    existing_entities = [str(item) for item in _as_list(payload.get("entity_ids")) if item]
    if existing_entities:
        entities = list(dict.fromkeys(existing_entities + entities))

    patch: Dict[str, Any] = {}
    if not payload.get("entity_ids") and entities:
        patch["entity_ids"] = entities
    if not payload.get("graph_node_ids") and entities:
        patch["graph_node_ids"] = entities
    if not payload.get("source_segment_ids"):
        patch["source_segment_ids"] = [_source_segment_id(payload, point_id)]
    if not payload.get("ontology_version") and entities:
        patch["ontology_version"] = ontology_version
    if not payload.get("entity_resolution_confidence") and entities:
        title_topic = f"{title} {topic}".lower()
        confidence = 0.90 if any(entity.lower() in title_topic for entity in entities) else 0.80
        patch["entity_resolution_confidence"] = confidence
    return patch, entities


def iter_scoped_points(
    client: QdrantClient,
    collection: str,
    scope: Filter,
    offset: Optional[Any],
    page_size: int,
) -> Iterable[Tuple[List[Any], Optional[Any]]]:
    current = offset
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=scope,
            limit=page_size,
            offset=current,
            with_payload=True,
            with_vectors=False,
        )
        yield points, next_offset
        if next_offset is None or not points:
            return
        current = next_offset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist payload patches; dry-run is the default")
    parser.add_argument("--reset-state", action="store_true", help="Ignore the saved cursor and restart")
    parser.add_argument("--url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom"))
    parser.add_argument("--tenant-id", default=os.environ.get("DEFAULT_TENANT_ID", "default"))
    parser.add_argument("--corpus-id", default=os.environ.get("DEFAULT_CORPUS_ID", "askmukthiguru"))
    parser.add_argument("--ontology-version", default=DEFAULT_ONTOLOGY_VERSION)
    parser.add_argument("--page-size", type=int, default=128)
    parser.add_argument("--max-points", type=int, default=0)
    parser.add_argument("--state-file", default=DEFAULT_STATE_PATH)
    parser.add_argument("--lock-file", default=DEFAULT_LOCK_PATH)
    args = parser.parse_args()

    if args.page_size <= 0:
        parser.error("--page-size must be positive")
    if args.max_points < 0:
        parser.error("--max-points cannot be negative")

    state_path = Path(args.state_file)
    lock_handle = _lock(Path(args.lock_file))
    try:
        client = QdrantClient(
            url=args.url,
            api_key=args.api_key or None,
            check_compatibility=False,
        )
        info = client.get_collection(args.collection)
        logger.info("Healthy collection=%s points=%s", args.collection, getattr(info, "points_count", None))
        state = _load_state(state_path, args.reset_state)
        scope = _scope_filter(args.tenant_id, args.corpus_id)
        offset = state.get("next_offset")
        total_processed = int(state.get("processed", 0) or 0)
        total_patched = int(state.get("patched", 0) or 0)
        total_skipped = int(state.get("skipped", 0) or 0)
        samples: List[Dict[str, Any]] = []

        for points, next_offset in iter_scoped_points(
            client, args.collection, scope, offset, args.page_size
        ):
            for point in points:
                if args.max_points and total_processed >= args.max_points:
                    next_offset = None
                    break
                payload = dict(point.payload or {})
                patch, entities = build_graph_patch(payload, point.id, args.ontology_version)
                total_processed += 1
                if not patch:
                    total_skipped += 1
                    continue
                total_patched += 1
                if len(samples) < 10:
                    samples.append({"id": point.id, "entities": entities, "patch": patch})
                if args.apply:
                    client.set_payload(
                        collection_name=args.collection,
                        payload=patch,
                        points=[point.id],
                    )
            state.update(
                {
                    "next_offset": _json_safe(next_offset),
                    "processed": total_processed,
                    "patched": total_patched,
                    "skipped": total_skipped,
                    "collection": args.collection,
                    "tenant_id": args.tenant_id,
                    "corpus_id": args.corpus_id,
                    "apply": bool(args.apply),
                }
            )
            _save_state(state_path, state)
            if next_offset is None or (args.max_points and total_processed >= args.max_points):
                break

        print(json.dumps({
            "collection": args.collection,
            "tenant_id": args.tenant_id,
            "corpus_id": args.corpus_id,
            "apply": bool(args.apply),
            "processed": total_processed,
            "patched": total_patched,
            "skipped": total_skipped,
            "state_file": str(state_path),
            "samples": samples,
        }, ensure_ascii=False, indent=2))
        if not args.apply:
            print("Dry run only; no Qdrant payloads were changed. Re-run with --apply after review.")
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
