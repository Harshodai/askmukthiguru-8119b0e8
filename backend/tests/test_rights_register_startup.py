"""T3-01 (DATA-02): rights register ships in the image; production fails closed."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.main import check_rights_register_startup
from services import first_person_serving_contract as fpsc

REPO = Path(__file__).resolve().parents[2]


def _point_at(monkeypatch, tmp_path, payload):
    f = tmp_path / "audits" / "evidence" / "x.json"
    f.parent.mkdir(parents=True)
    if payload is not None:
        f.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(fpsc, "RIGHTS_MANIFEST_RELPATH", str(f))
    monkeypatch.setattr(fpsc, "rights_manifest_path", lambda: f)


def test_missing_register_fails_production(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, None)
    assert check_rights_register_startup(SimpleNamespace(is_production=True))


def test_empty_register_fails_production(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, json.dumps({"assets": []}))
    assert check_rights_register_startup(SimpleNamespace(is_production=True))


def test_missing_register_ok_outside_production(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, None)
    assert check_rights_register_startup(SimpleNamespace(is_production=False)) == []


def test_present_register_passes_and_reports_digest(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, json.dumps({"assets": [{"video_id": "a"}, {"video_id": "b"}]}))
    assert check_rights_register_startup(SimpleNamespace(is_production=True)) == []
    st = fpsc.rights_register_status()
    assert st["present"] is True and st["asset_count"] == 2
    assert len(st["sha256_prefix"]) == 12
    assert set(st) == {"present", "asset_count", "sha256_prefix"}


def test_health_helper_has_no_path(monkeypatch, tmp_path):
    from app.api.health import _rights_register_health

    _point_at(monkeypatch, tmp_path, json.dumps({"assets": [{"video_id": "a"}]}))
    out = _rights_register_health()
    assert out["asset_count"] == 1
    assert str(tmp_path) not in json.dumps(out)


@pytest.mark.parametrize("name", ["Dockerfile", "Dockerfile.railway"])
def test_serving_images_copy_the_register(name):
    text = (REPO / "backend" / name).read_text(encoding="utf-8")
    assert fpsc.RIGHTS_MANIFEST_RELPATH in text
