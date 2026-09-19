"""Regression tests for AMK-D-001 (SSRF guardrail DNS resolution)."""

import socket
from unittest.mock import patch

from services.web_search_guardrails import check_url_safety


def test_hostname_resolving_to_loopback_is_rejected():
    """A hostname resolving to 127.0.0.1 must be rejected by check_url_safety."""
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        safe, reason = check_url_safety("http://attacker-domain.com/path")
        assert not safe, f"Expected safe=False, got safe={safe}, reason={reason}"
        assert (
            "private" in reason.lower()
            or "loopback" in reason.lower()
            or "unsafe" in reason.lower()
            or "blocked" in reason.lower()
        )


def test_hostname_resolving_to_private_ip_is_rejected():
    """A hostname resolving to a private IP (e.g. 10.0.0.5 or 169.254.169.254) must be rejected."""
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        safe, reason = check_url_safety("http://metadata.cloud-provider.internal/latest/meta-data")
        assert not safe
