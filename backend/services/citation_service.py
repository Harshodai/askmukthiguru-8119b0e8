"""
Citation layer — makes RAG answers verifiable, inline, and resolvable.

Skill applied: `cite-style-converter` (citation formatting/validation)
adapted from academic bibliographies to *scripture/teaching* citations, which
is what a spiritual RAG product actually needs.

Why this exists (repo gap): today citations survive only as frontend *chips*;
the inline `[Source]` markers the prompt asks for are added and then stripped
(wasted work). This service keeps inline markers, resolves them to real
sources, and formats them in a consistent style — the trust bar set by
Perplexity.

Flow
----
1. The generation prompt cites inline as `[^n]` where n indexes the retrieved
   context items.
2. `resolve(answer, context_items)` maps each marker to its source metadata.
3. `format_reference(source, style=...)` renders a consistent human label
   (e.g. "Ekam Teaching · Breath Awareness, 2023" or a scripture citation).
4. Output: `CitedAnswer{ text, references[] }` where references are ordered
   by first appearance and each carries a stable id the frontend links.

Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

_MARKER_RE = re.compile(r"\[\[CITE:(\d{1,3})\]\]|\[\^(\d{1,3})\]")


def _marker_index(match: re.Match) -> int:
    """Return the captured citation index from either [[CITE:N]] or [^N] markers."""
    return int(match.group(1) or match.group(2))


class CitationStyle(Enum):
    INLINE_NUMERIC = "inline_numeric"  # [1] [2] … (Perplexity-style)
    AUTHOR_TITLE = "author_title"  # (Ekam Teaching, 2023)
    FOOTNOTE = "footnote"  # superscript + footnote list


@dataclass
class Source:
    """One retrieved context item's provenance."""

    id: str
    title: str = ""
    teacher: Optional[str] = None
    source_text: Optional[str] = None  # scripture / discourse / book
    year: Optional[str] = None
    url: Optional[str] = None
    channel: str = "vector"  # vector | graph | doctrine
    extra: dict = field(default_factory=dict)


@dataclass
class Reference:
    n: int
    source: Source
    label: str
    url: Optional[str] = None


@dataclass
class CitedAnswer:
    text: str  # answer with inline markers preserved
    references: list[Reference]
    citation_count: int
    grounded: bool  # True if every claim region has a citation


# ---------------------------------------------------------------------------
# Reference formatting (the cite-style-converter heart)
# ---------------------------------------------------------------------------


def format_reference(src: Source, style: CitationStyle = CitationStyle.INLINE_NUMERIC) -> str:
    """Render a consistent human citation label for a teaching source."""
    if style == CitationStyle.AUTHOR_TITLE:
        who = src.teacher or src.source_text or "Ekam Teaching"
        yr = f", {src.year}" if src.year else ""
        return f"{who}{yr}"
    # default: a clean footnote-ish label
    parts = []
    if src.teacher:
        parts.append(src.teacher)
    if src.title:
        parts.append(f"\u201c{src.title}\u201d")
    if src.source_text and src.source_text != src.teacher:
        parts.append(src.source_text)
    if src.year:
        parts.append(src.year)
    return " \u00b7 ".join(parts) if parts else src.id


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve(
    answer: str, context_items: list[Any], style: CitationStyle = CitationStyle.INLINE_NUMERIC
) -> CitedAnswer:
    """Map inline `[^n]` markers to sources and build the reference list.

    `context_items` are the retrieved items (dicts or objects) in the SAME
    ORDER the prompt presented them, so marker n ↔ context_items[n-1].
    """
    # index sources by their 1-based position
    sources: dict[int, Source] = {}
    for i, item in enumerate(context_items, 1):
        sources[i] = _to_source(item, i)

    seen_order: list[int] = []
    for m in _MARKER_RE.finditer(answer):
        n = _marker_index(m)
        if n in sources and n not in seen_order:
            seen_order.append(n)

    references = [
        Reference(
            n=n, source=sources[n], label=format_reference(sources[n], style), url=sources[n].url
        )
        for n in seen_order
    ]

    grounded = _check_grounding(answer, context_items)

    return CitedAnswer(
        text=answer,
        references=references,
        citation_count=len(references),
        grounded=grounded,
    )


