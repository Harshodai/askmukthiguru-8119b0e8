"""Ontology Validation Service — Tony Seale's symbolic-backbone principle.

Implements the validation service from the KG Ontology Integration blueprint
(section 3) with one Ponytail upgrade over the analysis: `_extract_facts` is
NOT a placeholder. It reuses the proven `backend.ingest.triple_extractor`
LLM-backed (subject, relation, object) extractor instead of reinventing a
new extraction chain. That is the ponytail win — proven infra, no new deps.

`OntologyValidator` queries the REAL Neo4j graph (labels `Teacher` /
`Concept` / `Practice` / `base`, properties `entity_id` / `name`, relation
`EXPOUNDS`) via the standard sync `neo4j.Driver` API (`driver.session().run()`).
It NEVER imports `seed_ontology.py` — the graph is read, not seeded.

This module is a SOFT-GATE post-step for the Deep RAG strategy only. It never
blocks or modifies the generated response; it only reports
supported / unsupported / contradiction counts and a confidence score so the
deep tier can surface ontology drift in telemetry + logs.

Tony Seale principle: "The accuracy of information received is reliant upon
the lineage or provenance of the information." Validation, not suppression.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from domain.spiritual_ontology import RelationType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus gauge — incremented per contradiction found (deep tier only).
# Declared lazily so importing this module never crashes if prometheus_client
# is unavailable on a stripped-down host (ponytail: degrade gracefully).
# ---------------------------------------------------------------------------

ontology_contradiction_count: Any = None

try:
    from prometheus_client import Gauge as _Gauge

    ontology_contradiction_count = _Gauge(
        "ontology_contradiction_count",
        "Contradictions detected by the ontology validator (deep tier soft-gate)",
    )
except Exception:  # pragma: no cover - prometheus absent on minimal hosts
    logger.debug("prometheus_client unavailable; ontology_contradiction_count is a no-op")

    class _NoopGauge:
        def inc(self, *args, **kwargs) -> None:  # noqa: ANN
            pass

        def labels(self, *args, **kwargs) -> "_NoopGauge":  # noqa: ANN
            return self

        def set(self, *args, **kwargs) -> None:  # noqa: ANN
            pass

    ontology_contradiction_count = _NoopGauge()


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Outcome of validating a generated response against the ontology.

    Fields:
        supported_facts:   triples backed by a Neo4j relation (confidence > 0.7).
        unsupported_facts: triples not found and not contradicted (unknown).
        contradictions:    triples whose opposite relation exists in Neo4j.
        confidence:        supported / total (1.0 when no facts were extracted).
        is_valid:          confidence >= 0.7 AND zero contradictions.
    """

    supported_facts: list[dict] = field(default_factory=list)
    unsupported_facts: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    confidence: float = 1.0
    is_valid: bool = True

    def as_dict(self) -> dict:
        """Plain-dict shape for graph-state / telemetry serialization."""
        return {
            "supported": len(self.supported_facts),
            "unsupported": len(self.unsupported_facts),
            "contradictions": len(self.contradictions),
            "confidence": round(float(self.confidence), 4),
            "is_valid": bool(self.is_valid),
            "supported_facts": list(self.supported_facts),
            "unsupported_facts": list(self.unsupported_facts),
            "contradiction_facts": list(self.contradictions),
        }


# ---------------------------------------------------------------------------
# OntologyValidator
# ---------------------------------------------------------------------------

# Real-graph labels (see app/db/seed_ontology.py — read-only reference, never
# imported). We match against :base (the LightRAG-merged supertype) so a node
# keeps working whether or not it carries the extra :Teacher/:Concept/:Practice
# label. The `entity_id` and `name` properties are both populated at seed time.
_RELATION_CYPHER = """
MATCH (s:base)-[r]->(o:base)
WHERE (s.entity_id = $subject OR s.name = $subject)
  AND (o.entity_id = $object OR o.name = $object)
  AND coalesce(r.type, type(r)) = $predicate
RETURN coalesce(r.confidence, 1.0) AS confidence, type(r) AS rel_type
LIMIT 1
"""

# Broad contradiction sweep: any relation between the same pair whose type is
# in the opposite set. Uses the generic :base labels so we don't miss a Teacher
# that lacks the :Concept label, etc.
_OPPOSITE_CYPHER = """
MATCH (s:base)-[r]->(o:base)
WHERE (s.entity_id = $subject OR s.name = $subject)
  AND (o.entity_id = $object OR o.name = $object)
  AND coalesce(r.type, type(r)) IN $opposites
RETURN coalesce(r.confidence, 1.0) AS confidence, type(r) AS rel_type
LIMIT 1
"""

