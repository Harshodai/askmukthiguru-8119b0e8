"""Memgraph adapter with store-level rights enforcement and provenance-preserving traversal."""

from __future__ import annotations

import logging
from typing import Any

from domain.evidence_contract import EvidenceCandidate, make_source_id

logger = logging.getLogger(__name__)

# Every Memgraph read enforces rights_status = 'licensed' and tenant isolation
# at the store adapter boundary (never left to individual callers).
_CONCEPT_TRAVERSAL_CYPHER = """
UNWIND $concepts AS cname
MATCH (c:Concept)
WHERE toLower(c.name) CONTAINS toLower(cname)
OPTIONAL MATCH (c)-[r1]-(tu:TUTeachingUnit)
WHERE tu.rights_status = 'licensed'
  AND coalesce(tu.tenant_id, $tenant_id) = $tenant_id
OPTIONAL MATCH (tu)-[r2:TU_CONTINUES|TU_PRECEDES]-(adj:TUTeachingUnit)
WHERE adj.rights_status = 'licensed'
  AND coalesce(adj.tenant_id, $tenant_id) = $tenant_id
WITH collect(DISTINCT tu) + collect(DISTINCT adj) AS units, collect(DISTINCT c.name) AS matched_concepts
UNWIND units AS u
WITH DISTINCT u, matched_concepts
WHERE u IS NOT NULL AND u.rights_status = 'licensed'
RETURN u.span_id AS evidence_id,
       u.video_id AS video_id,
       u.guru_id AS guru_id,
       u.text AS text,
       u.verbatim_text AS verbatim_text,
       u.start_ms AS start_ms,
       u.end_ms AS end_ms,
       u.corpus_version AS corpus_version,
       u.rights_status AS rights_status,
       matched_concepts
LIMIT $limit
"""

_ADJACENCY_BY_SPAN_CYPHER = """
UNWIND $span_ids AS sid
MATCH (seed:TUTeachingUnit {span_id: sid})
WHERE seed.rights_status = 'licensed'
  AND coalesce(seed.tenant_id, $tenant_id) = $tenant_id
MATCH (seed)-[r:TU_CONTINUES|TU_PRECEDES|TU_HAS_TOPIC|TU_HAS_CONCEPT*1..2]-(neighbor:TUTeachingUnit)
WHERE neighbor.span_id <> sid
  AND neighbor.rights_status = 'licensed'
  AND coalesce(neighbor.tenant_id, $tenant_id) = $tenant_id
  AND NOT (seed)-[:TU_DUPLICATE_OF]-(neighbor)
RETURN DISTINCT neighbor.span_id AS evidence_id,
       neighbor.video_id AS video_id,
       neighbor.guru_id AS guru_id,
       neighbor.text AS text,
       neighbor.verbatim_text AS verbatim_text,
       neighbor.start_ms AS start_ms,
       neighbor.end_ms AS end_ms,
       neighbor.corpus_version AS corpus_version,
       neighbor.rights_status AS rights_status,
       seed.span_id AS seed_span_id,
       [rel IN r | type(rel)] AS rel_types
LIMIT $limit
"""


