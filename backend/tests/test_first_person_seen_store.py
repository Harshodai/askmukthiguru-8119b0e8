"""Unit tests for authoritative server-side seen-clip tracking (MEM-002 / D-PM4)."""

from unittest.mock import MagicMock

import pytest

from app.config import Settings
from services.first_person_seen_store import (
    _LOCAL_STORE,
    clear_seen_clips,
    get_seen_clips,
    record_seen_clip,
)


@pytest.fixture(autouse=True)
def clean_local_store():
    _LOCAL_STORE.clear()
    yield
    _LOCAL_STORE.clear()


def test_first_person_server_seen_clips_disabled_by_default():
    settings = Settings()
    assert settings.first_person_server_seen_clips_enabled is False


def test_record_and_get_seen_clips_in_memory():
    user_id = "user_123"
    tenant_id = "tenant_abc"

    assert record_seen_clip(user_id=user_id, tenant_id=tenant_id, clip_id="clip_1", video_id="vid_A")
    clips, videos = get_seen_clips(user_id=user_id, tenant_id=tenant_id)

    assert "clip_1" in clips
    assert "vid_A" in videos


def test_user_and_tenant_isolation():
    record_seen_clip(user_id="user_1", tenant_id="tenant_1", clip_id="clip_1", video_id="vid_1")
    record_seen_clip(user_id="user_2", tenant_id="tenant_1", clip_id="clip_2", video_id="vid_2")
    record_seen_clip(user_id="user_1", tenant_id="tenant_2", clip_id="clip_3", video_id="vid_3")

    c1, v1 = get_seen_clips(user_id="user_1", tenant_id="tenant_1")
    assert c1 == {"clip_1"}
    assert v1 == {"vid_1"}

    c2, v2 = get_seen_clips(user_id="user_2", tenant_id="tenant_1")
    assert c2 == {"clip_2"}
    assert v2 == {"vid_2"}

    c3, v3 = get_seen_clips(user_id="user_1", tenant_id="tenant_2")
    assert c3 == {"clip_3"}
    assert v3 == {"vid_3"}


def test_input_sanitization():
    # Disallowed characters in user_id, tenant_id, clip_id, video_id
    assert not record_seen_clip(user_id="bad user with spaces", tenant_id="tenant_1", clip_id="clip_1")
    assert not record_seen_clip(user_id="user_1", tenant_id="bad;tenant", clip_id="clip_1")
    assert not record_seen_clip(user_id="user_1", tenant_id="tenant_1", clip_id="clip\nmalicious")
    assert not record_seen_clip(user_id="user_1", tenant_id="tenant_1", clip_id="", video_id=None)

    # Empty lookup on invalid user
    c, v = get_seen_clips(user_id="bad id!", tenant_id="tenant_1")
    assert c == set()
    assert v == set()


def test_fail_open_on_redis_error():
    broken_redis = MagicMock()
    broken_redis.pipeline.side_effect = RuntimeError("Redis connection lost")
    broken_redis.smembers.side_effect = RuntimeError("Redis connection lost")

    # Write fails gracefully returning False without raising
    assert not record_seen_clip(
        user_id="user_1",
        tenant_id="tenant_1",
        clip_id="clip_1",
        redis_client=broken_redis,
    )

    # Read fails gracefully returning empty sets without raising
    c, v = get_seen_clips(
        user_id="user_1",
        tenant_id="tenant_1",
        redis_client=broken_redis,
    )
    assert c == set()
    assert v == set()


def test_clear_seen_clips():
    record_seen_clip(user_id="user_1", tenant_id="default", clip_id="clip_1", video_id="vid_1")
    c, v = get_seen_clips(user_id="user_1", tenant_id="default")
    assert len(c) == 1

    assert clear_seen_clips(user_id="user_1", tenant_id="default")
    c_after, v_after = get_seen_clips(user_id="user_1", tenant_id="default")
    assert c_after == set()
    assert v_after == set()
