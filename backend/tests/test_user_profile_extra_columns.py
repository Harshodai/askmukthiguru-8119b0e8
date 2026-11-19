"""A user_profiles row with columns the dataclass does not model must still load (production has tenant_id)."""

import asyncio
import uuid
from unittest.mock import MagicMock

from services.user_profile_service import LanguagePreference, UserProfileService


def _client_returning(row: dict) -> MagicMock:
    client = MagicMock()
    chain = client.table.return_value.select.return_value.eq.return_value
    chain.execute.return_value = MagicMock(data=[row])
    return client


def test_profile_loads_when_row_has_unmodelled_columns():
    user_id = str(uuid.uuid4())
    row = {
        "user_id": user_id,
        "preferred_language": "hi",
        "spiritual_level": "beginner",
        "topics_of_interest": ["meditation"],
        "total_conversations": 7,
        "created_at": 1.0,
        "updated_at": 2.0,
        "tenant_id": "oneness",  # the production column that used to raise TypeError
    }
    service = UserProfileService(supabase_client=_client_returning(row))

    profile = asyncio.run(service.get_or_create_profile(user_id))

    assert profile.user_id == user_id
    assert profile.preferred_language == LanguagePreference("hi")
    assert profile.total_conversations == 7  # the stored row was used, not a fresh default
    assert not hasattr(profile, "tenant_id")
