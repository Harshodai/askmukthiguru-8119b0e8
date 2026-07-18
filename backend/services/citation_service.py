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

_MARKER_RE = re.compile(r"\[\^(\d{1,3})\]")


class CitationStyle(Enum):
    INLINE_NUMERIC = "inline_numeric"      # [1] [2] … (Perplexity-style)
    AUTHOR_TITLE = "author_title"          # (Ekam Teaching, 2023)
    FOOTNOTE = "footnote"                  # superscript + footnote list


@dataclass
class Source:
    """One retrieved context item's provenance."""
    id: str
    title: str = ""
    teacher: Optional[str] = None
    source_text: Optional[str] = None     # scripture / discourse / book
    year: Optional[str] = None
    url: Optional[str] = None
    channel: str = "vector"               # vector | graph | doctrine
    extra: dict = field(default_factory=dict)


@dataclass
class Reference:
    n: int
    source: Source
    label: str
    url: Optional[str] = None


@dataclass
class CitedAnswer:
    text: str                      # answer with inline markers preserved
    references: list[Reference]
    citation_count: int
    grounded: bool                 # True if every claim region has a citation


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

def resolve(answer: str, context_items: list[Any],
            style: CitationStyle = CitationStyle.INLINE_NUMERIC) -> CitedAnswer:
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
        n = int(m.group(1))
        if n in sources and n not in seen_order:
            seen_order.append(n)

    references = [
        Reference(n=n, source=sources[n], label=format_reference(sources[n], style),
                  url=sources[n].url)
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
    (single paragraph <= 25 words) also require a citation. Empty context
    is considered grounded (no claims to verify)."""
    if not context_items:
        return True
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
    """Remove `[^n]` markers that point past the provided context (the model
    hallucinated a citation index). Prevents dead reference chips."""
    max_n = len(context_items)
    def _keep(m):
        n = int(m.group(1))
        return m.group(0) if 1 <= n <= max_n else ""
    return _MARKER_RE.sub(_keep, answer)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctx = [
        {"id": "d1", "title": "Breath Awareness", "teacher": "Sri Preethaji",
         "source": "Ekam Discourse", "year": "2023", "url": "https://\u2026/breath"},
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
