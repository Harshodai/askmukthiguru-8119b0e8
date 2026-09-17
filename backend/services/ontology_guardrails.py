"""Strict Ontology Guardrail Service (Graph Traversal Invariant Checker).

Enforces:
1. MUTUALLY_EXCLUSIVE invariant detection (e.g. Suffering State vs. Beautiful State).
2. CORE_PRACTICE lineage anchoring (Sri Preethaji / Sri Krishnaji doctrine preservation).
3. PRACTICE_PREREQUISITE DAG verification (cycle detection & prerequisite bypasses).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cypher for Mutual Exclusivity Violations
CHECK_MUTUAL_EXCLUSIVITY_CYPHER = """
MATCH (a:base)-[:MUTUALLY_EXCLUSIVE]-(b:base)
WHERE (a.entity_id IN $entities OR a.name IN $entities)
  AND (b.entity_id IN $entities OR b.name IN $entities)
RETURN a.name AS concept_a,
       b.name AS concept_b,
       'MUTUALLY_EXCLUSIVE_COOCCURRENCE' AS violation,
       'Concepts cannot co-occur as identical or compatible states in doctrine' AS description;
"""

# Cypher for Invalid Causal Relations Between Mutually Exclusive States
CHECK_MUTUAL_EXCLUSIVITY_CAUSAL_CYPHER = """
UNWIND $triples AS t
MATCH (s:base)-[r]->(o:base)
WHERE (s.entity_id = t.subject OR s.name = t.subject)
  AND (o.entity_id = t.object OR o.name = t.object)
  AND EXISTS {
    MATCH (s)-[:MUTUALLY_EXCLUSIVE]-(o)
  }
  AND NOT type(r) IN ['IS_OPPOSITE_OF', 'CONTRASTS_WITH', 'TRANSFORMS', 'DISSOLVES', 'PREVENTS']
RETURN s.name AS subject,
       o.name AS object,
       type(r) AS relation,
       'MUTUALLY_EXCLUSIVE_TRANSITION' AS violation,
       'Direct positive or causal relation asserted between mutually exclusive concepts' AS description;
"""

# Cypher for Core Practice Teacher Lineage Verification
CHECK_CORE_PRACTICE_LINEAGE_CYPHER = """
UNWIND $practices AS p_name
MATCH (p:Practice)
WHERE (p.entity_id = p_name OR p.name = p_name)
  AND (p.is_core = true OR 'CORE_PRACTICE' IN labels(p))
  AND NOT EXISTS {
    MATCH (t:Teacher)-[:TEACHES|EXPOUNDS]->(p)
    WHERE t.name IN ['Sri Krishnaji', 'Sri Preethaji', 'both']
  }
RETURN p.name AS practice,
       'UNANCHORED_CORE_PRACTICE' AS violation,
       'Core practice lacks authentic lineage verification to Sri Preethaji/Krishnaji' AS description;
"""

# Cypher for Prerequisite Dependency Verification & Bypass Detection
CHECK_PREREQUISITE_BYPASS_CYPHER = """
UNWIND $target_practices AS target_name
MATCH path = (prereq:base)-[:IS_PREREQUISITE_FOR*1..4]->(target:base)
WHERE (target.entity_id = target_name OR target.name = target_name)
  AND NOT (prereq.entity_id IN $completed_prereqs OR prereq.name IN $completed_prereqs)
RETURN target.name AS practice,
       prereq.name AS missing_prerequisite,
       length(path) AS distance,
       [n IN nodes(path) | n.name] AS dependency_chain,
       'PREREQUISITE_BYPASS' AS violation,
       'Attempted to prescribe practice without satisfying mandatory prerequisite' AS description
ORDER BY distance DESC;
"""

# Cypher for Prerequisite Cycle Detection (DAG Integrity)
CHECK_PREREQUISITE_CYCLES_CYPHER = """
MATCH path = (p:base)-[:IS_PREREQUISITE_FOR*2..6]->(p)
RETURN p.name AS cyclical_concept,
       [n IN nodes(path) | n.name] AS cycle,
       'PREREQUISITE_CYCLE' AS violation,
       'Illegal circular dependency loop detected in prerequisite DAG' AS description;
