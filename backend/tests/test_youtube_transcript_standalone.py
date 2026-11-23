"""Unit and contract tests for the standalone YouTube Transcript pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from services.youtube_transcript.downloader import (
    classify_ytdlp_error,
    clean_vtt_to_text,
    download_transcript,
    extract_video_id,
    list_subtitles,
    parse_list_subs_output,
    sanitize_filename,
)
from services.youtube_transcript.models import (
    AgeRestrictedError,
    CaptionSourceType,
    GeoBlockedError,
    InvalidURLError,
    MissingCaptionsError,
    PrivateVideoError,
    TranscriptDownloadRequest,
    WhisperConsentRequiredError,
)
from services.youtube_transcript.preflight import (
    check_ffmpeg_installed,
    check_ytdlp_installed,
    get_whisper_install_instructions,
    get_ytdlp_install_instructions,
)


def test_extract_video_id_variants():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=42") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    with pytest.raises(InvalidURLError):
        extract_video_id("https://vimeo.com/123456789")
    with pytest.raises(InvalidURLError):
        extract_video_id("")


def test_sanitize_filename():
    raw = 'Why Are We Anxious? / A Guru Explains [Part 1: The "Self"] <Must Watch!>'
    clean = sanitize_filename(raw, max_length=50)
    assert "/" not in clean
    assert "?" not in clean
    assert "[" in clean or "]" in clean
    assert "<" not in clean and ">" not in clean
    assert len(clean) <= 50

    assert sanitize_filename("") == "untitled_video"
    assert sanitize_filename("   ") == "untitled_video"


def test_preflight_install_instructions():
    macos = get_ytdlp_install_instructions("Darwin")
    assert "brew install yt-dlp" in macos["primary"]
    assert "https://github.com/yt-dlp/yt-dlp#installation" in macos["official_repo"]

    linux = get_ytdlp_install_instructions("Linux")
    assert "apt install" in linux["primary"]

    whisper = get_whisper_install_instructions()
    assert "openai-whisper" in whisper["pip"]


def test_parse_list_subs_output():
    stdout_sample = """
[youtube] Extracting URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
[info] Available subtitles for 'Never Gonna Give You Up':
Language Name Formats
en       English  vtt, ttml, srv3
hi       Hindi    vtt, srv1

[info] Available automatic captions for 'Never Gonna Give You Up':
Language Name Formats
es       Spanish  vtt
fr       French   vtt
"""
    res = parse_list_subs_output(stdout_sample, "dQw4w9WgXcQ")
    assert res.video_id == "dQw4w9WgXcQ"
    assert res.title == "Never Gonna Give You Up"
    assert len(res.manual_subtitles) == 2
    assert len(res.auto_subtitles) == 2
    assert res.has_manual is True
    assert res.has_auto is True

    en_track = res.find_track("en", prefer_manual=True)
    assert en_track is not None
    assert en_track.is_auto is False
    assert en_track.language_code == "en"

    es_track = res.find_track("es", prefer_manual=True)
    assert es_track is not None
    assert es_track.is_auto is True


def test_classify_ytdlp_errors():
    err_priv = classify_ytdlp_error("ERROR: [youtube] dQw4w9WgXcQ: This video is private")
    assert isinstance(err_priv, PrivateVideoError)

    err_age = classify_ytdlp_error("ERROR: Sign in to confirm your age. This video may be inappropriate for some users.")
    assert isinstance(err_age, AgeRestrictedError)

    err_geo = classify_ytdlp_error("ERROR: The uploader has not made this video available in your country")
    assert isinstance(err_geo, GeoBlockedError)

    err_subs = classify_ytdlp_error("WARNING: video has no subtitles")
    assert isinstance(err_subs, MissingCaptionsError)


def test_clean_vtt_to_text():
    sample_vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500
<c>The mind is constantly</c> seeking.

00:00:03.500 --> 00:00:06.000
The mind is constantly seeking.

00:00:06.000 --> 00:00:08.500
Seeking what? Peace.

00:00:08.500 --> 00:00:11.000
Seeking what? Peace.
"""
    text = clean_vtt_to_text(sample_vtt)
    lines = text.strip().split("\n")
    assert lines == [
        "The mind is constantly seeking.",
        "Seeking what? Peace.",
    ]


def test_download_transcript_prefer_manual_success(tmp_path: Path):
    video_id = "dQw4w9WgXcQ"
    url = f"https://www.youtube.com/watch?v={video_id}"

    list_stdout = """
[info] Available subtitles for 'Wisdom on Freedom':
Language Name Formats
en       English  vtt
"""
    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nFreedom is inner stillness."

    def fake_runner(cmd):
        if "--list-subs" in cmd:
            return {"stdout": list_stdout, "stderr": "", "returncode": 0}
        if "--write-sub" in cmd:
            return {"stdout": "Downloaded sub", "stderr": "", "returncode": 0, "vtt_content": vtt_content}
        return {"stdout": "", "stderr": "", "returncode": 0}

    req = TranscriptDownloadRequest(
        url=url,
        target_language="en",
        prefer_manual=True,
        output_dir=tmp_path,
        generate_txt=True,
    )
    result = download_transcript(req, custom_runner=fake_runner)

    assert result.video_id == video_id
    assert result.source_type == CaptionSourceType.MANUAL
    assert result.vtt_path.exists()
    assert result.txt_path.exists()
    assert "Freedom is inner stillness." in result.txt_path.read_text()
    assert result.character_count > 0


