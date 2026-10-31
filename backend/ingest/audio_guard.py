"""
Audio Extraction Guard — DE-3.3 (AGENTS.md X21)

Validates audio files (specifically PCM WAV and downloaded audio streams)
to fail fast on empty/header-only stubs (e.g. 86-byte WAV stubs) before
costly ASR/Whisper transcription and embedding.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minimum file size for any viable audio file (WAV headers alone are 44-86+ bytes)
MIN_AUDIO_FILE_SIZE_BYTES = 128
REASON_AUDIO_STUB = "audio_stub_no_pcm_data"


class AudioStubError(ValueError, RuntimeError):
    """Raised when an audio file is an empty or truncated stub without valid PCM data."""

    def __init__(self, message: str, reason: str = REASON_AUDIO_STUB):
        super().__init__(f"{message} (classification: {reason})")
        self.reason = reason


def parse_wav_header(path: Path) -> dict[str, Any] | None:
    """Parse a RIFF/WAVE header using standard library only.

    Returns details on channels, sample_rate, bits_per_sample, data_bytes,
    data_offset, duration_s, and whether actual PCM data exists on disk.
    """
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            header = handle.read(12)
            if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
                return None
            channels = sample_rate = bits = None
            data_bytes: int | None = None
            data_offset: int | None = None
            offset = 12
            while True:
                handle.seek(offset)
                chunk_header = handle.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[0:4]
                chunk_size = int.from_bytes(chunk_header[4:8], "little")
                body_offset = offset + 8
                if chunk_id == b"fmt ":
                    fmt = handle.read(min(chunk_size, 16))
                    if len(fmt) >= 16:
                        channels = int.from_bytes(fmt[2:4], "little")
                        sample_rate = int.from_bytes(fmt[4:8], "little")
                        bits = int.from_bytes(fmt[14:16], "little")
                elif chunk_id == b"data":
                    data_bytes = chunk_size
                    data_offset = body_offset
                    break
                offset = body_offset + chunk_size + (chunk_size % 2)
    except OSError:
        return None

    if not sample_rate or not channels or not bits or data_bytes is None:
        return None
    bytes_per_second = float(sample_rate) * float(channels) * (float(bits) / 8.0)
    if bytes_per_second <= 0:
        return None
    duration_s = float(data_bytes) / bytes_per_second
    actual_pcm_bytes = max(0, file_size - data_offset) if data_offset is not None else 0
    return {
        "path": str(path),
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "bits_per_sample": int(bits),
        "declared_data_bytes": int(data_bytes),
        "data_offset": data_offset,
        "file_bytes": int(file_size),
        "actual_pcm_bytes": actual_pcm_bytes,
        "duration_s": duration_s,
        "bytes_per_second": bytes_per_second,
        "audio_complete": bool(
            data_offset is not None and actual_pcm_bytes >= data_bytes and actual_pcm_bytes > 0
        ),
    }


def validate_audio_pcm(
    file_path: Path | str,
    declared_duration_s: float | None = None,
    raise_on_error: bool = True,
) -> tuple[bool, str]:
    """Validate that an audio file contains actual PCM audio bytes and is not an empty stub.

    Args:
        file_path: Path to the audio file.
        declared_duration_s: Optional declared duration in seconds (from metadata or ASR).
        raise_on_error: If True, raises AudioStubError on invalid audio; if False, returns (False, reason).

    Returns:
        tuple[bool, str]: (True, "valid_pcm") if valid.

    Raises:
        AudioStubError: If the file is a stub, empty, or inconsistent with declared duration.
    """
    path = Path(file_path)
    if not path.exists():
        err = AudioStubError(f"Audio file does not exist: {path}", reason=REASON_AUDIO_STUB)
        if raise_on_error:
            raise err
        return False, REASON_AUDIO_STUB

    if not path.is_file():
        err = AudioStubError(f"Audio path is not a file: {path}", reason=REASON_AUDIO_STUB)
        if raise_on_error:
            raise err
        return False, REASON_AUDIO_STUB

    file_size = path.stat().st_size

    # Check 1: File size threshold (stubs such as 86-byte WAV stubs)
    if file_size <= MIN_AUDIO_FILE_SIZE_BYTES:
        err = AudioStubError(
            f"Audio file is a stub: size is {file_size} bytes (<= {MIN_AUDIO_FILE_SIZE_BYTES} bytes): {path}",
            reason=REASON_AUDIO_STUB,
        )
        if raise_on_error:
            raise err
        return False, REASON_AUDIO_STUB

    # Check 2: WAV structure check
    header = parse_wav_header(path)
    if header is not None:
        # It's a RIFF WAVE file
        actual_pcm = header["actual_pcm_bytes"]
        if actual_pcm == 0 or header["declared_data_bytes"] == 0:
            err = AudioStubError(
                f"WAV file has zero actual PCM data bytes (file size: {file_size}): {path}",
                reason=REASON_AUDIO_STUB,
            )
            if raise_on_error:
                raise err
            return False, REASON_AUDIO_STUB

        if not header["audio_complete"]:
            err = AudioStubError(
                f"WAV declared {header['declared_data_bytes']} PCM bytes but only {actual_pcm} exist on disk: {path}",
                reason=REASON_AUDIO_STUB,
            )
            if raise_on_error:
                raise err
            return False, REASON_AUDIO_STUB

        # Consistency with declared duration if provided
        if declared_duration_s is not None and declared_duration_s > 1.0:
            expected_bytes = declared_duration_s * header["bytes_per_second"]
            # For PCM, actual bytes must reasonably cover the declared duration
            if actual_pcm < expected_bytes * 0.5:
                err = AudioStubError(
                    f"PCM bytes ({actual_pcm}) cannot support declared duration {declared_duration_s:.1f}s "
                    f"(expected ~{expected_bytes:.0f} bytes at {header['sample_rate']}Hz {header['bits_per_sample']}-bit): {path}",
                    reason=REASON_AUDIO_STUB,
                )
                if raise_on_error:
                    raise err
                return False, REASON_AUDIO_STUB
    else:
        # Non-WAV file (e.g. m4a, mp3)
        if declared_duration_s is not None and declared_duration_s > 1.0:
            # Even highly compressed 16kbps audio needs at least ~1000 bytes/sec
            min_expected_bytes = declared_duration_s * 500  # conservative 4kbps lower bound
            if file_size < min_expected_bytes:
                err = AudioStubError(
                    f"Audio file size ({file_size} bytes) cannot support declared duration {declared_duration_s:.1f}s: {path}",
                    reason=REASON_AUDIO_STUB,
                )
                if raise_on_error:
                    raise err
                return False, REASON_AUDIO_STUB

    return True, "valid_pcm"
