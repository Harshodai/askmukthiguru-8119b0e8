"""
OKF Quality Filter Service
--------------------------
Validates generated OKF markdown entries to ensure highest format and data quality.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Text that proves an entry is a machine artifact rather than a teaching. All of these
# were found live in memory/okf/: RAPTOR debug headers, unresolved provenance, and —
# worst — the extraction LLM's own commentary about its prompt ("The user wants me to
# analyze a spiritual teaching and list the top 3-5 distinct topics"). Every OKF entry
# is embedded and injected verbatim into answers, so this text gets cited to a seeker
# as the gurus' words. generation.py's own prompt (rule 6) forbids exposing exactly it.
#
# The shared table in ``services.text_quality_filter`` is the source of truth. The
# 2026-08-01 corpus audit proved these same artifacts reach BOTH the OKF bundle and
# the 89k-chunk Qdrant corpus, and maintaining two separate lists is exactly how the
# corpus ended up unguarded. A pattern added to the shared table is now enforced at
# every persistence point; only OKF-markdown-specific shapes stay local.
from services.text_quality_filter import _ARTIFACT_PATTERNS as _SHARED_ARTIFACT_PATTERNS

_LEAKAGE_PATTERNS = _SHARED_ARTIFACT_PATTERNS + (
    # OKF-markdown-specific: raw chunk provenance pasted in as a blockquote.
    r"^\s*>\s*\[Source:",
    r"^\s*>\s*\[RAPTOR",
    # Retained from the original OKF list. Ambiguous in free prose ("We are given
    # this life…"), so it is deliberately NOT in the shared corpus table — a false
    # positive there would delete real doctrine. Here it only blocks an
    # auto-extracted entry from going live, which human review can override.
    r"\bWe are given\b",
)
_LEAKAGE_RE = re.compile("|".join(_LEAKAGE_PATTERNS), re.IGNORECASE | re.MULTILINE)

# Shortest quotation that may be judged "fabricated" for restating the Summary.
# Below this a genuine short teaching line could legitimately appear in both.
_MIN_FABRICATED_QUOTE_CHARS = 60
_MATCH_NOISE_RE = re.compile(r"[^\w\s]+")

# A quotation longer than this must end on a sentence terminator; below it, a
# short quoted term or phrase is a legitimate gloss, not a truncated teaching.
_MIN_COMPLETE_QUOTE_CHARS = 40
_QUOTE_TERMINATORS = ".!?…\"'"


def _normalise_for_match(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for quote/summary comparison."""
    return " ".join(_MATCH_NOISE_RE.sub(" ", text.lower()).split())