# Confidence threshold above which a Neo4j relation is treated as authoritative.
# Matches the blueprint's 0.7 cutoff.
_CONFIDENCE_THRESHOLD = 0.7


class OntologyValidator:
    """Validates generated content against the formal ontology (Neo4j-backed).

    Soft-gate by construction: `validate_response` never raises — any
    extraction or graph error is caught and reported as an "unknown" fact so
    the caller (deep tier) can log it without blocking the answer.
    """

    def __init__(self, neo4j_driver: Any) -> None:
        self.neo4j = neo4j_driver

    async def validate_response(
        self,
        response_text: str,
        cited_concepts: Optional[list[str]] = None,
        *,
        llm: Any = None,
    ) -> ValidationResult:
        """Validate `response_text` against the ontology.

        Args:
            response_text: The generated answer (post-CoT-strip).
            cited_concepts: Optional list of cited concept labels (reserved
                for future scope-limiting; currently unused).
            llm: LLM service exposing
                ``async def generate(system_prompt, user_prompt, context="", **kw)``
                Used by `extract_triples`. If None, the container's configured
                LLM is resolved lazily (deep tier only).

        Returns:
            ValidationResult. Never raises.
        """
        cited_concepts = cited_concepts or []
        try:
            claimed_facts = await self._extract_facts(response_text, llm=llm)
        except Exception as exc:  # pragma: no cover - extractor is defensive
            logger.warning(f"OntologyValidator: fact extraction failed ({exc})")
            claimed_facts = []

        if not claimed_facts:
            # No claims → nothing to contradict; treat as fully valid.
            return ValidationResult()

        supported: list[dict] = []
        unsupported: list[dict] = []
        contradictions: list[dict] = []

        for fact in claimed_facts:
            try:
                verdict = await self._validate_fact(fact)
            except Exception as exc:  # pragma: no cover - graph errors
                logger.warning(
                    f"OntologyValidator: fact validation failed for {fact}: {exc}"
                )
                verdict = "unknown"

            if verdict == "supported":
                supported.append(fact)
            elif verdict == "contradicted":
                contradictions.append(fact)
            else:
                unsupported.append(fact)

        total = len(claimed_facts)
        confidence = len(supported) / total if total else 1.0
        is_valid = confidence >= 0.7 and len(contradictions) == 0

        # Prom gauge — one increment per contradiction (soft-gate signal).
        if contradictions and ontology_contradiction_count is not None:
            try:
                ontology_contradiction_count.inc(len(contradictions))
            except Exception:  # pragma: no cover - gauge defensive
                pass

        return ValidationResult(
            supported_facts=supported,
            unsupported_facts=unsupported,
            contradictions=contradictions,
            confidence=confidence,
            is_valid=is_valid,
        )

    async def _validate_fact(self, fact: dict) -> str:
        """Check a single (subject, predicate, object) fact against Neo4j.

        Returns: "supported" | "contradicted" | "unknown".
        """
        if self.neo4j is None:
            return "unknown"

        subject = (fact.get("subject") or "").strip()
        obj = (fact.get("object") or "").strip()
        predicate_raw = (fact.get("predicate") or fact.get("relation") or "").strip()
        if not subject or not obj or not predicate_raw:
            return "unknown"

        # Map the triple's predicate string to a canonical RelationType value
        # where possible. The extractor returns UPPERCASE verbs (EXPOUNDS,
        # TEACHES, …); the ontology uses snake_case values (is_a, leads_to, …).
        predicate = self._canonical_predicate(predicate_raw)
        if predicate is None:
            # Unknown to the ontology enum — still probe Neo4j with the raw
            # verb so a real-graph relation (e.g. EXPOUNDS) can still match.
            predicate = predicate_raw

        try:
            result = await asyncio.to_thread(self._run_cypher, _RELATION_CYPHER, {
                "subject": subject,
                "object": obj,
                "predicate": predicate,
            })
        except Exception as exc:
            logger.warning(f"OntologyValidator: relation query failed ({exc})")
            return "unknown"

        if result:
            conf = float(result[0].get("confidence", 1.0) or 1.0)
            if conf > _CONFIDENCE_THRESHOLD:
                return "supported"

        # Check for a contradiction (opposite relation between same pair).
        opposites = self._get_opposite_relations(predicate)
        if not opposites:
            return "unknown"

        try:
            opp = await asyncio.to_thread(self._run_cypher, _OPPOSITE_CYPHER, {
                "subject": subject,
                "object": obj,
                "opposites": opposites,
            })
        except Exception as exc:
            logger.warning(f"OntologyValidator: opposite query failed ({exc})")
            return "unknown"

        if opp:
            conf = float(opp[0].get("confidence", 1.0) or 1.0)
            if conf > _CONFIDENCE_THRESHOLD:
                return "contradicted"

        return "unknown"

    # ------------------------------------------------------------------
    # Internal helpers — Neo4j + predicate mapping
    # ------------------------------------------------------------------

    def _run_cypher(self, query: str, params: dict) -> list[dict]:
        """Execute a Cypher read query synchronously against the real driver.

        The real driver is a sync `neo4j.Driver`: ``driver.session().run(...)``.
        Wrapped in `asyncio.to_thread` by the caller so this stays blocking-safe.
        """
        records: list[dict] = []
        with self.neo4j.session() as session:
            result = session.run(query, **params)
            for rec in result:
                # neo4j.Record supports dict() and key access.
                try:
                    records.append(rec.data() if hasattr(rec, "data") else dict(rec))
                except Exception:
                    records.append(dict(rec))
        return records

    @staticmethod
    def _canonical_predicate(predicate_raw: str) -> Optional[str]:
        """Map an extractor verb to a RelationType value (snake_case) or None.

        The extractor emits UPPERCASE verbs (EXPOUNDS, TEACHES, PRACTICE_FOR,
        CONTRASTS_WITH, RELATED_TO, IS_A, LEADS_TO, …). The ontology enum uses
        lowercase snake_case values (is_a, leads_to, is_related_to, …). We
        normalize case-insensitively and also accept the enum's exact values.
        """
        if not predicate_raw:
            return None
        key = predicate_raw.strip().lower().replace(" ", "_")
        # Direct enum match (is_a, leads_to_state, is_opposite_of, …)
        for rt in RelationType:
            if rt.value == key:
                return rt.value
        # Alias map for extractor verbs that don't literally appear in the enum
        # but have a clear ontological counterpart.
        aliases = {
            "expounds": "is_related_to",
            "teaches": "is_taught_by",
            "practice_for": "is_technique_for",
            "contrasts_with": "is_opposite_of",
            "related_to": "is_related_to",
            "similar_to": "is_similar_to",
            "part_of": "part_of",
            "instance_of": "instance_of",
            "used_for": "is_used_for",
            "prerequisite_for": "is_prerequisite_for",
            "mentioned_in": "is_mentioned_in",
            "manifestation_of": "is_manifestation_of",
            "aspect_of": "is_aspect_of",
        }
        return aliases.get(key)

    @staticmethod
    def _get_opposite_relations(relation: str) -> list[str]:
        """Relations that contradict the given relation.

        Mirrors the analysis blueprint's mapping, extended to cover the
        predicate aliases so contradictions are detected even when the triple
        used an extractor verb (e.g. PREVENTS vs LEADS_TO).
        """
        opposites = {
            RelationType.LEADS_TO.value: [RelationType.PREVENTS.value],
            RelationType.CAUSES.value: [RelationType.PREVENTS.value],
            RelationType.PREVENTS.value: [
                RelationType.CAUSES.value,
                RelationType.LEADS_TO.value,
            ],
            RelationType.IS_A.value: [],
            RelationType.PRECEDES.value: [RelationType.FOLLOWS.value],
            RelationType.FOLLOWS.value: [RelationType.PRECEDES.value],
            RelationType.IS_OPPOSITE_OF.value: [RelationType.IS_SIMILAR_TO.value],
            RelationType.IS_SIMILAR_TO.value: [RelationType.IS_OPPOSITE_OF.value],
            RelationType.IS_TAUGHT_BY.value: [RelationType.PREVENTS.value],
            RelationType.IS_RELATED_TO.value: [RelationType.IS_OPPOSITE_OF.value],
        }
        return opposites.get(relation, [])

    # ------------------------------------------------------------------
    # Fact extraction — REUSES triple_extractor (the ponytail win)
    # ------------------------------------------------------------------

    async def _extract_facts(self, text: str, *, llm: Any = None) -> list[dict]:
        """Extract (subject, predicate, object) triples from `text`.

        Ponytail upgrade over the blueprint: instead of a placeholder `[]`,
        we reuse the proven `backend.ingest.triple_extractor.extract_triples`
        LLM-backed extractor. No new LLM chain, no new prompt, no new deps.

        If no `llm` is passed we lazily resolve the container's configured LLM
        (deep tier only — the standard/fast tiers don't call this validator).
        If the LLM or text is unavailable, returns [] (defensive, never raises).
        """
        if not text or not text.strip():
            return []

        from ingest.triple_extractor import extract_triples

        if llm is None:
            try:
                from app.dependencies import get_container

                llm = get_container().ollama_service
            except Exception:
                llm = None

        if llm is None:
            logger.debug("OntologyValidator: no LLM available; skipping extraction")
            return []

        triples = await extract_triples(text, llm)
        # Normalize keys: extractor returns {"subject","relation","object"};
        # downstream code reads "predicate". Keep both for resilience.
        normalized: list[dict] = []
        for t in triples:
            if not t:
                continue
            normalized.append({
                "subject": t.get("subject", ""),
                "predicate": t.get("predicate") or t.get("relation", ""),
                "object": t.get("object", ""),
            })
        return normalized


