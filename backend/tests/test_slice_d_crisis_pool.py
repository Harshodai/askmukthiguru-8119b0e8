"""Slice D — crisis admission pool hardening (RP-A2 follow-up).

Covers what test_chat_backpressure.py does not: the crisis pool itself is
BOUNDED (same per-worker cap as the ordinary pool) and its overflow path
admits WITHOUT a slot instead of shedding (the "never-shed" invariant).

Non-tautology notes:
- The bounded assertion reads the live semaphore's internal ``_value``
  against the live ``settings.max_concurrent_chat`` (not a constant).
- The overflow test holds a real crisis slot, forces a second crisis
  admission through the 0.05 s pool timeout, and asserts the admitted shape
  ``(None, None)`` — no 503 — plus the bypass counter moved by exactly 2.
- The independence test saturates the ORDINARY pool and proves a crisis
  admission still takes a crisis-pool slot (separate pool, not shared).
- Every admission is wrapped in ``asyncio.wait_for`` (bounded waits only).
"""

from __future__ import annotations

import asyncio

import pytest

import app.api.chat as chat_mod
from app.config import settings
from app.schemas import ChatRequest

CRISIS_MESSAGE = "I am thinking about suicide and want to end my life"
GENERIC_MESSAGE = "What is mindfulness?"


def _reset(monkeypatch) -> None:
    monkeypatch.setattr(chat_mod, "_chat_semaphore", None)
    monkeypatch.setattr(chat_mod, "_chat_semaphore_loop", None)
    monkeypatch.setattr(chat_mod, "_crisis_semaphore", None)
    monkeypatch.setattr(chat_mod, "_crisis_semaphore_loop", None)


@pytest.mark.asyncio
async def test_crisis_pool_is_bounded_to_the_configured_cap(monkeypatch):
    """The crisis pool is a real bound, not an unbounded bypass."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 3)
    _reset(monkeypatch)
    sem = chat_mod._get_crisis_semaphore()
    assert sem._value == settings.max_concurrent_chat == 3
    # Same loop -> same pool object (no per-call fresh semaphore).
    assert chat_mod._get_crisis_semaphore() is sem


@pytest.mark.asyncio
async def test_exhausted_crisis_pool_admits_without_slot_never_sheds(monkeypatch):
    """Pool-full crisis overflow: admitted, slotless, never a 503."""
    from app.metrics import CRISIS_BYPASS_TOTAL

    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset(monkeypatch)
    before = CRISIS_BYPASS_TOTAL._value.get()

    first_slot, first_shed = await asyncio.wait_for(
        chat_mod._admit_chat(ChatRequest(messages=[], user_message=CRISIS_MESSAGE)),
        timeout=10,
    )
    assert first_shed is None
    assert first_slot is not None  # pool had room: real slot held
    try:
        # Pool now exhausted: the second crisis admission must ride out the
        # 0.05 s pool timeout and come back slotless-but-admitted.
        slot, shed = await asyncio.wait_for(
            chat_mod._admit_chat(ChatRequest(messages=[], user_message=CRISIS_MESSAGE)),
            timeout=10,
        )
        assert shed is None, "exhausted crisis pool must never 503-shed"
        assert slot is None, "overflow admission holds no pool slot"
        assert CRISIS_BYPASS_TOTAL._value.get() == before + 2
    finally:
        first_slot.release()

    # Pool recovered: the next crisis admission takes a real slot again.
    slot3, shed3 = await asyncio.wait_for(
        chat_mod._admit_chat(ChatRequest(messages=[], user_message=CRISIS_MESSAGE)),
        timeout=10,
    )
    assert shed3 is None and slot3 is not None
    slot3.release()


@pytest.mark.asyncio
async def test_crisis_pool_is_independent_from_the_ordinary_pool(monkeypatch):
    """A saturated ordinary pool sheds generic traffic but not crisis traffic,
    and the crisis admission holds a crisis-pool slot (not the ordinary one)."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset(monkeypatch)
    ordinary = chat_mod._get_chat_semaphore()
    await ordinary.acquire()
    try:
        crisis_slot, crisis_shed = await asyncio.wait_for(
            chat_mod._admit_chat(ChatRequest(messages=[], user_message=CRISIS_MESSAGE)),
            timeout=10,
        )
        assert crisis_shed is None
        assert crisis_slot is not None
        assert crisis_slot is chat_mod._get_crisis_semaphore()
        assert ordinary.locked(), "ordinary pool must still be saturated"

        generic_slot, generic_shed = await asyncio.wait_for(
            chat_mod._admit_chat(ChatRequest(messages=[], user_message=GENERIC_MESSAGE)),
            timeout=10,
        )
        assert generic_slot is None
        assert generic_shed is not None and generic_shed.status_code == 503
        crisis_slot.release()
    finally:
        ordinary.release()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
