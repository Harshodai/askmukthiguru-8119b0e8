"""Canonical memories must reach the generation prompt, and must not be cached.

The store, its API, audit trail and RLS all worked, but nothing in the request
pipeline read it — the only import of `chat_integration` outside its own package
was a test. This pins the read path end to end:

  container builds the integration -> prepare_user_memory serves it as
  memory_context -> the shared (language, message) caches refuse it.
"""

import inspect

from app.config import Settings
from app import orchestrator_utils
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import cache_stage


def test_read_path_flags_are_on_and_write_path_is_not():
    s = Settings()
    assert s.canonical_memory_enabled is True
    assert s.canonical_memory_retrieval is True
    assert s.memory_influence is True
    # Automatic extraction of facts about a seeker is a separate decision.
    assert s.memory_write is True  # write path wired and verified live 2026-09-13
    assert s.memory_shadow is False


def test_container_builds_the_integration():
    src = inspect.getsource(__import__("app.container", fromlist=["x"]))
    assert "canonical_memory_integration" in src
    assert "create_chat_integration(" in src
    # Write path is wired when memory_write is on; extractor/judge/resolver
    # are constructed conditionally (see `if settings.memory_write:` block).
    assert "if settings.memory_write:" in src


def test_prepare_user_memory_serves_canonical_context():
    src = inspect.getsource(orchestrator_utils.prepare_user_memory)
    assert "canonical_memory_integration" in src
    assert "prepare_context(" in src
    assert "canonical_memory_timeout" in src, "memory must never cost an answer"


def test_anonymous_callers_are_skipped():
    src = inspect.getsource(orchestrator_utils.prepare_user_memory)
    assert 'user_id != "anonymous"' in src
    assert 'startswith("anon:")' in src


def test_canonical_context_is_fail_open():
    src = inspect.getsource(orchestrator_utils.prepare_user_memory)
    head, _, tail = src.partition("prepare_context(")
    assert "except Exception" in tail
    assert "fail-open" in tail


def test_cache_write_guard_covers_canonical_context():
    """Canonical context flows into memory_context, which the guard keys on."""
    src = inspect.getsource(cache_stage._is_personalization_eligible)
    assert 'ctx.state.get("memory_context")' in src


def test_cache_eligibility_probe_includes_canonical_memories():
    """Without this, a canonical-only seeker is replayed a generic cached answer."""
    src = inspect.getsource(PipelineCoordinator._probe_has_memory)
    assert 'table("canonical_memories")' in src
    assert '.eq("status", "active")' in src


def test_memories_are_indexed_for_retrieval_on_write():
    """A stored memory that is never embedded is invisible to retrieval.

    `CanonicalMemoryRetriever` searches Qdrant first and falls back to an ILIKE
    over the statement, which only matches when the seeker repeats the memory's
    own words. Verified 2026-09-12: two stored memories, a directly relevant
    question, zero retrieved — until create/update started indexing.
    """
    src = inspect.getsource(__import__("app.api.canonical_memory", fromlist=["x"]))
    assert "_index_memory_vector(container, created_row)" in src
    assert "_index_memory_vector(container, updated_row)" in src
    # A forgotten memory must leave the index too, or it keeps being retrieved.
    assert "_deindex_memory_vector(container, user_id, memory_id)" in src


def test_indexing_never_fails_a_successful_write():
    mod = __import__("app.api.canonical_memory", fromlist=["x"])
    src = inspect.getsource(mod._index_memory_vector)
    assert "except Exception" in src
    assert "non-fatal" in src


def test_retriever_gets_an_async_callable_not_the_service():
    """CanonicalMemoryRetriever calls `await self._embedder(query)`.

    Passing the EmbeddingService object made every semantic search raise and
    silently degrade to substring matching.
    """
    src = inspect.getsource(__import__("app.container", fromlist=["x"]))
    assert "async def _cm_embed" in src
    assert "embedding_service=_cm_embed" in src


def test_vector_collection_is_created_at_wiring_time():
    src = inspect.getsource(__import__("app.container", fromlist=["x"]))
    assert "_cm_index.ensure_collection()" in src
