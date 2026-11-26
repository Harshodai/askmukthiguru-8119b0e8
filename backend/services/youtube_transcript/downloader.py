"""Standalone YouTube Transcript Downloader implementation.

Implements the user-facing transcript capability contract:
1. Environment preflight check for yt-dlp.
2. `--list-subs` subtitle discovery.
3. Manual subtitles priority over auto-generated.
4. Auto-generated fallback.
5. Whisper only as last resort, strictly gated on explicit user consent (size/duration).
6. Title extraction & safe filename sanitization.
7. VTT delivery and order-preserving deduplicated TXT conversion.
8. Typed error classification (private, age-restricted, geo-blocked, missing-captions).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from services.youtube_transcript.models import (
    AgeRestrictedError,
    CaptionSourceType,
    GeoBlockedError,
    InvalidURLError,
    MissingCaptionsError,
    PrivateVideoError,
    SubtitleListResult,
    SubtitleTrack,
    TranscriptDownloadRequest,
    TranscriptDownloadResult,
    TranscriptError,
    WhisperConsentRequiredError,
    YtDlpNotFoundError,
)
from services.youtube_transcript.preflight import check_whisper_installed, check_ytdlp_installed

logger = logging.getLogger(__name__)

_YOUTUBE_URL_PATTERNS = [
    re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})"),
]


def extract_video_id(url: str) -> str:
    """Extract 11-character YouTube video ID from various URL formats."""
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL must be a non-empty string")
    url = url.strip()
    for pattern in _YOUTUBE_URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url
    raise InvalidURLError(f"Invalid YouTube URL or video ID: {url}")


def sanitize_filename(title: str, max_length: int = 80) -> str:
    """Sanitize title into a safe filesystem filename."""
    if not title:
        return "untitled_video"
    # Replace characters that are illegal or problematic across Windows, macOS, Linux
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    clean = re.sub(r"[\x00-\x1f\x7f]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        clean = "untitled_video"
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(" .-_")
    return clean


def parse_list_subs_output(stdout: str, video_id: str) -> SubtitleListResult:
    """Parse output of `yt-dlp --list-subs` into SubtitleListResult."""
    manual_subtitles: list[SubtitleTrack] = []
    auto_subtitles: list[SubtitleTrack] = []
    title = f"video_{video_id}"

    section = "none"
    for line in stdout.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        if "Available subtitles for" in line_clean:
            # Extract video title or ID if present
            match = re.search(r"Available subtitles for (?:'|\")?([^'\"]+)(?:'|\")?:", line_clean)
            if match:
                title = match.group(1)
            section = "manual"
            continue
        elif "Available automatic captions for" in line_clean:
            section = "auto"
            continue
        elif line_clean.startswith("[info] Available subtitles"):
            section = "manual"
            continue
        elif line_clean.startswith("[info] Available automatic captions"):
            section = "auto"
            continue
        elif line_clean.startswith("Language") and "formats" in line_clean.lower():
            # Header line: Language Name Formats
            continue

        # Check for language rows: e.g. "en      English   vtt, ttml, srv3, srv2, srv1, json3"
        parts = re.split(r"\s{2,}", line_clean)
        if len(parts) >= 2:
            code = parts[0].strip()
            # Must look like language code (e.g., en, hi, es, en-US, pt-BR)
            if re.match(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?$", code):
                name = parts[1].strip() if len(parts) > 2 else code
                ext = "vtt"
                track = SubtitleTrack(
                    language_code=code,
                    name=name,
                    extension=ext,
                    is_auto=(section == "auto"),
                )
                if section == "manual":
                    manual_subtitles.append(track)
                elif section == "auto":
                    auto_subtitles.append(track)

    return SubtitleListResult(
        video_id=video_id,
        title=title,
        manual_subtitles=manual_subtitles,
        auto_subtitles=auto_subtitles,
    )


def classify_ytdlp_error(stderr: str, returncode: int = 1) -> Exception:
    """Classify yt-dlp error output into typed domain exceptions."""
    err_lower = stderr.lower()
    if "private video" in err_lower or "this video is private" in err_lower:
        return PrivateVideoError(
            "This YouTube video is private and cannot be accessed.", details={"stderr": stderr}
        )
    if "age-restricted" in err_lower or "sign in to confirm your age" in err_lower:
        return AgeRestrictedError(
            "This YouTube video is age-restricted and requires authentication.",
            details={"stderr": stderr},
        )
    if (
        "not available in your country" in err_lower
        or "available in your country" in err_lower
        or "geo-restricted" in err_lower
        or "blocked in your country" in err_lower
    ):
        return GeoBlockedError(
            "This YouTube video is geo-restricted and not available in this region.",
            details={"stderr": stderr},
        )
    if "no subtitles" in err_lower or "there are no subtitles" in err_lower:
        return MissingCaptionsError(
            "No subtitles or captions are available for this video.", details={"stderr": stderr}
        )
    if (
        "urlopen error" in err_lower
        or "connection refused" in err_lower
        or "timed out" in err_lower
    ):
        return TranscriptError(
            f"Network error communicating with YouTube: {stderr[:200]}", details={"stderr": stderr}
        )
    return TranscriptError(
        f"yt-dlp command failed with code {returncode}: {stderr[:300]}", details={"stderr": stderr}
    )


def list_subtitles(url: str, custom_runner: Optional[Callable] = None) -> SubtitleListResult:
    """Discover available subtitles using `yt-dlp --list-subs`."""
    if not check_ytdlp_installed() and custom_runner is None:
        raise YtDlpNotFoundError("yt-dlp binary is not installed or not found on PATH.")

    video_id = extract_video_id(url)
    cmd = ["yt-dlp", "--list-subs", url]

    if custom_runner:
        res = custom_runner(cmd)
        stdout, stderr, code = (
            res.get("stdout", ""),
            res.get("stderr", ""),
            res.get("returncode", 0),
        )
    else:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except Exception as e:
            raise TranscriptError(f"Failed to execute yt-dlp: {e}")

    if code != 0:
        raise classify_ytdlp_error(stderr, returncode=code)

    return parse_list_subs_output(stdout, video_id)


def clean_vtt_to_text(vtt_content: str) -> str:
    """Clean WebVTT content into deduplicated, order-preserving plain text.

    Suppresses overlapping rolling-window duplicates while preserving sentence order.
    """
    if not vtt_content:
        return ""

    lines = vtt_content.splitlines()
    text_lines: list[str] = []

    # Regexes for cleaning
    timestamp_re = re.compile(
        r"^\d{2}:\d{2}(?::\d{2})?\.\d{3}\s*-->\s*\d{2}:\d{2}(?::\d{2})?\.\d{3}"
    )
    tag_re = re.compile(r"<[^>]+>")

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        # Skip WebVTT header lines
        if (
            line.startswith("WEBVTT")
            or line.startswith("Kind:")
            or line.startswith("Language:")
            or line.startswith("NOTE")
        ):
            continue
        # Skip cue numbers or timestamps
        if line.isdigit() or timestamp_re.search(line):
            continue

        # Strip inline markup
        clean = tag_re.sub("", line).strip()
        if not clean:
            continue

        # Deduplicate with recent buffer (within last 3 lines)
        recent_window = text_lines[-3:] if len(text_lines) >= 3 else text_lines
        if clean in recent_window:
            continue

        # Suppress prefix duplication common in YouTube auto captions
        if recent_window and (
            clean.startswith(recent_window[-1]) or recent_window[-1].startswith(clean)
        ):
            if len(clean) > len(recent_window[-1]):
                text_lines[-1] = clean
            continue

        text_lines.append(clean)

    return "\n".join(text_lines)


def _seconds_to_vtt_time(seconds: float) -> str:
    """Format a real ASR segment timestamp as a WebVTT timestamp."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds >= 1000:
        whole_seconds += 1
        milliseconds = 0
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _whisper_result_to_vtt(result: dict) -> str:
    """Convert timestamped segments returned by the canonical Whisper service to VTT.

    A transcript without segment timestamps is not promoted to a fabricated cue. The
    standalone workflow requires real segment coordinates so downstream clipping can
    safely align subtitles and audio.
    """
    segments = result.get("segments") if isinstance(result, dict) else None
    if not isinstance(segments, list) or not segments:
        raise TranscriptError("Whisper returned no timestamped segments.")

    cues: list[str] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        start = segment.get("start")
        end = segment.get("end")
        if not text or start is None or end is None:
            continue
        start_f, end_f = float(start), float(end)
        if end_f <= start_f:
            continue
        cues.append(
            f"{index}\n{_seconds_to_vtt_time(start_f)} --> {_seconds_to_vtt_time(end_f)}\n{text}\n"
        )

    if not cues:
        raise TranscriptError("Whisper returned no usable timestamped speech segments.")
    return "WEBVTT\n\n" + "\n".join(cues)


