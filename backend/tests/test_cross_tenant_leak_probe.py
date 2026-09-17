"""Gate 0.2: Cross-Tenant and Cross-Teacher Leak-Probe Suite.

Enforces strict zero-leakage isolation across:
1. Qdrant Dense & Hybrid Vector Retrieval (tenant_id + corpus_id + teacher_ids)
2. Qdrant Per-Teacher Scoped Retrieval (primary teacher_id & attributed teacher_ids)
3. Cache Keys and Semantic Cache
4. Neo4j Knowledge Graph Relational Expansion (r.tenant_id edge filtering)

Invariants (LAUNCH_READINESS_GATES_2026-09-13.md - Gate 0.2):
--------------------------------------------------------------
- Zero cross-bleed across dense, sparse, semantic cache, and Neo4j expansion.
- "We interpret the teachings of the gurus in the best and 100% correct way."
- Filtering by tenant must strictly reject any documents belonging to other tenants.
- Filtering by teacher must never return documents from unapproved or unrelated teachers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models

from rag.corpus_scope import CorpusScope
from services.qdrant.searcher import QdrantSearcher
from services.tenant_context import TenantContext


@pytest.fixture
def memory_qdrant_client():
    """Create an in-memory Qdrant instance with real payload indexes."""
    client = QdrantClient(":memory:")
    collection_name = "test_spiritual_wisdom_contextual"

    client.create_collection(
        collection_name=collection_name,
        vectors_config={"dense": models.VectorParams(size=4, distance=models.Distance.COSINE)},
    )

    # Initialize required keyword payload indexes
    for field_name in [
        "tenant_id",
        "corpus_id",
        "teacher_id",
        "teacher_ids",
        "domain_rights_status",
    ]:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    # Populate synthetic documents across two tenants and multiple teachers
    points = [
        # Tenant Alpha (Ekam Lineage)
        models.PointStruct(
            id=1,
            vector={"dense": [1.0, 0.0, 0.0, 0.0]},
            payload={
                "text": "Alpha: Sri Preethaji teaches the practice of Serene Mind and Inner Peace.",
                "title": "Serene Mind Meditation",
                "speaker": "Sri Preethaji",
                "tenant_id": "tenant_alpha",
                "corpus_id": "askmukthiguru",
                "teacher_id": "preethaji",
                "teacher_ids": ["preethaji", "krishnaji"],
                "domain_rights_status": "licensed",
                "content_type": "video",
                "raptor_level": 0,
            },
        ),
        models.PointStruct(
            id=2,
            vector={"dense": [0.9, 0.1, 0.0, 0.0]},
            payload={
                "text": "Alpha: Sri Krishnaji speaks on conscious living and dissolving the self-centric mind.",
                "title": "Conscious Living",
                "speaker": "Sri Krishnaji",
                "tenant_id": "tenant_alpha",
                "corpus_id": "askmukthiguru",
                "teacher_id": "krishnaji",
                "teacher_ids": ["krishnaji", "preethaji"],
                "domain_rights_status": "licensed",
                "content_type": "video",
                "raptor_level": 0,
            },
        ),
        models.PointStruct(
            id=3,
            vector={"dense": [0.8, 0.2, 0.0, 0.0]},
            payload={
                "text": "Alpha: Ekam World Peace Festival joint meditation by Preethaji and Krishnaji.",
                "title": "Peace Festival Discourse",
                "speaker": "Sri Preethaji & Sri Krishnaji",
                "tenant_id": "tenant_alpha",
                "corpus_id": "askmukthiguru",
                "teacher_id": "preethaji_krishnaji",
                "teacher_ids": ["preethaji", "krishnaji"],
                "domain_rights_status": "licensed",
                "content_type": "video",
                "raptor_level": 0,
            },
        ),
        # Tenant Beta (Separate organization / tenant)
        models.PointStruct(
            id=4,
            vector={"dense": [0.95, 0.05, 0.0, 0.0]},
            payload={
                "text": "Beta: Proprietary corporate meditation discourse for Beta organization.",
                "title": "Corporate Stillness",
                "speaker": "Beta Guide",
                "tenant_id": "tenant_beta",
                "corpus_id": "beta_corpus",
                "teacher_id": "beta_guide",
                "teacher_ids": ["beta_guide"],
                "domain_rights_status": "licensed",
                "content_type": "video",
                "raptor_level": 0,
            },
        ),
        models.PointStruct(
            id=5,
            vector={"dense": [0.7, 0.3, 0.0, 0.0]},
            payload={
                "text": "External: Reference discourse from unlicensed external teacher.",
                "title": "External Teaching",
                "speaker": "Sadhguru",
                "tenant_id": "tenant_alpha",
                "corpus_id": "askmukthiguru",
                "teacher_id": "sadhguru",
                "teacher_ids": ["sadhguru"],
                "domain_rights_status": "unlicensed_reference_only",
                "content_type": "video",
                "raptor_level": 0,
            },
        ),
    ]

    client.upsert(collection_name=collection_name, points=points)
    return client, collection_name


def test_qdrant_dense_retrieval_tenant_isolation(memory_qdrant_client):
    """Gate 0.2 Probe 1: Queries under Tenant Alpha must NEVER retrieve Tenant Beta documents."""
    client, collection_name = memory_qdrant_client
    searcher = QdrantSearcher(client=client, collection=collection_name)
    query_vector = [1.0, 0.0, 0.0, 0.0]

    # Query as Tenant Alpha
    TenantContext.set("tenant_alpha")
    alpha_results = searcher.search(
        query_vector=query_vector,
        limit=10,
        scope=CorpusScope(tenant_id="tenant_alpha", corpus_id="askmukthiguru"),
    )

    assert len(alpha_results) > 0, "Tenant Alpha should retrieve its own documents"
    for r in alpha_results:
        assert r.get("tenant_id") == "tenant_alpha", (
            f"LEAK DETECTED: Returned point from tenant {r.get('tenant_id')} to tenant_alpha!"
        )
        assert r.get("tenant_id") != "tenant_beta", "CRITICAL LEAK: Beta content returned to Alpha"

    # Query as Tenant Beta
    TenantContext.set("tenant_beta")
    beta_results = searcher.search(
        query_vector=query_vector,
        limit=10,
        scope=CorpusScope(tenant_id="tenant_beta", corpus_id="beta_corpus"),
    )

    assert len(beta_results) > 0, "Tenant Beta should retrieve its own documents"
    for r in beta_results:
        assert r.get("tenant_id") == "tenant_beta", (
            f"LEAK DETECTED: Returned point from tenant {r.get('tenant_id')} to tenant_beta!"
        )
        assert r.get("tenant_id") != "tenant_alpha", "CRITICAL LEAK: Alpha content returned to Beta"


def test_qdrant_teacher_scoped_retrieval_isolation(memory_qdrant_client):
    """Gate 0.2 Probe 2: Teacher scope checks both teacher_ids and teacher_id and isolates external teachers."""
    client, collection_name = memory_qdrant_client
    searcher = QdrantSearcher(client=client, collection=collection_name)
    query_vector = [1.0, 0.0, 0.0, 0.0]

    # 1. Scope: Sri Preethaji
    TenantContext.set("tenant_alpha")
    preethaji_scope = CorpusScope(
        tenant_id="tenant_alpha",
        corpus_id="askmukthiguru",
        teacher_id="preethaji",
    )
    preethaji_results = searcher.search(
        query_vector=query_vector,
        limit=10,
        scope=preethaji_scope,
    )

    assert len(preethaji_results) > 0
    for r in preethaji_results:
        teacher_ids = r.get("teacher_ids", [])
        primary_tid = r.get("teacher_id")
        assert "preethaji" in teacher_ids or primary_tid == "preethaji", (
            f"LEAK DETECTED: Document not attributed to Preethaji returned in Preethaji scope: {r}"
        )
        assert primary_tid != "sadhguru", "CRITICAL: External teacher returned in Preethaji scope!"

    # 2. Scope: Sri Krishnaji
    krishnaji_scope = CorpusScope(
        tenant_id="tenant_alpha",
        corpus_id="askmukthiguru",
        teacher_id="krishnaji",
    )
    krishnaji_results = searcher.search(
        query_vector=query_vector,
        limit=10,
        scope=krishnaji_scope,
    )

    assert len(krishnaji_results) > 0
    for r in krishnaji_results:
        teacher_ids = r.get("teacher_ids", [])
        primary_tid = r.get("teacher_id")
        assert "krishnaji" in teacher_ids or primary_tid == "krishnaji", (
            f"LEAK DETECTED: Document not attributed to Krishnaji returned in Krishnaji scope: {r}"
        )
        assert primary_tid != "sadhguru", "CRITICAL: External teacher returned in Krishnaji scope!"


def test_qdrant_licensed_domain_rights_isolation(memory_qdrant_client):
    """Gate 0.2 Probe 3: Licensed domain rights gate strictly excludes unlicensed reference content."""
    client, collection_name = memory_qdrant_client
    searcher = QdrantSearcher(client=client, collection=collection_name)
    query_vector = [1.0, 0.0, 0.0, 0.0]

    TenantContext.set("tenant_alpha")
    licensed_scope = CorpusScope(
        tenant_id="tenant_alpha",
        corpus_id="askmukthiguru",
        required_rights_status="licensed",
    )
    licensed_results = searcher.search(
        query_vector=query_vector,
        limit=10,
        scope=licensed_scope,
    )

    for r in licensed_results:
        assert r.get("domain_rights_status") == "licensed"
        assert r.get("teacher_id") != "sadhguru", (
            "Unlicensed external teacher leaked past rights gate!"
        )


@pytest.mark.asyncio
async def test_semantic_cache_cross_tenant_leak_prevention():
    """Gate 0.2 Probe 4: Semantic and exact cache keys MUST be tenant-scoped."""
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    coordinator = PipelineCoordinator(MagicMock())

    TenantContext.set("tenant_alpha")
    key_alpha = coordinator._build_context_aware_cache_key("What is the nature of suffering?", "en")

    TenantContext.set("tenant_beta")
    key_beta = coordinator._build_context_aware_cache_key("What is the nature of suffering?", "en")

    assert key_alpha != key_beta, "Cache keys for identical queries must differ between tenants"
    assert "tenant:tenant_alpha:" in key_alpha
    assert "tenant:tenant_beta:" in key_beta


@pytest.mark.asyncio
async def test_neo4j_kg_expansion_cross_tenant_isolation():
    """Gate 0.2 Probe 5: Neo4j ontology expansion must NOT traverse edges across different tenants."""
    from rag.kg_expansion import expand_query_via_kg

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Mock session.run to return results only if tenant_id matches
    def mock_run(cypher_query, concept, limit, tenant_id):
        # Assert tenant_id is parameterized in the Cypher call
        assert "$tenant_id" in cypher_query, "Cypher query must parameterize r.tenant_id"
        if tenant_id == "tenant_alpha":
            record = MagicMock()
            record.get.return_value = "Alpha Concept"
            return [record]
        elif tenant_id == "tenant_beta":
            record = MagicMock()
            record.get.return_value = "Beta Concept"
            return [record]
        return []

    mock_session.run.side_effect = mock_run

    # Run under tenant_alpha
    TenantContext.set("tenant_alpha")
    alpha_neighbors = await expand_query_via_kg(
        query="Tell me about Meditation and stillness",
        neo4j_driver=mock_driver,
    )

    assert "Alpha Concept" in alpha_neighbors
    assert "Beta Concept" not in alpha_neighbors, (
        "CRITICAL: Beta KG concept leaked to Alpha expansion!"
    )

    # Run under tenant_beta
    TenantContext.set("tenant_beta")
    beta_neighbors = await expand_query_via_kg(
        query="Tell me about Meditation and stillness",
        neo4j_driver=mock_driver,
    )

    assert "Beta Concept" in beta_neighbors
    assert "Alpha Concept" not in beta_neighbors, (
        "CRITICAL: Alpha KG concept leaked to Beta expansion!"
    )
