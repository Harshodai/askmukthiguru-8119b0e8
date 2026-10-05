"""
Tests for scripts/ops/reconcile_first_person_v7.py (Phase 1 index hygiene,
2026-09-30). Pure-function coverage: no Qdrant, no embeddings.

The module is loaded by file path because the container bind-mount maps
`/app/scripts` to the REPO-ROOT scripts/ (Audit A §5 harness gap), so
`from scripts.ops import ...` cannot resolve `backend/scripts/` there.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_NAME = "reconcile_first_person_v7.py"
_HERE = Path(__file__).resolve()
_CANDIDATES = [
    _HERE.parents[2] / "scripts" / "ops" / _NAME,  # host: repo_root/scripts/ops
    Path("/app/scripts/ops") / _NAME,  # container: repo-root scripts/ mount
    _HERE.parents[1] / "scripts" / "ops" / _NAME,  # fallback: backend/scripts/ops
]
for _p in _CANDIDATES:
    if _p.exists():
        _SCRIPT = _p
        break
else:
    raise FileNotFoundError(f"{_NAME} not found in any of: {_CANDIDATES}")


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_first_person_v7", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


recon = _load()


def _payload(text="Suffering is only a perception.", start=1000, end=5000, hash_hex=None):
    return {
        "video_id": "vid123",
        "start_ms": start,
        "end_ms": end,
        "speaker": "Sri Preethaji",
        "verbatim_text": text,
        "transcript_hash": hash_hex or hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def test_expected_id_matches_store_contract():
    """The reconcile script must derive IDs with the SAME function the store
    uses — uuid5(NS, f"{sha256(text)}:{start_ms}:{end_ms}")."""
    from services.first_person_store import make_first_person_point_id

    pl = _payload()
    expected, hash_hex = recon.expected_id_for(pl)
    assert hash_hex == pl["transcript_hash"]
    assert expected == make_first_person_point_id(pl["transcript_hash"], 1000, 5000)
    assert expected == str(
        __import__("uuid").uuid5(
            __import__("uuid").UUID("b3f9479e-4e67-4a0b-9d48-6a5814e5f7a2"),
            f"{pl['transcript_hash']}:1000:5000",
        )
    )


def test_consistent_point_is_not_a_mismatch():
    pl = _payload()
    expected, _ = recon.expected_id_for(pl)
    point = SimpleNamespace(id=expected, payload=pl, vector={})
    assert recon.find_mismatches([point]) == []


def test_stale_id_detected_with_expected_target():
    """Audit A-10: ID frozen at first write, text mutated later -> mismatch."""
    pl = _payload()
    point = SimpleNamespace(id="04306117-a10c-5d11-ad96-7c4414c1e607", payload=pl, vector={})
    mismatches = recon.find_mismatches([point])
    assert len(mismatches) == 1
    m = mismatches[0]
    expected, _ = recon.expected_id_for(pl)
    assert m["old_id"] == "04306117-a10c-5d11-ad96-7c4414c1e607"
    assert m["expected_id"] == expected
    assert m["hash_prefix"] == pl["transcript_hash"][:12]
    assert m["video_id"] == "vid123"
    assert m["start_ms"] == 1000 and m["end_ms"] == 5000


def test_hash_text_drift_fails_closed():
    """If stored transcript_hash != sha256(text), reconciliation must refuse
    (hash repair is a separate step — never guess which side is stale)."""
    pl = _payload(hash_hex="f" * 64)
    with pytest.raises(ValueError, match="hash drift"):
        recon.expected_id_for(pl)


def test_missing_verbatim_text_fails_closed():
    pl = _payload()
    del pl["verbatim_text"]
    point = SimpleNamespace(id="x", payload=pl, vector={})
    with pytest.raises(ValueError, match="missing verbatim_text"):
        recon.find_mismatches([point])


def test_scrolls_never_a_single_500_limit_page(monkeypatch):
    """Audit A-11(a): single scroll(limit=500) does partial work on larger
    collections — reconcile must paginate until offset is None."""
    calls = []
    client = SimpleNamespace()

    def _scroll(**kwargs):
        calls.append(kwargs["offset"])
        if len(calls) == 1:
            return [], "page-2-token"
        return [], None

    client.scroll = _scroll
    recon.scroll_all(client, "first_person_v7")
    assert calls == [None, "page-2-token"]
