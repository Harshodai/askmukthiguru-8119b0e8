"""/api/ingest/federated is off by default, path-allowlisted, and never leaks exception text."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ingest as ingest_api
from app.config import settings
from app.dependencies import get_container_async
from ingest.federated_engine import FederatedDataSourceIngestionEngine
from services.auth_service import require_aal2
from services.tenant_context import set_tenant_from_request


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(ingest_api.router, prefix="/api")
    app.dependency_overrides[require_aal2] = lambda: {"id": "a", "is_superuser": True}
    app.dependency_overrides[get_container_async] = lambda: SimpleNamespace()
    app.dependency_overrides[set_tenant_from_request] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _post(client, source_type="okf_staging", source_ref="x.md"):
    return client.post(
        "/api/ingest/federated", json={"source_type": source_type, "source_ref": source_ref}
    )


def test_route_is_404_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(settings, "federated_ingest_enabled", False)
    assert _post(client).status_code == 404


def test_path_outside_allowed_dir_is_rejected(client, monkeypatch, tmp_path):
    allowed = tmp_path / "ok"
    allowed.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("x")
    monkeypatch.setattr(settings, "federated_ingest_enabled", True)
    monkeypatch.setattr(settings, "federated_ingest_allowed_dir", str(allowed))
    assert _post(client, source_ref=str(secret)).status_code == 400
    assert _post(client, source_ref=str(allowed / ".." / "secret.md")).status_code == 400
    assert _post(client, source_ref="/etc/passwd").status_code == 400
    link = allowed / "link.md"
    link.symlink_to(secret)
    assert _post(client, source_ref=str(link)).status_code == 400


def test_no_allowed_dir_configured_rejects_path_types(client, monkeypatch):
    monkeypatch.setattr(settings, "federated_ingest_enabled", True)
    monkeypatch.setattr(settings, "federated_ingest_allowed_dir", "")
    assert _post(client, source_ref="/etc/passwd").status_code == 400


def test_youtube_ref_must_be_a_video_id_and_unknown_types_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "federated_ingest_enabled", True)
    assert _post(client, "youtube", "../../etc/passwd").status_code == 400
    assert _post(client, "whatsapp_reflection", "abc").status_code == 400


def test_failure_returns_generic_detail(client, monkeypatch, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("hello")
    monkeypatch.setattr(settings, "federated_ingest_enabled", True)
    monkeypatch.setattr(settings, "federated_ingest_allowed_dir", str(tmp_path))

    def boom(self, *a, **k):
        raise RuntimeError("secret internal path /srv/x")

    monkeypatch.setattr(FederatedDataSourceIngestionEngine, "ingest_source", boom)
    resp = _post(client, source_ref=str(f))
    assert resp.status_code == 500
    assert "secret" not in resp.text


def test_allowed_file_runs_engine(client, monkeypatch, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("hello")
    monkeypatch.setattr(settings, "federated_ingest_enabled", True)
    monkeypatch.setattr(settings, "federated_ingest_allowed_dir", str(tmp_path))
    monkeypatch.setattr(
        FederatedDataSourceIngestionEngine,
        "ingest_source",
        lambda self, **k: {"status": "success", "chunks_ingested": 1},
    )
    resp = _post(client, source_ref=str(f))
    assert resp.status_code == 200 and resp.json()["chunks_ingested"] == 1


def test_rights_gate_raises_not_asserts():
    engine = FederatedDataSourceIngestionEngine()

    class Bad:
        def fetch(self, ref, **k):
            return [{"content": "t"}]

        def parse_and_chunk(self, raw, **k):
            return [{"text": "t", "metadata": {"domain_rights_status": "unverified"}}]

    engine.adapters["okf_staging"] = Bad()
    with pytest.raises(ValueError, match="X40"):
        engine.ingest_source("okf_staging", "x")
