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

import asyncio
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase  # auth guard
from services.ontology_exporter import OntologyExporter
from domain.spiritual_ontology import ONTOLOGY_VERSION, SEED_CONCEPTS, SEED_RELATIONS

logger = logging.getLogger(__name__)

# Bounded admission control for Neo4j read queries.
# Limits concurrent residual work when asyncio.wait_for times out
# (the underlying sync driver thread continues running; this semaphore
# caps total in-flight queries to prevent unbounded thread pool growth).
_KG_QUERY_SEMAPHORE = asyncio.Semaphore(10)

router = APIRouter(tags=["kg"])

# Bounded admission control: limit concurrent Neo4j query threads to prevent
# unbounded residual work when asyncio.wait_for times out. The inner thread
# (neo4j sync driver) continues executing after timeout; this semaphore
# caps the total in-flight queries to settings.kg_max_concurrent_queries
# (default 10) to bound resource consumption.
_KG_QUERY_SEMAPHORE = asyncio.Semaphore(getattr(settings, "kg_max_concurrent_queries", 10))


_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_WS_RE = re.compile(r"\s+")

# Word-boundary denylist, checked against every token in the WHOLE normalized
# query (not just a literal substring search), so a write smuggled inside e.g.
# FOREACH still gets caught. Comments are stripped and whitespace collapsed
# first, so 'SET\t' / 'SE/**/T' normalize to a plain 'SET' token and can't
# dodge this the way the old uppercased-substring check could be dodged.
_WRITE_TOKENS = {
    "CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", "DROP",
    "CALL", "LOAD", "PERIODIC", "COMMIT", "START", "FOREACH",
}

# Read-only CALL subprocedures this endpoint explicitly allows: schema
# inspection plus the n10s inference hook documented above.
_ALLOWED_CALLS = re.compile(
    r"^CALL\s+(db\.(labels|relationshiptypes|propertykeys|schema\.visualization|"
    r"indexes|constraints)|n10s\.inference\.\w+)\s*\(",
    re.I,
)


def _normalize(query: str) -> str:
    """Strip Cypher comments and collapse whitespace runs to one space."""
    no_comments = _COMMENT_RE.sub(" ", query)
    return _WS_RE.sub(" ", no_comments).strip()


_CALL_KW_RE = re.compile(r"\bCALL\b", re.I)


def _find_call_tokens(query: str) -> list[int]:
    """Return start positions of actual Cypher CALL keywords,
    skipping occurrences inside single/double-quoted strings
    and backtick-delimited identifiers."""
    positions: list[int] = []
    i = 0
    while i < len(query):
        if query[i] in ("'", '"'):
            quote = query[i]
            i += 1
            while i < len(query) and query[i] != quote:
                if query[i] == "\\":
                    i += 1
                i += 1
            i += 1
        elif query[i] == "`":
            i += 1
            while i < len(query) and query[i] != "`":
                if query[i] == "\\":
                    i += 1
                i += 1
            i += 1
        elif query[i:i+4].upper() == "CALL" and (i + 4 >= len(query) or not query[i+4].isalnum() or query[i+4] == "_"):
            positions.append(i)
            i += 4
        else:
            i += 1
    return positions


def _assert_read_only(normalized: str) -> None:
    tokens = set(_WS_RE.split(normalized.upper()))
    bad = tokens & _WRITE_TOKENS
    if "CALL" in bad:
        call_positions = _find_call_tokens(normalized)
        if call_positions:
            all_allowed = True
            for pos in call_positions:
                rest = normalized[pos:]
                if not _ALLOWED_CALLS.match(rest):
                    all_allowed = False
                    break
            if all_allowed:
                bad.discard("CALL")
        else:
            bad.discard("CALL")
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Read-only endpoint. Disallowed token(s): {', '.join(sorted(bad))}",
        )


class SparqlRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.kg_max_query_len,
                        description="SPARQL or Cypher query string (read-only)")
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
    """Forward a (read-only) graph query to Neo4j via n10s.

    n10s 5.x has no SPARQL engine; the query is executed as read-only Cypher.
    Prefix with `CYPHER:` to make intent explicit. Writes are rejected — both
    by the token-boundary guard below and, in case that guard is ever
    bypassed, by the server itself: the query runs inside
    `session.execute_read`, a Neo4j-enforced read-only transaction, not a
    plain auto-commit `session.run`.
    """
    _require_admin(user)

    raw_query = req.query.strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="Empty query.")

    guardrails = getattr(get_container(), "guardrails", None)
    if guardrails is not None:
        gr_result = await guardrails.check_input(raw_query)
        if gr_result.get("blocked"):
            raise HTTPException(
                status_code=400,
                detail=f"Query blocked by guardrail: {gr_result.get('reason', 'unknown')}",
            )

    query = raw_query
    if query.upper().startswith("CYPHER:"):
        query = query[len("CYPHER:"):].strip()
        if not query:
            raise HTTPException(status_code=400, detail="Empty query after CYPHER: prefix.")

    normalized = _normalize(query)
    if not normalized:
        raise HTTPException(status_code=400, detail="Empty query after normalization.")
    _assert_read_only(normalized)

    container = get_container()
    driver = container.neo4j_driver
    if driver is None:
        raise HTTPException(status_code=503, detail="Neo4j driver unavailable.")

    import asyncio

    import neo4j

    timeout_s = settings.kg_query_timeout_s
    db_timeout_s = max(0.5, timeout_s - 0.5)
    _query = neo4j.Query(normalized, timeout=db_timeout_s)

    def _run() -> tuple[list[str], list[dict[str, Any]]]:
        def _read(tx):
            result = tx.run(_query)
            recs = []
            for rec in result:
                recs.append(rec)
                if len(recs) >= req.limit:
                    break
            cols = list(recs[0].keys()) if recs else []
            return cols, [{k: rec.get(k) for k in cols} for rec in recs]

        with driver.session() as session:
            return session.execute_read(_read)

    uid = user.get("id") if isinstance(user, dict) else getattr(user, "id", "?")
    started = time.monotonic()
    try:
        async with _KG_QUERY_SEMAPHORE:
            columns, rows = await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout_s)
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("kg/sparql query timed out (>%.0fs) user=%s", timeout_s, uid)
        raise HTTPException(status_code=504, detail="Query timed out.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("kg/sparql query failed: %s", exc)
        raise HTTPException(status_code=400, detail="Query execution failed. Check syntax and try again.")

    logger.info(
        "kg_audit user=%s len=%d rows=%d ms=%.0f query=%s",
        uid, len(normalized), len(rows), (time.monotonic() - started) * 1000, normalized[:300],
    )

    # Inference hook: when requested, document that n10s.inference.nodesLabelled
    # is available to expand label sets. Full integration is out of scope (YAGNI).
    note = "Executed as read-only Cypher (n10s 5.x has no SPARQL engine)."
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
    # Self-check: import + model sanity + read-only guard bypass coverage.
    assert SubgraphResponse(nodes=[], edges=[], query="x", count=0).count == 0
    assert _teacher_from_labels(["Ekam chunk"]) == "Ekam"
    assert _teacher_from_labels(["Misc"]) == "Misc"

    def _blocked(q: str) -> bool:
        try:
            _assert_read_only(_normalize(q))
            return False
        except HTTPException:
            return True

    # legit reads pass
    _assert_read_only(_normalize("MATCH (n:Concept) RETURN n LIMIT 10"))
    _assert_read_only(_normalize("CALL db.labels()"))
    # writes the old uppercased-substring guard missed are all now blocked
    assert _blocked("MATCH (n) DETACH DELETE n")
    assert _blocked("MATCH (n) SET\tn.x = 1")                       # whitespace variant
    assert _blocked("MATCH (n) CALL/**/apoc.create.node([],{})")     # comment-split phrase
    assert _blocked("LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row")
    assert _blocked("MATCH (n) FOREACH (x IN [1] | CREATE (m))")
    assert _blocked("CALL dbms.security.createUser('x','y',false)")  # non-allowlisted CALL
    print("kg.py ok")