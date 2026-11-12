"""Canonical hash-field semantics and helpers for first-person transcripts and spans (DATA-03 / T3-03).

In vNext (schema fp-context-v2):
- `video_transcript_sha256`: SHA-256 of the whole video verbatim transcript text.
- `span_text_sha256`: SHA-256 of the span's verbatim text (equal to sha256(verbatim_text)).

In legacy/v1 schemas:
- `transcript_hash` had ambiguous meanings (clip hash in v8 vs video transcript in v10).
- `source_text_hash` was the clip hash in v10.

This helper provides unambiguous hashing and extraction for all writers and readers.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def compute_span_text_sha256(verbatim_text: str) -> str:
    """SHA-256 hex digest of the verbatim span text."""
    return hashlib.sha256(str(verbatim_text).encode("utf-8")).hexdigest()


def compute_video_transcript_sha256(transcript_text: str) -> str:
    """SHA-256 hex digest of the full video transcript."""
    return hashlib.sha256(str(transcript_text).encode("utf-8")).hexdigest()


def resolve_span_text_sha256(payload: Mapping[str, Any]) -> str:
    """Extract or verify span text hash from payload across v1 and v2 schemas."""
    return str(
        payload.get("span_text_sha256")
        or payload.get("source_text_hash")
        or payload.get("transcript_hash")
        or ""
    )


def resolve_video_transcript_sha256(payload: Mapping[str, Any]) -> str:
    """Extract video transcript hash from payload across v1 and v2 schemas."""
    return str(
        payload.get("video_transcript_sha256")
        or payload.get("video_transcript_hash")
        or payload.get("transcript_hash")
        or ""
    )