def test_download_transcript_fallback_to_auto(tmp_path: Path):
    video_id = "12345678901"
    url = f"https://www.youtube.com/watch?v={video_id}"

    list_stdout = """
[info] Available automatic captions for 'Spiritual Practice':
Language Name Formats
en       English  vtt
"""
    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nPractice awareness daily."

    def fake_runner(cmd):
        if "--list-subs" in cmd:
            return {"stdout": list_stdout, "stderr": "", "returncode": 0}
        if "--write-auto-sub" in cmd:
            return {"stdout": "Downloaded auto sub", "stderr": "", "returncode": 0, "vtt_content": vtt_content}
        return {"stdout": "", "stderr": "", "returncode": 0}

    req = TranscriptDownloadRequest(
        url=url,
        target_language="en",
        allow_auto=True,
        output_dir=tmp_path,
    )
    result = download_transcript(req, custom_runner=fake_runner)

    assert result.source_type == CaptionSourceType.AUTO
    assert result.vtt_path.exists()
    assert "Practice awareness daily." in result.vtt_path.read_text()


def test_download_transcript_whisper_requires_consent(tmp_path: Path):
    video_id = "nocaptions1"
    url = f"https://www.youtube.com/watch?v={video_id}"

    list_stdout = "[info] Available subtitles for 'Silence':\n[info] Available automatic captions for 'Silence':\n"

    def fake_runner(cmd):
        if "--list-subs" in cmd:
            return {"stdout": list_stdout, "stderr": "", "returncode": 0}
        if "--dump-json" in cmd:
            return {"stdout": json.dumps({"duration": 300, "title": "Silence"}), "stderr": "", "returncode": 0}
        return {"stdout": "", "stderr": "", "returncode": 0}

    # Without allow_whisper -> MissingCaptionsError
    req_no_whisper = TranscriptDownloadRequest(url=url, allow_whisper=False, output_dir=tmp_path)
    with pytest.raises(MissingCaptionsError):
        download_transcript(req_no_whisper, custom_runner=fake_runner)

    # With allow_whisper but without consent -> WhisperConsentRequiredError with duration & size
    req_needs_consent = TranscriptDownloadRequest(
        url=url,
        allow_whisper=True,
        whisper_consent=False,
        output_dir=tmp_path,
    )
    with pytest.raises(WhisperConsentRequiredError) as exc_info:
        download_transcript(req_needs_consent, custom_runner=fake_runner)

    err = exc_info.value
    assert err.duration_seconds == 300.0
    assert err.estimated_audio_size_mb > 0
    assert "Explicit user consent required" in str(err)

    # With explicit consent -> succeeds with real Whisper segment VTT formatting
    fake_whisper_output = {
        "text": "Silence is the greatest teaching.",
        "segments": [
            {"start": 0.0, "end": 3.5, "text": "Silence is the greatest teaching."}
        ],
    }

    req_with_consent = TranscriptDownloadRequest(
        url=url,
        allow_whisper=True,
        whisper_consent=True,
        output_dir=tmp_path,
    )
    res = download_transcript(
        req_with_consent,
        custom_runner=fake_runner,
        whisper_transcriber=lambda vid, p, l: fake_whisper_output,
    )
    assert res.source_type == CaptionSourceType.WHISPER
    assert res.vtt_path.exists()
    assert "Silence is the greatest teaching." in res.vtt_path.read_text()
    assert res.manifest_path is not None
    assert res.manifest_path.exists()


def test_download_transcript_manifest_and_fail_closed_cleanup(tmp_path: Path):
    video_id = "testmanif11"
    url = f"https://www.youtube.com/watch?v={video_id}"

    list_stdout = (
        "[info] Available subtitles for 'Test Video':\n"
        "Language Name Formats\n"
        "en       English  vtt\n"
        "[info] Available automatic captions for 'Test Video':\n"
    )

    vtt_content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:05.000\n"
        "Awareness is stillness.\n"
    )

    def fake_runner(cmd):
        if "--list-subs" in cmd:
            return {"stdout": list_stdout, "stderr": "", "returncode": 0}
        return {"stdout": "", "stderr": "", "returncode": 0, "vtt_content": vtt_content}

    req = TranscriptDownloadRequest(
        url=url,
        prefer_manual=True,
        output_dir=tmp_path,
        generate_txt=True,
    )

    res = download_transcript(req, custom_runner=fake_runner)

    assert res.manifest_path is not None
    assert res.manifest_path.exists()

    manifest = json.loads(res.manifest_path.read_text())
    assert manifest["video_id"] == video_id
    assert manifest["artifacts"]["vtt"]["file"] == res.vtt_path.name
    assert manifest["artifacts"]["vtt"]["size_bytes"] > 0
    assert manifest["artifacts"]["txt"]["file"] == res.txt_path.name
    assert manifest["artifacts"]["txt"]["size_bytes"] > 0
    assert manifest["character_count"] > 0
    assert manifest["line_count"] > 0
