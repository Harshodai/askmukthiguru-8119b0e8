"""P1-8 / P2-27 / P2-29: rights register read failures must not stamp 'unverified' silently."""

import json
import os

import pytest

from services.qdrant import indexer


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.setattr(indexer, "_RIGHTS_REGISTER_CACHE", None)


def _point_loader_at(monkeypatch, tmp_path, text):
    manifest = tmp_path / "audits" / "evidence" / "public_release_phase4_rights_manifest_2026-10-22.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return manifest


def test_unreadable_manifest_raises_instead_of_stamping_unverified(monkeypatch, tmp_path):
    _point_loader_at(monkeypatch, tmp_path, "{not json")
    with pytest.raises(indexer.RightsRegisterUnavailable):
        indexer.resolve_source_rights_status("https://youtu.be/abc", "abc")
    # nothing cached from the failure
    assert indexer._RIGHTS_REGISTER_CACHE is None


def test_cache_follows_manifest_mtime(monkeypatch, tmp_path):
    manifest = _point_loader_at(monkeypatch, tmp_path, json.dumps({"assets": []}))
    assert indexer.resolve_source_rights_status("", "vid1") == "unverified"

    manifest.write_text(
        json.dumps({"assets": [{"video_id": "vid1", "rights_status": "cleared"}]}),
        encoding="utf-8",
    )
    st = manifest.stat()
    os.utime(manifest, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert indexer.resolve_source_rights_status("", "vid1") == "licensed"
