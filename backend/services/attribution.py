"""Speaker-attribution rule shared by every backend path that writes a teacher's
name next to a quote (L-NO-INVENTED-CREDIT-1, L-PROVENANCE-ISVERBATIM-1).

Python mirror of ``resolveAttributionLabel`` in ``src/lib/chat/types.ts``.
``is_verbatim`` proves the text is an exact transcript substring, NOT who
spoke it, so it never appears here.

Rule:
  - explicit ``speaker_verified is True`` keeps the speaker;
  - a bare teacher name is kept for the teachers' own channels;
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

# Mirrors TEACHER_OWNED_CHANNELS in src/lib/chat/types.ts (compared lower-case).
TEACHER_OWNED_CHANNELS = frozenset({"sri preethaji & sri krishnaji", "ekam", "o&o academy"})
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
    if known and ch.lower() in TEACHER_OWNED_CHANNELS:
        return name
    if route_gated and speaker_verified is not False and not known:
        return name
    if known:
        return f"shared in {ch}"
    return "unverified clip"


if __name__ == "__main__":  # ponytail: self-check
    assert resolve_attribution_label("Sri Krishnaji", None, "Some Vlog") == "shared in Some Vlog"
    assert resolve_attribution_label("Sri Krishnaji", True, "Some Vlog") == "Sri Krishnaji"
    assert resolve_attribution_label("Sri Krishnaji") == "unverified clip"
    print("attribution self-check passed")
