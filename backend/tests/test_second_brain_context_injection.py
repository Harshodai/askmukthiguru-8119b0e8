"""prepare_user_memory()'s Second Brain merge (app/orchestrator_utils.py).

Covers the three branches added for context injection: successful Mode-A
recall gets merged into memory_context, a Mode-B (owner-blind) vault is
skipped silently (no crash, no leak), and container.second_brain being
absent leaves the existing memory_service-only behavior untouched.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.orchestrator_utils import prepare_user_memory
from services.second_brain.crypto import UnlockedVault, VaultLockedError
from services.second_brain.second_brain_service import BrainItem


def _base_container():
    """container.user_profile truthy is required just to get past
    prepare_user_memory's very first guard (`if not container.user_profile:
    return "", []`) — it is unrelated to what this file tests, so it's wired
    with harmless no-op fakes rather than skipped."""
    container = MagicMock()
    container.user_profile.get_or_create_profile = AsyncMock(
        return_value=MagicMock(total_conversations=0)
    )
    container.user_profile.update_profile = AsyncMock(return_value=None)
    container.user_profile.get_recent_memories = AsyncMock(return_value=[])
    container.memory_service = None  # skip the unrelated memory_service branch
    return container


def test_second_brain_recall_merges_into_memory_context():
    container = _base_container()
    vault = UnlockedVault.from_dek(b"k" * 32)
    container.second_brain = MagicMock()
    container.second_brain.unlock = AsyncMock(return_value=vault)
    container.second_brain.personal_context = AsyncMock(
        return_value=[BrainItem(id="1", user_id="u1", kind="reflection",
                                 text="User is preparing for a job interview.",
                                 confidence=0.9, created_at=0.0)]
    )

    memory_context, _ = asyncio.run(
        prepare_user_memory(container, "u1", [{"role": "user", "content": "how do I stay calm?"}])
    )

    assert "job interview" in memory_context
    container.second_brain.unlock.assert_awaited_once_with("u1")


def test_second_brain_mode_b_vault_skipped_silently():
    container = _base_container()
    container.second_brain = MagicMock()
    container.second_brain.unlock = AsyncMock(side_effect=VaultLockedError("passphrase required"))

    memory_context, _ = asyncio.run(
        prepare_user_memory(container, "u2", [{"role": "user", "content": "hello"}])
    )

    assert "YOUR SECOND BRAIN" not in memory_context  # no crash, nothing leaked, nothing fabricated


def test_no_second_brain_service_leaves_existing_behavior_untouched():
    container = _base_container()
    container.second_brain = None

    memory_context, distress_history = asyncio.run(
        prepare_user_memory(container, "u3", [{"role": "user", "content": "hello"}])
    )

    assert "YOUR SECOND BRAIN" not in memory_context
    assert distress_history == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
