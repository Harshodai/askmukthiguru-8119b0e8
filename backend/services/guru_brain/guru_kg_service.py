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
from collections.abc import Callable
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
    tenant_id: str = ""
    source_asset_id: str = ""
    source_url: str = ""
    video_id: str = ""
    domain_rights_status: str = ""
    speaker_verified: bool = False
    speaker_verification_reference: str = ""


class GuruKGService:
    """Neo4j Knowledge Graph & OKF 5-Node Ontology Engine."""

    def __init__(
        self,
        neo4j_driver: Any = None,
        neo4j_driver_accessor: Optional[Callable[[], Any]] = None,
        *,
        source_write_authorizer: Optional[Callable[..., bool]] = None,
        user_state_write_authorizer: Optional[Callable[..., bool]] = None,
    ) -> None:
        self.neo4j_driver = neo4j_driver
        self._neo4j_driver_accessor = neo4j_driver_accessor
        # Database writes are disabled unless the caller injects an authority
        # that checks the current source-rights register or active user consent.
        # A Neo4j driver alone is never permission to mutate governed data.
        self._source_write_authorizer = source_write_authorizer
        self._user_state_write_authorizer = user_state_write_authorizer
        self._in_memory_graph: dict[str, list[OKFTransformationArc]] = {}

    @property
    def _resolved_driver(self):
        if self._neo4j_driver_accessor:
            return self._neo4j_driver_accessor()
        return self.neo4j_driver

    def populate_ontology_arc(
        self,
        seeker_dilemma: str,
        limiting_belief: str,
        teaching: str,
        target_state: str,
        practice_step: str,
        guru_speaker: str = "Sri Preethaji & Sri Krishnaji",
        *,
        tenant_id: str = "",
        source_asset_id: str = "",
        source_url: str = "",
        video_id: str = "",
        domain_rights_status: str = "",
        speaker_verified: bool = False,
        speaker_verification_reference: str = "",
    ) -> bool:
        """Persist a source-bound ontology arc only after authoritative clearance.

        This legacy writer is deliberately inert by default. Callers must supply
        source identity and an injected authorizer that re-checks the current
        rights register; a Bolt driver or a payload string is not clearance.
        The stored graph edge retains the source identity that justified it.
        """
        required_source_values = (
            str(tenant_id or "").strip(),
            str(source_asset_id or "").strip(),
            str(source_url or "").strip(),
            str(video_id or "").strip(),
            str(domain_rights_status or "").strip(),
            str(speaker_verification_reference or "").strip(),
        )
        if (
            not all(required_source_values)
            or str(domain_rights_status or "").strip().lower() != "licensed"
            or speaker_verified is not True
            or self._source_write_authorizer is None
        ):
            logger.warning(
                "GuruKGService: ontology write refused; tenant, source provenance, "
                "and a current rights authorizer are required."
            )
            return False

        try:
            authorized = bool(
                self._source_write_authorizer(
                    tenant_id=str(tenant_id or "").strip(),
                    source_asset_id=str(source_asset_id or "").strip(),
                    source_url=str(source_url or "").strip(),
                    video_id=str(video_id or "").strip(),
                    domain_rights_status=str(domain_rights_status or "").strip(),
                    speaker_verified=speaker_verified is True,
                    speaker_verification_reference=str(speaker_verification_reference or "").strip(),
                    guru_speaker=guru_speaker,
                )
            )
        except Exception as exc:
            logger.warning("GuruKGService: source authorization failed closed: %s", exc)
            return False
        if not authorized:
            logger.warning("GuruKGService: ontology write refused by source-rights authorizer.")
            return False

        driver = self._resolved_driver
        if driver is None:
            logger.warning("GuruKGService: ontology write refused; graph driver unavailable.")
            return False

        arc = OKFTransformationArc(
            seeker_dilemma=seeker_dilemma,
            limiting_belief=limiting_belief,
            teaching=teaching,
            target_state=target_state,
            practice_step=practice_step,
            guru_speaker=guru_speaker,
            tenant_id=str(tenant_id or "").strip(),
            source_asset_id=str(source_asset_id or "").strip(),
            source_url=str(source_url or "").strip(),
            video_id=str(video_id or "").strip(),
            domain_rights_status=str(domain_rights_status or "").strip(),
            speaker_verified=True,
            speaker_verification_reference=str(speaker_verification_reference or "").strip(),
        )
        cypher = """
        MERGE (g:GuruSpeaker {tenant_id: $tenant_id, name: $guru})
        MERGE (d:SeekerDilemma {tenant_id: $tenant_id, name: $dilemma})
        ON CREATE SET d.created_at = timestamp()
        MERGE (b:RootLimitingBelief {tenant_id: $tenant_id, name: $belief})
        ON CREATE SET b.created_at = timestamp()
        MERGE (t:GuruTeaching {tenant_id: $tenant_id, name: $teaching})
        ON CREATE SET t.created_at = timestamp()
        MERGE (s:BeautifulState {tenant_id: $tenant_id, name: $state})
        ON CREATE SET s.created_at = timestamp()
        MERGE (p:PracticeStep {tenant_id: $tenant_id, name: $practice})
        ON CREATE SET p.created_at = timestamp()
        MERGE (d)-[r1:DRIVEN_BY {
            tenant_id: $tenant_id, source_asset_id: $source_asset_id
        }]->(b)
        ON CREATE SET r1.valid_at = timestamp(), r1.source_url = $source_url,
                      r1.video_id = $video_id, r1.domain_rights_status = $rights_status,
                      r1.speaker_verified = $speaker_verified,
                      r1.speaker_verification_reference = $speaker_verification_reference
        MERGE (t)-[r2:DISMANTLES {
            tenant_id: $tenant_id, source_asset_id: $source_asset_id
        }]->(b)
        ON CREATE SET r2.valid_at = timestamp(), r2.source_url = $source_url,
                      r2.video_id = $video_id, r2.domain_rights_status = $rights_status,
                      r2.speaker_verified = $speaker_verified,
                      r2.speaker_verification_reference = $speaker_verification_reference
        MERGE (t)-[r3:TRANSFORMS_TO {
            tenant_id: $tenant_id, source_asset_id: $source_asset_id
        }]->(s)
        ON CREATE SET r3.valid_at = timestamp(), r3.source_url = $source_url,
                      r3.video_id = $video_id, r3.domain_rights_status = $rights_status,
                      r3.speaker_verified = $speaker_verified,
                      r3.speaker_verification_reference = $speaker_verification_reference
        MERGE (t)-[r4:PRESCRIBES {
            tenant_id: $tenant_id, source_asset_id: $source_asset_id
        }]->(p)
        ON CREATE SET r4.valid_at = timestamp(), r4.source_url = $source_url,
                      r4.video_id = $video_id, r4.domain_rights_status = $rights_status,
                      r4.speaker_verified = $speaker_verified,
                      r4.speaker_verification_reference = $speaker_verification_reference
        MERGE (g)-[r5:TEACHES {
            tenant_id: $tenant_id, source_asset_id: $source_asset_id
        }]->(t)
        ON CREATE SET r5.valid_at = timestamp(), r5.source_url = $source_url,
                      r5.video_id = $video_id, r5.domain_rights_status = $rights_status,
                      r5.speaker_verified = $speaker_verified,
                      r5.speaker_verification_reference = $speaker_verification_reference
        """
        try:
            with driver.session() as session:
                session.run(
                    cypher,
                    tenant_id=str(tenant_id or "").strip(),
                    source_asset_id=str(source_asset_id or "").strip(),
                    source_url=str(source_url or "").strip(),
                    video_id=str(video_id or "").strip(),
                    rights_status=str(domain_rights_status or "").strip(),
                    speaker_verified=speaker_verified is True,
                    speaker_verification_reference=str(speaker_verification_reference or "").strip(),
                    guru=guru_speaker,
                    dilemma=seeker_dilemma,
                    belief=limiting_belief,
                    teaching=teaching,
                    state=target_state,
                    practice=practice_step,
                )
            self._in_memory_graph.setdefault(str(tenant_id or "").strip(), []).append(arc)
            return True
        except Exception as exc:
            logger.warning("GuruKGService: governed ontology write failed: %s", exc)
            return False

    def record_user_state_transition(
        self,
        user_id: str,
        from_state: str,
        to_state: str,
        trigger_context: str = "",
        *,
        tenant_id: str = "",
        consent_receipt_id: str = "",
    ) -> bool:
        """Persist a seeker-state transition only after a caller proves consent.

        A configured authorizer must validate the active, tenant-scoped consent
        receipt. No graph driver or user ID alone authorizes a durable write.
        `trigger_context` is accepted for compatibility but never persisted:
        private reflections belong in the consent-managed memory plane.
        """
        if (
            not str(user_id or "").strip()
            or not str(tenant_id or "").strip()
            or not str(consent_receipt_id or "").strip()
            or not str(from_state or "").strip()
            or not str(to_state or "").strip()
            or self._user_state_write_authorizer is None
        ):
            logger.info(
                "GuruKGService: user-state write skipped; tenant-scoped consent proof is missing."
            )
            return False
        try:
            authorized = bool(
                self._user_state_write_authorizer(
                    user_id=str(user_id or "").strip(),
                    tenant_id=str(tenant_id or "").strip(),
                    consent_receipt_id=str(consent_receipt_id or "").strip(),
                )
            )
        except Exception as exc:
            logger.warning("GuruKGService: user-state consent check failed closed: %s", exc)
            return False
        if not authorized:
            logger.info("GuruKGService: user-state write refused by consent authorizer.")
            return False

        driver = self._resolved_driver
        if driver is None:
            return False
        try:
            with driver.session() as session:
                cypher = """
                MERGE (u:User {tenant_id: $tenant_id, id: $user_id})
                MERGE (s1:State {tenant_id: $tenant_id, name: $from_state})
                MERGE (s2:State {tenant_id: $tenant_id, name: $to_state})
                CREATE (u)-[:TRANSITIONED {
                    tenant_id: $tenant_id,
                    consent_receipt_id: $consent_receipt_id,
                    from_state: $from_state,
                    to_state: $to_state,
                    timestamp: timestamp()
                }]->(s2)
                MERGE (s1)-[:TRANSITIONS_TO {tenant_id: $tenant_id}]->(s2)
                """
                session.run(
                    cypher,
                    tenant_id=str(tenant_id or "").strip(),
                    user_id=str(user_id or "").strip(),
                    consent_receipt_id=str(consent_receipt_id or "").strip(),
                    from_state=str(from_state or "").strip()[:160],
                    to_state=str(to_state or "").strip()[:160],
                )
            logger.info("GuruKGService: consented user-state transition recorded.")
            return True
        except Exception as exc:
            logger.warning("GuruKGService: Failed to record consented user-state transition: %s", exc)
            return False

    def traverse_guru_ontology(
        self,
        query: str,
        limit: int = 3,
        timeout: float | None = 2.0,
        *,
        tenant_id: str = "",
    ) -> list[OKFTransformationArc]:
        """Perform tenant-scoped graph traversal with a real Bolt transaction timeout.

        Missing tenant scope, blank queries, and non-positive budgets fail closed.
        Legacy nodes/edges without tenant metadata are intentionally invisible.
        """
        query = str(query or "").strip()
        tenant = str(tenant_id or "").strip()
        limit = min(max(int(limit), 0), 50)
        if not query or not tenant or limit == 0:
            return []
        if timeout is not None and float(timeout) <= 0:
            return []

        driver = self._resolved_driver
        if driver is not None:
            cypher = """
            MATCH (d:SeekerDilemma {tenant_id: $tenant_id})
                -[driven:DRIVEN_BY]->
                (b:RootLimitingBelief {tenant_id: $tenant_id})
            MATCH (t:GuruTeaching {tenant_id: $tenant_id})
                -[dismantles:DISMANTLES]->(b)
            MATCH (t)-[transforms:TRANSFORMS_TO]->(s:BeautifulState {tenant_id: $tenant_id})
            MATCH (t)-[prescribes:PRESCRIBES]->(p:PracticeStep {tenant_id: $tenant_id})
            MATCH (g:GuruSpeaker {tenant_id: $tenant_id})-[teaches:TEACHES]->(t)
            WHERE driven.tenant_id = $tenant_id
              AND dismantles.tenant_id = $tenant_id
              AND transforms.tenant_id = $tenant_id
              AND prescribes.tenant_id = $tenant_id
              AND teaches.tenant_id = $tenant_id
              AND driven.source_asset_id = dismantles.source_asset_id
              AND driven.source_asset_id = transforms.source_asset_id
              AND driven.source_asset_id = prescribes.source_asset_id
              AND driven.source_asset_id = teaches.source_asset_id
              AND driven.domain_rights_status = 'licensed'
              AND dismantles.domain_rights_status = 'licensed'
              AND transforms.domain_rights_status = 'licensed'
              AND prescribes.domain_rights_status = 'licensed'
              AND teaches.domain_rights_status = 'licensed'
              AND driven.speaker_verified = true
              AND dismantles.speaker_verified = true
              AND transforms.speaker_verified = true
              AND prescribes.speaker_verified = true
              AND teaches.speaker_verified = true
              AND driven.speaker_verification_reference =
                  dismantles.speaker_verification_reference
              AND driven.speaker_verification_reference =
                  transforms.speaker_verification_reference
              AND driven.speaker_verification_reference =
                  prescribes.speaker_verification_reference
              AND driven.speaker_verification_reference =
                  teaches.speaker_verification_reference
              AND (
                toLower(d.name) CONTAINS toLower($q)
                OR toLower(t.name) CONTAINS toLower($q)
              )
            RETURN DISTINCT
                d.name AS dilemma,
                b.name AS belief,
                t.name AS teaching,
                s.name AS state,
                p.name AS practice,
                g.name AS guru,
                driven.tenant_id AS tenant_id,
                driven.source_asset_id AS source_asset_id,
                driven.source_url AS source_url,
                driven.video_id AS video_id,
                driven.domain_rights_status AS domain_rights_status,
                driven.speaker_verified AS speaker_verified,
                driven.speaker_verification_reference AS speaker_verification_reference
            LIMIT $limit
            """
            tx = None
            try:
                with driver.session() as session:
                    # session.run(timeout=...) forwards a query parameter. The
                    # Bolt transaction API is what enforces the server deadline.
                    tx = (
                        session.begin_transaction(timeout=float(timeout))
                        if timeout is not None
                        else session.begin_transaction()
                    )
                    result = tx.run(cypher, q=query, limit=limit, tenant_id=tenant)
                    arcs = [
                        OKFTransformationArc(
                            seeker_dilemma=record["dilemma"],
                            limiting_belief=record["belief"],
                            teaching=record["teaching"],
                            target_state=record["state"],
                            practice_step=record["practice"],
                            guru_speaker=record["guru"],
                            tenant_id=record["tenant_id"],
                            source_asset_id=record["source_asset_id"],
                            source_url=record["source_url"],
                            video_id=record["video_id"],
                            domain_rights_status=record["domain_rights_status"],
                            speaker_verified=bool(record["speaker_verified"]),
                            speaker_verification_reference=record["speaker_verification_reference"],
                        )
                        for record in result
                    ]
                    tx.commit()
                    if arcs:
                        logger.info(
                            "GuruKGService: tenant-scoped source-certified traversal found %d arcs (query_len=%d)",
                            len(arcs),
                            len(query),
                        )
                        return arcs[:limit]
            except Exception as exc:
                if tx is not None:
                    try:
                        tx.rollback()
                    except Exception:
                        pass
                logger.warning(
                    "GuruKGService: tenant-scoped traversal failed (fail-open): %s",
                    exc,
                )

        # Fallback contains only arcs accepted by the governed write path and
        # stored under the same tenant key. It never fabricates a default arc.
        return list(self._in_memory_graph.get(tenant, []))[:limit]

    def format_kg_ontology_context(self, arcs: list[OKFTransformationArc]) -> str:
        """Format retrieved 5-node OKF Knowledge Graph arcs into prompt context."""
        if not arcs:
            return ""

        blocks = [
            "=== STRUCTURED ONTOLOGY RELATIONSHIPS (not verbatim teacher quotations) ==="
        ]
        for i, a in enumerate(arcs, 1):
            blocks.append(
                f"Arc {i}: [Dilemma: {a.seeker_dilemma}] -> [Limiting Belief: {a.limiting_belief}]\n"
                f"  Teaching concept ({a.guru_speaker}): {a.teaching}\n"
                f"  Target state concept: {a.target_state} | Practice concept: {a.practice_step}\n"
                f"  Source: {a.source_asset_id or 'unavailable'} | Rights: {a.domain_rights_status or 'unknown'} | "
                f"Speaker verified: {a.speaker_verified}"
            )

        return "\n".join(blocks)


_kg_instance: Optional[GuruKGService] = None


def get_guru_kg_service(neo4j_driver: Any = None) -> GuruKGService:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = GuruKGService(neo4j_driver=neo4j_driver)
    return _kg_instance
