"""T6-04: Clip reporting categories and saved answers API (PRD-006, FR-SAVE-01, FR-CORR-01).

Tests:
1. /api/feedback/clip-report accepts reason_category ("wrong teacher", "wrong topic", "cut mid-thought", "other")
2. /api/feedback/clip-report allows question to default when omitted or empty
3. /api/feedback/saved-answers persists answers with collection, notes, and citations
4. /api/feedback/saved-answers GET filters by collection
5. /api/feedback/saved-answers DELETE removes saved answer
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.feedback import (
    ClipReportRequest,
    _build_clip_record,
    _escape_clip_report,
)
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_clip_report_accepts_reason_categories():
    """Clip reports accept canonical reason categories (wrong teacher, wrong topic, cut mid-thought, other)."""
    point_id = str(uuid4())
    req = ClipReportRequest(
        served_point_id=point_id,
        reason="The voice is clearly not Sri Krishnaji",
        reason_category="wrong teacher",
    )
    rec = _build_clip_record(req, user_id="user-123")
    assert rec["served_point_id"] == point_id
    assert rec["reason_category"] == "wrong teacher"
    assert rec["question"] == "Clip playback report"
    assert rec["reporter"] == "user-123"


def test_clip_report_defaults_unknown_category_to_other():
    """Unrecognized categories default safely to 'other'."""
    point_id = str(uuid4())
    req = ClipReportRequest(
        served_point_id=point_id,
        reason="Audio glitch",
        reason_category="unknown_category_value",
    )
    rec = _build_clip_record(req, user_id=None)
    assert rec["reason_category"] == "other"
    assert rec["reporter"] == "anonymous"


def test_clip_report_escaping_defense_in_depth():
    """Free text and reason category are HTML-escaped before display."""
    raw = {
        "ts": "2026-11-05T10:00:00Z",
        "served_point_id": "test-point-1",
        "question": "<script>alert(1)</script>",
        "reason": "quote & <bold>",
        "reason_category": "other",
        "reporter": "seeker<script>",
        "reporter_user_id": "",
    }
    escaped = _escape_clip_report(raw)
    assert "<script>" not in escaped["question"]
    assert "&lt;script&gt;" in escaped["question"]
    assert "&amp;" in escaped["reason"]
    assert "&lt;script&gt;" in escaped["reporter"]


def test_saved_answers_lifecycle(tmp_path: Path):
    """Saved answers can be persisted, listed by collection, and deleted."""
    temp_file = str(tmp_path / "test_saved_answers.jsonl")

    from services.auth_service import get_current_user_from_supabase

    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": "user-123"}
    try:
        with patch("app.api.feedback._default_saved_answers_path", return_value=temp_file):
            client = TestClient(app)

            # 1. Save an answer
            save_payload = {
                "message_id": "msg-001",
                "question": "How to stay in a beautiful state?",
                "answer_text": "Live in connection, not isolation.",
                "collection_name": "Inner Peace",
                "notes": "Remember during difficult conversations",
                "citations": [
                    {
                        "url": "https://youtube.com/watch?v=123",
                        "title": "Living in Connection",
                        "speaker": "Sri Preethaji",
                    }
                ],
            }
            res1 = client.post("/api/feedback/saved-answers", json=save_payload)
            assert res1.status_code == 201
            saved_data = res1.json()
            save_id = saved_data["id"]
            assert saved_data["collection_name"] == "Inner Peace"
            assert saved_data["notes"] == "Remember during difficult conversations"
            assert len(saved_data["citations"]) == 1

            # 2. List saved answers
            res2 = client.get("/api/feedback/saved-answers")
            assert res2.status_code == 200
            all_saved = res2.json()
            assert len(all_saved) == 1
            assert all_saved[0]["id"] == save_id

            # 3. Filter by collection
            res3_match = client.get("/api/feedback/saved-answers?collection=Inner%20Peace")
            assert res3_match.status_code == 200
            assert len(res3_match.json()) == 1

            res3_nomatch = client.get("/api/feedback/saved-answers?collection=NonExistent")
            assert res3_nomatch.status_code == 200
            assert len(res3_nomatch.json()) == 0

            # 4. Delete saved answer
            res4 = client.delete(f"/api/feedback/saved-answers/{save_id}")
            assert res4.status_code == 200
            assert res4.json()["status"] == "ok"

            # Verify it's gone
            res5 = client.get("/api/feedback/saved-answers")
            assert res5.status_code == 200
            assert len(res5.json()) == 0
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)
