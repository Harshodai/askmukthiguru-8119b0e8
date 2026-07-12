"""Tests for CSP nonce generation and TTL rate limiter."""

import time

from app.security_utils import TTLRateLimiter, build_csp


class TestBuildCSP:
    def test_csp_includes_nonce(self):
        csp = build_csp("test-nonce-123")
        assert "'nonce-test-nonce-123'" in csp
        # script-src must use nonce, not unsafe-inline
        script_src = [p for p in csp.split(";") if p.strip().startswith("script-src")]
        assert script_src
        assert "'unsafe-inline'" not in script_src[0]
        assert "script-src" in csp

    def test_csp_static_directives_present(self):
        csp = build_csp("abc")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


class TestTTLRateLimiter:
    def test_allows_under_limit(self):
        rl = TTLRateLimiter(ttl=60.0, max_requests=3)
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("a") is True

    def test_blocks_over_limit(self):
        rl = TTLRateLimiter(ttl=60.0, max_requests=2)
        assert rl.is_allowed("b") is True
        assert rl.is_allowed("b") is True
        assert rl.is_allowed("b") is False

    def test_expired_entries_cleared(self):
        rl = TTLRateLimiter(ttl=0.1, max_requests=1)
        assert rl.is_allowed("c") is True
        time.sleep(0.15)
        rl.clear_expired()
        assert rl.is_allowed("c") is True

    def test_different_keys_independent(self):
        rl = TTLRateLimiter(ttl=60.0, max_requests=1)
        assert rl.is_allowed("d1") is True
        assert rl.is_allowed("d2") is True
        assert rl.is_allowed("d1") is False

    def test_clear_expired_removes_empty_keys(self):
        rl = TTLRateLimiter(ttl=0.05, max_requests=2)
        assert rl.is_allowed("e") is True
        time.sleep(0.1)
        rl.clear_expired()
        assert "e" not in rl._store
