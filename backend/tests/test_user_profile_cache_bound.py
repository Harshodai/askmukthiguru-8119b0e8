"""Regression test for the unbounded-cache memory leak (lessons.md RULE 41).

UserProfileService._local_cache / _conversation_cache are process-wide
singleton dicts written on every chat turn. Before this fix they were plain
dicts with no eviction — this asserts the caches are actually bounded now.
"""

import time

from services.user_profile_service import ConversationMemory, UserProfile, UserProfileService


def test_local_cache_is_bounded():
    svc = UserProfileService(supabase_client=None)
    maxsize = svc._local_cache.maxsize

    for i in range(maxsize + 50):
        user_id = f"anon:{i}"
        svc._local_cache[user_id] = UserProfile(
            user_id=user_id, created_at=time.time(), updated_at=time.time()
        )

    assert len(svc._local_cache) <= maxsize


def test_conversation_cache_is_bounded():
    svc = UserProfileService(supabase_client=None)
    maxsize = svc._conversation_cache.maxsize

    for i in range(maxsize + 50):
        session_id = f"session-{i}"
        svc._conversation_cache[session_id] = ConversationMemory(
            session_id=session_id,
            user_id="anonymous",
            started_at=time.time(),
            messages=[],
            key_insights=[],
            emotional_arc=[],
            follow_up_suggestions=[],
        )

    assert len(svc._conversation_cache) <= maxsize


if __name__ == "__main__":
    test_local_cache_is_bounded()
    test_conversation_cache_is_bounded()
    print("OK")
