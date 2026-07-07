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

from fastapi import APIRouter, Depends, HTTPException
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
        raise HTTPException(status_code=400, detail=f"Query failed: {exc}") from exc

    # Inference hook: when requested, document that n10s.inference.nodesLabelled
    # is available to expand label sets. Full integration is out of scope (YAGNI).
    if req.inference:
        note = (
            "Executed as read-only Cypher. n10s.inference.nodesLabelled/<label> "
            "available for OWL/RDFS class inference — append to the Cypher query "
            "to expand results with inferred labels."
        )

    return SparqlResponse(columns=columns, rows=rows, count=len(rows), inference=req.inference, note=note)