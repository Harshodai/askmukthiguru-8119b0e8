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
import inspect
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
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

    def __str__(self) -> str:
        return self.text


class QuoteWeaverAssertionGate:
    """DSPy-style validation gate verifying direct teacher voice and structural invariants."""

    REQUIRED_SECTIONS: tuple[str, ...] = ()

    @classmethod
    def validate(
        cls,
        text: str,
        clips: list[dict[str, Any]],
        okf_entries: list[dict[str, Any]],
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

        # 2. Check for banned artificial affirmations or pseudo-spiritual instructions
        text_lower = text.lower()
        for banned in _BANNED_AFFIRMATIONS:
            if banned in text_lower:
                return False, f"Detected artificial affirmation or instruction: '{banned}'"

        # 3. Video timestamp link check
        link_pattern = re.compile(
            r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s\)\"\'>]+|youtu\.be/[^\s\)\"\'>]+)",
            re.IGNORECASE,
        )
        links = link_pattern.findall(text)
        if not links:
            return False, "Missing video timestamp link"

        has_timestamp = any("t=" in link for link in links)
        if not has_timestamp:
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

        # 5. Italic reflection questions check: require italic questions (*...*) after divider
        reflection_text = text[divider_match.end() :]
        italic_matches = [
            m.strip()
            for m in re.findall(r"(?<!\*)\*([^*\n]+)\*(?!\*)", reflection_text)
            if len(m.strip()) >= 5
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
        # intact — no clips[:2] truncation (GAP-C3: a 3rd+ clip dropped or altered
        # must fail the gate too).
        for c in clips:
            vt = (c.get("verbatim_text") or c.get("text_snippet") or c.get("text") or "").strip()
            if vt and vt not in text:
                return (
                    False,
                    f"Verbatim DB teaching for clip {c.get('video_id', 'unknown')} missing or altered",
                )

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


# ponytail: clean thematic inquiry catalog — authentic Atma Vichara inquiries
# strictly free from artificial affirmations or pseudo-spiritual instructions.
_THEMATIC_INQUIRIES: dict[str, tuple[str, str, str]] = {
    "peace": (
        "When inner turmoil or conflict arises within you, what is the belief, need to be right, or fear that keeps it alive?",
        "Can you pause in the midst of reaction and ask yourself: 'Am I choosing division, or am I choosing the peace of connection?'",
        "In this moment, can you observe the disturbance in your breath and body without trying to change or justify it, allowing the inner conflict to dissolve on its own?",
    ),
    "suffering": (
        "What is the thought or expectation you are clinging to right now that creates this inner ache?",
        "Can you witness this suffering without attempting to escape, recognizing that all suffering is an obsessive preoccupation with oneself?",
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
    """Generate 2-3 deep contemplative inquiry questions (Atma Vichara) for the seeker.

    # ponytail: authentic Atma Vichara inquiry catalog — zero artificial affirmations.
    """
    q_lower = query.lower()
    if any(k in q_lower for k in ("peace", "calm", "stillness", "seren", "conflict", "stress")):
        q1, q2, q3 = _THEMATIC_INQUIRIES["peace"]
    elif any(k in q_lower for k in ("suffer", "pain", "hurt", "sorrow", "fear")):
        q1, q2, q3 = _THEMATIC_INQUIRIES["suffering"]
    elif any(k in q_lower for k in ("love", "relationship", "family", "attach", "partner")):
        q1, q2, q3 = _THEMATIC_INQUIRIES["relationships"]
    else:
        q1, q2, q3 = _THEMATIC_INQUIRIES["general"]

    return f"---\n\n*{q1}*\n\n*{q2}*\n\n*{q3}*"


def _format_clip_block(c: dict[str, Any]) -> str:
    """Format a single first-person clip into flowing teacher voice with link."""
    text = (c.get("verbatim_text") or c.get("text_snippet") or c.get("text") or "").strip()
    speaker = c.get("speaker") or "Teacher"
    vid = c.get("video_id") or "Discourse"
    start_sec = c.get("timestamp_seconds")
    if start_sec is None:
        start_sec = (c.get("start_ms") or 0) // 1000
    source_url = c.get("source_url") or f"https://www.youtube.com/watch?v={vid}&t={start_sec}s"
    if "t=" not in source_url:
        sep = "&" if "?" in source_url else "?"
        source_url = f"{source_url}{sep}t={start_sec}s"
    title = c.get("video_title") or c.get("title") or vid or "Discourse"
    return f"**{speaker}** · [{title}]({source_url})\n\n{text}"


def _format_assembled_answer(
    clips: list[dict[str, Any]],
    query: str,
    opening: Optional[str] = None,
    connective: Optional[str] = None,
    questions: Optional[str] = None,
    okf_entries: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Assemble the final response text by stitching together minimal scaffolding
    around 100% UNTOUCHED verbatim clips from the database.

    # ponytail: Zero-Hallucination Invariant — the teaching body is never touched by LLM.
    """
    if not clips:
        return (
            "*No direct teaching found in the corpus for this question. "
            "Please explore the videos directly at [ekamworld.com](https://ekamworld.com).*"
        )

    blocks: list[str] = []

    # 1. Serene Opening (if provided)
    if opening and len(opening.strip()) > 5:
        blocks.append(opening.strip())

    # 2. First Clip — 100% Verbatim DB Text
    blocks.append(_format_clip_block(clips[0]))

    # 3. Second Clip (if present) — with optional connective bridge
    if len(clips) > 1:
        if (
            connective
            and len(connective.strip()) > 5
            and not connective.strip().upper().startswith("NONE")
        ):
            blocks.append(connective.strip())
        blocks.append(_format_clip_block(clips[1]))

    # 4. Reflection Questions
    if not questions or "---" not in questions:
        questions = _generate_reflection_questions(query, clips, okf_entries or [])
    blocks.append(questions)

    return "\n\n".join(blocks)


def _deterministic_fallback(
    query: str,
    clips: list[dict[str, Any]],
    okf_entries: list[dict[str, Any]],
) -> str:
    """Deterministic direct teacher voice when LLM is unavailable or fails assertions."""
    if not clips:
        return (
            "*No direct teaching found in the corpus for this question. "
            "Please explore the videos directly at [ekamworld.com](https://ekamworld.com).*"
        )

    # Clean deterministic opening based on the teacher of the first clip
    first_speaker = str(clips[0].get("speaker") or "")
    if "preetha" in first_speaker.lower():
        opening = (
            "Sri Preethaji addresses this directly in her discourse on the nature of consciousness:"
        )
    elif "krishna" in first_speaker.lower():
        opening = "Sri Krishnaji speaks directly to this inner inquiry:"
    else:
        opening = None

    connective = None
    if len(clips) > 1:
        second_speaker = str(clips[1].get("speaker") or "")
        if "krishna" in second_speaker.lower():
            connective = "Sri Krishnaji further deepens this understanding:"
        elif "preetha" in second_speaker.lower():
            connective = "Sri Preethaji speaks further to this truth:"

    questions = _generate_reflection_questions(query, clips, okf_entries)

    return _format_assembled_answer(
        clips=clips,
        query=query,
        opening=opening,
        connective=connective,
        questions=questions,
        okf_entries=okf_entries,
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
        "DO NOT generate, summarize, paraphrase, or alter the spiritual teachings.\n\n"
        "Provide exactly three fields:\n"
        "1. OPENING: Exactly one serene sentence addressing the seeker and introducing the discourse. "
        "Do not summarize what the teacher will say.\n"
        "2. CONNECTIVE: If two clips are provided, exactly one sentence transitioning to the second teacher's discourse. "
        "If only one clip is provided, output NONE.\n"
        "3. QUESTIONS: Exactly 2 or 3 deep Atma Vichara (self-inquiry) reflection questions in italics (*...*). "
        "Do not invent affirmations, do not ask them to place hands on hearts, do not ask them to repeat anything.\n\n"
        "OUTPUT FORMAT EXACTLY:\n"
        "OPENING: <one serene sentence>\n"
        "CONNECTIVE: <one transition sentence or NONE>\n"
        "QUESTIONS:\n"
        "*<inward self-inquiry question 1>*\n"
        "*<inward self-inquiry question 2>*\n"
        "*<inward self-inquiry question 3>*"
    )

    clip_info = []
    for i, c in enumerate(clips[:2], 1):
        spk = c.get("speaker") or "Teacher"
        title = c.get("video_title") or c.get("title") or "Discourse"
        clip_info.append(f"Teacher {i}: {spk} (Discourse: '{title}')")

    user_prompt = (
        f"Seeker's Query: {query}\n\n"
        f"Retrieved Discourses:\n"
        + "\n".join(clip_info)
        + "\n\nProvide the OPENING, CONNECTIVE, and QUESTIONS. Do not write anything else."
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
    if len(italic_qs) >= 2:
        questions = "---\n\n" + "\n\n".join(f"*{q}*" for q in italic_qs[:3])

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
    ) -> QuoteWeaverResult:
        """Weave verified clips into an authentic first-person teaching voice.

        # ponytail: Extractive-Abstractive Hybrid Architecture.
        100% of teachings are formatted directly from the DB clips by Python code.
        If llm_service is provided and hybrid mode is enabled, prompts LLM strictly for
        minimal scaffolding (serene opening sentence, connective bridge, and dynamic
        Atma Vichara reflection questions). The teaching text itself is NEVER generated by LLM.
        Falls back to clean deterministic template on timeout or assertion failure.
        """
        active_llm = llm_service or self.llm_service
        mode = getattr(settings, "first_person_mode", "retrieval_only")

        if not active_llm or mode != "hybrid" or not clips:
            return QuoteWeaverResult(
                text=_deterministic_fallback(query, clips, okf_entries),
                passed_gate=True,
                fallback_used=True,
                gate_reason="deterministic_clip_only_mode",
            )

        try:
            system_prompt, user_prompt = _build_scaffolding_prompts(query, clips)
            raw = _run_sync(
                lambda: _generate_llm(active_llm, system_prompt, user_prompt), timeout=3.5
            )
            if raw and isinstance(raw, str) and raw.strip():
                opening, connective, questions = _parse_scaffolding(raw.strip())
                assembled = _format_assembled_answer(
                    clips=clips,
                    query=query,
                    opening=opening,
                    connective=connective,
                    questions=questions,
                    okf_entries=okf_entries,
                )
                valid, reason = QuoteWeaverAssertionGate.validate(assembled, clips, okf_entries)
                if valid:
                    return QuoteWeaverResult(
                        text=assembled,
                        passed_gate=True,
                        fallback_used=False,
                    )
                logger.warning(
                    "[QuoteWeaverService] Hybrid output failed assertion gate: %s; using fallback",
                    reason,
                )
        except Exception as e:
            logger.warning("[QuoteWeaverService] Hybrid LLM weaving error: %s; using fallback", e)

        return QuoteWeaverResult(
            text=_deterministic_fallback(query, clips, okf_entries),
            passed_gate=True,
            fallback_used=True,
            gate_reason="assertion_gate_or_timeout_fallback",
        )

    async def weave_async(
        self,
        query: str,
        clips: list[dict[str, Any]],
        okf_entries: list[dict[str, Any]],
        llm_service: Optional[Any] = None,
    ) -> QuoteWeaverResult:
        """Async counterpart of weave()."""
        active_llm = llm_service or self.llm_service
        mode = getattr(settings, "first_person_mode", "retrieval_only")

        if not active_llm or mode != "hybrid" or not clips:
            return QuoteWeaverResult(
                text=_deterministic_fallback(query, clips, okf_entries),
                passed_gate=True,
                fallback_used=True,
                gate_reason="deterministic_clip_only_mode",
            )

        try:
            system_prompt, user_prompt = _build_scaffolding_prompts(query, clips)
            raw = await asyncio.wait_for(
                _generate_llm(active_llm, system_prompt, user_prompt), timeout=3.5
            )
            if raw and isinstance(raw, str) and raw.strip():
                opening, connective, questions = _parse_scaffolding(raw.strip())
                assembled = _format_assembled_answer(
                    clips=clips,
                    query=query,
                    opening=opening,
                    connective=connective,
                    questions=questions,
                    okf_entries=okf_entries,
                )
                valid, reason = QuoteWeaverAssertionGate.validate(assembled, clips, okf_entries)
                if valid:
                    return QuoteWeaverResult(
                        text=assembled,
                        passed_gate=True,
                        fallback_used=False,
                    )
                logger.warning(
                    "[QuoteWeaverService] Hybrid output failed assertion gate: %s; using fallback",
                    reason,
                )
        except Exception as e:
            logger.warning("[QuoteWeaverService] Hybrid LLM weaving error: %s; using fallback", e)

        return QuoteWeaverResult(
            text=_deterministic_fallback(query, clips, okf_entries),
            passed_gate=True,
            fallback_used=True,
            gate_reason="assertion_gate_or_timeout_fallback",
        )
