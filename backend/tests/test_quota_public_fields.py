"""UX-011: the client learns the remaining free turns before the limit, never for signed-in users."""

from app.api.chat import quota_headers, quota_public_fields
from services.anon_quota_port import QuotaResult


def test_anonymous_reservation_exposes_remaining_and_limit():
    q = QuotaResult(allowed=True, remaining=4, total_limit=5, reservation_id="r1")
    assert quota_public_fields(q) == {"remaining": 4, "limit": 5}
    assert quota_headers(q) == {"X-Quota-Remaining": "4", "X-Quota-Limit": "5"}


def test_no_reservation_means_no_counter():
    q = QuotaResult(allowed=True, remaining=0, total_limit=0, reservation_id=None)
    assert quota_public_fields(q) is None
    assert quota_headers(q) == {}


def test_remaining_never_negative():
    q = QuotaResult(allowed=True, remaining=-1, total_limit=5, reservation_id="r")
    assert quota_public_fields(q)["remaining"] == 0