def _to_source(item: Any, pos: int) -> Source:
    """Tolerant adapter: accept dicts or objects from either retrieval channel."""
    get = item.get if isinstance(item, dict) else lambda k, d=None: getattr(item, k, d)
    prov = get("provenance", {}) or {}
    return Source(
        id=str(get("id", None) or prov.get("id") or prov.get("uri") or f"ctx-{pos}"),
        title=get("title", "") or prov.get("title", "") or "",
        teacher=get("teacher", None) or prov.get("teacher"),
        source_text=get("source", None) or prov.get("source") or prov.get("source_text"),
        year=get("year", None) or prov.get("year"),
        url=get("url", None) or prov.get("url") or prov.get("uri"),
        channel=get("channel", "vector") or prov.get("channel", "vector"),
    )


def _check_grounding(answer: str, context_items: list[Any]) -> bool:
    """Heuristic: an answer is 'grounded' if every substantive paragraph
    (exceeding 25 words) has at least one citation marker. Short answers
    (single paragraph <= 25 words) also require a citation. An answer with
    NO retrieved context cannot be grounded (nothing to verify against)
    — this closes the P1-AI-12 vacuous-truth gap where empty context
    reported "grounded" and hid ungrounded answers. An empty answer is
    trivially grounded (nothing to verify)."""
    if not answer.strip():
        return True
    if not context_items:
        return False
    paragraphs = [p for p in re.split(r"\n{2,}", answer) if p.strip()]
    if not paragraphs:
        return True
    # Single short answer (<= 25 words) still requires a citation
    if len(paragraphs) == 1:
        word_count = len(paragraphs[0].split())
        if word_count <= 25:
            return bool(_MARKER_RE.search(paragraphs[0]))
    # Multi-paragraph: each substantive paragraph (> 25 words) must have citation
    for p in paragraphs:
        word_count = len(p.split())
        if word_count > 25:
            if not _MARKER_RE.search(p):
                return False
    return True


def strip_orphan_markers(answer: str, context_items: list[Any]) -> str:
    """Remove `[^n]` / `[[CITE:n]]` markers that point past the provided context
    (the model hallucinated a citation index). Prevents dead reference chips."""
    max_n = len(context_items)

    def _keep(m):
        n = _marker_index(m)
        return m.group(0) if 1 <= n <= max_n else ""

    return _MARKER_RE.sub(_keep, answer)


# ---------------------------------------------------------------------------
# Citation N-Gram Verification Protocol (8-word continuous match)
# ---------------------------------------------------------------------------

_QUOTE_RE = re.compile(r'["“]([^"”]+)["”]|[\'‘]([^\'’]+)[\'’]')


def extract_verbatim_quotes(text: str, min_words: int = 2) -> list[str]:
    """Extract quoted phrases from text (supporting straight and curly quotes)."""
    if not text:
        return []
    quotes = []
    for match in _QUOTE_RE.finditer(text):
        q = (match.group(1) or match.group(2) or "").strip()
        if len(q.split()) >= min_words:
            quotes.append(q)
    return quotes


def _normalize_words(text: str) -> list[str]:
    """Normalize text into lowercased alphanumeric words."""
    if not text:
        return []
    return re.findall(r"\b\w+\b", text.lower())


def check_continuous_ngram_match(quote: str, source_text: str, n: int = 8) -> bool:
    """Check if quote has an n-word continuous verbatim match in source_text.

    If the quote has fewer than n words, checks if the entire normalized quote
    appears continuously in the normalized source_text.
    If the quote has >= n words, checks if ANY continuous n-word sequence from the
    quote appears verbatim in the normalized source_text.
    """
    quote_words = _normalize_words(quote)
    source_words = _normalize_words(source_text)

    if not quote_words or not source_words:
        return False

    q_len = len(quote_words)
    s_len = len(source_words)

    if q_len < n:
        if q_len > s_len:
            return False
        # Check if entire quote_words appears continuously in source_words
        target = tuple(quote_words)
        for i in range(s_len - q_len + 1):
            if tuple(source_words[i : i + q_len]) == target:
                return True
        return False

    # For q_len >= n: check if any continuous n-gram appears in source_words
    source_ngrams = {
        tuple(source_words[i : i + n])
        for i in range(s_len - n + 1)
    }

    for i in range(q_len - n + 1):
        gram = tuple(quote_words[i : i + n])
        if gram in source_ngrams:
            return True

    return False


