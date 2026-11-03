"""Typed models for the TeachingUnit graph projection (Phase 5).

These models describe the separate `:TUTeachingUnit` graph projection built
from the fp-context Qdrant collection. They do NOT represent the live doctrine
graph nodes (`:base`, `:Concept`, `:Teacher`, etc.).

Naming: all Phase-5 node labels carry the ``TU`` prefix to avoid namespace
collision with the live doctrine graph. The Cypher labels used are:
- ``:TUTeachingUnit`` (spans)
- ``:TUTopic`` (topic facets)
- ``:TUConcept`` (concept terms)
- ``:TUVideoSource`` (video provenance)
- ``:TUGuru`` (speaker/guru)

Relationship types: ``TU_CONTINUES``, ``TU_PRECEDES``, ``TU_HAS_TOPIC``,
``TU_HAS_CONCEPT``, ``TU_FROM_VIDEO``, ``TU_SPOKEN_BY``, ``TU_DUPLICATE_OF``.

The build manifest (``GraphBuildManifest``) ties the graph state to the
Qdrant corpus version and point count so that stale projections can be
detected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

GRAPH_SCHEMA_VERSION = "tu_graph_v1"

# ---------------------------------------------------------------------------
# Epistemic state vocabulary
# ---------------------------------------------------------------------------
EpistemicState = Literal["observed", "verified", "inferred", "rejected"]


@dataclass(frozen=True, slots=True)
class TeachingUnitNode:
    """In-memory representation of a ``:TUTeachingUnit`` graph node.

    ``span_id`` is the Qdrant ``source_span_id`` — the canonical join key.
    ``parent_id`` is the Qdrant ``parent_unit_id``.
    ``rights_status`` is the payload value; must be ``"licensed"`` for
    retrieval to include this node in expansion (X40 filter, not yet enforced
    here — that gate is applied at the serving layer).
    """

    span_id: str
    parent_id: str
    video_id: str
    guru_id: str
    corpus_version: str
    rights_status: str
    topics: tuple[str, ...]
    concepts: tuple[str, ...]
    next_span_id: str | None = None
    previous_span_id: str | None = None
    schema_version: str = GRAPH_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class TeachingUnitEdge:
    """A directed relationship in the TeachingUnit projection.

    ``rel_type`` must be one of the ``TU_*`` relationship types.
    ``epistemic_state`` records the evidence basis:
    - ``verified``  → derived from reciprocal Qdrant pointer checks.
    - ``observed``  → derived from Qdrant payload field (no independent proof).
    - ``inferred``  → derived from Phase 4 near-duplicate detection.
    - ``rejected``  → edge was considered but found invalid (retained for audit).
    """

    from_span_id: str
    to_span_id: str
    rel_type: Literal[
        "TU_CONTINUES",
        "TU_PRECEDES",
        "TU_HAS_TOPIC",
        "TU_HAS_CONCEPT",
        "TU_FROM_VIDEO",
        "TU_SPOKEN_BY",
        "TU_DUPLICATE_OF",
    ]
    epistemic_state: EpistemicState
    schema_version: str = GRAPH_SCHEMA_VERSION


@dataclass
class GraphBuildManifest:
    """Records the provenance of a TeachingUnit graph build.

    Written to ``backend/config/teaching_unit_graph_manifest.json`` after
    each successful build. The serving layer compares ``corpus_version`` and
    ``qdrant_point_count`` against the live collection to detect staleness.
    """

    build_id: str
    built_at: str  # ISO 8601
    corpus_version: str
    qdrant_collection: str
    qdrant_point_count: int
    node_count: int
    edge_count: int
    rejection_count: int
    schema_version: str = GRAPH_SCHEMA_VERSION
    rights_filter_applied: bool = True
    rejected_span_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "build_id": self.build_id,
            "built_at": self.built_at,
            "corpus_version": self.corpus_version,
            "qdrant_collection": self.qdrant_collection,
            "qdrant_point_count": self.qdrant_point_count,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "rejection_count": self.rejection_count,
            "schema_version": self.schema_version,
            "rights_filter_applied": self.rights_filter_applied,
        }


if __name__ == "__main__":
    node = TeachingUnitNode(
        span_id="span_abc",
        parent_id="parent_xyz",
        video_id="dQw4w9WgXcQ",
        guru_id="krishnaji",
        corpus_version="fp-context-transcript-v2",
        rights_status="licensed",
        topics=("love", "connection"),
        concepts=("inner_state", "presence"),
        next_span_id="span_def",
        previous_span_id=None,
    )
    assert node.span_id == "span_abc"

    edge = TeachingUnitEdge(
        from_span_id="span_abc",
        to_span_id="span_def",
        rel_type="TU_CONTINUES",
        epistemic_state="verified",
    )
    assert edge.epistemic_state == "verified"

    manifest = GraphBuildManifest(
        build_id="build-2026-11-03",
        built_at="2026-11-03T12:00:00Z",
        corpus_version="fp-context-transcript-v2",
        qdrant_collection="fp_context_v1",
        qdrant_point_count=1600,
        node_count=1580,
        edge_count=820,
        rejection_count=20,
    )
    d = manifest.to_dict()
    assert d["node_count"] == 1580
    print("first_person_graph self-check passed")
