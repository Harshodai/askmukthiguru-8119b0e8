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
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Optional

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
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।॥])\s+")
_MIN_SENTENCE_CHARS = 20
_APOSTROPHES = str.maketrans("", "", "'’‘ʼ`")
# Labels a diariser or ingest stamps on a non-teacher turn. Words under such a
# label are someone else's, whatever the video's teacher_id says.
_OTHER_SPEAKER_RE = re.compile(
    r"\b(?:host|interviewer|anchor|guest|audience|moderator|questioner|seeker|"
    r"participant|narrator|other|speaker[\s_]?\d+)\b|^\s*[?o]\s*$",
    re.IGNORECASE,
)
# Display labels, keyed by canonical speaker. Nothing else may be shown.
TEACHER_LABELS = {
    "preethaji": "Sri Preethaji",
    "krishnaji": "Sri Krishnaji",
    "both": "Sri Preethaji & Sri Krishnaji",
}
# Link text shown when the store has no real title. It makes no title claim.
UNTITLED_LINK_LABEL = "Watch on YouTube"


def normalise(text: str) -> str:
    """Lower-case, drop punctuation and [t=] markers, keep every script's letters.

    Keeps Unicode letters, digits and combining marks (category L*, N*, M*) so
    Devanagari matras and anusvara survive; ``\\w`` would strip them.
    """
    text = _TS_MARKER_RE.sub(" ", text or "")
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).lower()
    kept = "".join(ch if unicodedata.category(ch)[0] in "LNM" else " " for ch in text)
    return " ".join(kept.split())


