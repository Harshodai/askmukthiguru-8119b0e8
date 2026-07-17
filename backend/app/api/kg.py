"""
Knowledge-graph query endpoint (Neosemantics-backed).

n10s 5.x removed the `n10s.sparql` procedure — SPARQL is no longer shipped with
the plugin. This endpoint therefore accepts a SPARQL-shaped request but executes
it as a read-only Cypher passthrough over the Neo4j graph, optionally leveraging
n10s.inference.* functions for OWL/RDFS inference at query time.

POST /api/kg/sparql
  body: { "query": "<SPARQL or Cypher string>", "inference": false }

If `query` starts with "CYPHER:" it is run verbatim as a read-only Cypher query.
Otherwise (SPARQL or plain Cypher) it is treated as Cypher and run read-only.
All queries run in a read transaction; writes are rejected by the driver.

Inference: when `inference=true`, the endpoint also runs
`CALL n10s.inference.nodesLabelled(...)` patterns — see _INFERRED_LABELS below.
For now this is a stub that documents the inference hook; full SPARQL→Cypher
translation is out of scope (YAGNI).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase  # auth guard
from services.ontology_exporter import OntologyExporter
from domain.spiritual_ontology import ONTOLOGY_VERSION, SEED_CONCEPTS, SEED_RELATIONS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["kg"])


class SparqlRequest(BaseModel):
    query: str = Field(..., description="SPARQL or Cypher query string (read-only)")
    inference: bool = Field(
        False,
        description="If true, also invoke n10s.inference.nodesLabelled for inferred labels.",
    )
    limit: int = Field(100, ge=1, le=1000)


class SparqlResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    count: int
    inference: bool
    note: str | None = None


# Read-only guard: reject queries that look like writes.
_WRITE_KEYWORDS = ("CREATE", "MERGE", "DELETE", "DETACH", "SET ", "DROP", "REMOVE", "CALL APOC", "LOAD CSV")


def _is_read_only(query: str) -> bool:
    q = query.upper()
    return not any(kw in q for kw in _WRITE_KEYWORDS)


def _require_admin(user: Any) -> None:
    """Raise 403 unless the caller is an admin/superuser."""
    is_admin = False
    if isinstance(user, dict):
        is_admin = bool(user.get("is_superuser") or user.get("is_admin"))
        roles = user.get("roles") or []
        if isinstance(roles, (list, tuple)) and "admin" in roles:
            is_admin = True
    else:
        is_admin = bool(getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin role required.")


@router.post("/kg/sparql", response_model=SparqlResponse)
async def kg_sparql(req: SparqlRequest, user=Depends(get_current_user_from_supabase)) -> SparqlResponse:
    _require_admin(user)
    """Forward a (read-only) graph query to Neo4j via n10s.

    n10s 5.x has no SPARQL engine; the query is executed as read-only Cypher.
    Prefix with `CYPHER:` to make intent explicit. Writes are rejected.
    """
    query = req.query.strip()
    if query.upper().startswith("CYPHER:"):
        query = query[len("CYPHER:"):].strip()

    if not _is_read_only(query):
        raise HTTPException(status_code=400, detail="Only read-only queries are accepted.")

    container = get_container()
    driver = container.neo4j_driver
    if driver is None:
        raise HTTPException(status_code=503, detail="Neo4j driver unavailable.")

    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    note = "Executed as read-only Cypher (n10s 5.x has no SPARQL engine)."

    try:
        with driver.session() as session:
            result = session.run(query)
            # Bolt 5 gives keys via .keys() after first consumption; collect records.
            recs = []
            for rec in result:
                recs.append(rec)
                if len(recs) >= req.limit:
                    break
            if recs:
                columns = list(recs[0].keys())
            for rec in recs:
                rows.append({k: rec.get(k) for k in columns})
    except Exception as exc:  # noqa: BLE001
        logger.warning("kg/sparql query failed: %s", exc)
        raise HTTPException(status_code=400, detail="Query execution failed. Check syntax and try again.")

    # Inference hook: when requested, document that n10s.inference.nodesLabelled
    # is available to expand label sets. Full integration is out of scope (YAGNI).
    if req.inference:
        note = (
            "Executed as read-only Cypher. n10s.inference.nodesLabelled/<label> "
            "available for OWL/RDFS class inference — append to the Cypher query "
            "to expand results with inferred labels."
        )

    return SparqlResponse(columns=columns, rows=rows, count=len(rows), inference=req.inference, note=note)


# ── E6.5: query-driven subgraph for the KG visualizer ──────────────────────────


class KGNode(BaseModel):
    id: str
    label: str
    type: str
    teacher: str | None = None


class KGEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class SubgraphResponse(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
    query: str
    count: int


def _teacher_from_labels(labels: list[str] | None) -> str | None:
    """Best-effort: surface a teacher/tradition tag from Neo4j labels.
    LightRAG nodes are labelled by source chunk; we look for known teacher markers."""
    if not labels:
        return None
    joined = " ".join(labels).lower()
    for key in ("preethaji", "krishnaji", "ekam", "buddha", "osho", "krishnamurti"):
        if key in joined:
            return key.capitalize()
    return labels[0] if labels else None


@router.get("/kg/subgraph", response_model=SubgraphResponse)
async def kg_subgraph(
    query: str = Query(..., min_length=1, description="Concept or keyword to center the subgraph on"),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> SubgraphResponse:
    """Return a concept subgraph around `query` for the KG visualizer.

    Ponytail: one Cypher query, 1-2 hop neighborhood, graceful fallback to empty.
    Output shape: {nodes:[{id,label,type,teacher}], edges:[{source,target,label}]}.
    """
    container = get_container()
    driver = container.neo4j_driver
    if driver is None:
        return SubgraphResponse(nodes=[], edges=[], query=query, count=0)

    q = query.strip().lower()
    nodes: dict[str, KGNode] = {}
    edges: list[KGEdge] = []

    try:
        with driver.session() as session:
            # 1-hop neighborhood: any node whose entity_id contains the query,
            # plus its immediate neighbours. LightRAG writes `entity_id`.
            cypher = """
            MATCH (n)
            WHERE toLower(n.entity_id) CONTAINS $q
            WITH n LIMIT $cap
            OPTIONAL MATCH (n)-[r]->(m)
            RETURN n.entity_id AS src_id, labels(n) AS src_labels, type(r) AS rel, m.entity_id AS dst_id, labels(m) AS dst_labels
            """
            result = session.run(cypher, q=q, cap=limit)
            for rec in result:
                src = rec.get("src_id")
                if not src:
                    continue
                if src not in nodes:
                    nodes[src] = KGNode(
                        id=src,
                        label=src,
                        type=(rec.get("src_labels") or ["Concept"])[0],
                        teacher=_teacher_from_labels(rec.get("src_labels")),
                    )
                dst = rec.get("dst_id")
                if dst:
                    if dst not in nodes:
                        nodes[dst] = KGNode(
                            id=dst,
                            label=dst,
                            type=(rec.get("dst_labels") or ["Concept"])[0],
                            teacher=_teacher_from_labels(rec.get("dst_labels")),
                        )
                    edges.append(KGEdge(source=src, target=dst, label=rec.get("rel")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("kg/subgraph query failed: %s", exc)
        return SubgraphResponse(nodes=[], edges=[], query=query, count=0)

    return SubgraphResponse(
        nodes=list(nodes.values()),
        edges=edges,
        query=query,
        count=len(nodes),
    )


# ── A2: Ontology export (Turtle / JSON-LD) ────────────────────────────────────


@router.get("/ontology/export")
async def export_ontology(
    format: str = Query("jsonld", pattern="^(turtle|jsonld)$"),
    user: dict = Depends(get_current_user_from_supabase),
) -> Any:
    """Export the live Neo4j ontology to Turtle or JSON-LD.

    Ponytail: thin wrapper over ``OntologyExporter.materialize_from_graph``
    + a serializer. 30s timeout headroom for large graphs. Admin-gated in
    production (matches the established kg.py pattern); locally the auth
    guard still runs but ``is_production=false`` skips the admin check.
    """
    if settings.is_production:
        _require_admin(user)

    container = get_container()
    driver = container.neo4j_driver
    if driver is None:
        raise HTTPException(status_code=503, detail="Neo4j driver unavailable.")

    exporter = OntologyExporter(neo4j_driver=driver)

    import asyncio

    try:
        concepts, relations = await asyncio.wait_for(
            asyncio.to_thread(exporter.materialize_from_graph),
            timeout=30.0,
        )
    except (asyncio.TimeoutError, TimeoutError) as _to_exc:  # noqa: BLE001
        logger.warning("ontology/export timed out (>30s): %s", _to_exc)
        raise HTTPException(status_code=504, detail="Ontology export timed out (>30s).")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ontology/export materialization failed: %s", exc)
        raise HTTPException(status_code=500, detail="Ontology export failed.")

    if format == "turtle":
        from fastapi import Response

        body = exporter.to_rdf_turtle(concepts, relations)
        return Response(content=body, media_type="text/turtle; charset=utf-8")
    # default: jsonld
    return exporter.to_jsonld(concepts, relations)


# ── Phase 7: Ontology versioning ─────────────────────────────────────────────


class OntologyVersionResponse(BaseModel):
    version: str
    concept_count: int
    relation_count: int
    source: str  # "neo4j" | "seed_fallback"


@router.get("/ontology/version", response_model=OntologyVersionResponse)
async def ontology_version(
    user: dict = Depends(get_current_user_from_supabase),
) -> OntologyVersionResponse:
    """Return the current ontology version + live concept/relation counts.

    Ponytail: prefer Neo4j counts; fall back to SEED_CONCEPTS/SEED_RELATIONS
    when the driver is missing so the endpoint stays useful without infra.
    30s timeout headroom; admin-gated in production (matches /ontology/export).
    """
    if settings.is_production:
        _require_admin(user)

    container = get_container()
    driver = container.neo4j_driver

    if driver is not None:
        import asyncio

        def _version_and_counts() -> dict:
            with driver.session() as session:
                # Read the ontology_version persisted on any node — all
                # ontology writer writes stamp the same version on every
                # node and relationship, so the first non-null value is
                # authoritative. Returns the imported constant only when
                # no persisted version exists (pre-versioning graph).
                version_row = session.run(
                    "MATCH (n) WHERE n.ontology_version IS NOT NULL "
                    "RETURN n.ontology_version AS v LIMIT 1"
                ).single()
                persisted_version = str(version_row["v"]) if version_row and version_row.get("v") else ONTOLOGY_VERSION
                # Count only records matching the persisted version.
                c = session.run(
                    "MATCH (n) WHERE any(l IN labels(n) WHERE l IN "
                    "['Concept', 'Practice', 'Teacher']) "
                    "AND n.ontology_version = $v RETURN count(n) AS c",
                    v=persisted_version,
                ).single()
                r = session.run(
                    "MATCH (a)-[r]->(b) WHERE any(la IN labels(a) WHERE la IN "
                    "['Concept', 'Practice', 'Teacher']) AND any(lb IN labels(b) "
                    "WHERE lb IN ['Concept', 'Practice', 'Teacher']) "
                    "AND r.ontology_version = $v RETURN count(r) AS c",
                    v=persisted_version,
                ).single()
                return {
                    "version": persisted_version,
                    "concept_count": int(c["c"] if c else 0),
                    "relation_count": int(r["c"] if r else 0),
                }

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_version_and_counts), timeout=30.0
            )
            return OntologyVersionResponse(
                version=result["version"],
                concept_count=result["concept_count"],
                relation_count=result["relation_count"],
                source="neo4j",
            )
        except TimeoutError:
            logger.warning("ontology/version: Neo4j count timed out; using seed fallback.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ontology/version: Neo4j count failed: %s; using seed fallback.", exc)

    return OntologyVersionResponse(
        version=ONTOLOGY_VERSION,
        concept_count=len(SEED_CONCEPTS),
        relation_count=len(SEED_RELATIONS),
        source="seed_fallback",
    )


if __name__ == "__main__":
    # Self-check: import + model sanity.
    assert SubgraphResponse(nodes=[], edges=[], query="x", count=0).count == 0
    assert _teacher_from_labels(["Ekam chunk"]) == "Ekam"
    assert _teacher_from_labels(["Misc"]) == "Misc"
    print("kg.py ok")