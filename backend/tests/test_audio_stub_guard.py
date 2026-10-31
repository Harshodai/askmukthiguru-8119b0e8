"""
Tests for Audio Extraction Guard — DE-3.3 (AGENTS.md X21)

Tests fast failure on empty/header-only WAV stubs (specifically the 86-byte stub class)
and successful validation on valid synthetic PCM WAV audio files.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from ingest.audio_guard import (
    REASON_AUDIO_STUB,
    AudioStubError,
    parse_wav_header,
    validate_audio_pcm,
)


def _create_valid_wav(path: Path, duration_s: float = 1.0, sample_rate: int = 16000) -> None:
    """Create a valid mono 16-bit 16kHz PCM WAV file with real sample data."""
    num_samples = int(duration_s * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        # Write real 16-bit zero PCM frames
        wav_file.writeframes(b"\x00\x00" * num_samples)


def _create_86_byte_stub(path: Path) -> None:
    """Create an exact 86-byte WAV stub that declares a duration but has no PCM data."""
    riff_size = 86 - 8
    # Standard 44-byte WAV header declaring 32000 bytes of PCM data
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM format
        1,  # mono
        16000,  # sample rate
        32000,  # byte rate (16000 * 2)
        2,  # block align
        16,  # 16-bit
        b"data",
        32000,  # declares 32000 bytes of PCM
    )
    # 44 bytes header + 42 bytes stub padding = exactly 86 bytes (no PCM bytes on disk)
    padding = b"\x00" * 42
    with open(path, "wb") as f:
        f.write(header)
        f.write(padding)
    assert path.stat().st_size == 86


def test_86_byte_wav_stub_fails_fast(tmp_path: Path) -> None:
    """AGENTS.md X21: 86-byte WAV stubs must fail fast with classified reason."""
    stub_file = tmp_path / "stub_video.wav"
    _create_86_byte_stub(stub_file)

    # 1. Verify it raises AudioStubError with reason audio_stub_no_pcm_data
    with pytest.raises(AudioStubError) as exc_info:
        validate_audio_pcm(stub_file)

    err = exc_info.value
    assert err.reason == REASON_AUDIO_STUB
    assert "audio_stub_no_pcm_data" in str(err)
    assert isinstance(err, ValueError)
    assert isinstance(err, RuntimeError)

    # 2. Verify boolean non-raising mode returns classified reason
    valid, reason = validate_audio_pcm(stub_file, raise_on_error=False)
    assert valid is False
    assert reason == REASON_AUDIO_STUB


def test_valid_synthetic_pcm_wav_passes(tmp_path: Path) -> None:
    """Valid synthetic PCM WAV file passes validation."""
    wav_file = tmp_path / "valid_audio.wav"
    _create_valid_wav(wav_file, duration_s=2.0, sample_rate=16000)

    # File size should be ~64044 bytes (44 bytes header + 64000 PCM bytes)
    assert wav_file.stat().st_size > 60000

    valid, reason = validate_audio_pcm(wav_file, declared_duration_s=2.0)
    assert valid is True
    assert reason == "valid_pcm"

    # Also test parse_wav_header directly
    header = parse_wav_header(wav_file)
    assert header is not None
    assert header["sample_rate"] == 16000
    assert header["channels"] == 1
    assert header["bits_per_sample"] == 16
    assert header["audio_complete"] is True
    assert header["actual_pcm_bytes"] >= 64000


def test_pcm_declared_duration_mismatch(tmp_path: Path) -> None:
    """A file with only 1 second of PCM cannot support a declared duration of 60 seconds."""
    wav_file = tmp_path / "short_audio.wav"
    _create_valid_wav(wav_file, duration_s=1.0, sample_rate=16000)

    # Declaring 60.0s when only 1.0s exists should be caught as inconsistent stub
    with pytest.raises(AudioStubError) as exc_info:
        validate_audio_pcm(wav_file, declared_duration_s=60.0)

    assert exc_info.value.reason == REASON_AUDIO_STUB
    assert "audio_stub_no_pcm_data" in str(exc_info.value)


def test_nonexistent_file_raises_stub_error(tmp_path: Path) -> None:
    """Nonexistent audio file raises AudioStubError."""
    missing = tmp_path / "missing_file.wav"
    with pytest.raises(AudioStubError) as exc_info:
        validate_audio_pcm(missing)
    assert exc_info.value.reason == REASON_AUDIO_STUB


def test_empty_or_tiny_stub_file(tmp_path: Path) -> None:
    """Arbitrary file under 128 bytes fails fast as stub."""
    tiny_file = tmp_path / "tiny.m4a"
    tiny_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert tiny_file.stat().st_size <= 128

    with pytest.raises(AudioStubError) as exc_info:
        validate_audio_pcm(tiny_file)
    assert exc_info.value.reason == REASON_AUDIO_STUB
