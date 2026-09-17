"""Unit tests for Memgraph Atomic GraphRAG and Ontology Guardrails.

Tests:
1. execute_atomic_graphrag / aexecute_atomic_graphrag
2. MemgraphCommunityService (detection, summarization, retrieval)
3. OntologyConstraintChecker (clean, mutual exclusivity, unanchored practice, prerequisite bypass, cycle)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag.nodes.atomic_graphrag import (
    aexecute_atomic_graphrag,
    execute_atomic_graphrag,
)
from services.memgraph_community_service import (
    MemgraphCommunityService,
)
from services.ontology_guardrails import (
    OntologyConstraintChecker,
)


class TestAtomicGraphRAG:
    """Test suite for Atomic GraphRAG traversal."""

    def test_execute_atomic_graphrag_driver_none(self) -> None:
        res = execute_atomic_graphrag(None, ["Karma"])
        assert res["subgraphs"] == []
        assert res["subgraph_text"] == ""
        assert res["retrieved_seeds_count"] == 0
        assert "error" in res

    def test_execute_atomic_graphrag_empty_seeds(self) -> None:
        mock_driver = MagicMock()
        res = execute_atomic_graphrag(mock_driver, [])
        assert res["subgraphs"] == []
        assert res["subgraph_text"] == ""
        assert res["retrieved_seeds_count"] == 0
        mock_driver.session.assert_not_called()

    def test_execute_atomic_graphrag_with_seeds(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        sample_subgraph = {
            "seed": {
                "name": "Beautiful State",
                "entity_id": "beautiful_state",
                "description": "Foundational inner state of peace and connection.",
            },
            "hop1_edges": [
                {
                    "source": "Beautiful State",
                    "target_name": "Inner Stillness",
                    "rel_type": "REQUIRES",
                    "rel_weight": 0.95,
                    "rel_desc": "Prerequisite condition",
                }
            ],
            "hop2_edges": [
                {
                    "source": "Inner Stillness",
                    "target_name": "Soul Sync",
                    "rel_type": "PRACTICE_FOR",
                    "rel_weight": 0.57,
                    "rel_desc": "Meditation practice",
                }
            ],
            "hop2_nodes": [
                {
                    "name": "Soul Sync",
                    "entity_id": "soul_sync",
                    "description": "Core meditation technique",
                }
            ],
        }

        mock_record = {"subgraph_context": sample_subgraph}
        mock_session.run.return_value = [mock_record]

        res = execute_atomic_graphrag(mock_driver, ["Beautiful State"])

        assert res["retrieved_seeds_count"] == 1
        assert len(res["subgraphs"]) == 1
        text = res["subgraph_text"]
        assert "Beautiful State" in text
        assert "Inner Stillness" in text
        assert "Soul Sync" in text
        assert "0.95" in text

        # Verify parameters passed to Cypher
        called_args, called_kwargs = mock_session.run.call_args
        assert called_kwargs["seed_entities"] == ["Beautiful State"]
        assert called_kwargs["hop1_limit"] == 8
        assert called_kwargs["hop2_limit"] == 5

    def test_execute_atomic_graphrag_vector_search(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_record = {
            "subgraph_context": {
                "seed": {
                    "name": "Awakening",
                    "entity_id": "awakening",
                    "description": "Shift in consciousness",
                    "similarity": 0.891,
                },
                "hop1_edges": [],
                "hop2_edges": [],
                "hop2_nodes": [],
            }
        }
        mock_session.run.return_value = [mock_record]

        res = execute_atomic_graphrag(
            mock_driver,
            seed_entities=None,
            query_vector=[0.1, 0.2, 0.3],
            top_k_seeds=2,
        )

        assert res["retrieved_seeds_count"] == 1
        assert "Similarity: 0.891" in res["subgraph_text"]
        called_args, called_kwargs = mock_session.run.call_args
        assert called_kwargs["query_vector"] == [0.1, 0.2, 0.3]
        assert called_kwargs["top_k_seeds"] == 2

    @pytest.mark.asyncio
    async def test_aexecute_atomic_graphrag(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_record = {
            "subgraph_context": {
                "seed": {"name": "Moksha", "entity_id": "moksha"},
                "hop1_edges": [],
                "hop2_edges": [],
                "hop2_nodes": [],
            }
        }
        mock_session.run.return_value = [mock_record]

        res = await aexecute_atomic_graphrag(mock_driver, ["Moksha"])
        assert res["retrieved_seeds_count"] == 1
        assert "Moksha" in res["subgraph_text"]


class TestMemgraphCommunityService:
    """Test suite for Memgraph MAGE Community detection and GraphRAG service."""

    def test_check_mage_available_true(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.single.return_value = {"cnt": 1}

        svc = MemgraphCommunityService(mock_driver)
        assert svc.check_mage_available() is True

    def test_check_mage_available_false(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.single.return_value = {"cnt": 0}

        svc = MemgraphCommunityService(mock_driver)
        assert svc.check_mage_available() is False

    def test_generate_community_summaries(self) -> None:
        svc = MemgraphCommunityService(MagicMock())
        raw_clusters = [
            {
                "cid": 42,
                "member_count": 3,
                "members": [
                    {"name": "Inner Stillness", "degree": 10, "description": "Quiet mind"},
                    {"name": "Beautiful State", "degree": 8, "description": "Peaceful awareness"},
                    {"name": "Soul Sync", "degree": 4, "description": "Meditation"},
                ],
            }
        ]

        clusters = svc.generate_community_summaries(raw_clusters)
        assert len(clusters) == 1
        c = clusters[0]
        assert c.community_id == 42
        assert "Inner Stillness" in c.central_entities
        assert "Inner Stillness & Beautiful State Teaching Domain" == c.title
        assert "3 interconnected concepts" in c.summary

    def test_compute_and_store_communities(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        # Probe MAGE
        mock_session.run.return_value.single.return_value = {"cnt": 1}

        # Return clusters on cluster_query
        cluster_record = {
            "cid": 1,
            "member_count": 2,
            "members": [
                {"name": "Deeksha", "degree": 6, "description": "Grace transmission"},
                {"name": "Grace", "degree": 5, "description": "Divine flow"},
            ],
        }

        # We configure run to return procedure count on first call, then cluster_record on second call
        def side_effect(query, **kwargs):
            m = MagicMock()
            if "mg.procedures" in query:
                m.single.return_value = {"cnt": 1}
                return m
            elif "MATCH (n:base)" in query and "WHERE n.community_id IS NOT NULL" in query:
                return [cluster_record]
            return m

        mock_session.run.side_effect = side_effect
        # 2026-09-16: the detect/cluster/persist pipeline now runs inside ONE
        # explicit transaction via session.execute_write(fn, **kwargs) so a
        # mid-run failure can't leave node.community_id committed with no
        # matching :Community node (see memgraph_community_service.py's
        # _run_community_pipeline_tx docstring). The real driver calls
        # fn(tx, **kwargs) with a transaction object exposing the same
        # .run() interface as a session; the mock session doubles as that
        # tx object here since both share the same .run side_effect.
        mock_session.execute_write.side_effect = lambda fn, **kwargs: fn(mock_session, **kwargs)

        svc = MemgraphCommunityService(mock_driver)
        res = svc.compute_and_store_communities(min_community_size=2)
        assert len(res) == 1
        assert res[0]["community_id"] == 1
        assert "Deeksha" in res[0]["title"]

    def test_retrieve_community_summaries(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        sample_community = {
            "community_id": 1,
            "title": "Oneness Teaching Domain",
            "summary": "Core cluster on oneness doctrine",
            "keywords": ["Oneness", "Ekam"],
            "central_entities": ["Oneness", "Ekam"],
            "member_count": 5,
            "matched_concepts": 2,
            "overlap": ["Oneness"],
        }
        mock_session.run.return_value = [sample_community]

        svc = MemgraphCommunityService(mock_driver)
        res = svc.retrieve_community_summaries(["Oneness"])
        assert len(res) == 1
        assert res[0]["title"] == "Oneness Teaching Domain"

    @pytest.mark.asyncio
    async def test_async_community_service_methods(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = []
        mock_session.execute_write.side_effect = lambda fn, **kwargs: fn(mock_session, **kwargs)

        svc = MemgraphCommunityService(mock_driver)
        res1 = await svc.acompute_and_store_communities()
        res2 = await svc.aretrieve_community_summaries(["Meditation"])
        assert res1 == []
        assert res2 == []


class TestOntologyConstraintChecker:
    """Test suite for Strict Ontology Guardrails."""

    def test_clean_case_no_violations(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        # All queries return empty records
        mock_session.run.return_value = []

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(
            entities=["Beautiful State", "Inner Stillness"],
            claimed_triples=[
                {"subject": "Inner Stillness", "predicate": "LEADS_TO", "object": "Beautiful State"}
            ],
            prescribed_practices=["Soul Sync"],
            user_completed_prereqs=["Inner Stillness"],
        )

        assert report.is_valid is True
        assert len(report.violations) == 0
        d = report.as_dict()
        assert d["is_valid"] is True
        assert d["violations_count"] == 0

    def test_mutual_exclusivity_cooccurrence_violation(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        violation_record = {
            "concept_a": "Suffering State",
            "concept_b": "Beautiful State",
            "violation": "MUTUALLY_EXCLUSIVE_COOCCURRENCE",
            "description": "Concepts cannot co-occur as identical or compatible states in doctrine",
        }

        def side_effect(query, **kwargs):
            if "MUTUALLY_EXCLUSIVE" in query and "entities" in kwargs:
                return [violation_record]
            return []

        mock_session.run.side_effect = side_effect

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(entities=["Suffering State", "Beautiful State"])

        assert report.is_valid is False
        assert len(report.violations) == 1
        assert report.violations[0].violation_type == "MUTUALLY_EXCLUSIVE_COOCCURRENCE"
        assert report.violations[0].subject == "Suffering State"
        assert report.violations[0].target == "Beautiful State"

    def test_mutual_exclusivity_causal_transition_violation(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        violation_record = {
            "subject": "Suffering State",
            "object": "Beautiful State",
            "relation": "CAUSES",
            "violation": "MUTUALLY_EXCLUSIVE_TRANSITION",
            "description": "Direct positive or causal relation asserted between mutually exclusive concepts",
        }

        def side_effect(query, **kwargs):
            if "MUTUALLY_EXCLUSIVE_TRANSITION" in query or "triples" in kwargs:
                return [violation_record]
            return []

        mock_session.run.side_effect = side_effect

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(
            claimed_triples=[
                {"subject": "Suffering State", "predicate": "CAUSES", "object": "Beautiful State"}
            ]
        )

        assert report.is_valid is False
        assert len(report.violations) == 1
        assert report.violations[0].violation_type == "MUTUALLY_EXCLUSIVE_TRANSITION"
        assert "CAUSES" in report.violations[0].description

    def test_core_practice_unanchored_violation(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        violation_record = {
            "practice": "Unauthorized Tantra",
            "violation": "UNANCHORED_CORE_PRACTICE",
            "description": "Core practice lacks authentic lineage verification to Sri Preethaji/Krishnaji",
        }

        def side_effect(query, **kwargs):
            if (
                "CHECK_CORE_PRACTICE" in query
                or "UNANCHORED_CORE_PRACTICE" in query
                or "practices" in kwargs
            ):
                return [violation_record]
            return []

        mock_session.run.side_effect = side_effect

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(prescribed_practices=["Unauthorized Tantra"])

        assert report.is_valid is False
        assert len(report.violations) == 1
        assert report.violations[0].violation_type == "UNANCHORED_CORE_PRACTICE"

    def test_prerequisite_bypass_violation(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        violation_record = {
            "practice": "Awakening",
            "missing_prerequisite": "Inner Stillness",
            "distance": 2,
            "dependency_chain": ["Inner Stillness", "Beautiful State", "Awakening"],
            "violation": "PREREQUISITE_BYPASS",
            "description": "Attempted to prescribe practice without satisfying mandatory prerequisite",
        }

        def side_effect(query, **kwargs):
            if "PREREQUISITE_BYPASS" in query or "target_practices" in kwargs:
                return [violation_record]
            return []

        mock_session.run.side_effect = side_effect

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(
            prescribed_practices=["Awakening"],
            user_completed_prereqs=[],
        )

        assert report.is_valid is False
        assert len(report.violations) == 1
        assert report.violations[0].violation_type == "PREREQUISITE_BYPASS"
        assert report.violations[0].target == "Inner Stillness"

    def test_prerequisite_cycle_violation(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        violation_record = {
            "cyclical_concept": "ConceptA",
            "cycle": ["ConceptA", "ConceptB", "ConceptA"],
            "violation": "PREREQUISITE_CYCLE",
            "description": "Illegal circular dependency loop detected in prerequisite DAG",
        }

        def side_effect(query, **kwargs):
            if "PREREQUISITE_CYCLE" in query:
                return [violation_record]
            return []

        mock_session.run.side_effect = side_effect

        checker = OntologyConstraintChecker(mock_driver)
        report = checker.check_constraints(check_dag_cycles=True)

        assert report.is_valid is False
        assert len(report.violations) == 1
        assert report.violations[0].violation_type == "PREREQUISITE_CYCLE"

    @pytest.mark.asyncio
    async def test_acheck_constraints(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = []

        checker = OntologyConstraintChecker(mock_driver)
        report = await checker.acheck_constraints(entities=["Karma"])
        assert report.is_valid is True
