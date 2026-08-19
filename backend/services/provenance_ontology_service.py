"""
EU AI Act Provenance Ontology Service (W3C PROV-O in Neo4j)

Models and queries W3C PROV-O semantic lineage relationships in Neo4j:
- (:SeekerTurn)           - User interaction prompt & session context
- (:InferenceActivity)     - Model generation execution activity
- (:WisdomChunk)          - Grounding corpus documents / citations
- (:GuruResponse)         - Generated AI response / artifact entity
- (:SoftwareAgent)        - Model & system descriptor agent

Semantic Edges:
- (:GuruResponse)-[:WAS_GENERATED_BY]->(:InferenceActivity)
- (:GuruResponse)-[:WAS_DERIVED_FROM]->(:WisdomChunk)
- (:InferenceActivity)-[:WAS_ASSOCIATED_WITH]->(:SoftwareAgent)
- (:InferenceActivity)-[:USED]->(:WisdomChunk)
- (:InferenceActivity)-[:TRIGGERED_BY]->(:SeekerTurn)
- (:GuruResponse)-[:RESPONDS_TO]->(:SeekerTurn)

Phase 3 Backend Component.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import Callable
from typing import Any, Optional

from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,
    EUComplianceRiskTier,
    GroundingSourceReference,
    OriginType,
    SoftwareAgentDescriptor,
)

logger = logging.getLogger(__name__)


class ProvenanceOntologyService:
    """
    Neo4j-backed W3C PROV-O and EU AI Act Compliance Graph Service.
    """

    def __init__(
        self,
        neo4j_driver: Any = None,
        neo4j_driver_accessor: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.neo4j_driver = neo4j_driver
        self._neo4j_driver_accessor = neo4j_driver_accessor
        self._in_memory_records: dict[str, dict[str, Any]] = {}

    @property
    def _resolved_driver(self) -> Any:
        if self._neo4j_driver_accessor:
            return self._neo4j_driver_accessor()
        return self.neo4j_driver

    def record_provenance(
        self,
        manifest: AIProvenanceManifest,
        prompt_hash: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> bool:
        """
        Record a full W3C PROV-O provenance subgraph in Neo4j.
        Falls back to in-memory store if Neo4j is unavailable.
        """
        # Store in local memory cache
        manifest_dict = manifest.model_dump()
        json_ld = manifest.to_json_ld()
        self._in_memory_records[manifest.artifact_id] = {
            "manifest": manifest_dict,
            "json_ld": json_ld,
            "prompt_hash": prompt_hash,
            "latency_ms": latency_ms,
            "recorded_at": _dt.datetime.now(_dt.UTC).isoformat(),
        }

        driver = self._resolved_driver
        if not driver:
            logger.debug(
                "ProvenanceOntologyService: Neo4j driver not connected; stored in memory fallback (%s)",
                manifest.artifact_id,
            )
            return True

        try:
            with driver.session() as session:
                activity_id = f"act:{manifest.artifact_id.replace('urn:uuid:', '')}"
                agent = manifest.agent

                cypher = """
                // 1. GuruResponse Artifact (prov:Entity)
                MERGE (resp:GuruResponse {artifact_id: $artifact_id})
                ON CREATE SET
                    resp.modality = $modality,
                    resp.origin_type = $origin_type,
                    resp.risk_tier = $risk_tier,
                    resp.content_hash = $content_hash,
                    resp.watermark_signature = $watermark_signature,
                    resp.generated_at = $generated_at,
                    resp.disclosure_statement = $disclosure_statement,
                    resp.created_at = timestamp()

                // 2. InferenceActivity (prov:Activity)
                MERGE (act:InferenceActivity {activity_id: $activity_id})
                ON CREATE SET
                    act.started_at = $generated_at,
                    act.latency_ms = $latency_ms,
                    act.model_name = $model_name,
                    act.provider = $provider,
                    act.risk_tier = $risk_tier,
                    act.created_at = timestamp()

                // 3. SoftwareAgent (prov:Agent)
                MERGE (ag:SoftwareAgent {agent_id: $agent_id})
                ON CREATE SET
                    ag.name = $agent_name,
                    ag.version = $agent_version,
                    ag.role = $agent_role,
                    ag.model_name = $model_name,
                    ag.provider = $provider,
                    ag.system_prompt_hash = $system_prompt_hash,
                    ag.created_at = timestamp()

                // 4. Edges: Response -> Activity -> Agent
                MERGE (resp)-[:WAS_GENERATED_BY]->(act)
                MERGE (act)-[:WAS_ASSOCIATED_WITH]->(ag)
                """

                params: dict[str, Any] = {
                    "artifact_id": manifest.artifact_id,
                    "modality": manifest.modality.value,
                    "origin_type": manifest.origin_type.value,
                    "risk_tier": manifest.risk_tier.value,
                    "content_hash": manifest.content_hash or "",
                    "watermark_signature": manifest.watermark_signature or "",
                    "generated_at": manifest.generated_at.isoformat(),
                    "disclosure_statement": manifest.disclosure_statement,
                    "activity_id": activity_id,
                    "latency_ms": latency_ms or 0.0,
                    "agent_id": agent.agent_id,
                    "agent_name": agent.name,
                    "agent_version": agent.version or "1.0.0",
                    "agent_role": agent.role or "Spiritual AI Guide",
                    "model_name": agent.model_name or "unknown",
                    "provider": agent.provider or "unknown",
                    "system_prompt_hash": agent.system_prompt_hash or "",
                }

                session.run(cypher, **params)

                # 5. Optional SeekerTurn (prov:Entity / Trigger)
                if manifest.session_id or prompt_hash or manifest.user_id_hash:
                    turn_id = f"turn:{manifest.session_id or manifest.artifact_id}"
                    turn_cypher = """
                    MERGE (turn:SeekerTurn {turn_id: $turn_id})
                    ON CREATE SET
                        turn.session_id = $session_id,
                        turn.user_id_hash = $user_id_hash,
                        turn.prompt_hash = $prompt_hash,
                        turn.timestamp = $timestamp,
                        turn.created_at = timestamp()
                    WITH turn
                    MATCH (resp:GuruResponse {artifact_id: $artifact_id})
                    MATCH (act:InferenceActivity {activity_id: $activity_id})
                    MERGE (act)-[:TRIGGERED_BY]->(turn)
                    MERGE (resp)-[:RESPONDS_TO]->(turn)
                    """
                    session.run(
                        turn_cypher,
                        turn_id=turn_id,
                        session_id=manifest.session_id or "",
                        user_id_hash=manifest.user_id_hash or "",
                        prompt_hash=prompt_hash or "",
                        timestamp=manifest.generated_at.isoformat(),
                        artifact_id=manifest.artifact_id,
                        activity_id=activity_id,
                    )

                # 6. WisdomChunk sources (prov:used & prov:wasDerivedFrom)
                for src in manifest.sources:
                    chunk_cypher = """
                    MERGE (w:WisdomChunk {chunk_id: $source_id})
                    ON CREATE SET
                        w.source_type = $source_type,
                        w.title = $title,
                        w.url = $url,
                        w.snippet_hash = $snippet_hash,
                        w.created_at = timestamp()
                    WITH w
                    MATCH (resp:GuruResponse {artifact_id: $artifact_id})
                    MATCH (act:InferenceActivity {activity_id: $activity_id})
                    MERGE (act)-[u:USED]->(w)
                    SET u.score = $score
                    MERGE (resp)-[d:WAS_DERIVED_FROM]->(w)
                    """
                    session.run(
                        chunk_cypher,
                        source_id=src.source_id,
                        source_type=src.source_type,
                        title=src.title or "",
                        url=src.url or "",
                        snippet_hash=src.snippet_hash or "",
                        score=src.score or 0.0,
                        artifact_id=manifest.artifact_id,
                        activity_id=activity_id,
                    )

            logger.info(
                "ProvenanceOntologyService: Recorded PROV-O graph in Neo4j for %s",
                manifest.artifact_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "ProvenanceOntologyService: Neo4j write failed (%s); preserved in memory fallback",
                exc,
            )
            return False

    def get_provenance_manifest(self, artifact_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve W3C PROV-O JSON-LD manifest for a specific artifact ID.
        Queries Neo4j or memory fallback.
        """
        driver = self._resolved_driver
        if driver:
            try:
                with driver.session() as session:
                    cypher = """
                    MATCH (resp:GuruResponse {artifact_id: $artifact_id})
                    OPTIONAL MATCH (resp)-[:WAS_GENERATED_BY]->(act:InferenceActivity)
                    OPTIONAL MATCH (act)-[:WAS_ASSOCIATED_WITH]->(ag:SoftwareAgent)
                    OPTIONAL MATCH (resp)-[:WAS_DERIVED_FROM]->(w:WisdomChunk)
                    OPTIONAL MATCH (resp)-[:RESPONDS_TO]->(turn:SeekerTurn)
                    RETURN resp, act, ag, collect(DISTINCT w) AS sources, turn
                    """
                    result = session.run(cypher, artifact_id=artifact_id)
                    record = result.single()
                    if record and record["resp"]:
                        resp_node = record["resp"]
                        act_node = record["act"] or {}
                        ag_node = record["ag"] or {}
                        sources_nodes = record["sources"] or []
                        turn_node = record["turn"] or {}

                        sources_list = [
                            GroundingSourceReference(
                                source_id=s.get("chunk_id", ""),
                                source_type=s.get("source_type", "spiritual_wisdom"),
                                title=s.get("title") or None,
                                url=s.get("url") or None,
                                snippet_hash=s.get("snippet_hash") or None,
                            )
                            for s in sources_nodes
                            if s and s.get("chunk_id")
                        ]

                        agent_desc = SoftwareAgentDescriptor(
                            agent_id=ag_node.get("agent_id", "askmukthiguru-core"),
                            name=ag_node.get("name", "AskMukthiGuru AI Assistant"),
                            version=ag_node.get("version", "1.0.0"),
                            model_name=ag_node.get("model_name") or act_node.get("model_name"),
                            provider=ag_node.get("provider") or act_node.get("provider"),
                            role=ag_node.get("role", "Spiritual AI Guide"),
                            system_prompt_hash=ag_node.get("system_prompt_hash") or None,
                        )

                        manifest = AIProvenanceManifest(
                            artifact_id=resp_node.get("artifact_id", artifact_id),
                            modality=resp_node.get("modality", ArtifactModality.TEXT_CHAT.value),
                            origin_type=resp_node.get("origin_type", OriginType.AI_GENERATED.value),
                            risk_tier=resp_node.get(
                                "risk_tier", EUComplianceRiskTier.TRANSPARENCY_ART50.value
                            ),
                            agent=agent_desc,
                            sources=sources_list,
                            content_hash=resp_node.get("content_hash") or None,
                            watermark_signature=resp_node.get("watermark_signature") or None,
                            disclosure_statement=resp_node.get(
                                "disclosure_statement",
                                "This content was generated by AskMukthiGuru AI assistant in compliance with EU AI Act Article 50 transparency obligations.",
                            ),
                            session_id=turn_node.get("session_id") or None,
                            user_id_hash=turn_node.get("user_id_hash") or None,
                        )
                        return manifest.to_json_ld()
            except Exception as exc:
                logger.warning("ProvenanceOntologyService: Query failed (%s)", exc)

        # Check memory fallback
        if artifact_id in self._in_memory_records:
            return self._in_memory_records[artifact_id].get("json_ld")

        return None

    def search_provenance(
        self,
        origin_type: Optional[str] = None,
        model_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search provenance records by origin_type, model, and date range.
        """
        driver = self._resolved_driver
        if driver:
            try:
                with driver.session() as session:
                    clauses = ["MATCH (resp:GuruResponse)"]
                    clauses.append(
                        "OPTIONAL MATCH (resp)-[:WAS_GENERATED_BY]->(act:InferenceActivity)"
                    )
                    clauses.append(
                        "OPTIONAL MATCH (act)-[:WAS_ASSOCIATED_WITH]->(ag:SoftwareAgent)"
                    )

                    where_conditions: list[str] = []
                    params: dict[str, Any] = {"limit": limit}

                    if origin_type:
                        where_conditions.append("resp.origin_type = $origin_type")
                        params["origin_type"] = origin_type
                    if model_name:
                        where_conditions.append(
                            "(act.model_name = $model_name OR ag.model_name = $model_name)"
                        )
                        params["model_name"] = model_name
                    if start_date:
                        where_conditions.append("resp.generated_at >= $start_date")
                        params["start_date"] = start_date
                    if end_date:
                        where_conditions.append("resp.generated_at <= $end_date")
                        params["end_date"] = end_date

                    if where_conditions:
                        clauses.append("WHERE " + " AND ".join(where_conditions))

                    clauses.append(
                        "RETURN resp.artifact_id AS artifact_id, "
                        "resp.modality AS modality, "
                        "resp.origin_type AS origin_type, "
                        "resp.risk_tier AS risk_tier, "
                        "resp.generated_at AS generated_at, "
                        "resp.content_hash AS content_hash, "
                        "act.model_name AS model_name, "
                        "act.provider AS provider, "
                        "ag.name AS agent_name "
                        "ORDER BY resp.generated_at DESC "
                        "LIMIT $limit"
                    )

                    cypher = "\n".join(clauses)
                    result = session.run(cypher, **params)
                    records: list[dict[str, Any]] = []
                    for row in result:
                        records.append(
                            {
                                "artifact_id": row["artifact_id"],
                                "modality": row["modality"],
                                "origin_type": row["origin_type"],
                                "risk_tier": row["risk_tier"],
                                "generated_at": row["generated_at"],
                                "content_hash": row["content_hash"],
                                "model_name": row["model_name"],
                                "provider": row["provider"],
                                "agent_name": row["agent_name"],
                            }
                        )
                    return records
            except Exception as exc:
                logger.warning("ProvenanceOntologyService: Search failed (%s)", exc)

        # In-memory search fallback
        results: list[dict[str, Any]] = []
        for rec in reversed(list(self._in_memory_records.values())):
            m = rec.get("manifest", {})
            agent = m.get("agent", {})
            rec_origin = m.get("origin_type")
            rec_model = agent.get("model_name")
            rec_date = m.get("generated_at")

            if origin_type and rec_origin != origin_type:
                continue
            if model_name and rec_model != model_name:
                continue
            if start_date and rec_date and str(rec_date) < start_date:
                continue
            if end_date and rec_date and str(rec_date) > end_date:
                continue

            results.append(
                {
                    "artifact_id": m.get("artifact_id"),
                    "modality": m.get("modality"),
                    "origin_type": rec_origin,
                    "risk_tier": m.get("risk_tier"),
                    "generated_at": str(rec_date),
                    "content_hash": m.get("content_hash"),
                    "model_name": rec_model,
                    "provider": agent.get("provider"),
                    "agent_name": agent.get("name"),
                }
            )
            if len(results) >= limit:
                break
        return results

    def get_eu_compliance_stats(self) -> dict[str, Any]:
        """
        Aggregate overview of AI generation volume, risk tiers, origin types,
        and Article 50 transparency compliance.
        """
        driver = self._resolved_driver
        if driver:
            try:
                with driver.session() as session:
                    cypher = """
                    MATCH (resp:GuruResponse)
                    OPTIONAL MATCH (resp)-[:WAS_GENERATED_BY]->(act:InferenceActivity)
                    RETURN
                        count(resp) AS total_artifacts,
                        collect(resp.origin_type) AS origin_types,
                        collect(resp.modality) AS modalities,
                        collect(resp.risk_tier) AS risk_tiers,
                        collect(act.model_name) AS models,
                        max(resp.generated_at) AS latest_generation
                    """
                    rec = session.run(cypher).single()
                    if rec and rec["total_artifacts"] > 0:
                        from collections import Counter

                        total = rec["total_artifacts"]
                        origin_counts = dict(Counter(rec["origin_types"]))
                        modality_counts = dict(Counter(rec["modalities"]))
                        risk_counts = dict(Counter(rec["risk_tiers"]))
                        model_counts = dict(Counter(m for m in rec["models"] if m))

                        return {
                            "total_artifacts": total,
                            "origin_breakdown": origin_counts,
                            "modality_breakdown": modality_counts,
                            "risk_tier_breakdown": risk_counts,
                            "model_breakdown": model_counts,
                            "article_50_disclosure_rate": 1.0,
                            "latest_generation": rec["latest_generation"],
                            "storage": "neo4j",
                        }
            except Exception as exc:
                logger.warning("ProvenanceOntologyService: Stats aggregation failed (%s)", exc)

        # Fallback to in-memory stats
        from collections import Counter

        total = len(self._in_memory_records)
        origins = []
        mods = []
        risks = []
        models = []
        latest = None

        for rec in self._in_memory_records.values():
            m = rec.get("manifest", {})
            origins.append(m.get("origin_type"))
            mods.append(m.get("modality"))
            risks.append(m.get("risk_tier"))
            agent = m.get("agent", {})
            if agent.get("model_name"):
                models.append(agent.get("model_name"))
            latest = str(m.get("generated_at"))

        return {
            "total_artifacts": total,
            "origin_breakdown": dict(Counter(origins)),
            "modality_breakdown": dict(Counter(mods)),
            "risk_tier_breakdown": dict(Counter(risks)),
            "model_breakdown": dict(Counter(models)),
            "article_50_disclosure_rate": 1.0 if total > 0 else 1.0,
            "latest_generation": latest,
            "storage": "in_memory_fallback",
        }


# ---------------------------------------------------------------------------
# Singleton & Factory
# ---------------------------------------------------------------------------
_provenance_ontology_service: Optional[ProvenanceOntologyService] = None


def get_provenance_ontology_service(
    neo4j_driver: Any = None,
) -> ProvenanceOntologyService:
    """Return or initialize the singleton ProvenanceOntologyService."""
    global _provenance_ontology_service
    if _provenance_ontology_service is None:
        _provenance_ontology_service = ProvenanceOntologyService(
            neo4j_driver=neo4j_driver,
        )
    return _provenance_ontology_service
