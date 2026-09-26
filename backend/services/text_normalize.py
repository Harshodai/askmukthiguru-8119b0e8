"""De-obfuscation for safety rails: the same text a person would read.

Red team 2026-09-26: "s u i c i d e", "k1ll mysel f", "end my l1fe", "k*ll myself"
and a Cyrillic homoglyph in "suicide" all passed crisis detection and the topic
rail. Rails check the original text AND ``deobfuscate(text)`` (so this can only
add matches), and ``compact_letters`` for obfuscated input only.
"""

from __future__ import annotations

import re
import unicodedata

# Cyrillic/Greek letters that render like Latin ones. NFKC does not fold these.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
        "і": "i", "ѕ": "s", "ј": "j", "ԁ": "d", "һ": "h", "ӏ": "l", "к": "k",
        "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    }
)

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

# A digit or symbol inside a word ("k1ll", "k*ll"), or 3+ single letters spaced out.
_IN_WORD_SUBSTITUTE = re.compile(r"(?<=[a-z])[0-9@$*!|](?=[a-z])|(?<=[a-z])[0-9@$](?=\b)|\b[0-9@$](?=[a-z])")
_SPACED_LETTERS = re.compile(r"\b(?:[a-z] ){2,}[a-z]\b")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_HOMOGLYPHS).lower()


def looks_obfuscated(text: str) -> bool:
    """True when text has homoglyphs, in-word digits/symbols, or spaced-out letters."""
    folded = _fold(text)
    return (
        folded != unicodedata.normalize("NFKC", text).lower()
        or bool(_IN_WORD_SUBSTITUTE.search(folded))
        or bool(_SPACED_LETTERS.search(folded))
    )


def _undo_leet(match: re.Match[str]) -> str:
    return match.group(0).translate(_LEET).replace("*", "i").replace("!", "i").replace("|", "l")


def deobfuscate(text: str) -> str:
    """Homoglyphs folded, in-word leetspeak undone, spaced letters joined. Lowercase."""
    folded = _IN_WORD_SUBSTITUTE.sub(_undo_leet, _fold(text))
    return _SPACED_LETTERS.sub(lambda m: m.group(0).replace(" ", ""), folded)


def compact_letters(text: str) -> str:
    """Letters only ("i want to k1ll mysel f" -> "iwanttokillmyself"), for phrase checks
    that must survive split words. Only use on text where looks_obfuscated() is True:
    on plain text it joins innocent words ("i skill myself" -> "...killmyself")."""
    return re.sub(r"[^a-z]", "", deobfuscate(text))


if __name__ == "__main__":
    assert deobfuscate("s u i c i d e is it") == "suicide is it"
    assert deobfuscate("i want to k1ll mysel f") == "i want to kill mysel f"
    assert deobfuscate("I want to ѕuicide") == "i want to suicide"
    assert compact_letters("how to k*ll myself") == "howtokillmyself"
    assert looks_obfuscated("i wanna end my l1fe")
    assert not looks_obfuscated("I have 3 kids and I skill myself up")
    print("text_normalize self-check ok")
