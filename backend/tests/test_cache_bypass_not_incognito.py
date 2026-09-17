"""cache_bypass is an evaluation control; incognito is a privacy boundary.

Every quality harness used `incognito=True` to force a cold path
(`ragas_eval.py:288` says so in its own cache_policy string), and
`memory_stage.py` skips the memory layer on that same flag. So a run
configured for "no cache, end to end, including memory" measured a system with
memory switched off and reported healthy faithfulness while doing it.

These tests pin the separation: bypassing the cache must not suppress memory,
and going incognito must still suppress everything.
"""

from __future__ import annotations

import pathlib

from app.pipeline.stages.context import PipelineContext
from app.schemas import ChatRequest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


def test_request_carries_cache_bypass_independently_of_incognito():
    req = ChatRequest(messages=[], user_message="q", cache_bypass=True)
    assert req.cache_bypass is True
    assert req.incognito is False, "cache_bypass must not imply incognito"


def test_context_defaults_keep_both_off():
    ctx = PipelineContext(container=None, coordinator=None, request=None)
    assert ctx.cache_bypass is False
    assert ctx.incognito is False


def test_a_mock_request_does_not_silently_opt_into_cache_bypass():
    """getattr(MagicMock(), "x", False) returns a truthy Mock, never the
    default — so bool() on it would read as an opt-in and disable the cache
    for every Mock-based test. The coordinator must compare identity."""
    src = (_BACKEND / "app" / "pipeline" / "pipeline_coordinator.py").read_text()
    assert 'getattr(chat_body, "cache_bypass", False) is True' in src, (
        "cache_bypass must be read with an identity check, not bool()"
    )


def test_cache_stage_checks_bypass_on_both_read_and_write():
    """A bypass that only skips the read would serve cold and then poison the
    cache with an eval answer, so the write side must check it too."""
    src = (_BACKEND / "app" / "pipeline" / "stages" / "cache_stage.py").read_text()
    assert src.count("ctx.cache_bypass") >= 2, (
        "cache_bypass must gate both the read (CacheCheckStage) and the write (CacheUpdateStage)"
    )


def test_memory_stage_does_not_key_on_cache_bypass():
    """The whole point: a cold run must still exercise the memory layer."""
    src = (_BACKEND / "app" / "pipeline" / "stages" / "memory_stage.py").read_text()
    assert "cache_bypass" not in src, (
        "memory_stage must not consult cache_bypass — bypassing the cache is "
        "not a reason to skip memory, and conflating them is the defect this "
        "test exists to prevent"
    )


def test_memory_stage_still_honours_incognito():
    """Separating the flags must not weaken the privacy boundary."""
    src = (_BACKEND / "app" / "pipeline" / "stages" / "memory_stage.py").read_text()
    assert "ctx.incognito" in src, "incognito must still suppress memory persistence"


def test_coordinator_wires_cache_bypass_from_the_request():
    src = (_BACKEND / "app" / "pipeline" / "pipeline_coordinator.py").read_text()
    assert "cache_bypass=getattr(chat_body" in src, (
        "an unwired field is a flag that silently does nothing"
    )


if __name__ == "__main__":
    test_request_carries_cache_bypass_independently_of_incognito()
    test_context_defaults_keep_both_off()
    test_cache_stage_checks_bypass_on_both_read_and_write()
    test_memory_stage_does_not_key_on_cache_bypass()
    test_memory_stage_still_honours_incognito()
    test_coordinator_wires_cache_bypass_from_the_request()
    print("cache_bypass separation holds")
