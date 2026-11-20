import asyncio

import pytest

from app import telemetry_db


def test_get_admins_raises_when_client_missing(monkeypatch):
    """An unavailable DB must surface as an error, not as an empty admin list."""
    monkeypatch.setattr(telemetry_db, "_get_client", lambda: None)
    with pytest.raises(RuntimeError):
        asyncio.run(telemetry_db.get_admins())
