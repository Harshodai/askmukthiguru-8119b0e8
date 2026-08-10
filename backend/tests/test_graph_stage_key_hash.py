"""P1-BE-7: graph-stage coalesce key must not embed raw user text.

The coalesce key previously interpolated ``user_msg_en`` verbatim — unbounded,
potentially PII-bearing, and locale-duplicating. It now carries a bounded
SHA-256 digest (first 16 hex chars) of the message.
"""

import hashlib

import pytest

from app.pipeline.stages.graph_stage import _coalesce_key


def test_key_contains_no_raw_user_text():
    msg = "my deepest private concern is visible in cache keys"
    key = _coalesce_key("user-1", "sess-1", "en", msg, "abc12345")
    assert msg not in key
    assert "deepest" not in key
    assert "visible" not in key


def test_key_is_bounded_regardless_of_message_length():
    long_msg = "x" * 100_000
    key = _coalesce_key("user-1", "sess-1", "en", long_msg, "abc12345")
    # user_id:session_id:lang:16-hex-digest:8-hex-history  — far below 10k
    assert len(key) < 200
    assert len(long_msg) > len(key)


def test_key_is_deterministic():
    k1 = _coalesce_key("user-1", "sess-1", "en", "breath awareness", "abc12345")
    k2 = _coalesce_key("user-1", "sess-1", "en", "breath awareness", "abc12345")
    assert k1 == k2


def test_key_differs_by_message():
    k1 = _coalesce_key("user-1", "sess-1", "en", "breath awareness", "abc12345")
    k2 = _coalesce_key("user-1", "sess-1", "en", "breath awareness 2", "abc12345")
    assert k1 != k2


def test_digest_matches_sha256_of_message():
    msg = "what is samadhi"
    expected = hashlib.sha256(msg.encode("utf-8")).hexdigest()[:16]
    key = _coalesce_key("user-1", "sess-1", "en", msg, "abc12345")
    assert expected in key
