"""The write path: extract facts from a turn, judge them, resolve the keepers.

Wired 2026-09-13. Three properties matter and each has bitten this codebase
before:

  - it runs behind the SAME consent gate the legacy outbox uses, because
    inferring durable facts about a seeker from their words is exactly what
    consent governs;
  - it cannot add latency to a reply that has already been produced;
  - the fire-and-forget task holds a strong reference, because an asyncio task
    with no reference can be collected before it runs and the write vanishes.
"""

import inspect

from app.config import Settings
from app.pipeline.stages import memory_stage


def test_write_flag_is_on_and_bounded():
    s = Settings()
    assert s.memory_write is True
    assert 0 < s.canonical_memory_write_timeout <= 60


def test_container_wires_extractor_judge_and_resolver_when_enabled():
    src = inspect.getsource(__import__("app.container", fromlist=["x"]))
    assert "if settings.memory_write:" in src
    assert "extract_memory_candidates" in src
    assert "MemoryJudge()" in src
    assert "MemoryResolver(" in src
    # The integration calls extractor(turns=...), the extractor's own signature
    # is (conversation_id, conversation_window, ...) — an adapter is required.
    assert "async def _cm_extract" in src
    assert "conversation_window=turns" in src


def test_write_runs_after_the_consent_gate():
    src = inspect.getsource(memory_stage.MemoryStage.run)
    consent_at = src.find("active_consent")
    write_at = src.find("post_response_memory")
    assert consent_at != -1 and write_at != -1
    assert consent_at < write_at, (
        "extraction must not run for a seeker who has not consented to memory"
    )


def test_write_is_non_blocking_and_bounded():
    src = inspect.getsource(memory_stage.MemoryStage.run)
    assert "create_task(" in src
    assert "canonical_memory_write_timeout" in src


def test_inflight_task_is_strongly_referenced():
    assert isinstance(memory_stage._CANONICAL_WRITE_TASKS, set)
    src = inspect.getsource(memory_stage.MemoryStage.run)
    assert "_CANONICAL_WRITE_TASKS.add(" in src
    assert "add_done_callback(_CANONICAL_WRITE_TASKS.discard)" in src


def test_write_failure_cannot_fail_the_turn():
    src = inspect.getsource(memory_stage.MemoryStage.run)
    _, _, tail = src.partition("post_response_memory")
    assert "except Exception" in tail
