"""Watermarking & Provenance Injection Service (EU AI Act Article 50).

Provides:
1. Zero-width invisible unicode text watermarking encoding, decoding, and stripping.
2. Audio ID3 metadata & RIFF WAV chunk provenance tag injection and extraction.
3. Standardized HTTP compliance headers builder for EU AI Act Article 50.
"""

from __future__ import annotations

import json
import logging
import re
import struct
from typing import Any, Optional

from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    OriginType,
)

logger = logging.getLogger(__name__)

# Zero-width Unicode markers for text steganography
_ZW_START = "\ufeff"  # Zero-width non-breaking space (BOM) as start/end delimiter
_ZW_END = "\ufeff"
_ZW_ZERO = "\u200b"  # Zero-width space represents bit '0'
_ZW_ONE = "\u200c"  # Zero-width non-joiner represents bit '1'
_ZW_DELIMS = {"\ufeff", "\u200b", "\u200c", "\u200d", "\u200e", "\u200f"}


class WatermarkingService:
    """Service for encoding, decoding, and validating EU AI Act provenance watermarks."""

    def __init__(self, default_payload: str = "AI_GENERATED_MUKTHIGURU_V1") -> None:
        self.default_payload = default_payload

    # -------------------------------------------------------------------------
    # Text Watermarking (Zero-Width Steganography)
    # -------------------------------------------------------------------------

    @classmethod
    def encode_text_watermark(
        cls,
        text: str,
        manifest_or_payload: AIProvenanceManifest | str | dict | None = None,
    ) -> str:
        """Embed an invisible zero-width watermark into text.

        Encodes manifest or payload string into binary bits represented by zero-width
        Unicode characters, and inserts it without modifying visible text.
        """
        if not text:
            return text

        if isinstance(manifest_or_payload, AIProvenanceManifest):
            data = {
                "artifact_id": manifest_or_payload.artifact_id,
                "origin_type": manifest_or_payload.origin_type.value,
                "model_name": manifest_or_payload.agent.model_name
                or manifest_or_payload.model_name
                or "AskMukthiGuru AI",
                "watermark_signature": manifest_or_payload.watermark_signature or "sig:zw-001",
            }
            payload_str = json.dumps(data)
        elif isinstance(manifest_or_payload, dict):
            payload_str = json.dumps(manifest_or_payload)
        elif isinstance(manifest_or_payload, str):
            payload_str = manifest_or_payload
        else:
            payload_str = "AI_GENERATED_MUKTHIGURU_V1"

        # Convert string to binary representation
        payload_bytes = payload_str.encode("utf-8")
        bits = "".join(f"{b:08b}" for b in payload_bytes)

        # Convert bits to zero-width characters
        zw_stream = "".join(_ZW_ZERO if bit == "0" else _ZW_ONE for bit in bits)
        watermark_sequence = f"{_ZW_START}{zw_stream}{_ZW_END}"

        # If already watermarked, strip previous watermark first
        clean_text = cls.strip_text_watermark(text)

        # Append zero-width watermark sequence at the end of text (invisible to user)
        return clean_text + watermark_sequence

    @classmethod
    def decode_text_watermark(cls, text: str) -> Optional[dict[str, Any] | str]:
        """Extract and decode a zero-width watermark payload from text.

        Returns decoded dict (if JSON payload) or string, or None if no valid watermark found.
        """
        if not text:
            return None

        # Look for content between _ZW_START and _ZW_END delimiters
        pattern = re.compile(f"{_ZW_START}([{_ZW_ZERO}{_ZW_ONE}]+){_ZW_END}")
        match = pattern.search(text)

        if not match:
            # Fallback: find any contiguous cluster of zero/one chars (min 8 chars)
            fallback_pattern = re.compile(f"([{_ZW_ZERO}{_ZW_ONE}]{{8,}})")
            fallback_match = fallback_pattern.search(text)
            if not fallback_match:
                return None
            zw_chars = fallback_match.group(1)
        else:
            zw_chars = match.group(1)

        # Convert zero-width chars to binary bits
        bits = "".join("0" if c == _ZW_ZERO else "1" for c in zw_chars)

        # Bits length must be multiple of 8
        valid_bits_len = (len(bits) // 8) * 8
        if valid_bits_len == 0:
            return None
        bits = bits[:valid_bits_len]

        # Convert bits to bytes
        byte_list = bytearray()
        for i in range(0, len(bits), 8):
            byte_val = int(bits[i : i + 8], 2)
            byte_list.append(byte_val)

        try:
            decoded_str = byte_list.decode("utf-8")
            try:
                parsed_json = json.loads(decoded_str)
                if isinstance(parsed_json, dict):
                    return parsed_json
            except (json.JSONDecodeError, ValueError):
                pass
            return decoded_str
        except UnicodeDecodeError:
            logger.debug("Failed to decode watermark bytes to UTF-8 string")
            return None

    @classmethod
    def has_watermark(cls, text: str) -> bool:
        """Check if text contains a valid zero-width watermark."""
        return cls.decode_text_watermark(text) is not None

    @classmethod
    def strip_text_watermark(cls, text: str) -> str:
        """Remove all zero-width watermark characters from text."""
        if not text:
            return text
        return "".join(c for c in text if c not in _ZW_DELIMS)

    @classmethod
    def strip_watermark(cls, text: str) -> str:
        """Alias for strip_text_watermark."""
        return cls.strip_text_watermark(text)

    # -------------------------------------------------------------------------
    # Audio Watermarking (ID3 & RIFF WAV Tag Injection)
    # -------------------------------------------------------------------------

    @classmethod
    def inject_audio_provenance(
        cls,
        audio_bytes: bytes,
        manifest: AIProvenanceManifest,
        format: str = "mp3",
    ) -> bytes:
        """Inject structured ID3v2 metadata provenance tags into audio bytes."""
        if not audio_bytes:
            return audio_bytes

        # Build tag dictionary
        is_ai = manifest.origin_type in (
            OriginType.AI_GENERATED,
            OriginType.AI_SYNTHESIZED,
            OriginType.AI_ASSISTED,
        )
        model_name = manifest.agent.model_name or manifest.model_name or "AskMukthiGuru AI"
        disclosure = (
            manifest.disclosure_statement
            or manifest.disclaimer
            or "This content was generated by AskMukthiGuru AI assistant in compliance with EU AI Act Article 50 transparency obligations."
        )

        tags = {
            "AI_GENERATED": "true" if is_ai else "false",
            "AI_MODEL": model_name,
            "PROVENANCE_ID": manifest.artifact_id,
            "EU_AI_ACT_DISCLOSURE": disclosure,
        }

        # Construct ID3v2.4 frame bytes
        frames_bytes = bytearray()
        for key, val in tags.items():
            desc_bytes = key.encode("utf-8") + b"\x00"
            val_bytes = val.encode("utf-8")
            body = b"\x03" + desc_bytes + val_bytes  # 0x03 = UTF-8 encoding

            # Frame Header: ID(4) + SyncsafeSize(4) + Flags(2)
            frame_id = b"TXXX"
            frame_len = len(body)
            # Encode syncsafe integer for ID3v2.4
            syncsafe_size = bytes(
                [
                    (frame_len >> 21) & 0x7F,
                    (frame_len >> 14) & 0x7F,
                    (frame_len >> 7) & 0x7F,
                    frame_len & 0x7F,
                ]
            )
            frame_flags = b"\x00\x00"
            frames_bytes.extend(frame_id + syncsafe_size + frame_flags + body)

        # ID3 Header: "ID3" + Version 2.4(0x04, 0x00) + Flags(0x00) + SyncsafeSize(4)
        total_len = len(frames_bytes)
        id3_syncsafe_size = bytes(
            [
                (total_len >> 21) & 0x7F,
                (total_len >> 14) & 0x7F,
                (total_len >> 7) & 0x7F,
                total_len & 0x7F,
            ]
        )
        id3_tag = b"ID3\x04\x00\x00" + id3_syncsafe_size + bytes(frames_bytes)

        fmt_lower = format.lower() if format else "mp3"

        if fmt_lower == "wav" and audio_bytes.startswith(b"RIFF"):
            # Inject "id3 " RIFF chunk before final data or at end
            id3_chunk_id = b"id3 "
            id3_chunk_len = struct.pack("<I", len(id3_tag))
            # Pad if odd length per RIFF specification
            id3_chunk = (
                id3_chunk_id + id3_chunk_len + id3_tag + (b"\x00" if len(id3_tag) % 2 != 0 else b"")
            )
            new_wav = audio_bytes[:12] + id3_chunk + audio_bytes[12:]
            # Update RIFF size in header (total size - 8)
            new_total_size = len(new_wav) - 8
            new_wav = new_wav[:4] + struct.pack("<I", new_total_size) + new_wav[8:]
            return new_wav

        # Default MP3/audio stream: prepend ID3 tag
        # Strip existing ID3 header if present
        clean_audio = audio_bytes
        if clean_audio.startswith(b"ID3") and len(clean_audio) >= 10:
            tag_size = (
                ((clean_audio[6] & 0x7F) << 21)
                | ((clean_audio[7] & 0x7F) << 14)
                | ((clean_audio[8] & 0x7F) << 7)
                | (clean_audio[9] & 0x7F)
            )
            clean_audio = clean_audio[10 + tag_size :]

        return id3_tag + clean_audio

    @classmethod
    def extract_audio_provenance(cls, audio_bytes: bytes) -> dict[str, str]:
        """Extract provenance metadata tags from ID3v2 or RIFF WAV audio bytes."""
        if not audio_bytes:
            return {}

        results: dict[str, str] = {}

        # Search for ID3 tag start
        id3_offset = audio_bytes.find(b"ID3")
        if id3_offset == -1:
            return results

        id3_header = audio_bytes[id3_offset : id3_offset + 10]
        if len(id3_header) < 10:
            return results

        tag_size = (
            ((id3_header[6] & 0x7F) << 21)
            | ((id3_header[7] & 0x7F) << 14)
            | ((id3_header[8] & 0x7F) << 7)
            | (id3_header[9] & 0x7F)
        )

        id3_payload = audio_bytes[id3_offset + 10 : id3_offset + 10 + tag_size]

        # Scan for TXXX frames
        pos = 0
        while pos + 10 <= len(id3_payload):
            if id3_payload[pos : pos + 4] == b"TXXX":
                frame_len = (
                    ((id3_payload[pos + 4] & 0x7F) << 21)
                    | ((id3_payload[pos + 5] & 0x7F) << 14)
                    | ((id3_payload[pos + 6] & 0x7F) << 7)
                    | (id3_payload[pos + 7] & 0x7F)
                )
                frame_body = id3_payload[pos + 10 : pos + 10 + frame_len]
                if frame_body and len(frame_body) > 1:
                    # Skip encoding byte at index 0
                    raw_content = frame_body[1:]
                    null_idx = raw_content.find(b"\x00")
                    if null_idx != -1:
                        key = raw_content[:null_idx].decode("utf-8", errors="ignore")
                        val = raw_content[null_idx + 1 :].decode("utf-8", errors="ignore")
                        if key:
                            results[key] = val
                pos += 10 + frame_len
            else:
                pos += 1

        return results

    # -------------------------------------------------------------------------
    # HTTP Compliance Header Builder
    # -------------------------------------------------------------------------

    @classmethod
    def build_http_provenance_headers(
        cls,
        manifest: AIProvenanceManifest,
    ) -> dict[str, str]:
        """Build standard EU AI Act Article 50 HTTP headers from an AIProvenanceManifest."""
        is_ai = manifest.origin_type in (
            OriginType.AI_GENERATED,
            OriginType.AI_SYNTHESIZED,
            OriginType.AI_ASSISTED,
        )
        model_name = manifest.agent.model_name or manifest.model_name or "AskMukthiGuru AI"
        risk_val = (
            manifest.risk_tier.value
            if hasattr(manifest.risk_tier, "value")
            else str(manifest.risk_tier)
        )

        return {
            "X-AI-Generated": "true" if is_ai else "false",
            "X-AI-Origin": manifest.origin_type.value,
            "X-AI-Model": model_name,
            "X-AI-Compliance": f"EU-AI-Act-Art50; risk_tier={risk_val}",
            "X-AI-Provenance-ID": manifest.artifact_id,
        }

    def build_compliance_headers(
        self,
        manifest: Optional[AIProvenanceManifest] = None,
        origin_type: str | OriginType = OriginType.AI_GENERATED,
        model_name: Optional[str] = None,
        watermarked: bool = True,
    ) -> dict[str, str]:
        """Instance alias / builder for compatibility."""
        if manifest:
            headers = self.build_http_provenance_headers(manifest)
            headers["X-Content-Watermarked"] = "true" if watermarked else "false"
            headers["X-EU-AI-Act-Compliance"] = "Article-50-Transparency"
            headers["X-Provenance-Schema"] = manifest.schema_version
            headers["X-AI-Origin-Type"] = manifest.origin_type.value
            return headers

        resolved_origin = origin_type.value if hasattr(origin_type, "value") else str(origin_type)
        is_ai = resolved_origin in (
            OriginType.AI_GENERATED.value,
            OriginType.AI_SYNTHESIZED.value,
            OriginType.AI_ASSISTED.value,
        )

        return {
            "X-AI-Generated": "true" if is_ai else "false",
            "X-AI-Origin": resolved_origin,
            "X-AI-Origin-Type": resolved_origin,
            "X-AI-Model": model_name or "AskMukthiGuru AI",
            "X-AI-Compliance": "EU-AI-Act-Art50; risk_tier=transparency_art50",
            "X-EU-AI-Act-Compliance": "Article-50-Transparency",
            "X-Provenance-Schema": "1.0",
            "X-Content-Watermarked": "true" if watermarked else "false",
        }


_GLOBAL_WATERMARKING_SERVICE: WatermarkingService | None = None


def get_watermarking_service() -> WatermarkingService:
    """Return singleton instance of WatermarkingService."""
    global _GLOBAL_WATERMARKING_SERVICE
    if _GLOBAL_WATERMARKING_SERVICE is None:
        _GLOBAL_WATERMARKING_SERVICE = WatermarkingService()
    return _GLOBAL_WATERMARKING_SERVICE
