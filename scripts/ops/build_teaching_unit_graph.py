"""Offline builder: Qdrant fp-context → Memgraph TeachingUnit projection.

Safety invariants (binding):
- Refuses to run in production (IS_PRODUCTION env must be falsy).
- Read-only from Qdrant: scrolls the fp-context collection with a
  rights_status="licensed" filter.  Never writes to Qdrant or changes aliases.
- Writes ONLY to the :TU_* label namespace in Memgraph (never :base, :Concept,
  :Teacher, or any live-doctrine label).
- All DDL runs in auto-commit sessions (NOT execute_write) — Memgraph constraint.
- Idempotent: every node/edge uses MERGE on span_id/video_id/guru_id.
- Rejected spans (missing required fields) are logged to stderr and recorded in
  the GraphBuildManifest.rejected_span_ids list.
- Writes GraphBuildManifest JSON to backend/config/teaching_unit_graph_manifest.json.

Usage (non-production only):
    cd backend
    IS_PRODUCTION=false python scripts/ops/build_teaching_unit_graph.py \\
        [--collection fp_context_v1] [--batch-size 200] [--dry-run]

Per X1/X28: this file lives in backend/scripts/ops/ (NOT bind-mounted in Docker).
The byte-identical copy at scripts/ops/build_teaching_unit_graph.py is the
container-accessible version; both must be kept in sync.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Absolute path resolution so this script can be run from anywhere.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/scripts/ops → backend → repo
_BACKEND_ROOT = _REPO_ROOT / "backend"
_CONFIG_DIR = _BACKEND_ROOT / "config"
_MANIFEST_PATH = _CONFIG_DIR / "teaching_unit_graph_manifest.json"
_QUERIES_PATH = _CONFIG_DIR / "teaching_unit_graph_queries.json"

# Ensure backend/ is on the path so domain/services can be imported.
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("build_teaching_unit_graph")

try:
    from services.guru_registry import canonical_guru_id, shared_attribution
except ImportError:
    canonical_guru_id = lambda g: g.lower().replace("-", "_") if g else g  # type: ignore
    shared_attribution = lambda: ("preethaji_krishnaji", ["preethaji", "krishnaji"])  # type: ignore

# ---------------------------------------------------------------------------
# Production guard — must be the first check after logging is up.
# ---------------------------------------------------------------------------
_IS_PRODUCTION_RAW = os.environ.get("IS_PRODUCTION", "false").strip().lower()
_IS_PRODUCTION = _IS_PRODUCTION_RAW in ("1", "true", "yes")


def _assert_non_production() -> None:
    """Raise RuntimeError immediately if IS_PRODUCTION is truthy."""
    if _IS_PRODUCTION:
        raise RuntimeError(
            "build_teaching_unit_graph.py refused to run: IS_PRODUCTION is set. "
            "This script may only run in non-production environments."
        )


# ---------------------------------------------------------------------------
# Qdrant field constants
# ---------------------------------------------------------------------------
_RIGHTS_FILTER_VALUE = "licensed"
_REQUIRED_PAYLOAD_FIELDS = ("source_span_id", "video_id", "guru_id")
_OPTIONAL_PAYLOAD_FIELDS = (
    "parent_unit_id",
    "corpus_version",
    "topics",
    "concepts",
    "next_span_id",
    "previous_span_id",
    "rights_status",
)


def _load_queries() -> dict[str, Any]:
    """Load Cypher query templates from config JSON."""
    with _QUERIES_PATH.open() as fh:
        return json.load(fh)["queries"]


# ---------------------------------------------------------------------------
# Rejection helpers
# ---------------------------------------------------------------------------


def _check_required(payload: dict[str, Any]) -> list[str]:
    """Return list of missing required field names."""
    return [f for f in _REQUIRED_PAYLOAD_FIELDS if not payload.get(f)]


# ---------------------------------------------------------------------------
# Memgraph DDL helpers — auto-commit (no execute_write)
# ---------------------------------------------------------------------------


def _run_ddl(driver: Any, cypher: str) -> None:
    """Execute a DDL statement in its own auto-commit session.

    Memgraph does NOT support DDL inside explicit transactions.  Each statement
    must be sent as a standalone query in a fresh session without
    ``execute_write`` / ``execute_read`` wrappers.
    """
    with driver.session() as session:
        session.run(cypher)


def _apply_constraints_and_indexes(driver: Any, queries: dict[str, Any]) -> None:
    """Create uniqueness constraints and indexes idempotently."""
    for stmt in queries.get("create_constraints", []):
        try:
            _run_ddl(driver, stmt)
        except Exception as exc:
            # Constraint already exists → ignore.  Any other error is logged.
            logger.debug("DDL (constraint) skipped or failed: %s — %s", stmt[:60], exc)
    for stmt in queries.get("create_index", []):
        try:
            _run_ddl(driver, stmt)
        except Exception as exc:
            logger.debug("DDL (index) skipped or failed: %s — %s", stmt[:60], exc)


# ---------------------------------------------------------------------------
# Node / edge merge helpers — use auto-commit sessions
# ---------------------------------------------------------------------------


def _merge_node(driver: Any, cypher: str, params: dict[str, Any]) -> None:
    with driver.session() as session:
        session.run(cypher, **params)


def _merge_edge(driver: Any, cypher: str, params: dict[str, Any]) -> None:
    with driver.session() as session:
        session.run(cypher, **params)


# ---------------------------------------------------------------------------
# Main build logic
# ---------------------------------------------------------------------------


def _scroll_qdrant(qdrant_client: Any, collection: str, batch_size: int) -> list[dict[str, Any]]:
    """Scroll the full collection with rights_status filter, return all payloads."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore[import]

    rights_filter = Filter(
        should=[
            FieldCondition(
                key="domain_rights_status", match=MatchValue(value=_RIGHTS_FILTER_VALUE)
            ),
            FieldCondition(key="rights_status", match=MatchValue(value=_RIGHTS_FILTER_VALUE)),
        ]
    )
    all_points: list[dict[str, Any]] = []
    offset = None
    while True:
        results, next_offset = qdrant_client.scroll(
            collection_name=collection,
            scroll_filter=rights_filter,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for record in results:
            payload = dict(record.payload or {})
            payload["_qdrant_id"] = str(record.id)
            all_points.append(payload)
        if next_offset is None:
            break
        offset = next_offset
    return all_points


def build_graph(
    *,
    collection: str = "first_person_v10",
    batch_size: int = 200,
    dry_run: bool = False,
    memgraph_uri: str = "bolt://localhost:7687",
    qdrant_url: str = "http://localhost:6333",
) -> GraphBuildManifest:  # noqa: F821 — imported lazily below
    """Build (or rebuild) the TeachingUnit graph projection.

    Returns a ``GraphBuildManifest`` capturing provenance.  Always writes the
    manifest to ``_MANIFEST_PATH`` on success (even in dry-run, for auditability).
    """
    from domain.first_person_graph import GraphBuildManifest  # noqa: PLC0415

    _assert_non_production()

    queries = _load_queries()

    # --- Connect to Qdrant (read-only) ---
    try:
        from qdrant_client import QdrantClient  # type: ignore[import]

        qdrant_client = QdrantClient(url=qdrant_url)
        info = qdrant_client.get_collection(collection)
        qdrant_point_count = info.points_count or 0
        logger.info("Connected to Qdrant '%s': %d points", collection, qdrant_point_count)
    except Exception as exc:
        raise RuntimeError(f"Cannot connect to Qdrant at {qdrant_url}: {exc}") from exc

    # --- Scroll all licensed payloads ---
    logger.info("Scrolling collection '%s' (rights_status=%s) …", collection, _RIGHTS_FILTER_VALUE)
    all_payloads = _scroll_qdrant(qdrant_client, collection, batch_size)
    logger.info("Scrolled %d payloads from Qdrant", len(all_payloads))

    # --- Validate and partition ---
    valid: list[dict[str, Any]] = []
    rejected_span_ids: list[str] = []

    for payload in all_payloads:
        missing = _check_required(payload)
        if missing:
            span_hint = payload.get("source_span_id") or payload.get("_qdrant_id", "unknown")
            logger.warning("Rejecting payload %s: missing required fields %s", span_hint, missing)
            rejected_span_ids.append(span_hint)
        else:
            valid.append(payload)

    logger.info("Validation: %d valid, %d rejected", len(valid), len(rejected_span_ids))

    # Build a lookup set of all span_ids so we only create continuation edges
    # when BOTH endpoints exist in this scroll (verified epistemic state).
    span_id_set: set[str] = {p["source_span_id"] for p in valid}

    # A1: Compute edge statistics across the scrolled units
    units_with_topics = sum(1 for p in valid if any(t for t in (p.get("topics") or p.get("topic_ids") or [])))
    units_with_concepts = sum(1 for p in valid if any(c for c in (p.get("concepts") or p.get("entity_ids") or [])))
    all_topics: set[str] = set()
    all_concepts: set[str] = set()
    total_topic_edges = 0
    total_concept_edges = 0
    total_video_edges = 0
    total_spoken_by_edges = 0
    total_temporal_edges = 0

    for p in valid:
        t_list = [t for t in (p.get("topics") or p.get("topic_ids") or []) if t]
        c_list = [c for c in (p.get("concepts") or p.get("entity_ids") or []) if c]
        all_topics.update(t_list)
        all_concepts.update(c_list)
        total_topic_edges += len(t_list)
        total_concept_edges += len(c_list)
        if p.get("video_id"):
            total_video_edges += 1
        if p.get("guru_id") or p.get("speaker"):
            total_spoken_by_edges += 1
        if p.get("next_span_id") and p.get("next_span_id") in span_id_set:
            total_temporal_edges += 1
        if p.get("previous_span_id") and p.get("previous_span_id") in span_id_set:
            total_temporal_edges += 1

    dry_run_total_edges = (
        total_video_edges
        + total_spoken_by_edges
        + total_topic_edges
        + total_concept_edges
        + total_temporal_edges
    )

    logger.info(
        "A1 Projection Coverage: %d/%d (%.1f%%) units carry topics (%d unique, %d edges), "
        "%d/%d (%.1f%%) units carry concepts (%d unique, %d edges). Edges: %d video, %d spoken_by, %d temporal.",
        units_with_topics,
        len(valid),
        (units_with_topics / len(valid) * 100.0) if valid else 0.0,
        len(all_topics),
        total_topic_edges,
        units_with_concepts,
        len(valid),
        (units_with_concepts / len(valid) * 100.0) if valid else 0.0,
        len(all_concepts),
        total_concept_edges,
        total_video_edges,
        total_spoken_by_edges,
        total_temporal_edges,
    )

    if dry_run:
        logger.info(
            "[DRY RUN] Would write %d nodes, %d edges (%d video, %d speaker, %d topic, %d concept, %d temporal); skip Memgraph apply.",
            len(valid),
            dry_run_total_edges,
            total_video_edges,
            total_spoken_by_edges,
            total_topic_edges,
            total_concept_edges,
            total_temporal_edges,
        )
        manifest = GraphBuildManifest(
            build_id=f"dryrun-{uuid.uuid4().hex[:8]}",
            built_at=datetime.now(UTC).isoformat(),
            corpus_version=valid[0].get("corpus_version", "unknown") if valid else "unknown",
            qdrant_collection=collection,
            qdrant_point_count=qdrant_point_count,
            node_count=len(valid),
            edge_count=dry_run_total_edges,
            rejection_count=len(rejected_span_ids),
            rights_filter_applied=True,
            rejected_span_ids=rejected_span_ids,
        )
        _write_manifest(manifest)
        return manifest

    # --- Connect to Memgraph ---
    try:
        from neo4j import GraphDatabase  # type: ignore[import]

        from app.config import settings

        user = (
            os.environ.get("MEMGRAPH_USER")
            or os.environ.get("NEO4J_USER")
            or settings.memgraph_username
            or settings.neo4j_user
            or "neo4j"
        )
        password = (
            os.environ.get("MEMGRAPH_PASSWORD")
            or os.environ.get("NEO4J_PASSWORD")
            or settings.memgraph_password
            or settings.neo4j_password
        )
        auth = (user, password) if password else None
        driver = GraphDatabase.driver(memgraph_uri, auth=auth)
        driver.verify_connectivity()
        logger.info("Connected to Memgraph at %s", memgraph_uri)
    except Exception as exc:
        raise RuntimeError(f"Cannot connect to Memgraph at {memgraph_uri}: {exc}") from exc

    try:
        # Apply DDL (auto-commit; idempotent)
        logger.info("Applying constraints and indexes …")
        _apply_constraints_and_indexes(driver, queries)

        schema_version = "tu_graph_v1"
        edge_count = 0
        corpus_version = "unknown"

        for i, payload in enumerate(valid):
            span_id: str = payload["source_span_id"]
            video_id: str = payload["video_id"]
            raw_guru_id: str = payload["guru_id"]
            guru_id: str = canonical_guru_id(raw_guru_id) or raw_guru_id
            parent_id: str = payload.get("parent_unit_id") or ""
            corpus_version = payload.get("corpus_version") or "unknown"
            rights_status: str = (
                payload.get("domain_rights_status")
                or payload.get("rights_status")
                or _RIGHTS_FILTER_VALUE
            )
            topics: list[str] = list(payload.get("topics") or payload.get("topic_ids") or [])
            concepts: list[str] = list(payload.get("concepts") or payload.get("entity_ids") or [])
            next_span_id: str | None = payload.get("next_span_id")
            previous_span_id: str | None = payload.get("previous_span_id")

            # TeachingUnit node
            _merge_node(
                driver,
                queries["merge_teaching_unit"],
                dict(
                    span_id=span_id,
                    parent_id=parent_id,
                    video_id=video_id,
                    guru_id=guru_id,
                    corpus_version=corpus_version,
                    rights_status=rights_status,
                    schema_version=schema_version,
                ),
            )

            # VideoSource node + TU_FROM_VIDEO edge
            _merge_node(
                driver,
                queries["merge_video_source"],
                dict(video_id=video_id, schema_version=schema_version),
            )
            _merge_edge(
                driver,
                queries["merge_from_video_edge"],
                dict(span_id=span_id, video_id=video_id, epistemic_state="observed"),
            )
            edge_count += 1

            # Guru node + TU_SPOKEN_BY edge
            _merge_node(
                driver, queries["merge_guru"], dict(guru_id=guru_id, schema_version=schema_version)
            )
            _merge_edge(
                driver,
                queries["merge_spoken_by_edge"],
                dict(span_id=span_id, guru_id=guru_id, epistemic_state="observed"),
            )
            edge_count += 1

            # Collective lineage edge for shared founder tradition
            shared_primary, shared_founders = shared_attribution()
            if guru_id in shared_founders and shared_primary and "merge_shared_founder_edge" in queries:
                _merge_node(
                    driver, queries["merge_guru"], dict(guru_id=shared_primary, schema_version=schema_version)
                )
                _merge_edge(
                    driver,
                    queries["merge_shared_founder_edge"],
                    dict(guru_id=guru_id, collective_id=shared_primary, epistemic_state="observed"),
                )
                edge_count += 1

            # Topic nodes + TU_HAS_TOPIC edges
            for topic in topics:
                if topic:
                    _merge_node(
                        driver,
                        queries["merge_topic"],
                        dict(name=topic, schema_version=schema_version),
                    )
                    _merge_edge(
                        driver,
                        queries["merge_has_topic_edge"],
                        dict(span_id=span_id, topic=topic, epistemic_state="observed"),
                    )
                    edge_count += 1

            # Concept nodes + TU_HAS_CONCEPT edges
            for concept in concepts:
                if concept:
                    _merge_node(
                        driver,
                        queries["merge_concept"],
                        dict(name=concept, schema_version=schema_version),
                    )
                    _merge_edge(
                        driver,
                        queries["merge_has_concept_edge"],
                        dict(span_id=span_id, concept=concept, epistemic_state="observed"),
                    )
                    edge_count += 1

            # TU_CONTINUES / TU_PRECEDES edges — only when both endpoints exist
            if next_span_id and next_span_id in span_id_set:
                _merge_edge(
                    driver,
                    queries["merge_continues_edge"],
                    dict(from_span_id=span_id, to_span_id=next_span_id, epistemic_state="verified"),
                )
                edge_count += 1

            if previous_span_id and previous_span_id in span_id_set:
                _merge_edge(
                    driver,
                    queries["merge_precedes_edge"],
                    dict(
                        from_span_id=span_id,
                        to_span_id=previous_span_id,
                        epistemic_state="verified",
                    ),
                )
                edge_count += 1

            if (i + 1) % 100 == 0:
                logger.info("  … merged %d / %d nodes", i + 1, len(valid))

        logger.info("Graph build complete: %d nodes, %d edge writes", len(valid), edge_count)

    finally:
        driver.close()

    manifest = GraphBuildManifest(
        build_id=_deterministic_build_id(collection, corpus_version, len(valid)),
        built_at=datetime.now(UTC).isoformat(),
        corpus_version=corpus_version,
        qdrant_collection=collection,
        qdrant_point_count=qdrant_point_count,
        node_count=len(valid),
        edge_count=edge_count,
        rejection_count=len(rejected_span_ids),
        rights_filter_applied=True,
        rejected_span_ids=rejected_span_ids,
    )
    _write_manifest(manifest)
    return manifest


def _deterministic_build_id(collection: str, corpus_version: str, node_count: int) -> str:
    """Short deterministic ID from build inputs (for idempotency checks)."""
    raw = f"{collection}:{corpus_version}:{node_count}"
    return "build-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _write_manifest(manifest: GraphBuildManifest) -> None:  # noqa: F821
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = manifest.to_dict()
    data["rejected_span_ids"] = manifest.rejected_span_ids
    with _MANIFEST_PATH.open("w") as fh:
        json.dump(data, fh, indent=2)
    logger.info("Manifest written to %s", _MANIFEST_PATH)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the TeachingUnit graph projection in Memgraph from fp-context Qdrant data."
    )
    parser.add_argument(
        "--collection",
        default="first_person_v10",
        help="Qdrant collection name (default: first_person_v10)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Qdrant scroll batch size (default: 200)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate payloads and write manifest without touching Memgraph",
    )
    parser.add_argument(
        "--memgraph-uri",
        default=os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687"),
        help="Memgraph Bolt URI",
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant base URL",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        manifest = build_graph(
            collection=args.collection,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            memgraph_uri=args.memgraph_uri,
            qdrant_url=args.qdrant_url,
        )
        print(
            f"Done. nodes={manifest.node_count}, edges={manifest.edge_count}, "
            f"rejected={manifest.rejection_count}"
        )
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
