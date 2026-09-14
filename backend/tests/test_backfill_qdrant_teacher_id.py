"""Unit and regression tests for backfill_qdrant_teacher_id.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops.backfill_qdrant_teacher_id import classify_teacher, main


def test_classify_solo_preethaji():
    title = "Calm Is Your Superpower: Sri Preethaji On Destiny, Dharma & Money"
    tid, tids, rat = classify_teacher(title, "Unknown Channel", [])
    assert tid == "preethaji"
    assert "preethaji" in tids
    assert "krishnaji" in tids
    assert rat == "title_speaker_preethaji"


def test_classify_solo_krishnaji():
    title = "Sri Krishnaji on Creating Fearless Thinkers"
    tid, tids, rat = classify_teacher(title, "Unknown Channel", [])
    assert tid == "krishnaji"
    assert "krishnaji" in tids
    assert "preethaji" in tids
    assert rat == "title_speaker_krishnaji"


def test_classify_co_taught():
    title = "Evolution Series with Preethaji & Krishnaji"
    tid, tids, rat = classify_teacher(title, "Sri Preethaji & Sri Krishnaji", [])
    assert tid == "preethaji_krishnaji"
    assert set(tids) == {"preethaji", "krishnaji"}
    assert rat == "title_speaker_both"


def test_no_false_positive_on_inflammation():
    # 'inflammation' contains 'amma' - ensure it doesn't trigger amma_bhagavan!
    title = "Sri Krishnaji on Chronic Inflammation of the Mind"
    tid, tids, rat = classify_teacher(title, "Unknown Channel", ["teacher:amma_bhagavan"])
    assert tid == "krishnaji"
    assert "amma_bhagavan" not in tids


def test_classify_shared_ekam():
    title = "Soul Sync - A Oneness Meditation - 10 Minute Meditation"
    tid, tids, rat = classify_teacher(title, "Ekam / O&O Academy", ["presence", "meditation"])
    assert tid == "ekam"
    assert "preethaji" in tids
    assert "krishnaji" in tids


def test_dry_run_does_not_write(monkeypatch):
    mock_client = MagicMock()
    # Fake 2 points returned by scroll
    pt1 = MagicMock(id="p1", payload={"title": "Discourse with Preethaji"})
    mock_client.scroll.side_effect = [([pt1], None)]
    
    with patch("qdrant_client.QdrantClient", return_value=mock_client):
        rc = main(["--qdrant-url", "http://fake:6333"])
        assert rc == 0
        assert mock_client.set_payload.call_count == 0


def test_apply_mode_invokes_set_payload(monkeypatch):
    mock_client = MagicMock()
    pt1 = MagicMock(id="p1", payload={"title": "Discourse with Krishnaji"})
    mock_client.scroll.side_effect = [([pt1], None)]
    mock_client.count.return_value = MagicMock(count=0)
    
    with patch("qdrant_client.QdrantClient", return_value=mock_client):
        rc = main(["--apply", "--qdrant-url", "http://fake:6333"])
        assert rc == 0
        assert mock_client.set_payload.call_count == 1
        args, kwargs = mock_client.set_payload.call_args
        assert kwargs["payload"]["teacher_id"] == "krishnaji"
