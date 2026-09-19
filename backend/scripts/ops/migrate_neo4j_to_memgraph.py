"""
Graph migration: export a Bolt graph to JSON, import it into another Bolt graph,
verify the result against the dump, then strip migration markers.

Works in both directions and against both engines (Neo4j 5.x and Memgraph 3.x) --
the only engine-specific surface is index DDL, which is detected at runtime.

    python3 -m scripts.ops.migrate_neo4j_to_memgraph export \
        --uri bolt://localhost:7687 --output data/graph_dump.json

    python3 -m scripts.ops.migrate_neo4j_to_memgraph import \
        --uri bolt://<target>:7687 --input data/graph_dump.json

    python3 -m scripts.ops.migrate_neo4j_to_memgraph verify \
        --uri bolt://<target>:7687 --against data/graph_dump.json

    python3 -m scripts.ops.migrate_neo4j_to_memgraph finalize \
        --uri bolt://<target>:7687

`import` is idempotent and safe to re-run against a partially-migrated target: it
MERGEs on migration markers rather than CREATEing. Those markers are what make a
retry safe, so they are removed by a separate `finalize` step and NOT by `import`.
Run `finalize` only once `verify` has passed.

Railway note: Bolt (7687) is not routable from outside the Railway private network.
Expose it with a TCP proxy first -- see scripts/ops/railway_graph_migrate.sh.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_graph")

# Migration markers. Present only between `import` and `finalize`.
NODE_MARKER_LABEL = "_MigrationNode"
NODE_MARKER_PROP = "_migration_id"
REL_MARKER_PROP = "_migration_rid"

# Only identifiers matching this may be interpolated into Cypher. Labels and
# relationship types cannot be parametrized, so every one is checked against the
# pattern before it reaches a query string.
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Payload indexes the application depends on, recreated on the target after import.
TARGET_INDEXES: tuple[tuple[str, str], ...] = (
    ("base", "entity_id"),
    ("base", "entity_name"),
    ("base", "entity_type"),
    ("base", "source_id"),
    ("base", "tenant_id"),
    ("Teacher", "name"),
    ("Concept", "name"),
    ("Practice", "name"),
)


class MigrationError(RuntimeError):
    """Raised when a migration step cannot complete safely."""


def _check_identifier(name: str, kind: str) -> str:
    if not SAFE_IDENTIFIER.match(name):
        raise MigrationError(f"Refusing to interpolate unsafe {kind} into Cypher: {name!r}")
    return name


def _server_kind(session: Session) -> str:
    """Return 'memgraph' or 'neo4j'. Index DDL differs between the two."""
    try:
        session.run("SHOW VERSION").single()
        return "memgraph"
    except Exception:
        return "neo4j"


def _sanitize_val(val: Any) -> Any:
    """Convert Neo4j temporal/spatial or non-JSON types to JSON-serializable types."""
    if hasattr(val, "iso_format"):
        return val.iso_format()
    if hasattr(val, "to_native"):
        return str(val.to_native())
    if isinstance(val, (int, float, str, bool)) or val is None:
        return val
    if isinstance(val, list):
        return [_sanitize_val(x) for x in val]
    if isinstance(val, dict):
        return {k: _sanitize_val(v) for k, v in val.items()}
    return str(val)


def _connect(uri: str, user: str, password: str):
    auth = (user, password) if user or password else None
    driver = GraphDatabase.driver(uri, auth=auth)
    driver.verify_connectivity()
    return driver


# --------------------------------------------------------------------------- export


def export_graph(uri: str, user: str, password: str, output_path: Path) -> dict[str, Any]:
    """Export every node and relationship to a JSON dump with a count manifest."""
    logger.info(f"Connecting to source at {uri}...")
    driver = _connect(uri, user, password)
    start = time.time()

    with driver.session() as session:
        logger.info(f"Source engine: {_server_kind(session)}")

        nodes = [
            {
                "elem_id": rec["elem_id"],
                "labels": rec["labels"],
                "props": _sanitize_val(rec["props"]),
            }
            for rec in session.run(
                "MATCH (n) RETURN elementId(n) AS elem_id, labels(n) AS labels, "
                "properties(n) AS props"
            )
        ]
        logger.info(f"Fetched {len(nodes)} nodes.")

        rels = [
            {
                "rel_id": rec["rel_id"],
                "start_elem_id": rec["start_elem_id"],
                "end_elem_id": rec["end_elem_id"],
                "rel_type": rec["rel_type"],
                "props": _sanitize_val(rec["props"]),
            }
            for rec in session.run(
                "MATCH (a)-[r]->(b) RETURN elementId(r) AS rel_id, "
                "elementId(a) AS start_elem_id, elementId(b) AS end_elem_id, "
                "type(r) AS rel_type, properties(r) AS props"
            )
        ]
        logger.info(f"Fetched {len(rels)} relationships.")

    driver.close()

    payload = {
        "timestamp": time.time(),
        "source_uri": uri,
        "node_count": len(nodes),
        "relationship_count": len(rels),
        "label_histogram": dict(Counter(lbl for n in nodes for lbl in n["labels"])),
        "reltype_histogram": dict(Counter(r["rel_type"] for r in rels)),
        "nodes": nodes,
        "relationships": rels,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        f"Exported {len(nodes)} nodes / {len(rels)} relationships to {output_path} "
        f"in {time.time() - start:.2f}s"
    )
    return payload


# --------------------------------------------------------------------------- indexes


def _create_marker_index(session: Session, engine: str) -> None:
    """Index the migration marker. Without it, relationship wiring is a full scan."""
    if engine == "memgraph":
        stmt = f"CREATE INDEX ON :{NODE_MARKER_LABEL}({NODE_MARKER_PROP})"
    else:
        stmt = (
            f"CREATE INDEX migration_marker_idx IF NOT EXISTS "
            f"FOR (n:{NODE_MARKER_LABEL}) ON (n.{NODE_MARKER_PROP})"
        )
    try:
        session.run(stmt).consume()
    except Exception as exc:  # already exists
        logger.debug(f"Marker index notice: {exc}")


def _drop_marker_index(session: Session, engine: str) -> None:
    if engine == "memgraph":
        stmt = f"DROP INDEX ON :{NODE_MARKER_LABEL}({NODE_MARKER_PROP})"
    else:
        stmt = "DROP INDEX migration_marker_idx IF EXISTS"
    try:
        session.run(stmt).consume()
    except Exception as exc:
        logger.debug(f"Marker index drop notice: {exc}")


def _create_target_indexes(session: Session, engine: str) -> None:
    for label, prop in TARGET_INDEXES:
        _check_identifier(label, "label")
        _check_identifier(prop, "property")
        if engine == "memgraph":
            stmt = f"CREATE INDEX ON :{label}({prop})"
        else:
            stmt = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
        try:
            session.run(stmt).consume()
        except Exception as exc:
            logger.debug(f"Index {label}({prop}): {exc}")


# --------------------------------------------------------------------------- import


def _import_nodes(session: Session, nodes: list[dict[str, Any]], batch_size: int) -> None:
    """MERGE nodes one UNWIND batch per distinct label set.

    Labels cannot be parametrized, so nodes are grouped by their label set and each
    group gets its own statement. 6,430 nodes across 13 label sets is ~13 distinct
    statements instead of 6,430 round trips.
    """
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        groups[tuple(sorted(node["labels"] or []))].append(node)

    logger.info(f"Importing {len(nodes)} nodes across {len(groups)} label sets...")
    done = 0
    for labels, group in groups.items():
        for label in labels:
            _check_identifier(label, "label")
        label_str = ":".join([*labels, NODE_MARKER_LABEL])
        cypher = (
            f"UNWIND $rows AS row "
            f"MERGE (n:{label_str} {{{NODE_MARKER_PROP}: row.id}}) "
            f"SET n += row.props"
        )
        for i in range(0, len(group), batch_size):
            rows = [{"id": n["elem_id"], "props": n["props"]} for n in group[i : i + batch_size]]
            session.run(cypher, rows=rows).consume()
            done += len(rows)
            logger.info(f"  nodes {done}/{len(nodes)}")


def _import_relationships(session: Session, rels: list[dict[str, Any]], batch_size: int) -> None:
    """MERGE relationships one UNWIND batch per relationship type.

    Edges are keyed on their source elementId, not on (start, type, end): this graph
    contains parallel same-type edges between the same pair, which a MERGE without a
    distinguishing property would silently collapse into one.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for idx, rel in enumerate(rels):
        groups[rel["rel_type"]].append({**rel, "_fallback_rid": f"idx:{idx}"})

    logger.info(f"Importing {len(rels)} relationships across {len(groups)} types...")
    done = 0
    for rel_type, group in groups.items():
        _check_identifier(rel_type, "relationship type")
        cypher = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{NODE_MARKER_LABEL} {{{NODE_MARKER_PROP}: row.s}}) "
            f"MATCH (b:{NODE_MARKER_LABEL} {{{NODE_MARKER_PROP}: row.e}}) "
            f"MERGE (a)-[r:{rel_type} {{{REL_MARKER_PROP}: row.rid}}]->(b) "
            f"SET r += row.props"
        )
        for i in range(0, len(group), batch_size):
            rows = [
                {
                    "s": r["start_elem_id"],
                    "e": r["end_elem_id"],
                    "rid": str(r.get("rel_id") or r["_fallback_rid"]),
                    "props": r["props"],
                }
                for r in group[i : i + batch_size]
            ]
            session.run(cypher, rows=rows).consume()
            done += len(rows)
            logger.info(f"  relationships {done}/{len(rels)}")


