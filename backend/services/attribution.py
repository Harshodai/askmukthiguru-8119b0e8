"""Speaker-attribution rule shared by every backend path that writes a teacher's
name next to a quote (L-NO-INVENTED-CREDIT-1, L-PROVENANCE-ISVERBATIM-1).

Python mirror of ``resolveAttributionLabel`` in ``src/lib/chat/types.ts``.
``is_verbatim`` proves the text is an exact transcript substring, NOT who
spoke it, so it never appears here.

Rule:
  - explicit ``speaker_verified is True`` keeps the speaker;
  - a bare teacher name is NOT kept just because the clip sits on a teacher-owned channel
    (owner ruling 2026-10-16: host and guest speech share those channels; host speech was
    6.9% of top clips), so an unverified clip reads ``shared in <channel>``;
  - otherwise it is downgraded to ``shared in <channel>`` (known third-party
    source) or ``unverified clip`` (unknown source);
  - ``route_gated=True`` (clips that already passed FirstPersonPipeline's
    allowlist + sha256 + voice gate) keeps the name when the payload carries
    no contrary evidence: no explicit ``speaker_verified is False`` and no
    third-party channel.
"""

from __future__ import annotations

import re
from typing import Optional

_TEACHER_NAME_RE = re.compile(r"\bsri\s+(preetha|krishna)ji\b", re.IGNORECASE)
_UNKNOWN_SOURCE_RE = re.compile(r"^\s*(unknown|n/a|none|-)\b", re.IGNORECASE)


def is_known_channel(channel: Optional[str]) -> bool:
    c = (channel or "").strip()
    return bool(c) and not _UNKNOWN_SOURCE_RE.match(c)


def resolve_attribution_label(
    speaker: Optional[str],
    speaker_verified: Optional[bool] = None,
    channel: Optional[str] = None,
    route_gated: bool = False,
) -> Optional[str]:
    name = (speaker or "").strip()
    if not name:
        return None
    if speaker_verified is True:
        return name
    if not _TEACHER_NAME_RE.search(name):
        return name
    ch = (channel or "").strip()
    known = is_known_channel(ch)
    if route_gated and speaker_verified is not False and not known:
        return name
    if known:
        return f"shared in {ch}"
    return "unverified clip"


# Payload placeholders that name nobody ("Unknown", "Unknown Channel",
# "Unknown Speaker", ...). Live 2026-10-11: a doctrine citation reached the
# wire with speaker "Unknown" because the public citation contract
# (rag/nodes/generation.py::_sanitize_citations) passed the Qdrant payload
# speaker through verbatim. Placeholders must be omitted (None) -- never
# surfaced as the teacher -- so the UI falls back to its existing
# shared-channel/unverified-clip label path.
_PLACEHOLDER_SPEAKER_RE = re.compile(
    r"^\s*(unknown(\s+(channel|speaker))?|speaker\s+unknown|n/a|none|-)\s*$",
    re.IGNORECASE,
)


def clean_wire_speaker(
    speaker: Optional[str],
    speaker_verified: Optional[bool] = None,
    channel: Optional[str] = None,
) -> Optional[str]:
    """Wire-level speaker for the public citation contract.

    Returns a verified teacher name, an already-downgraded label
    ("shared in <channel>", "unverified clip"), or None (omit the field).
    Placeholders and unverified bare names are omitted rather than
    surfaced: a wrongly named speaker is worse than none, and the frontend
    resolves the display label from speaker/speakerVerified/channel itself.
    Idempotent: downgraded labels pass through unchanged.
    """
    name = (speaker or "").strip()
    if not name or _PLACEHOLDER_SPEAKER_RE.match(name):
        return None
    if speaker_verified is True:
        return name
    lowered = name.lower()
    if lowered.startswith("shared in ") or lowered == "unverified clip":
        return name
    resolved = resolve_attribution_label(name, speaker_verified, channel)
    if resolved is None or _PLACEHOLDER_SPEAKER_RE.match(resolved):
        return None
    # Only a downgrade label (never a bare teacher name, never a channel
    # handle or other raw payload text) may ship unverified.
    if resolved == name and _TEACHER_NAME_RE.search(name):
        return None
    if resolved != name:
        return resolved
    return None


if __name__ == "__main__":  # ponytail: self-check
    assert resolve_attribution_label("Sri Krishnaji", None, "Some Vlog") == "shared in Some Vlog"
    assert resolve_attribution_label("Sri Krishnaji", True, "Some Vlog") == "Sri Krishnaji"
    assert resolve_attribution_label("Sri Krishnaji") == "unverified clip"
    assert clean_wire_speaker("Sri Preethaji", True) == "Sri Preethaji"
    assert clean_wire_speaker("Unknown") is None
    assert clean_wire_speaker("Unknown Channel") is None
    assert clean_wire_speaker("Sri Krishnaji", False, "Some Vlog") == "shared in Some Vlog"
    assert clean_wire_speaker("Sri Krishnaji") == "unverified clip"
    assert clean_wire_speaker("pkconsciousness") is None
    assert clean_wire_speaker("shared in Some Vlog") == "shared in Some Vlog"
    print("attribution self-check passed")
