"""Models and typed exceptions for the standalone YouTube Transcript pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CaptionSourceType(str, Enum):
    MANUAL = "manual"
    AUTO = "auto_generated"
    WHISPER = "whisper_fallback"


class TranscriptErrorCode(str, Enum):
    INVALID_URL = "invalid_url"
    YTDLP_NOT_FOUND = "ytdlp_not_found"
    PRIVATE_VIDEO = "private_video"
    AGE_RESTRICTED = "age_restricted"
    GEO_BLOCKED = "geo_blocked"
    MISSING_CAPTIONS = "missing_captions"
    WHISPER_CONSENT_REQUIRED = "whisper_consent_required"
    SUBPROCESS_FAILED = "subprocess_failed"
    NETWORK_ERROR = "network_error"
    DISK_ERROR = "disk_error"


class TranscriptError(Exception):
    """Base exception for transcript errors."""

    def __init__(self, message: str, code: TranscriptErrorCode = TranscriptErrorCode.SUBPROCESS_FAILED, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class InvalidURLError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.INVALID_URL, details)


class YtDlpNotFoundError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.YTDLP_NOT_FOUND, details)


class PrivateVideoError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.PRIVATE_VIDEO, details)


class AgeRestrictedError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.AGE_RESTRICTED, details)


class GeoBlockedError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.GEO_BLOCKED, details)


class MissingCaptionsError(TranscriptError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, TranscriptErrorCode.MISSING_CAPTIONS, details)


class WhisperConsentRequiredError(TranscriptError):
    def __init__(self, duration_seconds: float, estimated_audio_size_mb: float, message: str):
        details = {
            "duration_seconds": duration_seconds,
            "estimated_audio_size_mb": estimated_audio_size_mb,
            "requires_confirmation": True,
        }
        super().__init__(message, TranscriptErrorCode.WHISPER_CONSENT_REQUIRED, details)
        self.duration_seconds = duration_seconds
        self.estimated_audio_size_mb = estimated_audio_size_mb


@dataclass(frozen=True)
class SubtitleTrack:
    """Represents an individual subtitle or caption track."""
    language_code: str
    name: str
    extension: str = "vtt"
    is_auto: bool = False
    url: Optional[str] = None


@dataclass
class SubtitleListResult:
    """Result of listing available subtitles for a video."""
    video_id: str
    title: str
    manual_subtitles: list[SubtitleTrack] = field(default_factory=list)
    auto_subtitles: list[SubtitleTrack] = field(default_factory=list)

    @property
    def has_manual(self) -> bool:
        return len(self.manual_subtitles) > 0

    @property
    def has_auto(self) -> bool:
        return len(self.auto_subtitles) > 0

    def find_track(self, lang_code: str, prefer_manual: bool = True) -> Optional[SubtitleTrack]:
        """Find best matching track for a language code (e.g., 'en', 'en-US', 'hi')."""
        norm_code = lang_code.lower().split("-")[0]
        if prefer_manual:
            for track in self.manual_subtitles:
                if track.language_code.lower() == lang_code.lower() or track.language_code.lower().startswith(norm_code):
                    return track
        for track in self.auto_subtitles:
            if track.language_code.lower() == lang_code.lower() or track.language_code.lower().startswith(norm_code):
                return track
        if not prefer_manual and self.manual_subtitles:
            for track in self.manual_subtitles:
                if track.language_code.lower() == lang_code.lower() or track.language_code.lower().startswith(norm_code):
                    return track
        return None


@dataclass
class TranscriptDownloadRequest:
    """Input parameters for downloading a transcript."""
    url: str
    target_language: str = "en"
    prefer_manual: bool = True
    allow_auto: bool = True
    allow_whisper: bool = False
    whisper_consent: bool = False
    output_dir: Path = field(default_factory=lambda: Path("outputs/transcripts"))
    generate_txt: bool = True


@dataclass
class TranscriptDownloadResult:
    """Final artifact deliverable for a downloaded transcript."""
    video_id: str
    title: str
    language: str
    source_type: CaptionSourceType
    vtt_path: Path
    txt_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    character_count: int = 0
    line_count: int = 0
    duration_seconds: Optional[float] = None
    file_sha256: str = ""
    production_certified: bool = False