def verify_quote_ngram_fidelity(quote: str, source_text: str, n: int = 8) -> dict[str, Any]:
    """Compute detailed continuous n-gram matching metrics for a verbatim quote."""
    quote_words = _normalize_words(quote)
    source_words = _normalize_words(source_text)

    if not quote_words or not source_words:
        return {
            "quote": quote,
            "quote_word_count": len(quote_words),
            "matched": False,
            "match_ratio": 0.0,
            "matched_ngrams_count": 0,
            "total_ngrams_count": max(0, len(quote_words) - n + 1) if len(quote_words) >= n else 1,
        }

    q_len = len(quote_words)
    s_len = len(source_words)

    if q_len < n:
        matched = check_continuous_ngram_match(quote, source_text, n=n)
        return {
            "quote": quote,
            "quote_word_count": q_len,
            "matched": matched,
            "match_ratio": 1.0 if matched else 0.0,
            "matched_ngrams_count": 1 if matched else 0,
            "total_ngrams_count": 1,
        }

    source_ngrams = {
        tuple(source_words[i : i + n])
        for i in range(s_len - n + 1)
    }

    total_ngrams = q_len - n + 1
    matched_count = 0
    for i in range(total_ngrams):
        gram = tuple(quote_words[i : i + n])
        if gram in source_ngrams:
            matched_count += 1

    match_ratio = matched_count / total_ngrams if total_ngrams > 0 else 0.0
    return {
        "quote": quote,
        "quote_word_count": q_len,
        "matched": matched_count > 0,
        "match_ratio": match_ratio,
        "matched_ngrams_count": matched_count,
        "total_ngrams_count": total_ngrams,
    }


def verify_citation_ngrams(answer: str, context_items: list[Any], n: int = 8) -> dict[str, Any]:
    """Extract quoted text and verify each quote against retrieved context items.

    Returns a verification dict with boolean pass/fail status and breakdown per quote.
    """
    quotes = extract_verbatim_quotes(answer)
    if not quotes:
        return {
            "verified": True,
            "quotes_checked": 0,
            "quotes_passed": 0,
            "details": [],
        }

    combined_source_text = " ".join(
        (
            item.get("text", "") or item.get("content", "") or item.get("source_text", "")
            if isinstance(item, dict)
            else getattr(item, "text", "") or getattr(item, "content", "")
        )
        for item in context_items
    )

    details = []
    all_passed = True
    passed_count = 0

    for q in quotes:
        res = verify_quote_ngram_fidelity(q, combined_source_text, n=n)
        details.append(res)
        if res["matched"]:
            passed_count += 1
        else:
            all_passed = False

    return {
        "verified": all_passed,
        "quotes_checked": len(quotes),
        "quotes_passed": passed_count,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctx = [
        {
            "id": "d1",
            "title": "Breath Awareness",
            "teacher": "Sri Preethaji",
            "source": "Ekam Discourse",
            "year": "2023",
            "url": "https://\u2026/breath",
        },
        {"id": "d2", "title": "On Presence", "source": "Ekam Teaching", "year": "2022"},
    ]
    ans = (
        "When the mind is restless, return to the breath \u2014 this is the first "
        "and simplest instruction.[^1] From that steadiness, presence arises "
        "on its own.[^2]\n\n"
        "You do not force stillness; you make room for it.[^1]"
    )
    out = resolve(ans, ctx, CitationStyle.INLINE_NUMERIC)
    assert out.citation_count == 2
    assert out.references[0].label.startswith("Sri Preethaji")
    assert out.grounded is True
    print("citation service self-test OK \u2014")
    for r in out.references:
        print(f"  [^{r.n}] {r.label}")

    # orphan marker stripped
    bad = "This cites a fake source.[^9]"
    assert "[^9]" not in strip_orphan_markers(bad, ctx)
    print("orphan-marker stripping OK")

    # [[CITE:N]] marker support
    cited = "Breath awareness is the first step. [[CITE:1]]"
    out2 = resolve(cited, ctx)
    assert out2.citation_count == 1
    assert out2.grounded is True
    cleaned_orphan = strip_orphan_markers("[[CITE:9]]", ctx)
    assert "[[CITE:9]]" not in cleaned_orphan
    assert cleaned_orphan == ""
    print("[[CITE:N]] marker support OK")

    # 8-word continuous n-gram verification test
    raw_transcript = (
        "Every moment of your life you are living either in a beautiful state "
        "or in a suffering state. There is no third state."
    )
    exact_quote = "Every moment of your life you are living either in a beautiful state"
    assert check_continuous_ngram_match(exact_quote, raw_transcript, n=8) is True
    hallucinated_quote = "Every single person always lives happily in spiritual ecstasy forever and ever"
    assert check_continuous_ngram_match(hallucinated_quote, raw_transcript, n=8) is False
    print("8-word continuous ngram verification self-test OK")
