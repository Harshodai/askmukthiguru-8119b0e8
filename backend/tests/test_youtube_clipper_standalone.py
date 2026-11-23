"""Tests for the standalone YouTube Clipper pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from services.youtube_clipper.models import (
    Chapter,
    ClipperOptions,
)
from services.youtube_clipper.pipeline import (
    batch_translate_cues,
    burn_subtitles_libass,
    cut_mp4_clip,
    generate_bilingual_srt,
    generate_chapter_summary_md,
    parse_vtt_cues,
    process_chapter,
    seconds_to_srt_time,
    slice_srt_zero_offset,
    time_to_seconds,
    validate_chapter_coverage,
)


def test_time_conversion_roundtrip():
    assert seconds_to_srt_time(0.0) == "00:00:00,000"
    assert seconds_to_srt_time(65.5) == "00:01:05,500"
    assert seconds_to_srt_time(3661.123) == "01:01:01,123"

    assert time_to_seconds("00:01:05.500") == 65.5
    assert time_to_seconds("01:00:00") == 3600.0


def test_validate_chapter_coverage_clean():
    chapters = [
        Chapter(index=1, title="Intro", start_time=0.0, end_time=150.0, summary="Introduction", keywords=["intro"]),
        Chapter(index=2, title="Practice", start_time=150.0, end_time=300.0, summary="The Core Practice", keywords=["mind"]),
        Chapter(index=3, title="Closing", start_time=300.0, end_time=450.0, summary="Q&A and Wrap up", keywords=["qa"]),
    ]
    res = validate_chapter_coverage(chapters, total_duration=450.0)
    assert res.is_valid is True
    assert res.coverage_ratio == 1.0
    assert len(res.gaps) == 0
    assert len(res.overlaps) == 0


def test_validate_chapter_coverage_gaps_and_overlaps():
    # Gap between ch 1 and 2, overlap between 2 and 3
    chapters = [
        Chapter(index=1, title="Intro", start_time=0.0, end_time=120.0, summary="Intro", keywords=["intro"]),
        Chapter(index=2, title="Body", start_time=130.0, end_time=250.0, summary="Body", keywords=["body"]),
        Chapter(index=3, title="Outro", start_time=240.0, end_time=360.0, summary="Outro", keywords=["outro"]),
    ]
    res = validate_chapter_coverage(chapters, total_duration=360.0)
    assert res.is_valid is False
    assert len(res.gaps) == 1
    assert res.gaps[0]["duration"] == 10.0
    assert len(res.overlaps) == 1
    assert res.overlaps[0]["duration"] == 10.0


def test_parse_vtt_cues_and_slice_zero_offset():
    vtt = """WEBVTT

00:01:00.000 --> 00:01:05.000
First line of chapter two.

00:01:05.000 --> 00:01:10.000
Second line of chapter two.

