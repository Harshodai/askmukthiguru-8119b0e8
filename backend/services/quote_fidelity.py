"""Verify that a quote rendered as a named teacher's words is really theirs.

A rendered "hero quote" makes four claims at once: these exact words, said by
this speaker, in this video (with this title), at this timestamp. Nothing
checked any of them. The 2026-10-04 expanded benchmark scored 8/8 PASS on
formatting alone while, for example, video ``0z-IZ2ar4eA`` (stored as a Sri
Preethaji Times Now interview) was rendered under three different invented
titles and once as Sri Krishnaji, with quote text found nowhere in the repo.

This module checks each claim against the stored source records and fails
closed: a claim that cannot be checked (no stored title, no per-chunk timing,
no known speaker) is a failure, not a pass. Pure functions only, so a renderer
can call ``verify_quote`` as a gate and a benchmark can call it as a check.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class AttributedQuote:
    """One quote as the seeker sees it."""

    text: str
    speaker: str = ""
    title: str = ""
    video_id: str = ""
    start_seconds: Optional[float] = None
    case: str = ""


@dataclass
class ChunkRecord:
    text: str
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    speaker: str = ""


@dataclass
class SourceRecord:
    """Everything the store knows about one video."""

    video_id: str
    title: str = ""
    teacher_id: str = ""
    duration_seconds: Optional[float] = None
    chunks: list[ChunkRecord] = field(default_factory=list)


@dataclass
class QuoteVerdict:
    quote: AttributedQuote
    failures: list[str] = field(default_factory=list)
    missing_sentences: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_TS_MARKER_RE = re.compile(r"\[t=([0-9hms:.]+)\]")
_NOISE_RE = re.compile(r"[^\w\s]+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")
_MIN_SENTENCE_CHARS = 20


def normalise(text: str) -> str:
    text = _TS_MARKER_RE.sub(" ", text or "")
    text = text.replace("’", "'").replace("‘", "'").replace("'", "")
    return " ".join(_NOISE_RE.sub(" ", text.lower()).split())


def canonical_speaker(label: str) -> str:
    """Map a display label or a stored teacher_id onto a small closed set."""
    s = (label or "").lower()
    has_p = bool(re.search(r"preetha|prithaji", s))
    has_k = bool(re.search(r"krishnaji|sri\s*krishna\b|krishna\s*ji", s))
    if has_p and has_k:
        return "both"
    if has_p:
        return "preethaji"
    if has_k:
        return "krishnaji"
    return "unknown"


def parse_timestamp(value: str) -> Optional[float]:
    """Parse ``280``, ``280s``, ``4m40s``, ``1h2m3s``, ``04:40`` or ``1:02:03``."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if ":" in v:
        try:
            parts = [float(p) for p in v.split(":")]
        except ValueError:
            return None
        total = 0.0
        for p in parts:
            total = total * 60 + p
        return total
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?", v)
    if not m or not any(m.groups()):
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def split_sentences(text: str) -> list[str]:
    out = []
    for s in _SENTENCE_SPLIT_RE.split((text or "").strip()):
        if len(normalise(s)) >= _MIN_SENTENCE_CHARS:
            out.append(s.strip())
    return out


# ---------------------------------------------------------------------------
# Parsing rendered answers
# ---------------------------------------------------------------------------

# **Sri Preethaji** · [Title](https://www.youtube.com/watch?v=ID&t=280s)
_HEADER_RE = re.compile(
    r"^\s*>?\s*\*\*(?P<speaker>[^*]+)\*\*\s*[·•\-|]\s*"
    r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)\s*$"
)
_VIDEO_ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")
_URL_T_RE = re.compile(r"[?&#]t=([0-9hms]+)")
# Lines that end the quoted teaching block.
_STOP_RE = re.compile(
    r"^\s*>?\s*(?:───|---|\[▶|If you want to bring this alive|\*\*Deepen|\*[^*]+\?\*\s*$)"
)


def parse_attributed_quotes(markdown: str, case: str = "") -> list[AttributedQuote]:
    """Extract every speaker/title/link header and the teaching text under it."""
    quotes: list[AttributedQuote] = []
    lines = (markdown or "").splitlines()
    i = 0
    while i < len(lines):
        m = _HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        url = m.group("url")
        vid = _VIDEO_ID_RE.search(url)
        t = _URL_T_RE.search(url)
        body: list[str] = []
        i += 1
        while i < len(lines):
            line = lines[i]
            if _HEADER_RE.match(line) or _STOP_RE.match(line):
                break
            stripped = re.sub(r"^\s*>\s?", "", line).strip()
            if stripped and not stripped.startswith("```"):
                body.append(stripped)
            i += 1
        quotes.append(
            AttributedQuote(
                text=" ".join(body),
                speaker=m.group("speaker").strip(),
                title=m.group("title").strip(),
                video_id=vid.group(1) if vid else "",
                start_seconds=parse_timestamp(t.group(1)) if t else None,
                case=case,
            )
        )
    return quotes


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

