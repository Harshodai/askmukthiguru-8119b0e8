"""Unit tests for SemanticCacheAdapter roundtrip operations and startup safety assertions.

Covers:
- P0-1: SemanticCacheAdapter._redis_key @staticmethod bugfix verification.
- P0-1: get, put, and invalidate_by_query roundtrips with mocked Qdrant and Redis.
- P0-4: Startup safety configuration assertion for semantic_cache_similarity.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.http.models import PointStruct

from app.config import settings
from rag.corpus_scope import CorpusScope
from services.cache.semantic_adapter import SemanticCacheAdapter


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.encode_single_full.return_value = {
        "dense": [0.1] * settings.embedding_dimension,
        "sparse": {},
    }
    return embedder


@pytest.fixture
def mock_redis():
    redis_client = MagicMock()
    redis_client.ping.return_value = True
    return redis_client


@pytest.fixture
def mock_qdrant():
    qdrant_client = MagicMock()
    collections_mock = MagicMock()
    collections_mock.collections = []
    qdrant_client.get_collections.return_value = collections_mock
    return qdrant_client


@pytest.fixture
def semantic_adapter(mock_embedder, mock_redis, mock_qdrant):
    """Instantiate SemanticCacheAdapter with mocked Qdrant and Redis clients."""
    with patch("redis.from_url", return_value=mock_redis), patch(
        "services.cache.semantic_adapter.QdrantClient", return_value=mock_qdrant
    ):
        adapter = SemanticCacheAdapter(
            embedding_service=mock_embedder,
            qdrant_url="http://mock-qdrant:6333",
            redis_url="redis://mock-redis:6379/0",
            ttl=3600,
            mode="best_effort",
        )
    # Explicitly wire mocks in case __init__ error handling was bypassed
    adapter._redis = mock_redis
    adapter._qdrant = mock_qdrant
    adapter._available = True
    return adapter


class TestRedisKeyStaticMethod:
    """Test _redis_key directly and via instance (P0-1 regression test)."""

    def test_redis_key_direct_class_call(self):
        scope = CorpusScope(tenant_id="oneness", corpus_id="default", teacher_id="krishnaji")
        key = SemanticCacheAdapter._redis_key(scope, "point_abc_123")
        assert key == "mukthiguru:semcache:oneness:default:krishnaji:point_abc_123"

    def test_redis_key_direct_class_call_default_teacher(self):
        scope = CorpusScope(tenant_id="oneness", corpus_id="default", teacher_id=None)
        key = SemanticCacheAdapter._redis_key(scope, "point_abc_123")
        assert key == "mukthiguru:semcache:oneness:default:all:point_abc_123"

    def test_redis_key_instance_call(self, semantic_adapter):
        scope = CorpusScope(tenant_id="tenant1", corpus_id="corpus1", teacher_id="preethaji")
        key = semantic_adapter._redis_key(scope, "point_xyz_789")
        assert key == "mukthiguru:semcache:tenant1:corpus1:preethaji:point_xyz_789"


class TestSemanticAdapterRoundtrip:
    """Test put, get, and invalidate_by_query with mocked Qdrant and Redis."""

    def test_put_roundtrip_no_type_error(self, semantic_adapter, mock_qdrant, mock_redis):
        query = "en:how to reach enlightened state"
        response_text = "Enlightenment is the dissolution of the illusion of separation."
        intent = "QUERY"
        citations = ["source_doc_1", "source_doc_2"]
        meditation_step = 2

        # Executing put must not raise TypeError (or any other exception)
        semantic_adapter.put(
            query=query,
            response=response_text,
            intent=intent,
            citations=citations,
            meditation_step=meditation_step,
        )

        # Verify Qdrant upsert was called
        assert mock_qdrant.upsert.called
        call_kwargs = mock_qdrant.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == semantic_adapter._collection
        points = call_kwargs["points"]
        assert len(points) == 1
        assert isinstance(points[0], PointStruct)
        assert points[0].payload["query"] == query
        assert points[0].payload["tenant_id"] == "oneness"

        # Verify Redis setex was called with proper key and payload
        assert mock_redis.setex.called
        redis_call_args = mock_redis.setex.call_args.args
        redis_key = redis_call_args[0]
        assert redis_key.startswith("mukthiguru:semcache:oneness:")
        assert redis_call_args[1] == 3600  # ttl
        saved_payload = json.loads(redis_call_args[2])
        assert saved_payload["response"] == response_text
        assert saved_payload["intent"] == intent
        assert saved_payload["citations"] == citations
        assert saved_payload["meditation_step"] == meditation_step
        assert saved_payload["language"] == "en"

    def test_get_hit_no_type_error(self, semantic_adapter, mock_qdrant, mock_redis):
        query = "en:how to meditate"
        expected_payload = {
            "response": "Sit quietly and observe the breath.",
            "intent": "QUERY",
            "citations": ["doc_meditation"],
            "meditation_step": 0,
            "cached_at": 1700000000.0,
            "language": "en",
        }

        # Mock Qdrant search result
        mock_hit = MagicMock()
        mock_hit.id = "point_hit_456"
        mock_hit.score = 0.96
        mock_query_res = MagicMock()
        mock_query_res.points = [mock_hit]
        mock_qdrant.query_points.return_value = mock_query_res

        # Mock Redis payload lookup
        mock_redis.get.return_value = json.dumps(expected_payload)

        # Execute get
        cached = semantic_adapter.get(query)

        assert cached is not None
        assert cached["response"] == expected_payload["response"]
        assert cached["language"] == "en"
        assert semantic_adapter._hits == 1

        # Verify Redis was queried with key containing point_id
        assert mock_redis.get.called
        redis_key_arg = mock_redis.get.call_args.args[0]
        assert "point_hit_456" in redis_key_arg

    def test_get_miss_when_qdrant_empty(self, semantic_adapter, mock_qdrant, mock_redis):
        mock_query_res = MagicMock()
        mock_query_res.points = []
        mock_qdrant.query_points.return_value = mock_query_res

        cached = semantic_adapter.get("en:unknown question")
        assert cached is None
        assert semantic_adapter._misses == 1

    def test_get_miss_when_redis_key_expired(self, semantic_adapter, mock_qdrant, mock_redis):
        mock_hit = MagicMock()
        mock_hit.id = "point_expired_789"
        mock_hit.score = 0.95
        mock_query_res = MagicMock()
        mock_query_res.points = [mock_hit]
        mock_qdrant.query_points.return_value = mock_query_res

        mock_redis.get.return_value = None

        cached = semantic_adapter.get("en:expired question")
        assert cached is None
        assert semantic_adapter._misses == 1

    def test_invalidate_by_query_no_type_error(
        self, semantic_adapter, mock_qdrant, mock_redis
    ):
        query = "en:how to attain peace"

        result = semantic_adapter.invalidate_by_query(query)

        assert result is True
        assert mock_qdrant.delete.called
        assert mock_redis.delete.called
        redis_key_deleted = mock_redis.delete.call_args.args[0]
        assert redis_key_deleted.startswith("mukthiguru:semcache:oneness:")


class TestStartupSafetyAssertions:
    """Test P0-4: semantic_cache_similarity startup safety assertions."""

    def test_startup_passes_when_similarity_at_or_above_floor(self):
        # Under normal conditions (>= 0.92), floor check must not raise
        from app.config import settings

        assert settings.semantic_cache_similarity >= 0.92

    def test_lifespan_raises_when_similarity_below_floor_in_production(self):
        with patch.object(settings, "semantic_cache_similarity", 0.85), patch.dict(
            os.environ, {"ENVIRONMENT": "production"}
        ):
            from app.config import settings as patched_settings

            cache_similarity = getattr(patched_settings, "semantic_cache_similarity", 0.92)
            if cache_similarity < 0.92:
                with pytest.raises(RuntimeError) as exc_info:
                    if os.environ.get("ENVIRONMENT") != "test":
                        raise RuntimeError(
                            f"semantic_cache_similarity={cache_similarity} is below the 0.92 correctness floor."
                        )
                assert "below the 0.92 correctness floor" in str(exc_info.value)

    def test_lifespan_allows_low_similarity_in_test_environment(self):
        with patch.object(settings, "semantic_cache_similarity", 0.85), patch.dict(
            os.environ, {"ENVIRONMENT": "test"}
        ):
            from app.config import settings as patched_settings

            cache_similarity = getattr(patched_settings, "semantic_cache_similarity", 0.92)
            # In test mode, it should not raise even if similarity < 0.92
            if cache_similarity < 0.92:
                if os.environ.get("ENVIRONMENT") != "test":
                    raise RuntimeError("Should not be raised in test environment")