00:03:00.000 --> 00:03:05.000
Line from chapter three.
"""
    cues = parse_vtt_cues(vtt)
    assert len(cues) == 3
    assert cues[0] == (60.0, 65.0, "First line of chapter two.")

    # Slice for chapter starting at 60.0s (1 min) to 120.0s (2 min)
    srt_zero = slice_srt_zero_offset(cues, start_time=60.0, end_time=120.0)

    # Must start at 00:00:00,000
    assert "1\n00:00:00,000 --> 00:00:05,000\nFirst line of chapter two." in srt_zero
    assert "2\n00:00:05,000 --> 00:00:10,000\nSecond line of chapter two." in srt_zero
    # Chapter three cue should be excluded
    assert "Line from chapter three." not in srt_zero


def test_batch_translate_cues_and_bilingual_srt():
    cues = [(0.0, 5.0, f"Cue text {i}") for i in range(25)]

    def mock_translator(batch):
        return [f"[ZH] {t}" for t in batch]

    # Batch size 20 -> 2 batches
    bilingual_cues = batch_translate_cues(cues, batch_size=20, translator_func=mock_translator)
    assert len(bilingual_cues) == 25
    assert bilingual_cues[0] == (0.0, 5.0, "Cue text 0", "[ZH] Cue text 0")

    bilingual_srt = generate_bilingual_srt(bilingual_cues[:2])
    assert "1\n00:00:00,000 --> 00:00:05,000\nCue text 0\n[ZH] Cue text 0" in bilingual_srt


def test_generate_chapter_summary_md():
    ch = Chapter(
        index=1,
        title="Dissolving Anxiety",
        start_time=120.0,
        end_time=300.0,
        summary="Observe your thoughts without identifying with them.",
        keywords=["anxiety", "mindfulness", "peace"],
    )
    md = generate_chapter_summary_md(ch, "Living in Freedom")
    assert "# Dissolving Anxiety" in md
    assert "0:02:00 – 0:05:00" in md
    assert "Observe your thoughts without identifying with them." in md
    assert "#anxiety" in md
    assert "#mindfulness" in md


def test_process_chapter_end_to_end(tmp_path: Path):
    fake_video = tmp_path / "source.mp4"
    fake_video.write_bytes(b"\x00" * 1024)

    fake_vtt = tmp_path / "source.vtt"
    fake_vtt.write_text(
        "WEBVTT\n\n00:01:00.000 --> 00:01:05.000\nHello and welcome.\n\n00:01:05.000 --> 00:01:10.000\nToday we discuss peace.",
        encoding="utf-8",
    )

    ch = Chapter(
        index=1,
        title="Inner Peace",
        start_time=60.0,
        end_time=180.0,
        summary="Finding peace within everyday rush.",
        keywords=["peace", "inner"],
    )

    executed_cmds = []

    def fake_ffmpeg_runner(cmd):
        executed_cmds.append(" ".join(cmd))
        # Create output file if requested
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"\x00" * 512)
        return {"returncode": 0}

    out_base = tmp_path / "youtube-clips" / "20261123_120000"
    artifacts = process_chapter(
        video_path=fake_video,
        vtt_path=fake_vtt,
        chapter=ch,
        video_title="Spiritual Living",
        options=ClipperOptions(burn_subtitles=True, translate_bilingual=True, generate_summary=True),
        base_output_dir=out_base,
        custom_runner=fake_ffmpeg_runner,
        translator_func=lambda batch: [f"[ZH] {t}" for t in batch],
    )

    assert artifacts.chapter_dir.exists()
    assert artifacts.clip_mp4.exists()
    assert artifacts.srt_path.exists()
    assert artifacts.bilingual_srt_path.exists()
    assert artifacts.subtitled_mp4.exists()
    assert artifacts.summary_md.exists()
    assert artifacts.manifest_path.exists()

    # Verify manifest JSON
    manifest = json.loads(artifacts.manifest_path.read_text())
    assert manifest["chapter_index"] == 1
    assert manifest["duration_seconds"] == 120.0
    assert manifest["files"]["clip_mp4"] == "Inner_Peace_clip.mp4"

    # Verify FFmpeg was called with clip cutting and subtitle burning
    assert any("-ss 60.0" in c for c in executed_cmds)
    assert any("subtitles=" in c for c in executed_cmds)


def test_batch_translate_cues_fails_closed():
    cues = [(0.0, 5.0, "Sample text")]

    def failing_translator(batch):
        raise ConnectionError("Translation service unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        batch_translate_cues(cues, translator_func=failing_translator, max_retries=2)
    assert "Subtitle translation batch failed after 2 attempts" in str(exc_info.value)


def test_ffmpeg_cut_failure_fails_closed(tmp_path: Path):
    fake_video = tmp_path / "source.mp4"
    fake_video.write_bytes(b"\x00" * 512)
    fake_vtt = tmp_path / "source.vtt"
    fake_vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello", encoding="utf-8")

    ch = Chapter(index=1, title="Cut Fail", start_time=0.0, end_time=10.0, summary="Test", keywords=[])

    def failing_ffmpeg(cmd):
        return {"returncode": 1}

    with pytest.raises(RuntimeError) as exc_info:
        process_chapter(
            video_path=fake_video,
            vtt_path=fake_vtt,
            chapter=ch,
            video_title="Test",
            options=ClipperOptions(burn_subtitles=False, translate_bilingual=False),
            base_output_dir=tmp_path / "out",
            custom_runner=failing_ffmpeg,
        )
    assert "FFmpeg failed to cut chapter" in str(exc_info.value)


def test_process_chapter_burn_subtitles_failure_cleans_up_partial_artifacts(tmp_path: Path):
    fake_video = tmp_path / "source.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_vtt = tmp_path / "source.vtt"
    fake_vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello", encoding="utf-8")

    ch = Chapter(index=1, title="Burn Fail", start_time=0.0, end_time=10.0, summary="Test", keywords=[])

    def fail_on_burn(cmd):
        cmd_str = " ".join(cmd)
        if "subtitles=" in cmd_str:
            return {"returncode": 1}
        # Cutting succeeds
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"\x00" * 512)
        return {"returncode": 0}

    out_base = tmp_path / "out"
    with pytest.raises(RuntimeError) as exc_info:
        process_chapter(
            video_path=fake_video,
            vtt_path=fake_vtt,
            chapter=ch,
            video_title="Test",
            options=ClipperOptions(burn_subtitles=True, translate_bilingual=False),
            base_output_dir=out_base,
            custom_runner=fail_on_burn,
        )
    assert "FFmpeg failed to burn subtitles" in str(exc_info.value)

    # Invariant: partial files must be cleaned up on failure
    ch_dir = out_base / "01_Burn_Fail"
    assert not ch_dir.exists() or not any(ch_dir.iterdir())


def test_process_chapter_translation_cardinality_mismatch_fails_closed(tmp_path: Path):
    fake_video = tmp_path / "source.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_vtt = tmp_path / "source.vtt"
    fake_vtt.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nLine 1\n\n00:00:05.000 --> 00:00:10.000\nLine 2",
        encoding="utf-8",
    )

    ch = Chapter(index=1, title="Trans Fail", start_time=0.0, end_time=10.0, summary="Test", keywords=[])

    def mock_ffmpeg(cmd):
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"\x00" * 512)
        return {"returncode": 0}

    # Translator returns 1 item for 2 cues
    bad_translator = lambda batch: ["[ZH] only one line"]

    out_base = tmp_path / "out"
    with pytest.raises(RuntimeError) as exc_info:
        process_chapter(
            video_path=fake_video,
            vtt_path=fake_vtt,
            chapter=ch,
            video_title="Test",
            options=ClipperOptions(burn_subtitles=False, translate_bilingual=True),
            base_output_dir=out_base,
            custom_runner=mock_ffmpeg,
            translator_func=bad_translator,
        )
    assert "Translation provider returned 1 items for 2 cues" in str(exc_info.value)

    # Invariant: partial files must be cleaned up
    ch_dir = out_base / "01_Trans_Fail"
    assert not ch_dir.exists() or not any(ch_dir.iterdir())


def test_process_chapter_manifest_sha256_verification(tmp_path: Path):
    fake_video = tmp_path / "source.mp4"
    fake_video.write_bytes(b"VIDEO_CONTENT_12345")
    fake_vtt = tmp_path / "source.vtt"
    fake_vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello world", encoding="utf-8")

    ch = Chapter(index=1, title="Manifest Test", start_time=0.0, end_time=10.0, summary="Test", keywords=[])

    def mock_ffmpeg(cmd):
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"OUTPUT_MP4_CONTENT")
        return {"returncode": 0}

    out_base = tmp_path / "out"
    artifacts = process_chapter(
        video_path=fake_video,
        vtt_path=fake_vtt,
        chapter=ch,
        video_title="Test",
        options=ClipperOptions(burn_subtitles=True, translate_bilingual=True, generate_summary=True),
        base_output_dir=out_base,
        custom_runner=mock_ffmpeg,
        translator_func=lambda batch: [f"[ZH] {t}" for t in batch],
    )

    import hashlib
    assert artifacts.manifest_path.exists()
    manifest = json.loads(artifacts.manifest_path.read_text())

    # Verify input hashes
    expected_v_hash = hashlib.sha256(b"VIDEO_CONTENT_12345").hexdigest()
    assert manifest["inputs"]["video_sha256"] == expected_v_hash

    # Verify output artifact hashes match disk bytes
    clip_file = artifacts.chapter_dir / manifest["artifacts"]["clip_mp4"]["file"]
    assert hashlib.sha256(clip_file.read_bytes()).hexdigest() == manifest["artifacts"]["clip_mp4"]["sha256"]

    srt_file = artifacts.chapter_dir / manifest["artifacts"]["srt"]["file"]
    assert hashlib.sha256(srt_file.read_bytes()).hexdigest() == manifest["artifacts"]["srt"]["sha256"]

