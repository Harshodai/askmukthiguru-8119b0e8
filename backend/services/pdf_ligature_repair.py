"""Repairs the pypdf ligature-drop bug: some PDF fonts map a single ligature
glyph (fi/fl/ff/ffi/ffl) to a ToUnicode entry pypdf can't resolve, so
`page.extract_text()` emits a literal U+0000 in its place instead of the
missing letters -- "first" becomes "\x00rst", "difficult" becomes "di\x00cult".

Confirmed live 2026-09-18 against the 70 Qdrant chunks ingested from The Four
Sacred Secrets (scripts/ingestion/ingest_four_sacred_secrets.py): 52/70 chunks
carried at least one dropped ligature. Every occurrence disambiguates to
exactly one of the five standard PDF ligatures by dictionary lookup on the
surrounding word -- there is no ambiguity to resolve at runtime once the
corrupted word is known, so this is a closed lookup table built from that
corpus, not a live dictionary guesser. Update `_LIGATURE_WORD_MAP` if a new
source surfaces an unmapped corrupted word; unmapped occurrences are logged
and the NUL is stripped (never left in output), which is a visible-typo
regression but never a silent data-loss regression.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_NUL = "\x00"

# corrupted-word -> repaired-word, built by enumerating every unique
# NUL-containing token in the ingested book text and confirming the ligature
# from surrounding context (see handoff.md 2026-09-18).
_LIGATURE_WORD_MAP: dict[str, str] = {
    "\x00ash": "flash",
    "\x00ber": "fiber",
    "\x00eeting": "fleeting",
    "\x00eld": "field",
    "\x00ip": "flip",
    "\x00ipped": "flipped",
    "\x00lled": "filled",
    "\x00lm": "film",
    "\x00nal": "final",
    "\x00nally": "finally",
    "\x00nancial": "financial",
    "\x00nd": "find",
    "\x00ne": "fine",
    "\x00oating": "floating",
    "\x00ow": "flow",
    "\x00owing": "flowing",
    "\x00red": "fired",
    "\x00rst": "first",
    "\x00ve": "five",
    "Su\x00ering": "Suffering",
    "a\x00ect": "affect",
    "a\x00ected": "affected",
    "bene\x00cially": "beneficially",
    "con\x00dent": "confident",
    "con\x00icting": "conflicting",
    "de\x00nitely": "definitely",
    "di\x00cult": "difficult",
    "di\x00erence": "difference",
    "di\x00erent": "different",
    "e\x00ort": "effort",
    "e\x00ortless": "effortless",
    "e\x00ortlessness": "effortlessness",
    "e\x00orts": "efforts",
    "ful\x00ll": "fulfill",
    "ful\x00lled": "fulfilled",
    "ful\x00lling": "fulfilling",
    "magni\x00cent": "magnificent",
    "no-su\x00ering": "no-suffering",
    "o\x00": "off",
    "o\x00-kilter": "off-kilter",
    "o\x00er": "offer",
    "o\x00shore": "offshore",
    "re\x00ect": "reflect",
    "re\x00ected": "reflected",
    "re\x00ections": "reflections",
    "scienti\x00c": "scientific",
    "su\x00ering": "suffering",
    "twenty-\x00ve": "twenty-five",
    "una\x00ected": "unaffected",
}

_CORRUPT_WORD_RE = re.compile(r"[A-Za-z\x00-]*\x00[A-Za-z\x00-]*")


def repair_ligature_drops(text: str) -> str:
    """Fix known pypdf ligature-drop corruption. No-op on clean text."""
    if not text or _NUL not in text:
        return text

    def _replace(match: re.Match) -> str:
        token = match.group(0)
        fixed = _LIGATURE_WORD_MAP.get(token)
        if fixed is None:
            logger.warning("repair_ligature_drops: no mapping for corrupted token %r", token)
            return token.replace(_NUL, "")
        return fixed

    return _CORRUPT_WORD_RE.sub(_replace, text)


if __name__ == "__main__":
    _sample = "Ever since my \x00rst spiritual e\x00ort, the di\x00erence was clear."
    _fixed = repair_ligature_drops(_sample)
    assert _fixed == "Ever since my first spiritual effort, the difference was clear.", _fixed
    assert repair_ligature_drops("no ligatures here") == "no ligatures here"
    _unmapped = repair_ligature_drops("\x00unmapped\x00")
    assert "\x00" not in _unmapped and _unmapped == "unmapped", _unmapped
    print("ok:", _fixed)
