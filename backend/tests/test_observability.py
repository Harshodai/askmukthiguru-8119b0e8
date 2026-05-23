from fastapi import FastAPI

from app import observability


def test_observability_respects_disabled_env(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setattr(observability, "_INITIALIZED", False)

    assert observability.init_observability(FastAPI()) is False


def test_observability_is_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(observability, "_INITIALIZED", True)

    assert observability.init_observability(FastAPI()) is True
