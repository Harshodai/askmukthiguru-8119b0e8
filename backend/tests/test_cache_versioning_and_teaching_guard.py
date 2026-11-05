"""Unit tests for T7-04 / CQ-003: cache key versioning and teaching answer guards."""

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages.cache_stage import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.context import PipelineContext
from app.release_manifest import ReleaseManifest, set_release_manifest


def _test_manifest():
    return ReleaseManifest(
        release_id="rel-2026-11-05-A",
        git_sha="0123456789abcdef0123456789abcdef01234567",
        build_timestamp="2026-11-05T00:00:00Z",
        corpus_version="v10",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="policy-v1",
        schema_version="1.0.0",
    )


def test_collection_switch_invalidates_cache_key():
    set_release_manifest(_test_manifest())
    coordinator = PipelineCoordinator(MagicMock())

    orig_collection = settings.first_person_collection
    try:
        settings.first_person_collection = "first_person_v10"
        key_v10 = coordinator._build_context_aware_cache_key("What is meditation?", "en")

        settings.first_person_collection = "first_person_v11"
        key_v11 = coordinator._build_context_aware_cache_key("What is meditation?", "en")

        assert key_v10 != key_v11
        assert ":col:first_person_v10:" in key_v10
        assert ":col:first_person_v11:" in key_v11
    finally:
        settings.first_person_collection = orig_collection


def test_prompt_and_cache_version_change_invalidates_cache_key():
    set_release_manifest(_test_manifest())
    coordinator = PipelineCoordinator(MagicMock())

    orig_cv = settings.cache_key_version
    orig_pv = settings.prompt_version
    try:
        settings.cache_key_version = "v2"
        settings.prompt_version = "v1"
        key_1 = coordinator._build_context_aware_cache_key("What is suffering?", "en")

        settings.cache_key_version = "v3"
        key_2 = coordinator._build_context_aware_cache_key("What is suffering?", "en")

        settings.prompt_version = "v2"
        key_3 = coordinator._build_context_aware_cache_key("What is suffering?", "en")

        assert key_1 != key_2
        assert key_2 != key_3
        assert ":cv:v2" in key_1
        assert ":cv:v3" in key_2
        assert ":pv:v2" in key_3
    finally:
        settings.cache_key_version = orig_cv
        settings.prompt_version = orig_pv


@pytest.mark.asyncio
async def test_teaching_answer_not_written_to_semantic_cache():
    container = MagicMock()
    container.exact_cache = MagicMock()
    container.exact_cache.put = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    container.semantic_cache.put = MagicMock()

    coordinator = PipelineCoordinator(container)
    coordinator.coalescer = MagicMock()

    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="What is oneness?",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-1",
        start_time=0.0,
        cache_key="ck:en:what is oneness",
        query_for_embedding="what is oneness",
        is_indic=False,
        user_id="user-1",
        stable_session_id="sess-1",
        chat_body_messages=[],
        state={"user_msg_en": "what is oneness", "chat_history_en": [], "memory_context": ""},
        final_answer="Oneness is experiencing the interconnectedness of all life.",
        intent="QUERY",
        med_step=0,
        citations=[{"id": "c1", "source_url": "u1", "score": 0.95}],
        route_metadata={"fp_served": True},
        graph_result={"is_faithful": True, "faithfulness_score": 0.98},
    )

    await CacheUpdateStage().run(ctx)

    # Exact cache is written with composite key
    container.exact_cache.put.assert_called_once()
    # Semantic cache MUST NOT be written for teaching answers (CQ-003)
    container.semantic_cache.put.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_cache_hit_with_teaching_is_discarded():
    container = MagicMock()
    container.exact_cache = MagicMock()
    container.exact_cache.get = MagicMock(return_value=None)
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    # Simulate a legacy or poisoned entry in semantic cache that claims to be fp_served
    container.semantic_cache.get = MagicMock(
        return_value={
            "response": "Verbatim teacher quote.",
            "intent": "QUERY",
            "citations": [{"id": "c1"}],
            "route_metadata": {"fp_served": True},
        }
    )

    coordinator = PipelineCoordinator(container)
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="What is freedom?",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-1",
        start_time=0.0,
        cache_key="ck:en:what is freedom",
        query_for_embedding="what is freedom",
        is_indic=False,
        user_id="user-1",
        stable_session_id="sess-1",
        chat_body_messages=[],
        state={"user_msg_en": "what is freedom", "chat_history_en": [], "memory_context": ""},
    )

    stage = CacheCheckStage()
    result = await stage.run(ctx)

    # The semantic cache hit MUST be discarded (treated as miss)
    assert result is None