TIMESTAMP_TOLERANCE_S = 15.0


def _chunk_timing(chunk: ChunkRecord) -> tuple[Optional[float], Optional[float]]:
    if chunk.start_seconds is not None:
        return chunk.start_seconds, chunk.end_seconds
    markers = [parse_timestamp(x) for x in _TS_MARKER_RE.findall(chunk.text or "")]
    markers = [x for x in markers if x is not None]
    if not markers:
        return None, None
    return min(markers), max(markers)


def verify_quote(quote: AttributedQuote, source: Optional[SourceRecord]) -> QuoteVerdict:
    """Check text, speaker, title and timestamp. Unverifiable means failed."""
    v = QuoteVerdict(quote=quote)

    if not quote.video_id:
        v.failures.append("no_video_id")
    if source is None or not source.chunks:
        v.failures.append("video_not_in_corpus")
        return v

    # 1. Verbatim text: every sentence must appear in this video's stored text.
    sentences = split_sentences(quote.text)
    if not sentences:
        v.failures.append("empty_quote")
    matched_chunks: list[ChunkRecord] = []
    for s in sentences:
        ns = normalise(s)
        hits = [c for c in source.chunks if ns in normalise(c.text)]
        if hits:
            matched_chunks.extend(hits)
        else:
            v.missing_sentences.append(s)
    if v.missing_sentences:
        v.failures.append("text_not_verbatim")

    # 2. Speaker: the label must agree with what the store knows. A video whose
    # speaker the store does not know cannot carry a named-teacher label.
    shown = canonical_speaker(quote.speaker)
    chunk_speakers = {canonical_speaker(c.speaker) for c in matched_chunks if c.speaker}
    chunk_speakers.discard("unknown")
    stored = (
        chunk_speakers.pop()
        if len(chunk_speakers) == 1
        else canonical_speaker(source.teacher_id.replace("_", " "))
    )
    if stored == "unknown":
        v.failures.append("speaker_unverifiable")
    elif stored != "both" and shown != stored:
        v.failures.append("speaker_mismatch")

    # 3. Title: the displayed title must be the stored one, not an invented one.
    stored_title = normalise(source.title)
    if not stored_title or stored_title == normalise(source.video_id):
        v.failures.append("title_unverifiable")
    elif normalise(quote.title) != stored_title:
        v.failures.append("title_mismatch")

    # 4. Timestamp: inside the video, and inside the chunk the words came from.
    if quote.start_seconds is not None:
        if (
            source.duration_seconds
            and quote.start_seconds > source.duration_seconds + TIMESTAMP_TOLERANCE_S
        ):
            v.failures.append("timestamp_past_end_of_video")
        timed = [t for t in (_chunk_timing(c) for c in matched_chunks) if t[0] is not None]
        if not timed:
            v.failures.append("timestamp_unverifiable")
        elif not any(
            start - TIMESTAMP_TOLERANCE_S
            <= quote.start_seconds
            <= (end if end is not None else start) + TIMESTAMP_TOLERANCE_S
            for start, end in timed
        ):
            v.failures.append("timestamp_mismatch")

    return v


def cross_case_conflicts(quotes: Iterable[AttributedQuote]) -> list[str]:
    """One video rendered with different titles or speakers across answers."""
    by_vid: dict[str, list[AttributedQuote]] = {}
    for q in quotes:
        if q.video_id:
            by_vid.setdefault(q.video_id, []).append(q)
    problems = []
    for vid, qs in sorted(by_vid.items()):
        titles = {normalise(q.title) for q in qs}
        speakers = {canonical_speaker(q.speaker) for q in qs}
        if len(titles) > 1:
            problems.append(f"{vid}: rendered under {len(titles)} different titles")
        if len(speakers) > 1:
            problems.append(f"{vid}: attributed to {len(speakers)} different speakers")
    return problems


if __name__ == "__main__":
    src = SourceRecord(
        video_id="0z-IZ2ar4eA",
        title="IEC 2023 | Mukti Guru Sri Preethaji Speaks On Consciousness",
        teacher_id="preethaji",
        chunks=[
            ChunkRecord(text="[t=300s] Consciousness is your superpower. It changes everything.")
        ],
    )
    bad = AttributedQuote(
        text="Oneness is not a philosophy to be debated; it is a living shift.",
        speaker="Sri Krishnaji",
        title="The Living Reality of Oneness Beyond Philosophy",
        video_id="0z-IZ2ar4eA",
        start_seconds=320,
    )
    verdict = verify_quote(bad, src)
    assert {"text_not_verbatim", "speaker_mismatch", "title_mismatch"} <= set(verdict.failures)
    good = AttributedQuote(
        text="Consciousness is your superpower.",
        speaker="Sri Preethaji",
        title=src.title,
        video_id=src.video_id,
        start_seconds=305,
    )
    assert verify_quote(good, src).ok, verify_quote(good, src).failures
    print("quote_fidelity self-check ok")
