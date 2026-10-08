"""
Mukthi Guru — Quote-Weaver Service & DSPy-style Assertion Gate (Phase F / Subagent 2)

Weaves authentic first-person video clips and curated OKF doctrine into an Ask Sadhguru-style
direct flowing teacher voice:
  - Teacher speaks directly in flowing prose under speaker name and video citation link.
  - Optional OKF practice presented as flowing prose imperatives ("If you want to bring this alive —").
  - Concludes with a divider (`---`) and 2-3 sharp inward reflection questions in italics (`*...*`).
  - NO section headers (no `###`).

Enforces zero-hallucination via `QuoteWeaverAssertionGate`:
  - Requires video timestamp link (`t=`), `---` divider, and italic reflection questions (`*...*`).
  - The `t=` value must fall inside the cited clip's time window (GAP-C1).
  - No machine artifacts, CoT leaks, or degradation strings (via `find_artifact()`).
  - If quotes in `""` are present, must be exact substrings of provided clips or OKF entries.
  - Unquoted teacher-attributed statements must be verbatim too (GAP-C2), and every
    provided clip's verbatim text must appear intact — no `clips[:2]` truncation (GAP-C3).
  - If assertions fail or LLM times out/fails, gracefully falls back to deterministic flowing template.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import difflib
import hashlib
import inspect
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from ingest.verbatim.asr_cleaner import clean_verbatim_text
from services.quote_fidelity import (
    TEACHER_LABELS,
    UNTITLED_LINK_LABEL,
    AttributedQuote,
    SourceRecord,
    canonical_speaker,
    normalise,
    parse_timestamp,
    verify_quote,
)
from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)

# ponytail: banned artificial affirmations — teachers never ask seekers to repeat
# affirmations or place hands on hearts. Reject any generated or template text containing these.
_BANNED_AFFIRMATIONS = (
    "place your hands",
    "place your palms",
    "hands upon your heart",
    "palms upon your heart",
    "repeat after me",
    "repeat these words",
    "say to yourself",
    "i forgive myself",
    "affirm:",
)

# Reject canned AI apologies, disclaimers, or generic AI framing
_CANNED_AI_PHRASES = (
    "as an ai",
    "as a large language model",
    "as an artificial intelligence",
    "i apologize",
    "i am sorry",
    "i cannot answer",
    "i am unable to",
    "i don't have access to",
    "based on the provided text",
    "according to the provided text",
    "in this chapter, we will explore",
)

# GAP-C1: sanity ceiling when a clip carries no start/end window — YouTube caps
# standard uploads at 12h, so any t= beyond that cannot point at a real video
# (e.g. the fabricated t=99999s ≈ 27.8h the gap test ships).
_MAX_CLIP_TIMESTAMP_S = 12 * 3600

# GAP-C2: unquoted sentences that co-occur a guru's name with a speech/teaching
# attribution verb assert "the guru said X" and must be verbatim in a source.
# Framing verbs used by the deterministic templates (addresses / speaks /
# deepens) are deliberately absent so scaffold prose is not misclassified.
_TEACHER_NAME_RE = re.compile(r"\b(?:Sri\s+)?(?:Preethaji|Krishnaji)\b", re.IGNORECASE)
_ATTRIBUTION_RE = re.compile(
    r"\b(?:"
    r"teach(?:es|ed|ing)?|say|says|said|state|states|stated|"
    r"claim|claims|claimed|explain|explains|explained|"
    r"assert|asserts|asserted|insist|insists|insisted|"
    r"tell|tells|told|remind|reminds|reminded|urge|urges|urged|"
    r"according to|words of"
    r")\b",
    re.IGNORECASE,
)


def _extract_t_seconds(link: str) -> tuple[bool, Optional[int]]:
    """Pull the ``t=`` offset out of a YouTube link.

    Returns ``(has_t, seconds)``: ``has_t`` is False when the link carries no
    ``t=`` parameter; ``seconds`` is None when the value is present but
    unparseable. Accepts YouTube's plain (``99``), suffixed (``99s``), and
    composite (``1h2m3s``) forms.
    """
    m = re.search(r"[?&]t=([^&#\s\)\"'>]+)", link)
    if not m:
        return False, None
    raw = m.group(1)
    if raw.isdigit():
        return True, int(raw)
    parts = re.findall(r"(\d+)([hms])", raw)
    if not parts or sum(len(n) + len(u) for n, u in parts) != len(raw):
        return True, None
    return True, sum(int(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in parts)


def _clip_time_window(clip: dict[str, Any]) -> Optional[tuple[int, int]]:
    """Inclusive ``[start, end]`` second window of a clip.

    ``None`` when the clip carries no usable timing (partial rows / minimal
    fixtures) — callers fall back to ``_MAX_CLIP_TIMESTAMP_S``. The start is
    floored exactly like citation links are built
    (``first_person_pipeline``: ``start_ms // 1000``), the end is ceil'ed so
    end-of-window offsets remain valid.
    """
    start_ms, end_ms = clip.get("start_ms"), clip.get("end_ms")
    if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
        return None
    if end_ms < start_ms:
        return None
    return int(start_ms) // 1000, -(-int(end_ms) // 1000)


@dataclass
class QuoteWeaverResult:
    """Container for quote-woven answers with gate verification metadata."""

    text: str
    passed_gate: bool
    fallback_used: bool
    gate_reason: Optional[str] = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    atma_vichara_inquiry: Optional[str] = None
    practice_recommendation: Optional[dict[str, Any]] = None
    audio_playback_clip: Optional[dict[str, Any]] = None
    audio_playback_clips: list[dict[str, Any]] = field(default_factory=list)
    detected_concepts: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return self.text


_TS_MARKER_RE = re.compile(r"\[t=([0-9hms:.]+)\]")


def _clip_text(c: dict[str, Any]) -> str:
    return (c.get("verbatim_text") or c.get("text_snippet") or c.get("text") or "").strip()


def _clip_start_seconds(c: dict[str, Any]) -> Optional[int]:
    """Stored start of the words: first-person ``start_ms``, else the earliest
    inline ``[t=..]`` marker. None when the store holds no timing at all.
    """
    if isinstance(c.get("start_ms"), (int, float)):
        return int(c["start_ms"]) // 1000
    marks = [parse_timestamp(m) for m in _TS_MARKER_RE.findall(_clip_text(c))]
    marks = [m for m in marks if m is not None]
    return int(min(marks)) if marks else None


def _format_time(seconds: int) -> str:
    """Format integer seconds into MM:SS or HH:MM:SS string."""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_sources_footer(clips: list[dict[str, Any]]) -> str:
    """Format Sources of Wisdom footer with book-style footnote references.

    Example:
    ---
    *Sources of Wisdom:*
    [1] Sri Krishnaji — [The Beautiful State](https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s) (01:12 – 02:45)
    """
    if not clips:
        return ""
    lines = ["---", "*Sources of Wisdom:*"]
    for i, c in enumerate(clips, 1):
        hero = c.get("_hero") or {}
        if hero:
            # A verified clip renders only stored metadata: an unstored
            # clip["video_title"] must never reach the seeker.
            speaker = hero.get("label") or "Teacher"
            title = hero.get("title") or UNTITLED_LINK_LABEL
        else:
            speaker = c.get("speaker") or "Teacher"
            title = c.get("video_title") or c.get("title") or UNTITLED_LINK_LABEL
        url = hero.get("url") or c.get("source_url") or c.get("url") or ""
        vid = c.get("video_id") or hero.get("video_id") or ""

        start_sec = hero.get("start_sec")
        if start_sec is None:
            start_sec = _clip_start_seconds(c)
        if not url and vid:
            url = f"https://www.youtube.com/watch?v={vid}" + (
                f"&t={start_sec}s" if start_sec is not None else ""
            )

        start_ms, end_ms = c.get("start_ms"), c.get("end_ms")
        timing_str = ""
        if (
            isinstance(start_ms, (int, float))
            and isinstance(end_ms, (int, float))
            and end_ms > start_ms
        ):
            s_sec = int(start_ms) // 1000
            e_sec = -(-int(end_ms) // 1000)
            timing_str = f" ({_format_time(s_sec)} – {_format_time(e_sec)})"
        elif start_sec is not None:
            timing_str = f" ({_format_time(start_sec)})"

        if url:
            lines.append(f"[{i}] {speaker} — [{title}]({url}){timing_str}")
        else:
            lines.append(f"[{i}] {speaker} — {title}{timing_str}")

    return "\n".join(lines)


def _check_clip_token_overlap(
    clip_text: str, document_text: str, min_overlap: float = 1.0
) -> tuple[bool, float]:
    """Verify that clip_text appears verbatim in document_text.

    Fast path: exact substring match (raw or cleaned).
    Fallback path: lowercase word tokens of the ASR-cleaned clip must appear as
    one contiguous run in the answer (raw or ASR-cleaned), so punctuation, case
    and deterministic stutter removal are tolerated but no word may change.
    ``min_overlap`` stays 1.0 in production: anything lower lets an LLM edit a
    teacher's words and still render them as the teacher's speech.
    """
    if not clip_text or not clip_text.strip():
        return True, 1.0

    stripped = clip_text.strip()
    if stripped in document_text:
        return True, 1.0

    cleaned = clean_verbatim_text(stripped)
    if cleaned in document_text:
        return True, 1.0

    clip_tokens = [w.lower() for w in re.findall(r"\b\w+\b", cleaned)]
    if not clip_tokens:
        return True, 1.0

    # Contiguous only: summing scattered matching blocks let an altered clip
    # pass on words found elsewhere in the answer (e.g. in a reflection
    # question). The clip must appear as one run of tokens.
    overlap = 0.0
    for doc in (document_text, clean_verbatim_text(document_text)):
        doc_tokens = [w.lower() for w in re.findall(r"\b\w+\b", doc)]
        if not doc_tokens:
            continue
        matcher = difflib.SequenceMatcher(None, clip_tokens, doc_tokens, autojunk=False)
        longest = matcher.find_longest_match(0, len(clip_tokens), 0, len(doc_tokens))
        overlap = max(overlap, longest.size / len(clip_tokens))
    return overlap >= min_overlap, overlap


def _check_footnote_citations(text: str, clips: list[dict[str, Any]]) -> tuple[bool, Optional[str]]:
    """Validate in-text footnote markers and Sources of Wisdom footer against verified clips."""
    if not clips:
        return True, None

    # Check Sources of Wisdom footer if present
    if "*Sources of Wisdom:*" in text or "Sources of Wisdom:" in text:
        footer_pattern = re.compile(r"\[(\d+)\]\s+[^\[\n]+\[([^\]]+)\]\(([^)]+)\)")
        matches = footer_pattern.findall(text)
        for idx_str, _title, url in matches:
            idx = int(idx_str)
            if idx < 1 or idx > len(clips):
                return False, f"Footnote citation [{idx}] out of range (expected 1 to {len(clips)})"
            target_clip = clips[idx - 1]
            vid = str(target_clip.get("video_id") or "")
            if vid and vid not in url:
                return (
                    False,
                    f"Footnote citation [{idx}] URL does not match verified clip video_id {vid}: {url}",
                )

    # Check in-text footnote markers [k]
    divider_match = re.search(r"(?:^|\n)\s*---\s*(?:\n|$)", text)
    body = text[: divider_match.start()] if divider_match else text
    footnote_markers = [int(m) for m in re.findall(r"\[(\d+)\]", body)]
    for fn in footnote_markers:
        if fn < 1 or fn > len(clips):
            return (
                False,
                f"In-text footnote marker [{fn}] references non-existent clip (max {len(clips)})",
            )

    return True, None


def _extract_inquiry_from_chapter(text: str) -> Optional[str]:
    """Extract italic reflection questions from woven text without divider or footer."""
    if "---" not in text:
        return None
    parts = text.split("---")
    if len(parts) >= 2:
        inquiry = parts[1].strip()
        if "*Sources of Wisdom:*" in inquiry:
            inquiry = inquiry.split("*Sources of Wisdom:*")[0].strip()
        return inquiry if inquiry else None
    return None


class QuoteWeaverAssertionGate:
    """DSPy-style validation gate verifying direct teacher voice and structural invariants."""

    REQUIRED_SECTIONS: tuple[str, ...] = ()

    @classmethod
    def validate(
        cls,
        text: str,
        clips: list[dict[str, Any]],
        okf_entries: list[dict[str, Any]],
        is_practice: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """Validate generated or fallback text against strict quote-weaving invariants.

        Returns:
            (True, None) if all assertions pass.
            (False, reason_str) if any assertion fails.
        """
        if not text or len(text.strip()) < 40:
            return False, "Response text is empty or too short"

        # 1. Quality gate: ensure no machine artifacts, CoT leaks, or degradation strings
        artifact = find_artifact(text)
        if artifact is not None:
            return False, f"Detected machine artifact or CoT leak: {artifact}"

        # 1b. Strict SHA-256 transcript hash verification for every Qdrant clip
        import hashlib

        for c in clips:
            vt = (c.get("verbatim_text") or c.get("text_snippet") or c.get("text") or "").strip()
            th = c.get("transcript_hash")
            if th and vt:
                computed_hash = hashlib.sha256(vt.encode("utf-8")).hexdigest()
                if computed_hash != th:
                    return (
                        False,
                        f"Clip {c.get('video_id', 'unknown')} failed SHA-256 transcript hash mismatch verification",
                    )

        # 2. Check for banned artificial affirmations or pseudo-spiritual instructions
        text_lower = text.lower()
        for banned in _BANNED_AFFIRMATIONS:
            if banned in text_lower:
                return False, f"Detected artificial affirmation or instruction: '{banned}'"

        # 2b. Check for canned AI apologies, disclaimers, or generic AI framing
        for phrase in _CANNED_AI_PHRASES:
            if phrase in text_lower:
                return False, f"Detected canned AI phrase or disclaimer: '{phrase}'"

        # 3. Video timestamp link check
        link_pattern = re.compile(
            r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s\)\"\'>]+|youtu\.be/[^\s\)\"\'>]+)",
            re.IGNORECASE,
        )
        links = link_pattern.findall(text)
        if not links:
            return False, "Missing video timestamp link"

        # A t= is required only when a clip carries stored timing; without it a
        # t= would be a guess, so the renderer omits it.
        has_timestamp = any("t=" in link for link in links)
        if not has_timestamp and any(_clip_time_window(c) for c in clips):
            return False, "Video link lacks timestamp parameter (&t=...)"

        # If clips are provided with video_ids, verify that at least one link references a known clip
        clip_vids = {c.get("video_id") for c in clips if c.get("video_id")}
        if clip_vids:
            if not any(any(vid in link for vid in clip_vids) for link in links):
                return False, "Video link does not match any provided clip video_id"

        # 3b. Timestamp VALUE check (GAP-C1): a matching video_id with an
        # out-of-window t= is still a fabricated citation. Links to clips that
        # carry a [start_ms, end_ms] window must point inside it; clips/window-less
        # links fall back to the 12h upload ceiling so absurd values still fail.
        for link in links:
            has_t, t_s = _extract_t_seconds(link)
            if not has_t:
                continue
            if t_s is None:
                return False, f"Unparseable video timestamp value in link: {link}"
            windows = []
            for c in clips:
                if c.get("video_id") and str(c["video_id"]) in link:
                    win = _clip_time_window(c)
                    if win is not None:
                        windows.append(win)
            if windows:
                if not any(lo <= t_s <= hi for lo, hi in windows):
                    return False, (
                        f"Video timestamp t={t_s}s lies outside the cited clip's "
                        f"time window: {link}"
                    )
            elif t_s > _MAX_CLIP_TIMESTAMP_S:
                return False, (
                    f"Video timestamp t={t_s}s exceeds any possible video length: {link}"
                )

        # 4. Divider check: must have a '---' divider
        divider_match = re.search(r"(?:^|\n)\s*---\s*(?:\n|$)", text)
        if not divider_match:
            return False, "Missing '---' divider before reflection questions"

        # 4b. Ban markdown bullet points (*, -) and numbered lists (Rule 8)
        pre_divider_text = text[: divider_match.start()]
        for line in pre_divider_text.splitlines():
            sline = line.strip()
            if not sline:
                continue
            if re.match(r"^[-*•]\s+", sline):
                return False, f"Banned bullet point detected in teaching answer: '{sline[:30]}...'"
            if not is_practice and re.match(r"^\d+\.\s+", sline):
                return (
                    False,
                    f"Banned numbered list detected in non-practice teaching: '{sline[:30]}...'",
                )

        # 5. Italic reflection questions check: require italic questions (*...*) after divider
        reflection_text = text[divider_match.end() :]
        italic_matches = [
            m.strip()
            for m in re.findall(r"(?<!\*)\*([^*\n]+)\*(?!\*)", reflection_text)
            if len(m.strip()) >= 5 and not m.strip().startswith("Sources of Wisdom")
        ]
        if not italic_matches:
            return False, "Missing italic reflection questions (*...*)"

        # 6. Quoted teachings exact substring check (if quotes inside quotation marks are present)
        quote_pattern = re.compile(r'["“]([^"”]+)["”]', re.DOTALL)
        raw_quotes = quote_pattern.findall(text)

        substantive_quotes = [
            q.strip() for q in raw_quotes if len(q.strip()) >= 6 and re.search(r"\w", q)
        ]

        # Collect all valid source texts from clips and OKF entries — shared by the
        # quoted-quote check (6) and the unquoted attributed-claim check (6b).
        source_texts: list[str] = []
        for c in clips:
            for k in ("verbatim_text", "text_snippet", "text"):
                val = c.get(k)
                if val:
                    source_texts.append(str(val))
        for e in okf_entries:
            for k in ("body", "summary", "description", "title"):
                val = e.get(k)
                if val:
                    source_texts.append(str(val))
            for kt in e.get("key_teachings", []):
                if kt:
                    source_texts.append(str(kt))

        def _norm(s: str) -> str:
            s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
            s = re.sub(r"[^\w\s]", "", s)
            return re.sub(r"\s+", " ", s).strip().lower()

        normalized_sources = [_norm(s) for s in source_texts if s]

        if substantive_quotes:
            for q in substantive_quotes:
                q_norm = _norm(q)
                if len(q_norm) < 4:
                    continue
                is_valid_substring = any(q_norm in src for src in normalized_sources)
                if not is_valid_substring:
                    return False, f"Fabricated or non-verbatim quote detected: '{q}'"

        # 6b. Unquoted attributed-claim check (GAP-C2): quoting is not the only
        # way a sentence can assert "the guru said X" — an LLM opening/connective
        # naming a teacher with a speech/teaching verb must ALSO be verbatim in a
        # clip/OKF source. Scans only the pre-divider region (opening + connective
        # + clip bodies); citation header lines are machine-built from clip
        # metadata and are skipped.
        pre_divider = text[: divider_match.start()]
        for line in pre_divider.splitlines():
            line = line.strip()
            if not line or "](" in line or re.match(r"https?://\S+$", line):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", line):
                s = sentence.strip()
                if len(s) < 6:
                    continue
                if not (_TEACHER_NAME_RE.search(s) and _ATTRIBUTION_RE.search(s)):
                    continue
                s_norm = _norm(s)
                if len(s_norm) < 4 or any(s_norm in src for src in normalized_sources):
                    continue
                return False, (
                    f"Unquoted teacher-attributed claim is not verbatim in any source: '{s}'"
                )

        # 7. Verbatim DB check: EVERY provided clip's verbatim text must be present
        # intact: every word, in order (punctuation, case and ASR stutter cleanup aside)
        # no clips[:2] truncation (GAP-C3: a 3rd+ clip dropped or altered must fail the gate too).
        for c in clips:
            vt = (c.get("verbatim_text") or c.get("text_snippet") or c.get("text") or "").strip()
            if vt:
                has_overlap, overlap = _check_clip_token_overlap(vt, text)
                if not has_overlap:
                    return (
                        False,
                        f"Verbatim DB teaching for clip {c.get('video_id', 'unknown')} missing or altered (only {overlap:.1%} of its words verbatim)",
                    )

        # 8. Footnote citation check
        valid_fn, fn_reason = _check_footnote_citations(text, clips)
        if not valid_fn:
            return False, fn_reason

        return True, None


# ponytail: general string hygiene — zero hardcoded affirmation completions.
def _sanitize_step(step: str) -> str:
    """Ensure balanced quotes and terminal punctuation for practice steps."""
    s = step.strip()
    if not s:
        return ""
    if s.count('"') % 2 == 1:
        if s.endswith(","):
            s = s[:-1] + '."'
        elif not s.endswith("."):
            s = s + '."'
        else:
            s = s + '"'
    return s


_PRACTICE_QUERY_RE = re.compile(
    r"\b(?:"
    r"how to (?:meditate|breathe|practice)|"
    r"how do i (?:meditate|breathe|practice)|"
    r"teach me (?:to meditate|a meditation|a practice|how to breathe)|"
    r"guided meditation|breathing technique|sadhana|kriya|"
    r"steps to meditate|meditation technique"
    r")\b",
    re.IGNORECASE,
)


def _is_practice_intent(query: str, intent: Optional[str] = None) -> bool:
    """Check if query intent allows/requires practice steps in the main body."""
    if intent:
        intent_up = intent.upper()
        if intent_up == "PRACTICE":
            return True
        if intent_up in (
            "QUERY",
            "DOCTRINE",
            "PHILOSOPHICAL",
            "TEACHING",
            "FACTUAL",
            "COMPARATIVE",
        ):
            return False
    return bool(_PRACTICE_QUERY_RE.search(query))


def _extract_practice_recommendation(
    okf_entries: list[dict[str, Any]],
    query: str,
) -> Optional[dict[str, Any]]:
    """Extract structured practice recommendation for the action bar metadata."""
    # Only a practice-typed OKF entry is a practice. No match means nothing
    # sourced to recommend: return None ("no action bar") rather than invent
    # steps, a duration, or recast a teaching's key points as steps.
    practice_entries = [e for e in okf_entries or [] if e.get("type") == "practice"]
    if not practice_entries:
        return None
    top = practice_entries[0]
    steps = [s for s in (_sanitize_step(t) for t in top.get("key_teachings") or []) if s]
    title = top.get("title")
    if not title or not steps:
        return None
    return {
        "title": title,
        "action_label": f"🫁 {title}",
        "type": "practice",
        "teacher": top.get("teacher"),
        "summary": top.get("summary") or top.get("description") or "",
        "steps": steps,
        "source": top.get("source"),
        # LLM-extracted OKF summary (invariant 12): never render as the teacher's words.
        "is_verbatim": False,
    }


def _clean_pointer(
    pointer: Optional[str],
    default_speaker: str = "Teacher",
    is_opening: bool = True,
) -> Optional[str]:
    """Clean and enforce strict <= 15-word constraint on minimal connective pointers.
    Forbids synthesized summaries, bullet points, and verbose lead-ins.
    """
    if not pointer or not pointer.strip():
        return None
    cleaned = pointer.strip()
    if cleaned.upper().startswith("NONE"):
        return None
    cleaned = re.sub(r"^[-*•\d\.]+\s*", "", cleaned).strip()
    words = cleaned.split()
    if len(words) > 15:
        if is_opening:
            return f"{default_speaker} speaks to a related theme:"
        return f"{default_speaker} observes:"
    return cleaned


# ponytail: clean thematic inquiry catalog — authentic Atma Vichara inquiries
# strictly free from artificial affirmations or pseudo-spiritual instructions.
# These are product-written questions, not quotes: never a doctrinal claim
# stated as fact ("all suffering is ...", 2026-10-05 QA audit), only an
# invitation to look.
_THEMATIC_INQUIRIES: dict[str, tuple[str, str, str]] = {
    "peace": (
        "When inner turmoil or conflict arises within you, what is the belief, need to be right, or fear that keeps it alive?",
        "Can you pause in the midst of reaction and ask yourself: 'Am I choosing division, or am I choosing the peace of connection?'",
        "In this moment, can you observe the disturbance in your breath and body without trying to change or justify it, allowing the inner conflict to dissolve on its own?",
    ),
    "suffering": (
        "What is the thought or expectation you are clinging to right now that creates this inner ache?",
        "Can you witness this suffering without attempting to escape it, and notice how much of it circles around your own self?",
        "What shift occurs in your body and consciousness when you shift from self-centric fear into conscious connection with life?",
    ),
    "relationships": (
        "In your relationship, are you seeking to love the other as they are, or are you seeking love to fulfill an inner emptiness?",
        "When friction surfaces with someone you care about, can you drop the compulsive need to make them wrong?",
        "How would this connection transform if you met the other from a quiet, fulfilled heart rather than an anxious demand?",
    ),
    "general": (
        "What is the primary inner state from which you are living, deciding, and acting in this chapter of your life?",
        "If you let go of the urge to resist what is currently unfolding, what space of stillness opens within you?",
        "How can you bring serene observation rather than habitual reaction to the very next challenge you encounter today?",
    ),
}


def _generate_reflection_questions(
    query: str,
    clips: list[dict[str, Any]],
    okf_entries: list[dict[str, Any]],
) -> str:
    """Generate 1-2 sharp contemplative inquiry questions (Atma Vichara) for the seeker.

    # ponytail: authentic Atma Vichara inquiry catalog — zero artificial affirmations.
    """
    q_lower = query.lower()
    if any(k in q_lower for k in ("peace", "calm", "stillness", "seren", "conflict", "stress")):
        q1, q2, _ = _THEMATIC_INQUIRIES["peace"]
    elif any(k in q_lower for k in ("suffer", "pain", "hurt", "sorrow", "fear")):
        q1, q2, _ = _THEMATIC_INQUIRIES["suffering"]
    elif any(k in q_lower for k in ("love", "relationship", "family", "attach", "partner")):
        q1, q2, _ = _THEMATIC_INQUIRIES["relationships"]
    else:
        q1, q2, _ = _THEMATIC_INQUIRIES["general"]

    return f"---\n\n*{q1}*\n\n*{q2}*"


def _verified_clips(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fail closed: render only clips whose verbatim_text matches their stored
    transcript_hash and that carry a stored speaker. A clip with no hash or no
    speaker cannot be shown as a teacher's words. This is defence in depth --
    provenance itself comes from FirstPersonPipeline's integrity gate over the
    Qdrant payload; a caller that hashes its own invented text still passes.
    """
    kept = []
    for c in clips or []:
        vt = c.get("verbatim_text") or ""
        th = c.get("transcript_hash") or ""
        if vt and th and c.get("speaker") and hashlib.sha256(vt.encode("utf-8")).hexdigest() == th:
            kept.append(c)
    if len(kept) != len(clips or []):
        logger.warning(
            "[QuoteWeaver] Dropped %d clip(s) failing hash/speaker verification",
            len(clips or []) - len(kept),
        )
    return kept


from services.attribution import resolve_attribution_label  # noqa: E402


def _stored_label(c: dict[str, Any]) -> Optional[str]:
    """Display label from payload metadata only: per-clip speaker, else teacher_id."""
    canon = canonical_speaker(str(c.get("speaker") or ""))
    if canon == "unknown":
        canon = canonical_speaker(str(c.get("teacher_id") or ""))
    return TEACHER_LABELS.get(canon)


def verify_hero_clip(
    c: dict[str, Any], sources: Optional[dict[str, SourceRecord]]
) -> Optional[dict[str, Any]]:
    """Header a clip may be rendered under, or None when any claim is unbacked.

    Speaker label, title and ``t=`` come only from stored payload metadata, and
    the whole rendered claim is re-checked by ``verify_quote`` against
    ``sources`` (the retrieved payloads, by video_id). No ``sources`` means
    nothing to check against, so nothing is rendered.
    """
    vid = str(c.get("video_id") or "")
    source = (sources or {}).get(vid)
    label = _stored_label(c)
    if source is None or label is None:
        reason = "no_stored_source" if source is None else "no_teacher_label"
        logger.warning("[QuoteWeaver] hero dropped for %s: %s", vid or "?", reason)
        return None
    title = source.title if normalise(source.title) not in ("", normalise(vid)) else ""
    start = _clip_start_seconds(c)
    url = f"https://www.youtube.com/watch?v={vid}" + (f"&t={start}s" if start is not None else "")
    quote = AttributedQuote(
        text=_clip_text(c), speaker=label, title=title, video_id=vid, start_seconds=start
    )
    verdict = verify_quote(quote, source)
    if not verdict.ok:
        logger.warning("[QuoteWeaver] hero dropped for %s: %s", vid, ",".join(verdict.failures))
        return None
    # Display label obeys the shared attribution rule (L-NO-INVENTED-CREDIT-1): is_verbatim
    # proves the text, not the speaker, so a third-party / explicitly unverified clip is never
    # headed with a bare teacher name. Verification above used the stored teacher label.
    display = resolve_attribution_label(
        label,
        speaker_verified=c.get("speaker_verified"),
        channel=c.get("channel") or c.get("channel_name"),
        route_gated=True,
    )
    return {
        "label": display or label,
        "title": title or None,
        "url": url,
        "start_sec": start,
        "video_id": vid,
    }


def audio_strip_for(c: dict[str, Any], hero: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Audio strip for a verified hero clip; None unless start AND end are stored."""
    start_ms, end_ms = c.get("start_ms"), c.get("end_ms")
    if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
        return None
    if end_ms <= start_ms:
        return None
    return {
        "video_id": hero["video_id"],
        "url": hero["url"],
        "speaker": hero["label"],
        "start_sec": int(start_ms) // 1000,
        "end_sec": -(-int(end_ms) // 1000),
        "duration_sec": -(-int(end_ms - start_ms) // 1000),
        "title": hero["title"],
    }


def is_hero_forbidden(query: str) -> bool:
    """Crisis, medical and every other blocked topic never get a teacher quote.

    FirstPersonPipeline already pre-empts these before retrieval; repeating it
    where quotes are rendered means a direct caller cannot skip it.
    """
    from guardrails.lightweight_handler import match_blocked_topic
    from services.serene_mind_engine import DistressLevel, SereneMindEngine

    if match_blocked_topic(query) is not None:
        return True
    assessment = SereneMindEngine().assess_distress(query)
    return bool(assessment and assessment.level.value >= DistressLevel.SEVERE.value)


def _hero_clips(
    query: str, clips: list[dict[str, Any]], sources: Optional[dict[str, SourceRecord]]
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Clips that may be rendered as teacher words, each carrying ``_hero``."""
    if is_hero_forbidden(query):
        return [], "safety_path_no_hero_quote"
    kept = []
    for c in _verified_clips(clips):
        hero = verify_hero_clip(c, sources)
        if hero is not None:
            kept.append({**c, "_hero": hero})
    return kept, (None if kept else "hero_quote_unverified")


def _format_clip_block(c: dict[str, Any]) -> str:
    """Render one verified clip: header from ``c["_hero"]``, body = stored text."""
    hero = c["_hero"]
    link_text = hero["title"] or UNTITLED_LINK_LABEL
    return f"**{hero['label']}** · [{link_text}]({hero['url']})\n\n{_clip_text(c)}"


_CLAIMS_DIRECT_RE = re.compile(r"\bdirect(ly)?\b|\bexactly\b|\banswers?\b", re.IGNORECASE)


def _pointer_for(pointer: Optional[str], c: dict[str, Any], is_opening: bool) -> str:
    """A pointer may name a teacher only if it is this clip's verified speaker."""
    label = c["_hero"]["label"]
    clean = _clean_pointer(pointer, default_speaker=label, is_opening=is_opening)
    named = canonical_speaker(clean or "")
    # No calibrated profile backs a "direct answer" claim (CLAUDE.md invariant
    # 3), so a pointer may not assert one, whoever wrote it.
    if (
        clean
        and len(clean) > 5
        and named in ("unknown", canonical_speaker(label))
        and not _CLAIMS_DIRECT_RE.search(clean)
    ):
        return clean
    return f"{label} speaks to a related theme:" if is_opening else f"{label} observes:"


def _format_assembled_answer(
    clips: list[dict[str, Any]],
    query: str,
    opening: Optional[str] = None,
    connective: Optional[str] = None,
    questions: Optional[str] = None,
    okf_entries: Optional[list[dict[str, Any]]] = None,
    intent: Optional[str] = None,
) -> str:
    """Assemble the final response text by stitching together minimal scaffolding
    around 100% UNTOUCHED verbatim clips from the database.

    Acoustic cadence structure:
    short punchy statement -> double newline -> flowing discourse excerpt -> double newline -> inquiry.
    """
    if not clips:
        return (
            "*No direct teaching found in the corpus for this question. "
            "Please explore the videos directly at [ekamworld.com](https://ekamworld.com).*"
        )

    blocks: list[str] = []

    # 1. Short punchy statement (minimal pointer <= 15 words)
    blocks.append(_pointer_for(opening, clips[0], is_opening=True))

    # 2. Hero: First Clip — 100% Verbatim DB Text
    blocks.append(_format_clip_block(clips[0]))

    # 3. Subsequent Clips (if present) with minimal connective bridge (<= 15 words)
    if len(clips) > 1:
        blocks.append(_pointer_for(connective, clips[1], is_opening=False))
        for clip in clips[1:]:
            blocks.append(_format_clip_block(clip))

    # 4. Practice steps never enter the answer body. OKF is LLM-extracted
    # summary text (invariant 12), so it can't sit next to verbatim clips where
    # it reads as the teacher's words; it ships only as structured
    # practice_recommendation metadata for the action bar.

    # 5. Inquiry (1-2 sharp inward Atma Vichara questions)
    if not questions or "---" not in questions:
        questions = _generate_reflection_questions(query, clips, okf_entries or [])
    blocks.append(questions)

    # 6. Sources of Wisdom Footer
    footer = _format_sources_footer(clips)
    if footer:
        blocks.append(footer)

    return "\n\n".join(blocks)


def _deterministic_fallback(
    query: str,
    clips: list[dict[str, Any]],
    okf_entries: list[dict[str, Any]],
    intent: Optional[str] = None,
) -> str:
    """Deterministic direct teacher voice when LLM is unavailable or fails assertions."""
    if not clips:
        return (
            "*No direct teaching found in the corpus for this question. "
            "Please explore the videos directly at [ekamworld.com](https://ekamworld.com).*"
        )

    # Openings name only the verified speaker (``_pointer_for``) and claim
    # nothing about the video's topic.
    opening = None
    connective = None

    questions = _generate_reflection_questions(query, clips, okf_entries)

    return _format_assembled_answer(
        clips=clips,
        query=query,
        opening=opening,
        connective=connective,
        questions=questions,
        okf_entries=okf_entries,
        intent=intent,
    )


def _build_scaffolding_prompts(
    query: str,
    clips: list[dict[str, Any]],
) -> tuple[str, str]:
    """Construct strict system and user prompts requesting ONLY minimal framing scaffolding.
    The LLM is NOT provided the teaching text to prevent summarization, rewriting, or distortion.
    """
    system_prompt = (
        "You are a serene spiritual facilitator for the wisdom teachings of Sri Preethaji and Sri Krishnaji.\n"
        "Your task is strictly to provide MINIMAL serene framing for the retrieved video teachings.\n"
        "DO NOT generate, summarize, paraphrase, or alter the spiritual teachings.\n"
        "DO NOT use bullet points (*, -), numbered lists (1. 2. 3.), or markdown headers (###).\n\n"
        "Provide exactly three fields:\n"
        "1. OPENING: A minimal pointer of 15 words or fewer introducing the discourse "
        "(e.g., 'Sri Preethaji speaks to a related theme:' or 'Sri Krishnaji observes:'). "
        "Do NOT summarize what the teacher will say.\n"
        "2. CONNECTIVE: If two clips are provided, a minimal pointer of 15 words or fewer transitioning "
        "to the second teacher's discourse (e.g., 'Sri Krishnaji further deepens this understanding:'). "
        "If only one clip is provided, output NONE.\n"
        "3. QUESTIONS: Exactly 1 or 2 sharp inward Atma Vichara (self-inquiry) reflection questions "
        "in italics (*...*) turning attention back to the observer. Do not invent affirmations, do not ask them to place hands on hearts.\n\n"
        "OUTPUT FORMAT EXACTLY:\n"
        "OPENING: <minimal pointer <= 15 words>\n"
        "CONNECTIVE: <minimal pointer <= 15 words or NONE>\n"
        "QUESTIONS:\n"
        "*<inward self-inquiry question 1>*\n"
        "*<inward self-inquiry question 2>*"
    )

    clip_info = []
    for i, c in enumerate(clips[:2], 1):
        hero = c.get("_hero") or {}
        spk = hero.get("label") or "Teacher"
        title = hero.get("title")
        clip_info.append(f"Teacher {i}: {spk}" + (f" (Discourse: '{title}')" if title else ""))

    user_prompt = (
        f"Seeker's Query: {query}\n\n"
        f"Retrieved Discourses:\n"
        + "\n".join(clip_info)
        + "\n\nProvide the OPENING, CONNECTIVE, and QUESTIONS. Do not write anything else."
    )
    return system_prompt, user_prompt


def _build_editorial_review_prompt(
    query: str,
    clips: list[dict[str, Any]],
    metadata: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    """Construct prompt for the Elite Spiritual Manuscript Editor persona.
    Enforces the Sacred Arc of Awakening, ASR proofreading, antecedent grounding,
    and zero-paraphrase invariant.
    """
    system_prompt = (
        "You are an Elite Spiritual Manuscript Editor for the sacred teachings of Sri Krishnaji and Sri Preethaji.\n"
        "Your role is to edit, proofread, and weave the authentic spoken words of the Gurus into ONE continuous, "
        "flowing book chapter in the style of 'The Four Sacred Secrets'.\n\n"
        "CORE INVARIANTS (NON-NEGOTIABLE):\n"
        "1. ZERO PARAPHRASE / ZERO REGENERATION: Do NOT rewrite, summarize, explain, or regenerate the Gurus' teachings. "
        "100% of the substantive spiritual insights, parables, and metaphors MUST remain the Gurus' authentic spoken words.\n"
        "2. ASR PROOFREADING ONLY: Proofread oral transcript artifacts: remove stuttered word repetitions "
        "(e.g., 'carried carried' -> 'carried', 'her her' -> 'her', 'healing Healing' -> 'healing'), remove Whisper decoder hallucinations "
        "(e.g., 'arise eyes.' -> 'arise.'), restore clean oral punctuation and capitalization, and excise ephemeral "
        "retreat dates or logistics (e.g., 'In February when we meet').\n"
        "3. ANTECEDENT GROUNDING: Where spoken pronouns are ambiguous without video context, anchor them to the sacred context "
        "(e.g., replace 'him living with 10 heads' with 'Ravana living with ten heads').\n"
        "4. NO HEADERS OR BULLETS: Absolutely NO markdown section headers (no ###) and NO bullet points (no *, -).\n"
        "5. SACRED ARC OF AWAKENING:\n"
        "   Weave the discourses into one seamless chapter following the natural movement of consciousness:\n"
        "   - The Seeker's Predicament (validating the inner turmoil, conflict, or division)\n"
        "   - The Foundational Law (The Two States / Inner State determining destiny)\n"
        "   - The Living Metaphor & Parable (e.g., The Hollow Bamboo / Ravana's Ten Heads)\n"
        "   - The Awakening Shift (Somatic stillness / Living presence / Dropping resistance)\n"
        "6. SACRED MICRO-BRIDGES: Connect the voices with minimal, elegant micro-bridges "
        "(e.g., 'Sri Krishnaji reveals the foundational law:', 'Sri Preethaji observes how this manifests in the heart:').\n"
        "7. FOOTNOTE CITATION MARKERS: Insert footnote markers [1], [2] at the end of corresponding discourse segments.\n"
        "8. ATMA VICHARA INQUIRY: Conclude the chapter with a single divider '---' followed by 2–3 sharp, inward "
        "contemplative reflection questions in italics (*...*) that turn the seeker's attention back to the observer.\n\n"
        "Do NOT include conversational filler, greetings, or canned AI disclaimers (e.g., 'As an AI', 'In this chapter')."
    )

    clip_blocks = []
    for i, c in enumerate(clips, 1):
        hero = c.get("_hero") or {}
        speaker = hero.get("label") or c.get("speaker") or "Teacher"
        title = hero.get("title") or c.get("video_title") or c.get("title") or "Discourse"
        raw_text = _clip_text(c)
        cleaned = clean_verbatim_text(raw_text)
        clip_blocks.append(
            f"--- DISCOURSE CLIP [{i}] ---\n"
            f"Speaker: {speaker}\n"
            f"Context / Title: {title}\n"
            f"Spoken Transcript:\n{cleaned}"
        )

    user_prompt = (
        f"Seeker Inquiry: {query}\n\n"
        f"Retrieved Spoken Discourses:\n" + "\n\n".join(clip_blocks) + "\n\n"
        "Instructions:\n"
        "Proofread, anchor antecedents, and weave the authentic spoken words above into ONE continuous book chapter "
        "with footnote markers [1], [2], followed by '---' and 2–3 italic reflection questions (*...*). "
        "Do not summarize or paraphrase. Keep the Gurus' authentic words intact."
    )
    return system_prompt, user_prompt


def _build_prompts(
    query: str,
    clips: list[dict[str, Any]],
    okf_entries: list[dict[str, Any]],
) -> tuple[str, str]:
    """Backward-compatible prompt builder alias."""
    return _build_scaffolding_prompts(query, clips)


def _parse_scaffolding(raw_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse OPENING, CONNECTIVE, and QUESTIONS from LLM output.
    Returns (opening, connective, reflection_questions).
    """
    if not raw_text or not raw_text.strip():
        return None, None, None

    opening = None
    connective = None
    questions = None

    # Parse OPENING
    m_open = re.search(
        r"(?i)OPENING:\s*(.+?)(?=\n(?:CONNECTIVE|QUESTIONS):|$)", raw_text, re.DOTALL
    )
    if m_open:
        op = m_open.group(1).strip()
        if op and not op.upper().startswith("NONE"):
            opening = op

    # Parse CONNECTIVE
    m_conn = re.search(r"(?i)CONNECTIVE:\s*(.+?)(?=\nQUESTIONS:|$)", raw_text, re.DOTALL)
    if m_conn:
        cn = m_conn.group(1).strip()
        if cn and not cn.upper().startswith("NONE"):
            connective = cn

    # Parse QUESTIONS
    m_q = re.search(r"(?i)QUESTIONS:\s*(.+)$", raw_text, re.DOTALL)
    q_block = m_q.group(1).strip() if m_q else raw_text
    italic_qs = [
        m.strip()
        for m in re.findall(r"(?<!\*)\*([^*\n]+)\*(?!\*)", q_block)
        if len(m.strip()) >= 10
    ]
    if len(italic_qs) >= 1:
        questions = "---\n\n" + "\n\n".join(f"*{q}*" for q in italic_qs[:2])

    return opening, connective, questions


async def _generate_llm(llm_service: Any, system_prompt: str, user_prompt: str) -> str:
    """Invoke an LLM service (sync or async) and return the generated text."""
    if hasattr(llm_service, "generate"):
        res = llm_service.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        if inspect.isawaitable(res):
            return await res
        return str(res)
    elif callable(llm_service):
        res = llm_service(system_prompt, user_prompt)
        if inspect.isawaitable(res):
            return await res
        return str(res)
    raise TypeError(f"llm_service must have .generate() or be callable, got {type(llm_service)}")


def _run_sync(coro_or_fn: Any, timeout: float = 4.5) -> Any:
    """Run an async coroutine or factory cleanly from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:

            def _runner():
                async def _inner():
                    coro = coro_or_fn() if callable(coro_or_fn) else coro_or_fn
                    return await asyncio.wait_for(coro, timeout=timeout)

                return asyncio.run(_inner())

            return pool.submit(_runner).result(timeout=timeout + 0.5)
    else:
        coro = coro_or_fn() if callable(coro_or_fn) else coro_or_fn
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


def _no_hero_result(reason: str) -> QuoteWeaverResult:
    """No teacher quote, no audio strip, no citations: the caller falls back."""
    logger.info("[QuoteWeaver] no hero quote rendered: %s", reason)
    return QuoteWeaverResult(
        text=_deterministic_fallback("", [], []),
        passed_gate=False,
        fallback_used=True,
        gate_reason=reason,
        audio_playback_clips=[],
    )


class QuoteWeaverService:
    """Weaves first-person teacher clips and curated OKF doctrine into an integrated spiritual answer."""

    def __init__(self, llm_service: Optional[Any] = None) -> None:
        self.llm_service = llm_service

    def weave(
        self,
        query: str,
        clips: list[dict[str, Any]],
        okf_entries: list[dict[str, Any]],
        llm_service: Optional[Any] = None,
        intent: Optional[str] = None,
        sources: Optional[dict[str, SourceRecord]] = None,
    ) -> QuoteWeaverResult:
        """Weave verified clips into an authentic first-person teaching voice.

        ``sources`` maps video_id to the stored record the clips were retrieved
        from (``quote_fidelity.sources_from_payloads``). Every clip is checked
        against it before rendering; a clip that fails is dropped, and when none
        survive the result has ``passed_gate=False`` and empty text so the caller
        falls back to its normal grounded answer with no quote and no audio.

        # ponytail: Extractive-Abstractive Hybrid Architecture.
        100% of teachings are formatted directly from the DB clips by Python code.
        If llm_service is provided and hybrid/editorial mode is enabled, prompts LLM strictly for
        editorial manuscript proofreading, micro-bridges, and dynamic Atma Vichara reflection questions.
        The teaching text itself is NEVER regenerated by LLM.
        Falls back to clean deterministic template on timeout or assertion failure.
        """
        clips, no_hero = _hero_clips(query, clips, sources)
        if no_hero:
            return _no_hero_result(no_hero)

        all_audios = []
        for c in clips:
            hero = c.get("_hero")
            if hero:
                strip = audio_strip_for(c, hero)
                if strip:
                    all_audios.append(strip)
        audio = all_audios[0] if all_audios else None

        active_llm = llm_service or self.llm_service
        mode = getattr(settings, "first_person_mode", "retrieval_only")
        is_practice = _is_practice_intent(query, intent)
        practice_rec = _extract_practice_recommendation(okf_entries, query)

        if not active_llm or mode not in ("hybrid", "editorial") or not clips:
            text = _deterministic_fallback(query, clips, okf_entries, intent=intent)
            inquiry = _extract_inquiry_from_chapter(text)
            return QuoteWeaverResult(
                text=text,
                passed_gate=True,
                fallback_used=True,
                gate_reason="deterministic_clip_only_mode",
                atma_vichara_inquiry=inquiry,
                practice_recommendation=practice_rec,
                audio_playback_clip=audio,
                audio_playback_clips=all_audios,
            )

        try:
            system_prompt, user_prompt = _build_editorial_review_prompt(query, clips)
            raw = _run_sync(
                lambda: _generate_llm(active_llm, system_prompt, user_prompt), timeout=3.5
            )
            if raw and isinstance(raw, str) and raw.strip():
                raw_str = raw.strip()
                if "OPENING:" in raw_str:
                    opening, connective, questions = _parse_scaffolding(raw_str)
                    assembled = _format_assembled_answer(
                        clips=clips,
                        query=query,
                        opening=opening,
                        connective=connective,
                        questions=questions,
                        okf_entries=okf_entries,
                        intent=intent,
                    )
                else:
                    if "*Sources of Wisdom:*" not in raw_str:
                        footer = _format_sources_footer(clips)
                        assembled = (raw_str + "\n\n" + footer) if footer else raw_str
                    else:
                        assembled = raw_str

                valid, reason = QuoteWeaverAssertionGate.validate(
                    assembled, clips, okf_entries, is_practice=is_practice
                )
                if valid:
                    inquiry = _extract_inquiry_from_chapter(assembled)
                    return QuoteWeaverResult(
                        text=assembled,
                        passed_gate=True,
                        fallback_used=False,
                        atma_vichara_inquiry=inquiry,
                        practice_recommendation=practice_rec,
                        audio_playback_clip=audio,
                        audio_playback_clips=all_audios,
                    )
                logger.warning(
                    "[QuoteWeaverService] Hybrid output failed assertion gate: %s; using fallback",
                    reason,
                )
        except Exception as e:
            logger.warning("[QuoteWeaverService] Hybrid LLM weaving error: %s; using fallback", e)

        fallback_text = _deterministic_fallback(query, clips, okf_entries, intent=intent)
        inquiry = _extract_inquiry_from_chapter(fallback_text)
        return QuoteWeaverResult(
            text=fallback_text,
            passed_gate=True,
            fallback_used=True,
            gate_reason="assertion_gate_or_timeout_fallback",
            atma_vichara_inquiry=inquiry,
            practice_recommendation=practice_rec,
            audio_playback_clip=audio,
            audio_playback_clips=all_audios,
        )

    async def weave_async(
        self,
        query: str,
        clips: list[dict[str, Any]],
        okf_entries: list[dict[str, Any]],
        llm_service: Optional[Any] = None,
        intent: Optional[str] = None,
        sources: Optional[dict[str, SourceRecord]] = None,
    ) -> QuoteWeaverResult:
        """Async counterpart of weave()."""
        clips, no_hero = _hero_clips(query, clips, sources)
        if no_hero:
            return _no_hero_result(no_hero)

        all_audios = []
        for c in clips:
            hero = c.get("_hero")
            if hero:
                strip = audio_strip_for(c, hero)
                if strip:
                    all_audios.append(strip)
        audio = all_audios[0] if all_audios else None

        active_llm = llm_service or self.llm_service
        mode = getattr(settings, "first_person_mode", "retrieval_only")
        is_practice = _is_practice_intent(query, intent)
        practice_rec = _extract_practice_recommendation(okf_entries, query)

        if not active_llm or mode not in ("hybrid", "editorial") or not clips:
            text = _deterministic_fallback(query, clips, okf_entries, intent=intent)
            inquiry = _extract_inquiry_from_chapter(text)
            return QuoteWeaverResult(
                text=text,
                passed_gate=True,
                fallback_used=True,
                gate_reason="deterministic_clip_only_mode",
                atma_vichara_inquiry=inquiry,
                practice_recommendation=practice_rec,
                audio_playback_clip=audio,
                audio_playback_clips=all_audios,
            )

        try:
            system_prompt, user_prompt = _build_editorial_review_prompt(query, clips)
            raw = await asyncio.wait_for(
                _generate_llm(active_llm, system_prompt, user_prompt), timeout=3.5
            )
            if raw and isinstance(raw, str) and raw.strip():
                raw_str = raw.strip()
                if "OPENING:" in raw_str:
                    opening, connective, questions = _parse_scaffolding(raw_str)
                    assembled = _format_assembled_answer(
                        clips=clips,
                        query=query,
                        opening=opening,
                        connective=connective,
                        questions=questions,
                        okf_entries=okf_entries,
                        intent=intent,
                    )
                else:
                    if "*Sources of Wisdom:*" not in raw_str:
                        footer = _format_sources_footer(clips)
                        assembled = (raw_str + "\n\n" + footer) if footer else raw_str
                    else:
                        assembled = raw_str

                valid, reason = QuoteWeaverAssertionGate.validate(
                    assembled, clips, okf_entries, is_practice=is_practice
                )
                if valid:
                    inquiry = _extract_inquiry_from_chapter(assembled)
                    return QuoteWeaverResult(
                        text=assembled,
                        passed_gate=True,
                        fallback_used=False,
                        atma_vichara_inquiry=inquiry,
                        practice_recommendation=practice_rec,
                        audio_playback_clip=audio,
                        audio_playback_clips=all_audios,
                    )
                logger.warning(
                    "[QuoteWeaverService] Hybrid output failed assertion gate: %s; using fallback",
                    reason,
                )
        except Exception as e:
            logger.warning("[QuoteWeaverService] Hybrid LLM weaving error: %s; using fallback", e)

        fallback_text = _deterministic_fallback(query, clips, okf_entries, intent=intent)
        inquiry = _extract_inquiry_from_chapter(fallback_text)
        return QuoteWeaverResult(
            text=fallback_text,
            passed_gate=True,
            fallback_used=True,
            gate_reason="assertion_gate_or_timeout_fallback",
            atma_vichara_inquiry=inquiry,
            practice_recommendation=practice_rec,
            audio_playback_clip=audio,
            audio_playback_clips=all_audios,
        )
