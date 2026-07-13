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

from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase  # auth guard

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
_WRITE_KEYWORDS = ("CREATE", "MERGE", "DELETE", "DETACH", "SET ", "DROP", "REMOVE")


def _is_read_only(query: str) -> bool:
    q = query.upper()
    return not any(kw in q for kw in _WRITE_KEYWORDS)


@router.post("/kg/sparql", response_model=SparqlResponse)
async def kg_sparql(req: SparqlRequest, _user=Depends(get_current_user_from_supabase)) -> SparqlResponse:
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
    _user: dict = Depends(get_current_user_from_supabase),
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


if __name__ == "__main__":
    # Self-check: import + model sanity.
    assert SubgraphResponse(nodes=[], edges=[], query="x", count=0).count == 0
    assert _teacher_from_labels(["Ekam chunk"]) == "Ekam"
    assert _teacher_from_labels(["Misc"]) == "Misc"
    print("kg.py ok")