"""


@dataclass
class ConstraintViolation:
    violation_type: str
    subject: str
    target: str
    description: str
    remedy_hint: str


@dataclass
class GuardrailReport:
    is_valid: bool
    violations: list[ConstraintViolation] = field(default_factory=list)
    checked_entities_count: int = 0
    checked_triples_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "violations_count": len(self.violations),
            "violations": [
                {
                    "type": v.violation_type,
                    "subject": v.subject,
                    "target": v.target,
                    "description": v.description,
                    "remedy_hint": v.remedy_hint,
                }
                for v in self.violations
            ],
            "checked_entities_count": self.checked_entities_count,
            "checked_triples_count": self.checked_triples_count,
        }


class OntologyConstraintChecker:
    """Evaluates strict ontological invariants against Memgraph / Neo4j."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    def check_constraints(
        self,
        *,
        entities: Optional[list[str]] = None,
        claimed_triples: Optional[list[dict[str, str]]] = None,
        prescribed_practices: Optional[list[str]] = None,
        user_completed_prereqs: Optional[list[str]] = None,
        check_dag_cycles: bool = True,
    ) -> GuardrailReport:
        """Synchronously execute full multi-invariant graph traversal validation.

        Args:
            entities: Concept names or entity IDs extracted from input or response.
            claimed_triples: List of dicts with keys {'subject', 'predicate'/'relation', 'object'}.
            prescribed_practices: Practices recommended or discussed in the text.
            user_completed_prereqs: Prerequisites already satisfied or present.
            check_dag_cycles: Whether to run cycle detection on IS_PREREQUISITE_FOR edges.

        Returns:
            GuardrailReport detailing validity, violations, and remedy hints.
        """
        if self.driver is None:
            return GuardrailReport(is_valid=True)

        clean_entities = [e.strip() for e in (entities or []) if e and e.strip()]
        triples = claimed_triples or []
        practices = [p.strip() for p in (prescribed_practices or []) if p and p.strip()]
        completed = [c.strip() for c in (user_completed_prereqs or []) if c and c.strip()]
        violations: list[ConstraintViolation] = []

        try:
            with self.driver.session() as session:
                # 1. Mutual Exclusivity Co-occurrence
                if len(clean_entities) >= 2:
                    records = session.run(CHECK_MUTUAL_EXCLUSIVITY_CYPHER, entities=clean_entities)
                    for r in records:
                        violations.append(
                            ConstraintViolation(
                                violation_type=r["violation"],
                                subject=r["concept_a"],
                                target=r["concept_b"],
                                description=r["description"],
                                remedy_hint="Clarify that these two states are opposites and cannot exist simultaneously.",
                            )
                        )

                # 2. Mutually Exclusive Causal Transitions
                if triples:
                    # Normalize triples to keys: subject, object
                    norm_triples = [
                        {
                            "subject": t.get("subject", "").strip(),
                            "object": t.get("object", "").strip(),
                            "relation": t.get("predicate", t.get("relation", "")).strip(),
                        }
                        for t in triples
                        if t.get("subject") and t.get("object")
                    ]
                    if norm_triples:
                        records = session.run(
                            CHECK_MUTUAL_EXCLUSIVITY_CAUSAL_CYPHER, triples=norm_triples
                        )
                        for r in records:
                            violations.append(
                                ConstraintViolation(
                                    violation_type=r["violation"],
                                    subject=r["subject"],
                                    target=r["object"],
                                    description=f"{r['description']} via relation {r['relation']}",
                                    remedy_hint="Insert transformation or dissolution doctrine rather than direct causality.",
                                )
                            )

                # 3. Core Practice Lineage Anchoring
                if practices:
                    records = session.run(CHECK_CORE_PRACTICE_LINEAGE_CYPHER, practices=practices)
                    for r in records:
                        violations.append(
                            ConstraintViolation(
                                violation_type=r["violation"],
                                subject=r["practice"],
                                target="Sri Preethaji / Sri Krishnaji",
                                description=r["description"],
                                remedy_hint="Attribute practice to authentic lineage or mark as unsupported external technique.",
                            )
                        )

                # 4. Prerequisite Bypass Detection
                if practices:
                    records = session.run(
                        CHECK_PREREQUISITE_BYPASS_CYPHER,
                        target_practices=practices,
                        completed_prereqs=completed,
                    )
                    for r in records:
                        chain_str = " -> ".join(r.get("dependency_chain", []))
                        violations.append(
                            ConstraintViolation(
                                violation_type=r["violation"],
                                subject=r["practice"],
                                target=r["missing_prerequisite"],
                                description=f"{r['description']}. Path: {chain_str}",
                                remedy_hint=f"Prescribe foundational prerequisite '{r['missing_prerequisite']}' before '{r['practice']}'.",
                            )
                        )

                # 5. Prerequisite Cycle (DAG Integrity) Check
                if check_dag_cycles:
                    records = session.run(CHECK_PREREQUISITE_CYCLES_CYPHER)
                    for r in records:
                        violations.append(
                            ConstraintViolation(
                                violation_type=r["violation"],
                                subject=r["cyclical_concept"],
                                target=" -> ".join(r.get("cycle", [])),
                                description=r["description"],
                                remedy_hint="Break circular edge in the ontology graph.",
                            )
                        )

        except Exception as e:
            logger.error(f"OntologyConstraintChecker failed: {e}")

        is_valid = len(violations) == 0
        return GuardrailReport(
            is_valid=is_valid,
            violations=violations,
            checked_entities_count=len(clean_entities),
            checked_triples_count=len(triples),
        )

    async def acheck_constraints(
        self,
        *,
        entities: Optional[list[str]] = None,
        claimed_triples: Optional[list[dict[str, str]]] = None,
        prescribed_practices: Optional[list[str]] = None,
        user_completed_prereqs: Optional[list[str]] = None,
        check_dag_cycles: bool = True,
    ) -> GuardrailReport:
        """Async convenience wrapper for check_constraints."""
        return await asyncio.to_thread(
            self.check_constraints,
            entities=entities,
            claimed_triples=claimed_triples,
            prescribed_practices=prescribed_practices,
            user_completed_prereqs=user_completed_prereqs,
            check_dag_cycles=check_dag_cycles,
        )
