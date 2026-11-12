"""Server-side authoritative seen-clip tracking (MEM-002 / D-PM4 / T6-02).

Tracks served first-person clips per (tenant_id, user_id) to promote clip diversity
for returning seekers without relying on client-supplied state or altering quote text.

Features:
- Strict tenant and user isolation: keys are namespaced `fp_seen:{tenant_id}:{user_id}:*`
- Retention TTL: 90 days per D-PM4 retention policy, bounded storage
- Input sanitization: opaque IDs only, alphanumeric/hyphen/underscore validation
- Fail-open: any storage exception, timeout, or missing connection returns empty sets
- Local fallback store for testing and disconnected environments
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# D-PM4 proposed retention: 90 days for learning/seen events
SEEN_CLIPS_TTL_SECONDS = 90 * 86400
MAX_SEEN_ITEMS = 500

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\:]{1,128}$")

try:
    import redis

    _REDIS_ERRORS: tuple[type[BaseException], ...] = (
        redis.RedisError,
        RuntimeError,
        OSError,
        ConnectionError,
        TimeoutError,
        ValueError,
        KeyError,
        AttributeError,
    )
except ImportError:
    _REDIS_ERRORS = (
        RuntimeError,
        OSError,
        ConnectionError,
        TimeoutError,
        ValueError,
        KeyError,
        AttributeError,
    )

# In-memory fallback cache for testing / redis-less environments
_LOCAL_STORE: dict[str, set[str]] = {}


def _is_safe_id(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    return bool(_SAFE_ID_RE.match(value.strip()))


def _clip_key(tenant_id: str, user_id: str) -> str:
    return f"fp_seen:{tenant_id}:{user_id}:clips"


def _video_key(tenant_id: str, user_id: str) -> str:
    return f"fp_seen:{tenant_id}:{user_id}:videos"


def record_seen_clip(
    user_id: str,
    tenant_id: str = "default",
    clip_id: str | None = None,
    video_id: str | None = None,
    redis_client: Any = None,
) -> bool:
    """Record a served clip and video ID for the given user.

    Returns True on success, False on invalid input or failure. Never raises.
    """
    if not _is_safe_id(user_id) or not _is_safe_id(tenant_id):
        return False

    valid_clip = clip_id.strip() if _is_safe_id(clip_id) else None
    valid_video = video_id.strip() if _is_safe_id(video_id) else None

    if not valid_clip and not valid_video:
        return False

    c_key = _clip_key(tenant_id, user_id)
    v_key = _video_key(tenant_id, user_id)

    if redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            if valid_clip:
                pipe.sadd(c_key, valid_clip)
                pipe.expire(c_key, SEEN_CLIPS_TTL_SECONDS)
            if valid_video:
                pipe.sadd(v_key, valid_video)
                pipe.expire(v_key, SEEN_CLIPS_TTL_SECONDS)
            pipe.execute()
            return True
        except _REDIS_ERRORS as exc:
            logger.debug("[FirstPersonSeenStore] redis write error (fail-open): %s", exc)
            return False

    # In-memory fallback
    if valid_clip:
        _LOCAL_STORE.setdefault(c_key, set()).add(valid_clip)
    if valid_video:
        _LOCAL_STORE.setdefault(v_key, set()).add(valid_video)
    return True


def get_seen_clips(
    user_id: str,
    tenant_id: str = "default",
    redis_client: Any = None,
) -> tuple[set[str], set[str]]:
    """Return (seen_clip_ids, seen_video_ids) for a user.

    Returns empty sets on invalid user, missing client, or error. Never raises.
    """
    if not _is_safe_id(user_id) or not _is_safe_id(tenant_id):
        return set(), set()

    c_key = _clip_key(tenant_id, user_id)
    v_key = _video_key(tenant_id, user_id)

    if redis_client is not None:
        try:
            raw_clips = redis_client.smembers(c_key) or set()
            raw_videos = redis_client.smembers(v_key) or set()
            clips = {
                c.decode("utf-8") if isinstance(c, bytes) else str(c)
                for c in raw_clips
                if _is_safe_id(c.decode("utf-8") if isinstance(c, bytes) else str(c))
            }
            videos = {
                v.decode("utf-8") if isinstance(v, bytes) else str(v)
                for v in raw_videos
                if _is_safe_id(v.decode("utf-8") if isinstance(v, bytes) else str(v))
            }
            return clips, videos
        except _REDIS_ERRORS as exc:
            logger.debug("[FirstPersonSeenStore] redis read error (fail-open): %s", exc)
            return set(), set()

    # In-memory fallback
    clips = set(_LOCAL_STORE.get(c_key) or set())
    videos = set(_LOCAL_STORE.get(v_key) or set())
    return clips, videos


def clear_seen_clips(
    user_id: str,
    tenant_id: str = "default",
    redis_client: Any = None,
) -> bool:
    """Clear seen clips for erasure / reset."""
    if not _is_safe_id(user_id) or not _is_safe_id(tenant_id):
        return False

    c_key = _clip_key(tenant_id, user_id)
    v_key = _video_key(tenant_id, user_id)

    if redis_client is not None:
        try:
            redis_client.delete(c_key, v_key)
            return True
        except _REDIS_ERRORS as exc:
            logger.debug("[FirstPersonSeenStore] redis delete error: %s", exc)
            return False

    _LOCAL_STORE.pop(c_key, None)
    _LOCAL_STORE.pop(v_key, None)
    return True