class MemgraphEvidenceAdapter:
    """Executes bounded, rights-filtered graph queries and normalizes into EvidenceCandidate."""

    def __init__(self, driver: Any, *, tenant_id: str = "oneness") -> None:
        self._driver = driver
        self._tenant_id = tenant_id

    def discover_by_concepts(
        self,
        concepts: list[str],
        *,
        limit: int = 12,
        teacher_id: str | None = None,
        raise_on_error: bool = False,
    ) -> list[EvidenceCandidate]:
        if self._driver is None or not concepts or limit <= 0:
            return []
        clean_concepts = [c.strip() for c in concepts if isinstance(c, str) and c.strip()][:8]
        if not clean_concepts:
            return []
        try:
            with self._driver.session() as session:
                rows = [
                    dict(r)
                    for r in session.run(
                        _CONCEPT_TRAVERSAL_CYPHER,
                        concepts=clean_concepts,
                        tenant_id=self._tenant_id,
                        limit=limit * 2,
                    )
                ]
            return self._rows_to_candidates(rows, teacher_id=teacher_id, limit=limit)
        except Exception as exc:
            if raise_on_error:
                logger.warning("[MemgraphEvidenceAdapter] concept traversal failed: %s", exc)
                raise
            logger.debug("[MemgraphEvidenceAdapter] concept traversal failed: %s", exc)
            return []

    def expand_from_evidence_ids(
        self,
        evidence_ids: list[str],
        *,
        limit: int = 12,
        teacher_id: str | None = None,
    ) -> list[EvidenceCandidate]:
        if self._driver is None or not evidence_ids or limit <= 0:
            return []
        clean_ids = [eid.strip() for eid in evidence_ids if isinstance(eid, str) and eid.strip()][
            :12
        ]
        if not clean_ids:
            return []
        try:
            with self._driver.session() as session:
                rows = [
                    dict(r)
                    for r in session.run(
                        _ADJACENCY_BY_SPAN_CYPHER,
                        span_ids=clean_ids,
                        tenant_id=self._tenant_id,
                        limit=limit * 2,
                    )
                ]
            return self._rows_to_candidates(rows, teacher_id=teacher_id, limit=limit)
        except Exception as exc:
            logger.debug("[MemgraphEvidenceAdapter] span expansion failed: %s", exc)
            return []

    def get_concept_neighborhood(
        self, concept_names: list[str], *, limit: int = 25
    ) -> list[dict[str, Any]]:
        """Return concept-to-concept relationships with provenance for dossiers & concept maps."""
        if self._driver is None or not concept_names:
            return []
        cypher = """
        UNWIND $names AS cname
        MATCH (c:Concept)-[r]-(nbr)
        WHERE toLower(c.name) CONTAINS toLower(cname)
          AND (nbr:Concept OR nbr:Practice OR nbr:Teacher)
        RETURN DISTINCT c.name AS source_concept,
               type(r) AS relationship,
               coalesce(nbr.name, nbr.entity_id) AS target_concept,
               labels(nbr) AS target_labels,
               coalesce(r.provenance_kind, 'unverified_edge') AS provenance_kind,
               coalesce(r.confidence, 1.0) AS confidence
        LIMIT $limit
        """
        try:
            with self._driver.session() as session:
                return [dict(r) for r in session.run(cypher, names=concept_names[:8], limit=limit)]
        except Exception as exc:
            logger.debug("[MemgraphEvidenceAdapter] neighborhood query failed: %s", exc)
            return []

    def _rows_to_candidates(
        self,
        rows: list[dict[str, Any]],
        *,
        teacher_id: str | None,
        limit: int,
    ) -> list[EvidenceCandidate]:
        out: list[EvidenceCandidate] = []
        tid_filter = teacher_id.strip().lower() if teacher_id else None
        if tid_filter in {"", "both", "all"}:
            tid_filter = None

        for rank, row in enumerate(rows):
            if row.get("rights_status") != "licensed":
                continue
            eid = str(row.get("evidence_id") or "").strip()
            if not eid:
                continue
            gid = str(row.get("guru_id") or "").strip() or None
            if tid_filter and gid and gid.lower() not in {tid_filter, "preethaji_krishnaji"}:
                continue
            text = str(row.get("verbatim_text") or row.get("text") or "").strip()
            if not text:
                continue
            vid = str(row.get("video_id") or "").strip()
            url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
            start_ms = row.get("start_ms")
            end_ms = row.get("end_ms")
            rel_types = row.get("rel_types") or []
            seed_id = row.get("seed_span_id")
            graph_paths = (
                [f"{seed_id}-[{'->'.join(rel_types)}]->{eid}"] if seed_id and rel_types else []
            )

            out.append(
                EvidenceCandidate(
                    evidence_id=eid,
                    source_id=make_source_id(url or vid or eid),
                    source_type="video" if vid else "document",
                    source_url=url,
                    teacher_id=gid,
                    speaker_verified=False,  # Graph nodes require Qdrant/Canonical verification before verbatim display
                    text=text,
                    start_time=(float(start_ms) / 1000.0)
                    if isinstance(start_ms, (int, float))
                    else None,
                    end_time=(float(end_ms) / 1000.0) if isinstance(end_ms, (int, float)) else None,
                    retrieval_source="memgraph",
                    retrieval_score=1.0 / (1.0 + rank),
                    source_version=str(row.get("corpus_version") or "1"),
                    verification_status="automated_candidate",
                    rights_status="licensed",
                    concepts=[str(c) for c in (row.get("matched_concepts") or []) if c],
                    graph_paths=graph_paths,
                    provenance={"seed_span_id": seed_id, "rel_types": rel_types},
                )
            )
            if len(out) >= limit:
                break
        return out