def import_graph(
    uri: str, user: str, password: str, input_path: Path, batch_size: int = 500
) -> None:
    """Import a dump into the target. Idempotent; leaves migration markers in place."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    rels = data.get("relationships", [])
    logger.info(f"Dump {input_path}: {len(nodes)} nodes, {len(rels)} relationships.")

    driver = _connect(uri, user, password)
    start = time.time()

    with driver.session() as session:
        engine = _server_kind(session)
        logger.info(f"Target engine: {engine} at {uri}")

        _create_marker_index(session, engine)
        _import_nodes(session, nodes, batch_size)
        _create_target_indexes(session, engine)
        _import_relationships(session, rels, batch_size)

        live_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        live_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

    driver.close()
    logger.info(
        f"Import finished in {time.time() - start:.2f}s. "
        f"Target now holds {live_nodes} nodes / {live_rels} relationships."
    )
    logger.info("Migration markers retained so a retry stays safe. Run `verify`, then `finalize`.")


# --------------------------------------------------------------------------- verify


def verify_graph(uri: str, user: str, password: str, against: Path | None) -> bool:
    """Compare the live target against the dump manifest. Returns True when it matches."""
    driver = _connect(uri, user, password)
    with driver.session() as session:
        live = {
            "node_count": session.run("MATCH (n) RETURN count(n) AS c").single()["c"],
            "relationship_count": session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()[
                "c"
            ],
            "label_histogram": {
                rec["l"]: rec["c"]
                for rec in session.run("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c")
                if rec["l"] != NODE_MARKER_LABEL
            },
            "reltype_histogram": {
                rec["t"]: rec["c"]
                for rec in session.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c")
            },
        }
    driver.close()

    logger.info(
        f"Target {uri}: {live['node_count']} nodes, {live['relationship_count']} relationships"
    )
    if against is None:
        logger.warning("No --against dump supplied; counts reported but NOT verified.")
        return True

    expected = json.loads(against.read_text(encoding="utf-8"))
    return _report_mismatches(expected, live)


def _report_mismatches(expected: dict[str, Any], live: dict[str, Any]) -> bool:
    """Log every discrepancy between dump and target. Returns True when identical."""
    failures: list[str] = []

    for key in ("node_count", "relationship_count"):
        if expected.get(key) != live[key]:
            failures.append(f"{key}: dump={expected.get(key)} target={live[key]}")

    for key in ("label_histogram", "reltype_histogram"):
        exp_hist: dict[str, int] = expected.get(key, {})
        live_hist: dict[str, int] = live[key]
        for name in sorted(set(exp_hist) | set(live_hist)):
            if exp_hist.get(name, 0) != live_hist.get(name, 0):
                failures.append(
                    f"{key}[{name}]: dump={exp_hist.get(name, 0)} target={live_hist.get(name, 0)}"
                )

    if failures:
        logger.error(f"VERIFY FAILED -- {len(failures)} mismatch(es):")
        for line in failures:
            logger.error(f"  {line}")
        return False

    logger.info(
        f"VERIFY PASSED -- {live['node_count']} nodes, {live['relationship_count']} "
        f"relationships, {len(live['label_histogram'])} labels, "
        f"{len(live['reltype_histogram'])} relationship types all match the dump."
    )
    return True


# --------------------------------------------------------------------------- finalize


def finalize_graph(uri: str, user: str, password: str, batch_size: int = 1000) -> None:
    """Strip migration markers. Run only after `verify` passes -- this ends retry safety."""
    driver = _connect(uri, user, password)
    with driver.session() as session:
        engine = _server_kind(session)

        removed = _drain(
            session,
            f"MATCH (n:{NODE_MARKER_LABEL}) WITH n LIMIT $limit "
            f"REMOVE n:{NODE_MARKER_LABEL}, n.{NODE_MARKER_PROP} RETURN count(*) AS c",
            batch_size,
        )
        logger.info(f"Cleared node markers from {removed} nodes.")

        removed = _drain(
            session,
            f"MATCH ()-[r]->() WHERE r.{REL_MARKER_PROP} IS NOT NULL WITH r LIMIT $limit "
            f"REMOVE r.{REL_MARKER_PROP} RETURN count(*) AS c",
            batch_size,
        )
        logger.info(f"Cleared relationship markers from {removed} relationships.")

        _drop_marker_index(session, engine)
    driver.close()
    logger.info("Finalize complete. The target is now a plain graph with no migration metadata.")


def _drain(session: Session, cypher: str, batch_size: int) -> int:
    """Run a LIMIT-ed mutation repeatedly until it stops matching rows.

    Batched because the target runs under a hard memory cap (Memgraph is started with
    --memory-limit=512); a single transaction touching every node can exceed it.
    """
    total = 0
    while True:
        count = session.run(cypher, limit=batch_size).single()["c"]
        if not count:
            return total
        total += count


# --------------------------------------------------------------------------- cli


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a Bolt graph between servers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--uri", default="bolt://localhost:7687")
        sub.add_argument("--user", default="neo4j")
        sub.add_argument("--password", default="")

    exp = subparsers.add_parser("export")
    _common(exp)
    exp.add_argument("--output", default="data/graph_dump.json")

    imp = subparsers.add_parser("import")
    _common(imp)
    imp.add_argument("--input", default="data/graph_dump.json")
    imp.add_argument("--batch-size", type=int, default=500)

    ver = subparsers.add_parser("verify")
    _common(ver)
    ver.add_argument(
        "--against", default=None, help="Dump to compare against; omit for counts only"
    )

    fin = subparsers.add_parser("finalize")
    _common(fin)
    fin.add_argument("--batch-size", type=int, default=1000)

    args = parser.parse_args()

    if args.command == "export":
        export_graph(args.uri, args.user, args.password, Path(args.output))
    elif args.command == "import":
        import_graph(
            args.uri, args.user, args.password, Path(args.input), batch_size=args.batch_size
        )
    elif args.command == "verify":
        against = Path(args.against) if args.against else None
        if not verify_graph(args.uri, args.user, args.password, against):
            return 1
    elif args.command == "finalize":
        finalize_graph(args.uri, args.user, args.password, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