def download_transcript(
    request: TranscriptDownloadRequest,
    custom_runner: Optional[Callable] = None,
    whisper_transcriber: Optional[Callable[[str, Path, str], dict]] = None,
) -> TranscriptDownloadResult:
    """Execute complete transcript workflow according to capability contract."""
    if not check_ytdlp_installed() and custom_runner is None:
        raise YtDlpNotFoundError("yt-dlp is not installed on the system.")

    video_id = extract_video_id(request.url)
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: List subtitles
    list_res = list_subtitles(request.url, custom_runner=custom_runner)

    target_lang = request.target_language.lower()
    selected_track = list_res.find_track(target_lang, prefer_manual=request.prefer_manual)

    # Step 2: Fallback logic for subtitles
    source_type = CaptionSourceType.MANUAL
    download_cmd: list[str] = []

    if selected_track and not selected_track.is_auto:
        source_type = CaptionSourceType.MANUAL
        download_cmd = [
            "yt-dlp",
            "--write-sub",
            "--sub-lang",
            selected_track.language_code,
            "--skip-download",
            "--sub-format",
            "vtt",
            "-o",
            str(output_dir / "%(id)s.%(ext)s"),
            request.url,
        ]
    elif selected_track and selected_track.is_auto and request.allow_auto:
        source_type = CaptionSourceType.AUTO
        download_cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang",
            selected_track.language_code,
            "--skip-download",
            "--sub-format",
            "vtt",
            "-o",
            str(output_dir / "%(id)s.%(ext)s"),
            request.url,
        ]
    else:
        # Check if Whisper is requested
        if not request.allow_whisper:
            raise MissingCaptionsError(
                f"No captions available for video '{list_res.title}' in language '{target_lang}'. Whisper fallback not enabled."
            )

        # Estimate audio duration and size before proceeding with Whisper
        meta_cmd = ["yt-dlp", "--dump-json", "--skip-download", request.url]
        duration = 0.0
        size_mb = 0.0

        if custom_runner:
            m_res = custom_runner(meta_cmd)
            try:
                data = json.loads(m_res.get("stdout", "{}"))
                duration = float(data.get("duration", 0.0))
                # Approximate 128kbps audio size: duration * 16KB/s
                size_mb = round((duration * 16) / 1024, 2)
            except Exception:
                pass
        else:
            try:
                proc = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=20)
                if proc.returncode == 0:
                    data = json.loads(proc.stdout)
                    duration = float(data.get("duration", 0.0))
                    size_mb = round((duration * 16) / 1024, 2)
            except Exception:
                pass

        # Gated consent check
        if not request.whisper_consent:
            raise WhisperConsentRequiredError(
                duration_seconds=duration,
                estimated_audio_size_mb=size_mb,
                message=(
                    f"No captions found on YouTube for '{list_res.title}'. "
                    f"Whisper fallback requires downloading ~{size_mb} MB of audio ({round(duration / 60, 1)} minutes). "
                    "Explicit user consent required before downloading audio."
                ),
            )

        source_type = CaptionSourceType.WHISPER

    # Execute subtitle download if caption path chosen
    vtt_content = ""
    actual_lang = selected_track.language_code if selected_track else target_lang

    if source_type in (CaptionSourceType.MANUAL, CaptionSourceType.AUTO):
        if custom_runner:
            res = custom_runner(download_cmd)
            code, stderr = res.get("returncode", 0), res.get("stderr", "")
            vtt_content = res.get("vtt_content", "")
        else:
            proc = subprocess.run(download_cmd, capture_output=True, text=True, timeout=60)
            code, stderr = proc.returncode, proc.stderr

        if code != 0:
            raise classify_ytdlp_error(stderr, returncode=code)

        # Locate downloaded VTT if not directly supplied by runner
        if not vtt_content:
            expected_files = list(output_dir.glob(f"{video_id}.*.vtt"))
            if expected_files:
                vtt_content = expected_files[0].read_text(encoding="utf-8")
            else:
                raise MissingCaptionsError(
                    "yt-dlp completed successfully but no VTT file was produced."
                )
    else:
        # Whisper path: use the canonical local implementation instead of creating
        # a placeholder transcript. Consent has already been checked above.
        audio_dir = output_dir / ".whisper_audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        if whisper_transcriber is not None:
            whisper_result = whisper_transcriber(video_id, audio_dir, target_lang)
            if not whisper_result:
                raise TranscriptError("Whisper transcriber returned no result.")
            vtt_content = _whisper_result_to_vtt(whisper_result)
        else:
            if not check_whisper_installed():
                raise TranscriptError(
                    "Whisper fallback was consented to, but no supported local Whisper backend is installed."
                )
            from services.whisper_local_service import (
                download_audio,
                get_cached_whisperx_result,
                transcribe_with_whisper,
            )

            audio_path = download_audio(video_id, str(audio_dir))
            if not audio_path:
                raise TranscriptError("Whisper fallback could not download the YouTube audio.")
            transcript = transcribe_with_whisper(
                video_id=video_id,
                audio_path=audio_path,
                language=target_lang,
            )
            if not transcript:
                raise TranscriptError("Whisper fallback returned no transcript text.")
            whisper_result = get_cached_whisperx_result(video_id)
            if not whisper_result:
                raise TranscriptError("Whisper completed without a timestamped result cache.")
            vtt_content = _whisper_result_to_vtt(whisper_result)

    # Save final artifacts with sanitized filenames
    clean_title = sanitize_filename(list_res.title)
    final_vtt_name = f"{clean_title} [{video_id}].{actual_lang}.vtt"
    final_vtt_path = output_dir / final_vtt_name
    final_txt_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    created_artifacts: list[Path] = []

    try:
        final_vtt_path.write_text(vtt_content, encoding="utf-8")
        if not final_vtt_path.exists() or final_vtt_path.stat().st_size == 0:
            raise TranscriptError(f"Generated VTT artifact for {video_id} is missing or empty.")
        created_artifacts.append(final_vtt_path)

        cleaned_text = clean_vtt_to_text(vtt_content)

        if request.generate_txt:
            final_txt_name = f"{clean_title} [{video_id}].{actual_lang}.txt"
            final_txt_path = output_dir / final_txt_name
            final_txt_path.write_text(cleaned_text, encoding="utf-8")
            if not final_txt_path.exists() or final_txt_path.stat().st_size == 0:
                raise TranscriptError(f"Generated TXT artifact for {video_id} is missing or empty.")
            created_artifacts.append(final_txt_path)

        file_hash = hashlib.sha256(vtt_content.encode("utf-8")).hexdigest()
        txt_hash = (
            hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest() if final_txt_path else None
        )

        # Determine certification
        is_production_certified = bool(
            custom_runner is None and whisper_transcriber is None and len(cleaned_text) > 0
        )

        # Write deterministic manifest
        manifest_name = f"{clean_title} [{video_id}].manifest.json"
        manifest_path = output_dir / manifest_name
        manifest_data = {
            "video_id": video_id,
            "title": list_res.title,
            "source_url": request.url,
            "source_type": source_type.value,
            "language": actual_lang,
            "created_at": subprocess.run(
                ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True
            ).stdout.strip()
            if shutil.which("date")
            else "2026-11-23T00:00:00Z",
            "artifacts": {
                "vtt": {
                    "file": final_vtt_path.name,
                    "sha256": file_hash,
                    "size_bytes": final_vtt_path.stat().st_size,
                },
                "txt": {
                    "file": final_txt_path.name if final_txt_path else None,
                    "sha256": txt_hash,
                    "size_bytes": final_txt_path.stat().st_size if final_txt_path else 0,
                }
                if final_txt_path
                else None,
            },
            "character_count": len(cleaned_text),
            "line_count": len(cleaned_text.splitlines()),
            "whisper_backend": "mlx_whisper" if check_whisper_installed() else "none",
            "production_certified": is_production_certified,
            "certification_status": "CERTIFIED"
            if is_production_certified
            else "UNCERTIFIED_OR_TEST",
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        created_artifacts.append(manifest_path)
    except Exception:
        for p in created_artifacts:
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        raise

    return TranscriptDownloadResult(
        video_id=video_id,
        title=list_res.title,
        language=actual_lang,
        source_type=source_type,
        vtt_path=final_vtt_path,
        txt_path=final_txt_path,
        manifest_path=manifest_path,
        character_count=len(cleaned_text),
        line_count=len(cleaned_text.splitlines()),
        file_sha256=file_hash,
        production_certified=is_production_certified,
    )
