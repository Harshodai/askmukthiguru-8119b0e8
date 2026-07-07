"""
Neosemantics (n10s) initialization + RDF export for Neo4j.

Requires: NEO4J_PLUGINS=["apoc","n10s"] on the neo4j container.

This module:
  1. Creates the n10s uniqueness constraint on :Resource.uri.
  2. Initializes the n10s graph config (one-time per DB; idempotent here).
  3. Records schema-check availability (n10s 5.17.0 removed `n10s.schema.check`;
     only `n10s.validation.shacl.*` remains).
  4. Exports the existing spiritual ontology (seed_ontology.py output) to RDF/Turtle
     via n10s.rdf.export.cypher + n10s.rdf.collect.ttl, saved under data/ontology/.

n10s 5.x NOTES:
  - `n10s.sparql` was REMOVED. Use Cypher + n10s.inference.* functions for graph
    queries. The /api/kg/sparql endpoint therefore degrades to a read-only Cypher
    passthrough that returns rows — documented in its docstring. No SPARQL executed.
  - `n10s.schema.check` was REMOVED. Use n10s.validation.shacl.* for validation.
  - RDF export = `n10s.rdf.export.cypher(cypherQuery, params)` (streams SPO triples)
    piped through the scalar `n10s.rdf.collect.ttl(...)` accumulator.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Repo root = backend/..  (this script lives in backend/scripts/)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPORT_DIR = _REPO_ROOT / "data" / "ontology"


def _driver():
    """Build a Neo4j driver from app settings (mirrors ServiceContainer)."""
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    from app.config import settings  # noqa: WPS433

    if not settings.neo4j_uri:
        raise RuntimeError("NEO4J_URI not configured")

    from neo4j import GraphDatabase  # noqa: WPS433

    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def init_neosemantics(driver) -> dict[str, Any]:
    """
    Run the n10s init dance. Idempotent — safe to call on every boot.

    Returns a dict with the constraint / graphconfig / schema.check results.
    """
    results: dict[str, Any] = {}

    def _constraint(tx):
        tx.run(
            "CREATE CONSTRAINT n10sUniqueConstrain IF NOT EXISTS "
            "FOR (r:Resource) REQUIRE r.uri IS UNIQUE"
        )

    def _graphconfig(tx):
        # graphconfig.init returns the initial config map (one row) on first call,
        # and errors if called twice — guard with try/except.
        try:
            recs = list(
                tx.run("CALL n10s.graphconfig.init() YIELD param, value RETURN param, value")
            )
            return [{"param": r["param"], "value": r["value"]} for r in recs]
        except Exception as exc:  # noqa: BLE001
            # Already initialized — fall back to show()
            try:
                recs = list(
                    tx.run("CALL n10s.graphconfig.show() YIELD param, value RETURN param, value")
                )
                return [{"param": r["param"], "value": r["value"], "existing": True} for r in recs]
            except Exception:
                return {"error": str(exc)}

    with driver.session() as session:
        session.execute_write(_constraint)
        results["constraint"] = "n10sUniqueConstrain ensured"

    with driver.session() as session:
        results["graphconfig"] = session.execute_write(_graphconfig)

    # schema.check — NOT available in n10s 5.17.0 (procedure removed; only
    # n10s.validation.shacl.* remains for validation). Record availability.
    try:
        with driver.session() as session:
            rec = session.run(
                "SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'n10s.validation' RETURN count(*) AS n"
            ).single()
            results["schema_check"] = f"n10s.schema.check not in n10s 5.x; validation procs available: {rec['n'] if rec else 0}"
    except Exception as exc:  # noqa: BLE001
        results["schema_check"] = f"error: {exc}"

    logger.info("n10s init complete: %s", results)
    return results


def export_ontology_to_ttl(driver, out_path: Path | None = None) -> Path:
    """
    Export the spiritual ontology (all :base / :Teacher / :Concept / :Practice
    nodes + their relationships) to a Turtle (.ttl) file via n10s.

    n10s 5.x exposes RDF export as:
      - n10s.rdf.export.cypher(cypher, params) → streams SPO triples for the
        subgraph matched by the given Cypher query.
      - n10s.rdf.collect.ttl(s, p, o, isLit, type, lang, sspo) → scalar function
        that accumulates a row into a Turtle document; final row's return value
        is the complete .ttl text.

    We run a Cypher query that returns every ontology node + relationship as RDF
    triples, pipe each triple through n10s.rdf.collect.ttl, and write the final
    accumulated string to disk.

    The seed_ontology.py nodes are NOT :Resource, so n10s needs handleVocabUris
    config to map them — we tag them with synthetic URIs first, export, then
    strip the temporary tags. Original seed data is left untouched.

    Returns the path to the written .ttl file.
    """
    out_path = out_path or _EXPORT_DIR / "spiritual_ontology.ttl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Tag nodes with synthetic URIs so n10s can address them as resources.
    tag_cypher = """
    MATCH (n)
    WHERE (n:Teacher OR n:Concept OR n:Practice OR n:base)
      AND NOT n:Resource
    SET n:Resource,
        n.uri = coalesce(n.uri, 'urn:mukthiguru:' + coalesce(n.entity_id, n.name))
    RETURN count(n) AS tagged
    """
    # Cypher query handed to n10s.rdf.export.cypher — it walks the matched
    # subgraph and emits one row per RDF triple (subject, predicate, object, ...).
    export_query = """
    MATCH (n:Resource)
    WHERE n.uri STARTS WITH 'urn:mukthiguru:'
    RETURN n
    """

    ttl_text = ""
    with driver.session() as session:
        # 1. Tag
        rec = session.run(tag_cypher).single()
        logger.info("Tagged %s ontology nodes as :Resource", rec["tagged"] if rec else "?")

        # 2. Export via n10s.rdf.export.cypher + n10s.rdf.collect.ttl
        try:
            cypher = (
                "CALL n10s.rdf.export.cypher($q) "
                "YIELD subject, predicate, object, isLiteral, literalType, literalLang, subjectSPO "
                "WITH subject, predicate, object, isLiteral, literalType, literalLang, subjectSPO "
                "RETURN n10s.rdf.collect.ttl("
                "subject, predicate, object, isLiteral, literalType, literalLang, subjectSPO"
                ") AS ttl"
            )
            last_ttl = ""
            for rec in session.run(cypher, {"q": export_query}):
                last_ttl = rec["ttl"]
            ttl_text = last_ttl
        except Exception as exc:  # noqa: BLE001
            logger.warning("n10s RDF export failed: %s", exc)
            _strip_resource_tags(driver)
            raise

    out_path.write_text(ttl_text, encoding="utf-8")

    # 3. Cleanup — remove temporary :Resource labels + synthetic uris.
    _strip_resource_tags(driver)

    logger.info("Exported ontology TTL -> %s (%d bytes)", out_path, len(ttl_text))
    return out_path


def _strip_resource_tags(driver) -> None:
    """Remove the temporary :Resource label + synthetic uri we added during export."""
    cypher = """
    MATCH (n:Resource)
    WHERE (n:Teacher OR n:Concept OR n:Practice OR n:base)
      AND n.uri STARTS WITH 'urn:mukthiguru:'
    REMOVE n:Resource
    REMOVE n.uri
    """
    try:
        with driver.session() as session:
            session.run(cypher)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resource tag cleanup failed (non-fatal): %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    drv = _driver()
    try:
        drv.verify_connectivity()
        print("Connected to Neo4j.")
        res = init_neosemantics(drv)
        print("init_neosemantics result:")
        for k, v in res.items():
            print(f"  {k}: {v}")
        path = export_ontology_to_ttl(drv)
        print(f"RDF export -> {path} ({path.stat().st_size} bytes)")
    finally:
        drv.close()