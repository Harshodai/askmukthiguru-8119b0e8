"""Focused tests for CORS origin regex/wildcard handling in app.main."""

import logging
import re

from app.config import settings


def _reload_cors_state(monkeypatch, origins, is_production):
    """Re-import main.py with patched settings to capture module-level CORS state."""
    monkeypatch.setattr(settings, "cors_origins", origins)
    monkeypatch.setattr(settings, "is_production", is_production)
    import importlib

    import app.main as main_module

    importlib.reload(main_module)
    return main_module


def test_no_wildcard_gives_regex_none(monkeypatch):
    """When no configured origins contain '*', the regex should be None."""
    main_module = _reload_cors_state(
        monkeypatch,
        origins="https://example.com,https://app.example.com",
        is_production=False,
    )
    assert main_module.cors_origins_regex is None
    assert main_module.cors_origins_exact == ["https://example.com", "https://app.example.com"]


def test_wildcard_regex_matches_subdomain(monkeypatch):
    """Wildcard origins build a regex that matches intended subdomains."""
    main_module = _reload_cors_state(
        monkeypatch,
        origins="https://*.example.com",
        is_production=False,
    )
    regex = main_module.cors_origins_regex
    assert regex is not None
    assert re.fullmatch(regex, "https://app.example.com")
    assert not re.fullmatch(regex, "https://evil.com/.example.com")


def test_wildcard_with_regex_metacharacters_is_literal(monkeypatch):
    """Special regex characters in the origin (other than *) are escaped."""
    main_module = _reload_cors_state(
        monkeypatch,
        origins=r"https://*.example.com+(test)",
        is_production=False,
    )
    regex = main_module.cors_origins_regex
    assert regex is not None
    assert re.fullmatch(regex, "https://sub.example.com+(test)")


def test_production_warns_on_filtered_origins(monkeypatch, caplog):
    """Production emits a warning when wildcards are stripped from origins."""
    with caplog.at_level(logging.WARNING, logger="app.main"):
        _reload_cors_state(
            monkeypatch,
            origins="https://app.example.com,https://*.example.com",
            is_production=True,
        )
    assert any("wildcard origins removed" in rec.message for rec in caplog.records)


def test_production_warns_when_exact_origins_empty(monkeypatch, caplog):
    """Production emits a warning when exact-origins allowlist becomes empty."""
    with caplog.at_level(logging.WARNING, logger="app.main"):
        _reload_cors_state(
            monkeypatch,
            origins="https://*.example.com,*",
            is_production=True,
        )
    assert any("empty in production" in rec.message for rec in caplog.records)
