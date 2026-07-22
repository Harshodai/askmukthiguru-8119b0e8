"""
GuruKGService — Neo4j Knowledge Graph & OKF Ontology Engine for Guru Brain.

Builds and queries 5-node structural ontology of spiritual state transformations:
Nodes: (:SeekerDilemma), (:RootLimitingBelief), (:GuruTeaching), (:BeautifulState), (:PracticeStep), (:GuruSpeaker)

Relations:
  (:SeekerDilemma)-[:DRIVEN_BY]->(:RootLimitingBelief)
  (:GuruTeaching)-[:DISMANTLES]->(:RootLimitingBelief)
  (:GuruTeaching)-[:TRANSFORMS_TO]->(:BeautifulState)
  (:GuruTeaching)-[:PRESCRIBES]->(:PracticeStep)
  (:GuruSpeaker)-[:TEACHES]->(:GuruTeaching)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OKFTransformationArc:
    seeker_dilemma: str
    limiting_belief: str
    teaching: str
    target_state: str
    practice_step: str
    guru_speaker: str


class GuruKGService:
    """Neo4j Knowledge Graph & OKF 5-Node Ontology Engine."""

    def __init__(self, neo4j_driver: Any = None) -> None:
        self.neo4j_driver = neo4j_driver
        self._in_memory_graph: list[OKFTransformationArc] = []

    def populate_ontology_arc(
        self,
        seeker_dilemma: str,
        limiting_belief: str,
        teaching: str,
        target_state: str,
        practice_step: str,
        guru_speaker: str = "Sri Preethaji & Sri Krishnaji",
    ) -> None:
        """Add a 5-node spiritual transformation arc entry into Knowledge Graph."""
        arc = OKFTransformationArc(
            seeker_dilemma=seeker_dilemma,
            limiting_belief=limiting_belief,
            teaching=teaching,
            target_state=target_state,
            practice_step=practice_step,
            guru_speaker=guru_speaker,
        )
        self._in_memory_graph.append(arc)

        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    cypher = """
                    MERGE (g:GuruSpeaker {name: $guru})
                    MERGE (d:SeekerDilemma {name: $dilemma})
                    MERGE (b:RootLimitingBelief {name: $belief})
                    MERGE (t:GuruTeaching {name: $teaching})
                    MERGE (s:BeautifulState {name: $state})
                    MERGE (p:PracticeStep {name: $practice})
                    MERGE (d)-[:DRIVEN_BY]->(b)
                    MERGE (t)-[:DISMANTLES]->(b)
                    MERGE (t)-[:TRANSFORMS_TO]->(s)
                    MERGE (t)-[:PRESCRIBES]->(p)
                    MERGE (g)-[:TEACHES]->(t)
                    """
                    session.run(
                        cypher,
                        guru=guru_speaker,
                        dilemma=seeker_dilemma,
                        belief=limiting_belief,
                        teaching=teaching,
                        state=target_state,
                        practice=practice_step,
                    )
            except Exception as exc:
                logger.warning(f"GuruKGService: Neo4j Cypher write failed ({exc}), stored in graph memory fallback.")

    def traverse_guru_ontology(self, query: str, limit: int = 3) -> list[OKFTransformationArc]:
        """Perform 5-node multi-hop graph traversal to discover spiritual transformation arcs."""
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    cypher = """
                    MATCH (d:SeekerDilemma)-[:DRIVEN_BY]->(b:RootLimitingBelief)
                    MATCH (t:GuruTeaching)-[:DISMANTLES]->(b)
                    MATCH (t)-[:TRANSFORMS_TO]->(s:BeautifulState)
                    MATCH (t)-[:PRESCRIBES]->(p:PracticeStep)
                    MATCH (g:GuruSpeaker)-[:TEACHES]->(t)
                    WHERE toLower(d.name) CONTAINS toLower($q) OR toLower(t.name) CONTAINS toLower($q)
                    RETURN d.name AS dilemma, b.name AS belief, t.name AS teaching, s.name AS state, p.name AS practice, g.name AS guru
                    LIMIT $limit
                    """
                    result = session.run(cypher, q=query, limit=limit)
                    arcs = []
                    for record in result:
                        arcs.append(
                            OKFTransformationArc(
                                seeker_dilemma=record["dilemma"],
                                limiting_belief=record["belief"],
                                teaching=record["teaching"],
                                target_state=record["state"],
                                practice_step=record["practice"],
                                guru_speaker=record["guru"],
                            )
                        )
                    if arcs:
                        return arcs
            except Exception as exc:
                logger.warning(f"GuruKGService: Neo4j traversal failed ({exc}), falling back to in-memory graph.")

        # Fallback in-memory graph traversal
        matched = []
        q_lower = query.lower()
        for arc in self._in_memory_graph:
            if any(w in arc.seeker_dilemma.lower() or w in arc.teaching.lower() for w in q_lower.split()):
                matched.append(arc)
            if len(matched) >= limit:
                break

        if not matched:
            matched = [
                OKFTransformationArc(
                    seeker_dilemma="Experiencing anxiety, stress, or lack of peace",
                    limiting_belief="Belief that peace depends on external outcomes or controlling thoughts",
                    teaching="Present Moment Awareness & Witnessing Consciousness",
                    target_state="Beautiful State (Serene Mind)",
                    practice_step="Observe thoughts as cloud formations passing across awareness without judgment",
                    guru_speaker="Sri Preethaji & Sri Krishnaji",
                )
            ]

        return matched[:limit]

    def format_kg_ontology_context(self, arcs: list[OKFTransformationArc]) -> str:
        """Format retrieved 5-node OKF Knowledge Graph arcs into prompt context."""
        if not arcs:
            return ""

        blocks = ["=== 5-NODE NEO4J KNOWLEDGE GRAPH & OKF ONTOLOGY ARCS ==="]
        for i, a in enumerate(arcs, 1):
            blocks.append(
                f"Arc {i}: [Dilemma: {a.seeker_dilemma}] -> [Limiting Belief: {a.limiting_belief}]\n"
                f"  Teaching ({a.guru_speaker}): {a.teaching}\n"
                f"  Target State: {a.target_state} | Practice: {a.practice_step}"
            )

        return "\n".join(blocks)


_kg_instance: Optional[GuruKGService] = None


def get_guru_kg_service(neo4j_driver: Any = None) -> GuruKGService:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = GuruKGService(neo4j_driver=neo4j_driver)
    return _kg_instance
