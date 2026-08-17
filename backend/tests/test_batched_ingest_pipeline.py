"""Unit tests for the batched local transcription and Railway ingestion pipeline."""

import importlib.util
import tempfile
from pathlib import Path
import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
FETCH_PATH = REPO_ROOT / "scripts" / "ingestion" / "1_fetch_transcripts_local.py"
UPLOAD_PATH = REPO_ROOT / "scripts" / "ingestion" / "2_upload_transcripts_to_railway.py"

fetch_spec = importlib.util.spec_from_file_location("fetch_mod", FETCH_PATH)
fetch_mod = importlib.util.module_from_spec(fetch_spec)
fetch_spec.loader.exec_module(fetch_mod)

upload_spec = importlib.util.spec_from_file_location("upload_mod", UPLOAD_PATH)
upload_mod = importlib.util.module_from_spec(upload_spec)
upload_spec.loader.exec_module(upload_mod)


def test_extract_speaker_heuristics():
    """Verify speaker attribution extraction from titles and metadata."""
    assert fetch_mod.extract_speaker("Sri Preethaji on Freedom from Fear") == "Sri Preethaji"
    assert fetch_mod.extract_speaker("Discourse by Prithaji at Ekam") == "Sri Preethaji"
    assert fetch_mod.extract_speaker("Sri Krishnaji on Consciousness and Wisdom") == "Sri Krishnaji"
    assert fetch_mod.extract_speaker("Q&A with Preethaji & Krishnaji") == "Sri Preethaji & Sri Krishnaji"
    assert fetch_mod.extract_speaker("Ekam Meditation Gathering", uploader="Ekam") == "Sri Preethaji & Sri Krishnaji"
    assert fetch_mod.extract_speaker("Morning Chants and Silence") == "Sri Preethaji & Sri Krishnaji"


def test_strip_bracketed_tags():
    """Verify removal of bracketed noise/audio annotations."""
    raw = "Welcome everyone [music] today we learn [applause] how to live in peace [laughter] (music)."
    cleaned = fetch_mod.strip_bracketed_tags(raw)
    assert "[music]" not in cleaned
    assert "[applause]" not in cleaned
    assert "[laughter]" not in cleaned
    assert "(music)" not in cleaned
    assert "Welcome everyone today we learn how to live in peace ." in cleaned or "Welcome everyone today we learn how to live in peace" in cleaned


def test_restore_punctuation():
    """Verify basic capitalization and ending punctuation."""
    raw = "welcome to the meditation session we sit in silence"
    restored = fetch_mod.restore_punctuation(raw)
    assert restored.startswith("W")
    assert restored.endswith(".")


def test_transcript_md_write_and_parse_roundtrip():
    """Verify that .md files written by Phase 1 parse cleanly in Phase 2."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fetch_mod.OUT_DIR = tmp_path

        video_info = {
            "video_id": "test_vid_123",
            "url": "https://www.youtube.com/watch?v=test_vid_123",
            "title": "Sri Preethaji — The Beautiful State",
            "speaker": "Sri Preethaji",
        }
        text = "When you are in a beautiful state you experience true connection and peace with life."
        md_file = fetch_mod.write_transcript_md(video_info, text, method="manual_api")
        assert md_file.exists()

        # Parse with Phase 2
        parsed = upload_mod.parse_transcript_md(md_file)
        assert parsed is not None
        assert parsed["video_id"] == "test_vid_123"
        assert parsed["title"] == "Sri Preethaji — The Beautiful State"
        assert parsed["speaker"] == "Sri Preethaji"
        assert "beautiful state" in parsed["text"]


def test_raw_text_ingest_request_schema():
    """Verify RawTextIngestRequest model accepts speaker field."""
    from app.api.ingest import RawTextIngestRequest

    req = RawTextIngestRequest(
        text="Teaching about the mind and consciousness.",
        source_url="https://www.youtube.com/watch?v=abc12345678",
        title="Mindful Awareness",
        speaker="Sri Krishnaji",
        tags=["wisdom"],
    )
    assert req.speaker == "Sri Krishnaji"
    assert req.title == "Mindful Awareness"
    assert req.tags == ["wisdom"]

    # Default speaker when omitted
    req_default = RawTextIngestRequest(
        text="Teaching about the mind.",
        source_url="https://www.youtube.com/watch?v=abc12345678",
    )
    assert req_default.speaker == "Unknown"
