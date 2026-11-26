"""The canonical-memory branch of prepare_user_memory must not call a method
UserProfileService does not have.

Live 2026-11-19: every signed-in turn that served canonical memory logged
"Failed to fetch user profile alongside canonical memory: 'UserProfileService'
object has no attribute 'get_distress_history'".
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app import orchestrator_utils
from services.user_profile_service import UserProfile


class _Profiles:
    """Only the methods the real UserProfileService has."""

    def __init__(self) -> None:
        self.profile = UserProfile(
            user_id="11111111-1111-1111-1111-111111111111", created_at=0.0, updated_at=0.0
        )

    async def get_or_create_profile(self, user_id: str) -> UserProfile:
        return self.profile

    async def update_profile(self, profile: UserProfile) -> None:
        return None


class _Consent:
    async def active_consent(self, *, user_id: str, tenant_id: str) -> dict:
        return {"id": "receipt"}


class _Canonical:
    async def prepare_context(self, **_kw) -> str:
        return "SEEKER-STATED FACTS:\n- prefers mornings"


@pytest.mark.asyncio
async def test_canonical_branch_returns_profile_without_warning(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.pipeline.stages.off_topic_stage.should_skip_long_term_memory", lambda _q: False
    )
    container = SimpleNamespace(
        memory_outbox=_Consent(),
        second_brain=None,
        canonical_memory_integration=_Canonical(),
        user_profile=_Profiles(),
    )
    with caplog.at_level(logging.WARNING):
        _ctx, history, profile, block = await orchestrator_utils.prepare_user_memory(
            container,
            "11111111-1111-1111-1111-111111111111",
            [{"role": "user", "content": "how do I sleep better"}],
            user_msg_en="how do I sleep better",
        )
    assert block.startswith("SEEKER-STATED FACTS")
    assert profile is container.user_profile.profile
    assert history == []
    assert "alongside canonical memory" not in caplog.text