def canonical_speaker(label: str) -> str:
    """Map a display label or a stored teacher_id onto a small closed set.

    ``other`` = a labelled non-teacher turn (host, interviewer, ...);
    ``unknown`` = no usable label (empty, a channel name, ``ekam``).
    """
    s = (label or "").replace("_", " ").lower()
    has_p = bool(re.search(r"preetha|prithaji", s))
    has_k = bool(re.search(r"krishnaji|sri\s*krishna\b|krishna\s*ji", s))
    if has_p and has_k:
        return "both"
    if has_p:
        return "preethaji"
    if has_k:
        return "krishnaji"
    if _OTHER_SPEAKER_RE.search(s):
        return "other"
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
    # a short scaffold pointer between clips ("Sri Krishnaji observes:")
    r"|^(?!\s*>)[^\n]{1,120}:\s*$"
)
# Weak-match shape: "<quote>"\n— Sri Preethaji (VIDEOID, 280s)
_WEAK_RE = re.compile(
    r'"(?P<text>[^"]+)"\s*\n\s*[—-]\s*(?P<speaker>[^(\n]+?)\s*'
    r"\((?P<vid>[A-Za-z0-9_-]{11}),\s*(?P<t>\d+)s\)"
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
    for m in _WEAK_RE.finditer(markdown or ""):
        quotes.append(
            AttributedQuote(
                text=m.group("text").strip(),
                speaker=m.group("speaker").strip(),
                video_id=m.group("vid"),
                start_seconds=float(m.group("t")),
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


def _merge_overlapping(a: str, b: str, max_overlap: int = 600) -> str:
    """Join two normalised adjacent chunks, dropping a shared overlap once."""
    for k in range(min(len(a), len(b), max_overlap), 0, -1):
        if a.endswith(b[:k]):
            return a + b[k:]
    return f"{a} {b}"


def _locate(needle: str, chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    """Chunks whose text (alone, or merged with the next one) holds ``needle``.

    ponytail: spans at most two adjacent chunks; a quote crossing three would
    fail closed. Chunks are 400+ chars, so a hero quote rarely does.
    """
    norm = [normalise(c.text) for c in chunks]
    hits = [c for c, n in zip(chunks, norm) if needle in n]
    if hits:
        return hits
    for i in range(len(chunks) - 1):
        if needle in _merge_overlapping(norm[i], norm[i + 1]):
            return [chunks[i], chunks[i + 1]]
    return []


def _stored_speaker(source: SourceRecord, matched: list[ChunkRecord]) -> str:
    """Per-chunk speaker labels win over the video's teacher_id.

    Any matched chunk labelled as a non-teacher turn makes the whole quote
    ``other``: those words are not the teacher's, whatever the video is filed as.
    """
    per_chunk = {canonical_speaker(c.speaker) for c in matched if c.speaker}
    if "other" in per_chunk:
        return "other"
    per_chunk.discard("unknown")
    if len(per_chunk) == 1:
        return per_chunk.pop()
    if len(per_chunk) > 1:
        return "mixed"
    return canonical_speaker(source.teacher_id)


def shows_title(quote: AttributedQuote) -> bool:
    """False when the link text makes no title claim (neutral label or bare id)."""
    t = normalise(quote.title)
    return bool(t) and t not in {normalise(UNTITLED_LINK_LABEL), normalise(quote.video_id)}


def verify_quote(quote: AttributedQuote, source: Optional[SourceRecord]) -> QuoteVerdict:
    """Check text, speaker, title and timestamp. Unverifiable means failed.

    Title and timestamp are checked only when shown: a renderer that has no
    stored title or timing must omit them, and omitting is not a claim.
    """
    v = QuoteVerdict(quote=quote)

    if not quote.video_id:
        v.failures.append("no_video_id")
    if source is None or not source.chunks:
        v.failures.append("video_not_in_corpus")
        return v
    if source.video_id and quote.video_id and source.video_id != quote.video_id:
        v.failures.append("video_id_mismatch")

    # 1. Verbatim text: the whole quote must be contiguous in the stored text of
    # this video. Per-sentence misses are reported to say what was invented.
    whole = normalise(quote.text)
    matched = _locate(whole, source.chunks) if whole else []
    if not whole:
        v.failures.append("empty_quote")
    elif not matched:
        v.failures.append("text_not_verbatim")
        for s in split_sentences(quote.text) or [quote.text]:
            ns = normalise(s)
            if ns and not _locate(ns, source.chunks):
                v.missing_sentences.append(s)

    # 2. Speaker: the label must equal what the store says about these words.
    shown = canonical_speaker(quote.speaker)
    stored = _stored_speaker(source, matched)
    if stored in ("unknown", "mixed"):
        v.failures.append("speaker_unverifiable")
    elif stored == "other" or shown != stored:
        v.failures.append("speaker_mismatch")

    # 3. Title: shown only if it is the stored one, and never an id posing as one.
    if shows_title(quote):
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
        timed = [t for t in (_chunk_timing(c) for c in matched) if t[0] is not None]
        if not timed:
            v.failures.append("timestamp_unverifiable")
        elif not any(
            start - TIMESTAMP_TOLERANCE_S
            <= quote.start_seconds
            <= max(start, end if end is not None else start) + TIMESTAMP_TOLERANCE_S
            for start, end in timed
        ):
            v.failures.append("timestamp_mismatch")

    return v


def _seconds(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parse_timestamp(str(value))


def source_from_payloads(video_id: str, payloads: list[dict[str, Any]]) -> SourceRecord:
    """Build a SourceRecord from stored Qdrant payloads of one video.

    Reads both shapes: first-person clips (``verbatim_text``, ``start_ms``,
    ``end_ms``, ``duration_ms``, diarised ``speaker``) and chat-corpus chunks
    (``text``, ``timestamp_start``/``_end``, ``title``, ``duration``).
    Chat-corpus ``speaker`` often holds a channel name; ``canonical_speaker``
    maps that to ``unknown`` so it is ignored, not trusted.
    """

    def first(key: str) -> Any:
        return next((p.get(key) for p in payloads if p.get(key) not in (None, "")), None)

    dur_ms = first("duration_ms")
    chunks = []
    for p in payloads:
        start = p.get("start_ms")
        end = p.get("end_ms")
        chunks.append(
            ChunkRecord(
                text=str(p.get("verbatim_text") or p.get("text") or ""),
                start_seconds=start / 1000.0
                if isinstance(start, (int, float))
                else _seconds(p.get("timestamp_start")),
                end_seconds=end / 1000.0
                if isinstance(end, (int, float))
                else _seconds(p.get("timestamp_end")),
                speaker=str(p.get("speaker") or ""),
            )
        )
    return SourceRecord(
        video_id=video_id,
        # Only the stored ``title`` field. ``video_title`` is not a stored
        # payload field; on a clip dict it was set by a caller, not the store.
        title=str(first("title") or ""),
        teacher_id=str(first("teacher_id") or ""),
        duration_seconds=dur_ms / 1000.0
        if isinstance(dur_ms, (int, float))
        else _seconds(first("duration")),
        chunks=chunks,
    )


def sources_from_payloads(payloads: Iterable[dict[str, Any]]) -> dict[str, SourceRecord]:
    """Group retrieved payloads by video_id into SourceRecords."""
    by_vid: dict[str, list[dict[str, Any]]] = {}
    for p in payloads:
        if p.get("video_id"):
            by_vid.setdefault(str(p["video_id"]), []).append(p)
    return {vid: source_from_payloads(vid, ps) for vid, ps in by_vid.items()}


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