class OKFQualityFilter:
    """Filters and validates synthesized OKF entries."""

    MIN_BODY_LENGTH = 100
    REQUIRED_FIELDS = {"type", "title"}

    @classmethod
    def validate_entry(cls, parsed: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate parsed OKF dictionary representation.
        Returns (is_valid, error_reason).
        """
        title = parsed.get("title", "").strip()
        body = parsed.get("body", "").strip()
        type_ = parsed.get("type", "").strip()
        source = str(parsed.get("source", "") or "").strip()

        # Check required fields
        if not title:
            return False, "Empty title"
        if not body:
            return False, "Empty body content"
        if not type_:
            return False, "Empty type field"

        # Check body length
        if len(body) < cls.MIN_BODY_LENGTH:
            return False, f"Body too short ({len(body)} chars, min={cls.MIN_BODY_LENGTH})"

        # Provenance is mandatory: format_final_answer cites every OKF-derived claim.
        # An entry with no source cannot be attributed, so it cannot be doctrine.
        if not source:
            return False, "Missing 'source' — an uncitable entry cannot be doctrine"

        # Machine artifacts must never be served as teachings.
        leak = _LEAKAGE_RE.search(body)
        if leak:
            return False, f"Extraction artifact / prompt leakage in body: {leak.group(0)!r}"

        # A "quotation" that merely restates the entry's own machine-written
        # Summary is not a quotation -- it is the extractor's prose wearing
        # quotation marks, and several such entries name a LIVING teacher as the
        # speaker. That is the single worst output this product can produce.
        fabricated = cls._fabricated_quote(body)
        if fabricated:
            quote, attribution = fabricated
            return False, (
                "Fabricated quote: quoted text is the entry's own machine-written "
                f"Summary, attributed to {attribution!r}: {quote[:80]!r}"
            )

        truncated = cls._truncated_quote(body)
        if truncated:
            return False, (
                "Truncated quote: the quotation is cut off mid-sentence, so it "
                f"misquotes the teacher it attributes: ...{truncated[-60:]!r}"
            )

        # Verify doctrine-specific validation
        body_lower = body.lower()
        if (
            "sri preethaji" not in body_lower
            and "sri krishnaji" not in body_lower
            and "ekam" not in body_lower
        ):
            # We don't fail, but log warning for low spiritual context
            logger.debug(f"OKF Warning: '{title}' has low doctrine term density.")

        return True, ""

    @classmethod
    def _fabricated_quote(cls, body: str) -> tuple[str, str] | None:
        """Return (quote, attribution) if a blockquote restates the ## Summary.

        Found live 2026-09-17: 26 of 488 quotations across the OKF bundle were
        the entry's own Summary paragraph repeated verbatim inside quotation
        marks, and 5 of those carried "-- Sri Preethaji". The extractor writes a
        machine summary, then re-emits it as a "## Quotes" blockquote attributed
        to a living teacher. Every OKF entry is injected verbatim into answers,
        so promoting one of these quotes fabricated speech and attached a real
        person's name to it.

        Matching is normalised (case/punctuation-insensitive, whitespace
        collapsed) because the extractor re-punctuates between the two copies.
        The >=60-character floor keeps a genuinely short quotation that happens
        to also appear in the summary from tripping this -- a teacher really can
        be quoted in one short line that the summary then reuses.
        """
        summary_match = re.search(r"##\s*Summary\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
        if not summary_match:
            return None
        summary = _normalise_for_match(summary_match.group(1))
        if not summary:
            return None

        for quote, attribution in re.findall(r'^>\s*"(.+?)"(?:\s*—\s*(.*))?$', body, re.M):
            normalised = _normalise_for_match(quote)
            if len(normalised) >= _MIN_FABRICATED_QUOTE_CHARS and normalised in summary:
                return quote, (attribution or "").strip() or "unattributed"
        return None

    @classmethod
    def _truncated_quote(cls, body: str) -> str | None:
        """Return a quotation that is cut off mid-sentence, if any.

        The extractor slices a fixed number of characters out of a transcript
        chunk, so quotes routinely stop mid-word: 127 live entries carried one
        on 2026-09-17, including "...step away from all this tumul" and
        "...everything in this universe i". The words are genuinely the
        teacher's, which makes this subtler than fabrication — but a quotation
        mark around half a sentence still misquotes a living teacher, and it is
        injected verbatim into answers.

        The repair is always subtractive (cut back to the last complete
        sentence, or drop the quote) — never complete a quote from inference.
        """
        for quote, _attrib in re.findall(r'^>\s*"(.+?)"(?:\s*—\s*(.*))?$', body, re.M):
            stripped = quote.strip()
            # Short fragments are legitimately used as glossed terms; only a
            # substantial span reads to a seeker as a full quoted teaching.
            if len(stripped) > _MIN_COMPLETE_QUOTE_CHARS and stripped[-1] not in _QUOTE_TERMINATORS:
                return stripped
        return None

    @classmethod
    def filter_duplicate_entries(cls, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicates by title (case-insensitive), keeping the longest body."""
        seen: dict[str, dict[str, Any]] = {}
        for entry in entries:
            title_key = entry.get("title", "").strip().lower()
            if not title_key:
                continue

            existing = seen.get(title_key)
            if not existing or len(entry.get("body", "")) > len(existing.get("body", "")):
                seen[title_key] = entry

        return list(seen.values())
