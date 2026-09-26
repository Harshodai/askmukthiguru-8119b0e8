"""Which routes get traced. The exclusion regex is inverted: only matches are skipped."""

import re

from app.observability import DEFAULT_FASTAPI_EXCLUDED_URLS

EXCLUDED = re.compile(DEFAULT_FASTAPI_EXCLUDED_URLS)


def test_serving_routes_are_traced():
    for url in (
        "http://x/api/chat",
        "http://x/api/chat/stream",
        "http://x/api/first-person/query",
    ):
        assert not EXCLUDED.search(url), url


def test_noise_routes_stay_excluded():
    for url in ("http://x/api/health", "http://x/api/metrics", "http://x/internal/metrics"):
        assert EXCLUDED.search(url), url
