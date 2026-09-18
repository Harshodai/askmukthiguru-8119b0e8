"""PII scrubbing gap fix (System Design for the LLM Era book cross-check).

PIIScrubber previously only ever wrapped the telemetry-logging path
(telemetry_sink.py/telemetry_db.py). prepare_user_memory() -- the single
place memory_context is assembled before it's interpolated into a live
prompt (rag/nodes/generation.py:792) -- had no scrubbing anywhere in its
chain, so a phone number or email a seeker typed once and that got
fact-extracted into memory could resurface unfiltered in a later prompt.

Covers the same Second Brain merge path as test_second_brain_context_injection.py
but with PII-shaped recalled text, asserting the final memory_context returned
to the caller is scrubbed regardless of which memory source produced it.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.orchestrator_utils import _scrub_memory_context, prepare_user_memory
from services.second_brain.crypto import UnlockedVault
from services.second_brain.second_brain_service import BrainItem


def _base_container():
    container = MagicMock()
    container.user_profile.get_or_create_profile = AsyncMock(
        return_value=MagicMock(total_conversations=0)
    )
    container.user_profile.update_profile = AsyncMock(return_value=None)
    container.user_profile.get_recent_memories = AsyncMock(return_value=[])
    container.memory_service = None
    return container


def test_scrub_memory_context_redacts_email_and_phone():
    raw = "Reach the seeker at seeker@example.com or 555-123-4567 about their practice."
    scrubbed = _scrub_memory_context(raw)
    assert "seeker@example.com" not in scrubbed
    assert "555-123-4567" not in scrubbed
    assert "[EMAIL]" in scrubbed
    assert "[PHONE]" in scrubbed


def test_scrub_memory_context_passthrough_for_empty():
    assert _scrub_memory_context("") == ""
    assert _scrub_memory_context(None) is None


def test_prepare_user_memory_scrubs_second_brain_pii():
    container = _base_container()
    vault = UnlockedVault.from_dek(b"k" * 32)
    container.second_brain = MagicMock()
    container.second_brain.unlock = AsyncMock(return_value=vault)
    container.second_brain.personal_context = AsyncMock(
        return_value=[
            BrainItem(
                id="1",
                user_id="u1",
                kind="reflection",
                text="Contact me at leaked@example.com before our next session.",
                confidence=0.9,
                created_at=0.0,
            )
        ]
    )

    memory_context, _, _, _ = asyncio.run(
        prepare_user_memory(
            container,
            "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6",
            [{"role": "user", "content": "how do I stay calm?"}],
        )
    )

    assert "leaked@example.com" not in memory_context
    assert "[EMAIL]" in memory_context


if __name__ == "__main__":
    test_scrub_memory_context_redacts_email_and_phone()
    test_scrub_memory_context_passthrough_for_empty()
    test_prepare_user_memory_scrubs_second_brain_pii()
    print("OK")
