"""Transcription Provider Protocol — defines the contract for transcription backends.

Covers batch transcription of local audio files (MLX Whisper, YouTube caption
hybrid) and realtime chunk transcription (browser voice input / WebSocket),
returning plain text rather than segment dicts.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class TranscriptionProvider(Protocol):
    """Unified interface for speech-to-text providers (MLX Whisper, Sarvam Cloud STT, etc.)."""

    def transcribe(
        self,
        audio_path: str,
        *,
        video_id: str = "",
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Transcribe a local audio file and return the full text.

        Args:
            audio_path: filesystem path to the audio file
            video_id: optional YouTube video id for caption-hybrid lookups
            language: optional BCP-47 language hint (e.g. "en", "hi")
            model: optional model override (e.g. Whisper model size)

        Returns:
            Full transcript text, or None if transcription failed.
        """
        ...

    def transcribe_realtime(
        self,
        audio_bytes: bytes,
        *,
        language: Optional[str] = None,
    ) -> str:
        """Transcribe a small audio chunk for realtime / WebSocket use.

        Args:
            audio_bytes: raw audio bytes captured in the browser
            language: optional BCP-47 language hint

        Returns:
            Transcribed text for the chunk (empty string if nothing decoded).
        """
        ...

    def health_check(self) -> bool:
        """Return True if the transcription provider is reachable and ready."""
        ...