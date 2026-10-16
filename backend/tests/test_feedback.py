"""Tests for the feedback loop: POST /api/feedback/rate, retry_analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── retry_analysis unit tests (no app import needed) ────────────────


class TestRetryAnalysis:
    def test_empty_returns_empty(self):
        """No rows → empty clusters."""
        from ops.retry_analysis import analyze_retry_patterns

        with patch("ops.retry_analysis._get_client", return_value=None):
            result = analyze_retry_patterns(since_days=7)
        assert result == []

    def test_clusters_by_similarity(self):
        """Similar queries cluster together."""
        from ops.retry_analysis import analyze_retry_patterns

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value.data = [
            {"query_text": "What is meditation practice?", "feedback_type": "negative"},
            {"query_text": "Tell me about meditation practice", "feedback_type": "negative"},
            {"query_text": "How does meditation practice work?", "feedback_type": "negative"},
            {"query_text": "What is peace?", "feedback_type": "negative"},
        ]

        with patch("ops.retry_analysis._get_client", return_value=mock_client):
            result = analyze_retry_patterns(since_days=7)

        assert len(result) >= 1
        meditation_cluster = next(
            (c for c in result if "meditation" in c["representative_query"].lower()),
            None,
        )
        assert meditation_cluster is not None
        assert meditation_cluster["frequency"] >= 3

    def test_empty_queries_skipped(self):
        """Empty query_text entries are skipped."""
        from ops.retry_analysis import analyze_retry_patterns

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value.data = [
            {"query_text": "", "feedback_type": "negative"},
            {"query_text": "   ", "feedback_type": "negative"},
            {"query_text": "What is peace?", "feedback_type": "negative"},
        ]

        with patch("ops.retry_analysis._get_client", return_value=mock_client):
            result = analyze_retry_patterns(since_days=7)

        assert len(result) == 1
        assert "peace" in result[0]["representative_query"].lower()


# ── word overlap helper ─────────────────────────────────────────────


class TestWordOverlap:
    def test_identical(self):
        from ops.retry_analysis import _word_overlap

        assert _word_overlap("meditation practice", "meditation practice") == 1.0

    def test_partial(self):
        from ops.retry_analysis import _word_overlap

        score = _word_overlap("what is meditation", "tell me about meditation")
        assert 0.3 < score < 0.8

    def test_no_overlap(self):
        from ops.retry_analysis import _word_overlap

        assert _word_overlap("meditation", "peace") == 0.0


# ── Feedback endpoint validation (schema-level, no app import) ──────


class TestRateFeedbackSchema:
    def test_valid_positive(self):
        from app.api.feedback import RateFeedbackRequest

        req = RateFeedbackRequest(message_id="msg-1", feedback_type="positive", query_text="hi")
        assert req.feedback_type == "positive"

    def test_valid_negative(self):
        from app.api.feedback import RateFeedbackRequest

        req = RateFeedbackRequest(message_id="msg-1", feedback_type="negative")
        assert req.feedback_type == "negative"

    def test_invalid_type_rejected(self):
        from pydantic import ValidationError

        from app.api.feedback import RateFeedbackRequest

        with pytest.raises(ValidationError):
            RateFeedbackRequest(message_id="msg-1", feedback_type="maybe")

    def test_missing_message_id_rejected(self):
        from pydantic import ValidationError

        from app.api.feedback import RateFeedbackRequest

        with pytest.raises(ValidationError):
            RateFeedbackRequest(feedback_type="positive")


# ── Faculty clip-report intake + quality blocklist (T-B12 quarantine) ──────
# Appended 2026-10-14: POST /api/feedback/clip-report validation (ids only,
# never transcript text) and the serving-side quarantine. All file I/O goes
# to tmp_path via monkeypatched settings paths / module constants.


class TestClipReportValidation:
    def test_valid_report_builds_ids_only_record(self):
        from app.api.feedback import ClipReportRequest, _build_clip_record

        body = ClipReportRequest(
            served_point_id="550e8400-e29b-41d4-a716-446655440000",
            question="What is stillness?",
            reason="Wrong speaker attributed",
            reporter="faculty-1",
        )
        record = _build_clip_record(body, "user-9")
        assert set(record) == {
            "ts",
            "served_point_id",
            "question",
            "reason",
            "reporter",
            "reporter_user_id",
        }
        assert record["served_point_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert record["question"] == "What is stillness?"
        assert record["reason"] == "Wrong speaker attributed"
        assert record["reporter"] == "faculty-1"
        assert record["reporter_user_id"] == "user-9"
        assert record["ts"]

    def test_reporter_defaults_to_user_id(self):
        from app.api.feedback import ClipReportRequest, _build_clip_record

        body = ClipReportRequest(
            served_point_id="clipA", question="What is stillness?", reason="Mid-thought cut"
        )
        assert _build_clip_record(body, "user-9")["reporter"] == "user-9"
        assert _build_clip_record(body, "user-9")["reporter_user_id"] == "user-9"
        assert _build_clip_record(body, None)["reporter"] == "anonymous"
        assert _build_clip_record(body, None)["reporter_user_id"] == ""

    def test_empty_point_id_rejected_422(self):
        from fastapi import HTTPException

        from app.api.feedback import _validate_clip_point_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_clip_point_id("   ")
        assert exc_info.value.status_code == 422

    def test_garbage_point_id_rejected_422(self):
        from fastapi import HTTPException

        from app.api.feedback import _validate_clip_point_id

        for bad in ("a", "has space", "bad!chars", "x" * 200):
            with pytest.raises(HTTPException) as exc_info:
                _validate_clip_point_id(bad)
            assert exc_info.value.status_code == 422

    def test_short_uint_point_ids_accepted(self):
        from app.api.feedback import _validate_clip_point_id

        assert _validate_clip_point_id("1") == "1"
        assert _validate_clip_point_id("42") == "42"
        assert _validate_clip_point_id("  7  ") == "7"
        assert _validate_clip_point_id(str(2**53)) == str(2**53)

    def test_out_of_range_uint_point_ids_rejected_422(self):
        from fastapi import HTTPException

        from app.api.feedback import _validate_clip_point_id

        for bad in ("0", str(2**53 + 1), "18446744073709551615", "-1", "+1", "1.5", "0x1"):
            with pytest.raises(HTTPException) as exc_info:
                _validate_clip_point_id(bad)
            assert exc_info.value.status_code == 422

    def test_empty_question_rejected_422(self):
        from fastapi import HTTPException

        from app.api.feedback import ClipReportRequest, _build_clip_record

        body = ClipReportRequest(
            served_point_id="clipA", question="  ", reason="Trimmed mid-thought"
        )
        with pytest.raises(HTTPException) as exc_info:
            _build_clip_record(body, "user-9")
        assert exc_info.value.status_code == 422

    def test_empty_reason_rejected_422(self):
        from fastapi import HTTPException

        from app.api.feedback import ClipReportRequest, _build_clip_record

        body = ClipReportRequest(
            served_point_id="clipA", question="What is stillness?", reason="  "
        )
        with pytest.raises(HTTPException) as exc_info:
            _build_clip_record(body, "user-9")
        assert exc_info.value.status_code == 422

    def test_append_writes_jsonl_ids_only(self, tmp_path, monkeypatch):
        import json

        import app.api.feedback as feedback_mod
        from app.api.feedback import ClipReportRequest, _append_clip_report, _build_clip_record

        target = tmp_path / "reports.jsonl"
        monkeypatch.setattr(feedback_mod, "CLIP_REPORTS_FILE_PATH", str(target))
        body = ClipReportRequest(
            served_point_id="clipA", question="What is stillness?", reason="Mid-thought cut"
        )
        _append_clip_report(_build_clip_record(body, "user-9"))
        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert set(parsed) == {
            "ts",
            "served_point_id",
            "question",
            "reason",
            "reporter",
            "reporter_user_id",
        }
        assert parsed["served_point_id"] == "clipA"
        assert parsed["reporter_user_id"] == "user-9"

    def test_clip_report_routes_registered(self):
        from app.api.feedback import router

        routes = {(r.path, m) for r in router.routes for m in getattr(r, "methods", [])}
        assert any(p.endswith("/clip-report") and m == "POST" for p, m in routes)
        assert any(p.endswith("/clip-reports") and m == "GET" for p, m in routes)

    @pytest.mark.asyncio
    async def test_get_clip_reports_unauthenticated_raises_401(self):
        from fastapi import HTTPException

        from app.api.feedback import get_clip_reports

        with pytest.raises(HTTPException) as exc_info:
            await get_clip_reports(user=None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"


# ── Clip-reports store path: absolute, CWD-independent, volume-backed ───────


class TestClipReportsPath:
    def test_default_path_is_absolute(self):
        import os

        import app.api.feedback as feedback_mod

        assert os.path.isabs(feedback_mod.CLIP_REPORTS_FILE_PATH)
        assert feedback_mod.CLIP_REPORTS_FILE_PATH.endswith(
            os.path.join("data", "feedback_clip_reports.jsonl")
        )

    def test_default_path_ignores_cwd(self, tmp_path, monkeypatch):
        import app.api.feedback as feedback_mod

        before = feedback_mod._default_clip_reports_path()
        monkeypatch.chdir(tmp_path)
        assert feedback_mod._default_clip_reports_path() == before

    def test_env_override_wins(self, tmp_path, monkeypatch):
        import app.api.feedback as feedback_mod

        # Env binds to Settings.feedback_clip_reports_path at startup
        # (pydantic case-insensitive field match); the module reads only the
        # settings field — no direct os.environ read (pinned by
        # tests/test_settings_guards.py). Patch the field the way the value
        # actually arrives.
        target = str(tmp_path / "custom.jsonl")
        monkeypatch.setattr(feedback_mod.settings, "feedback_clip_reports_path", target)
        assert feedback_mod._default_clip_reports_path() == target

    @pytest.mark.asyncio
    async def test_write_and_read_share_one_store(self, tmp_path, monkeypatch):
        import app.api.feedback as feedback_mod
        from app.api.feedback import ClipReportRequest, _append_clip_report, _build_clip_record

        target = tmp_path / "reports.jsonl"
        monkeypatch.setattr(feedback_mod, "CLIP_REPORTS_FILE_PATH", str(target))
        # Per-request path resolves from settings (B7); the module constant is
        # the default only. Patch both so write and read share one store.
        monkeypatch.setattr(
            feedback_mod.settings, "feedback_clip_reports_path", str(target)
        )
        body = ClipReportRequest(
            served_point_id="1", question="What is stillness?", reason="Mid-thought cut"
        )
        _append_clip_report(_build_clip_record(body, "user-9"))
        reports = await feedback_mod.get_clip_reports(user={"is_superuser": True})
        assert len(reports) == 1
        assert reports[0]["served_point_id"] == "1"
        assert reports[0]["reporter_user_id"] == "user-9"


# ── Quality blocklist: quarantine wins, off by default, mtime reload ───────

_BL_TEXT_A = (
    "Awareness watches each passing thought without holding on, and in that open "
    "watching the mind settles into quiet rest."
)
_BL_TEXT_B = (
    "Attention returning again and again to the breath builds a steady inner ground "
    "where clarity appears on its own."
)


def _bl_clip(text, point_id, video_id, dense):
    import hashlib

    return {
        "point_id": point_id,
        "video_id": video_id,
        "start_ms": 65000,
        "end_ms": 85000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "verbatim_text": text,
        "passage_dense": dense,
        "source_url": f"https://youtube.com/watch?v={video_id}",
        "caption_status": "auto_transcript",
    }


class _BlLLM:
    """Answerability YES; relevance gate is disabled in these tests."""

    async def generate(self, system_prompt="", user_prompt="", **kw):
        return "YES"


def _bl_run(monkeypatch, tmp_path, blocked, approved=None):
    import json
    from unittest.mock import MagicMock

    from app.config import settings
    from services.first_person_pipeline import FirstPersonPipeline

    if blocked is not None:
        bf = tmp_path / "blocked.json"
        bf.write_text(json.dumps(blocked), encoding="utf-8")
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", str(bf))
    else:
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", "")
    if approved is not None:
        af = tmp_path / "approved.json"
        af.write_text(json.dumps({"approved": approved}), encoding="utf-8")
        monkeypatch.setattr(settings, "first_person_quality_allowlist_path", str(af))
    else:
        monkeypatch.setattr(settings, "first_person_quality_allowlist_path", "")
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)

    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = [
        _bl_clip(_BL_TEXT_A, "clipA", "vidA", [1.0, 0.0]),
        _bl_clip(_BL_TEXT_B, "clipB", "vidB", [0.9, 0.1]),
    ]
    redis = MagicMock()
    redis.get.return_value = None
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=_BlLLM()
    )
    return pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])


class TestQualityBlocklist:
    def test_off_by_default(self, monkeypatch):
        from app.config import settings
        from services.first_person_pipeline import _quality_blocklist

        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", "")
        assert settings.first_person_quality_blocklist_path == ""
        assert _quality_blocklist() is None

    def test_unblocked_clips_serve_top_ranked(self, monkeypatch, tmp_path):
        res = _bl_run(monkeypatch, tmp_path, [])
        assert res.status == "weak_match"
        assert res.citations[0]["point_id"] == "clipA"

    def test_quarantined_clip_is_unservable(self, monkeypatch, tmp_path):
        res = _bl_run(monkeypatch, tmp_path, ["clipA"])
        assert res.status == "weak_match"
        assert res.citations[0]["point_id"] == "clipB"

    def test_quarantine_all_abstains(self, monkeypatch, tmp_path):
        res = _bl_run(monkeypatch, tmp_path, ["clipA", "clipB"])
        assert res.status == "abstained" and res.citations == []

    def test_quarantine_wins_over_allowlist(self, monkeypatch, tmp_path):
        res = _bl_run(monkeypatch, tmp_path, ["clipA"], approved=["clipA", "clipB"])
        assert res.status == "weak_match"
        assert res.citations[0]["point_id"] == "clipB"

    def test_allowlisted_but_quarantined_only_abstains(self, monkeypatch, tmp_path):
        res = _bl_run(monkeypatch, tmp_path, ["clipA"], approved=["clipA"])
        assert res.status == "abstained" and res.citations == []

    def test_missing_blocklist_file_fails_closed(self, monkeypatch, tmp_path):
        from app.config import settings
        from services.first_person_pipeline import _quality_blocklist

        monkeypatch.setattr(
            settings, "first_person_quality_blocklist_path", str(tmp_path / "nope.json")
        )
        monkeypatch.setattr(settings, "first_person_quality_allowlist_path", "")
        monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
        assert _quality_blocklist() is None  # unreadable: no list could be loaded
        from unittest.mock import MagicMock

        from services.first_person_pipeline import FirstPersonPipeline

        store = MagicMock()
        store.collection = "first_person_v1"
        store.search_hybrid.return_value = [_bl_clip(_BL_TEXT_A, "clipA", "vidA", [1.0, 0.0])]
        redis = MagicMock()
        redis.get.return_value = None
        pipeline = FirstPersonPipeline(
            store=store, redis_client=redis, calibration_profile=None, llm_service=_BlLLM()
        )
        res = pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])
        assert res.status == "abstained" and res.citations == []

    def test_blocklist_reloads_when_the_file_changes(self, monkeypatch, tmp_path):
        import json
        import os

        from app.config import settings
        from services.first_person_pipeline import _quality_blocklist

        bf = tmp_path / "blocked.json"
        bf.write_text(json.dumps(["clipA"]), encoding="utf-8")
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", str(bf))
        assert _quality_blocklist() == frozenset({"clipA"})
        bf.write_text(json.dumps({"blocked": ["clipA", "clipB"]}), encoding="utf-8")
        os.utime(bf, (os.path.getmtime(bf) + 5, os.path.getmtime(bf) + 5))
        assert _quality_blocklist() == frozenset({"clipA", "clipB"})

    def test_fingerprint_rekeys_on_quarantine_change(self, monkeypatch, tmp_path):
        import json
        import os
        from unittest.mock import MagicMock

        from app.config import settings
        from services.first_person_pipeline import FirstPersonPipeline

        store = MagicMock()
        store.collection = "first_person_v1"
        pipe = FirstPersonPipeline(store=store, redis_client=MagicMock(), llm_service=_BlLLM())
        monkeypatch.setattr(settings, "first_person_quality_allowlist_path", "")
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", "")
        off = pipe._serving_policy_fingerprint()
        bf = tmp_path / "blocked.json"
        bf.write_text(json.dumps(["clipA"]), encoding="utf-8")
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", str(bf))
        quarantined = pipe._serving_policy_fingerprint()
        assert quarantined != off
        bf.write_text(json.dumps(["clipA", "clipB"]), encoding="utf-8")
        os.utime(bf, (os.path.getmtime(bf) + 5, os.path.getmtime(bf) + 5))
        assert pipe._serving_policy_fingerprint() != quarantined
