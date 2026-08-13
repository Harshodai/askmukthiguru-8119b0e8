"""Preserve answer citation markers across every provider translation path."""
from __future__ import annotations

import re

_CITATION_MARKER = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")


def citation_numbers(text: str) -> list[str]:
    """Return unique citation numbers in first-seen order."""
    numbers: list[str] = []
    for group in _CITATION_MARKER.findall(text or ""):
        for value in group.split(","):
            number = value.strip()
            if number and number not in numbers:
                numbers.append(number)
    return numbers


def restore_citation_markers(source_text: str, translated_text: str) -> str:
    """Append source markers missing from translation without altering sources."""
    translated = (translated_text or "").strip()
    missing: list[str] = []
    present = citation_numbers(translated)
    for number in citation_numbers(source_text):
        if number not in present:
            missing.append(number)
    if not missing:
        return translated
    return "{} {}".format(translated.rstrip(), " ".join("[{}]".format(n) for n in missing)).strip()