# ---------------------------------------------------------------------------
# Soft-gate wiring helper for the Deep tier
# ---------------------------------------------------------------------------


async def run_ontology_soft_gate(
    response_text: str,
    cited_concepts: Optional[list[str]] = None,
    *,
    neo4j_driver: Any = None,
) -> dict:
    """Run the ontology validator as a SOFT GATE. Never blocks, never raises.

    Used by the Deep RAG strategy post-generation step. Returns a dict shaped
    for ``GraphState["ontology_validation"]``:
        {supported, unsupported, contradictions, confidence, is_valid, ...}

    On ANY error (Neo4j down, LLM unavailable, extraction failure) returns a
    neutral dict with ``error`` set and zero contradictions — the response is
    never modified or blocked.
    """
    if not response_text or not response_text.strip():
        return {
            "supported": 0,
            "unsupported": 0,
            "contradictions": 0,
            "confidence": 1.0,
            "is_valid": True,
            "skipped": True,
            "reason": "empty_response",
        }

    if neo4j_driver is None:
        try:
            from app.dependencies import get_container

            neo4j_driver = get_container().neo4j_driver
        except Exception:
            neo4j_driver = None

    try:
        validator = OntologyValidator(neo4j_driver)
        result = await validator.validate_response(response_text, cited_concepts)
        out = result.as_dict()
        if result.contradictions:
            logger.warning(
                "ontology soft-gate: %d contradiction(s) detected — "
                "response NOT blocked (soft-gate). facts=%s",
                len(result.contradictions),
                result.contradictions,
            )
        return out
    except Exception as exc:  # pragma: no cover - never blocks
        logger.warning(f"ontology soft-gate failed ({exc}); response NOT blocked")
        return {
            "supported": 0,
            "unsupported": 0,
            "contradictions": 0,
            "confidence": 1.0,
            "is_valid": True,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Self-check — runs with a MOCK neo4j driver (no live graph needed).
# ---------------------------------------------------------------------------


class _MockRecord:
    """Minimal stand-in for neo4j.Record — supports dict() and key access."""

    def __init__(self, data: dict) -> None:
        self._data = dict(data)

    def data(self) -> dict:
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return list(self._data.keys())


class _MockResult:
    """Iterable Cypher result that yields _MockRecord from canned rows."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = list(rows)

    def __iter__(self):
        return iter([_MockRecord(r) for r in self._rows])


class _MockSession:
    """Matches the real neo4j session() context-manager API.

    ``canned`` may be either:
      - {signature: rows}         → matched by substring on the query, OR
      - {(signature, param_key, param_value): rows}
                                 → matched by substring on the query AND
                                   equality of params[param_key]. This lets the
                                   self-check distinguish the same query shape
                                   for different facts.
    """

    def __init__(self, canned: dict) -> None:
        self._canned = canned

    def run(self, query: str, **params) -> _MockResult:
        for key, rows in self._canned.items():
            if isinstance(key, tuple):
                sig, pk, pv = key
                if sig in query and params.get(pk) == pv:
                    return _MockResult(rows)
            else:
                if key in query:
                    return _MockResult(rows)
        return _MockResult([])

    def __enter__(self) -> "_MockSession":
        return self

    def __exit__(self, *exc) -> None:
        return None


class _MockNeo4jDriver:
    """Sync neo4j.Driver stand-in. ``driver.session()`` yields a context mgr."""

    def __init__(self, canned: dict) -> None:
        self._canned = canned

    def session(self) -> _MockSession:
        return _MockSession(self._canned)


class _MockLLM:
    """Fake LLM returning canned extractor JSON (no external calls)."""

    def __init__(self, raw: str) -> None:
        self._raw = raw

    async def generate(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        return self._raw


if __name__ == "__main__":
    # Canned Neo4j rows keyed by a substring of the Cypher query.
    # The validator's relation query contains "coalesce(r.type, type(r)) = $predicate"
    # and the opposite query contains "IN $opposites".
    canned = {
        # Relation query for fact 1 (Breath Awareness → leads_to_state → Presence):
        # SUPPORTED (conf 0.95). Param-keyed so only this exact fact matches.
        ("coalesce(r.type, type(r)) = $predicate", "subject", "Breath Awareness"): [
            {"confidence": 0.95, "rel_type": "leads_to_state"},
        ],
        # Relation query for fact 2 (Witnessing → prevents → Presence): no row →
        # falls through to the opposite check.
        ("coalesce(r.type, type(r)) = $predicate", "subject", "Witnessing"): [],
        # Opposite query for fact 2: PREVENTS's opposites are [causes, leads_to].
        # Canned row simulates a stored `leads_to` relation between Witnessing and
        # Presence at high confidence → contradicts the "prevents" claim.
        ("IN $opposites", "subject", "Witnessing"): [
            {"confidence": 0.9, "rel_type": "leads_to"},
        ],
    }

    driver = _MockNeo4jDriver(canned)

    # Canned extractor output: two triples. The first matches the SUPPORTED row
    # above (subject=Breath Awareness, predicate=LEADS_TO_STATE, object=Presence).
    # The second (Witnessing, PREVENTS, Presence) maps to PREVENTS and triggers
    # the opposite query — but PREVENTS's opposites are CAUSES/LEADS_TO, so with
    # the canned opposite row keyed on "IN $opposites" returning prevents (0.9),
    # we simulate a contradiction against the second fact's subject/object.
    # To keep the self-check deterministic, we craft the canned LLM to emit one
    # supported + one contradicted fact.
    canned_llm_json = (
        '{"triples": ['
        '{"subject": "Breath Awareness", "relation": "LEADS_TO_STATE", "object": "Presence"},'
        '{"subject": "Witnessing", "relation": "PREVENTS", "object": "Presence"}'
        "]}"
    )

    sample_response = (
        "Breath Awareness leads to the state of Presence. "
        "Witnessing prevents Presence from arising."
    )

    validator = OntologyValidator(driver)
    # Run extraction+validation. The mock LLM returns canned JSON; the mock
    # driver returns the canned rows. We use asyncio.run for the self-check.
    import json as _json

    result = asyncio.run(
        validator.validate_response(
            sample_response,
            cited_concepts=["Breath Awareness", "Presence", "Witnessing"],
            llm=_MockLLM(canned_llm_json),
        )
    )

    print(f"supported:   {len(result.supported_facts)}")
    print(f"unsupported: {len(result.unsupported_facts)}")
    print(f"contradictions: {len(result.contradictions)}")
    print(f"confidence:  {result.confidence:.3f}")
    print(f"is_valid:    {result.is_valid}")

    # Sanity assertions (deterministic given the canned fixtures).
    assert len(result.supported_facts) >= 1, f"expected >=1 supported, got {result.supported_facts}"
    assert len(result.contradictions) >= 1, f"expected >=1 contradiction, got {result.contradictions}"
    assert 0.0 <= result.confidence <= 1.0
    assert result.is_valid is False, "contradictions present → is_valid must be False"

    # Soft-gate helper must never raise and must return a dict.
    sg = asyncio.run(run_ontology_soft_gate(sample_response, neo4j_driver=driver))
    assert isinstance(sg, dict) and "contradictions" in sg

    # Empty-response soft-gate short-circuits cleanly.
    sg_empty = asyncio.run(run_ontology_soft_gate("", neo4j_driver=driver))
    assert sg_empty.get("skipped") is True

    # No-driver path returns neutral dict, never raises.
    sg_nodriver = asyncio.run(run_ontology_soft_gate("x", neo4j_driver=None))
    assert isinstance(sg_nodriver, dict)

    print("B1 OK")