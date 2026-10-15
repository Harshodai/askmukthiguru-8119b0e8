"""
Mukthi Guru — First-Person Verbatim Pipeline (Phase F)

Executes the specialized verbatim-serving path behind FIRST_PERSON_MODE.
An answer is the teacher's own recorded words, served as a validated pointer
with exact seconds and speaker identity, never LLM-generated text.

Pipeline Flow:
  1. Crisis/Safety Pre-Check (fails closed to crisis helplines)
  2. Exact-Match Cache Check (exact query hash; strictly NO semantic cache)
  3. Hybrid Retrieval from FirstPersonStore (dense + sparse)
  4. Serve-time Integrity Gate (hash match, allowlisted speaker, no artifacts)
  5. Calibrated Confidence Decision (cosine of query vs top-1 clip):
       - No calibration profile: every non-empty answer is 'weak_match'
       - Confident (>= profile threshold): direct first-person teaching(s)
       - Below threshold: closest clip labeled 'Related, not a direct answer'
  6. Timestamped Citation Formatting & Exact-Cache Population
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

import numpy as np

from app.config import settings
from app.metrics import (
    FIRST_PERSON_ABSTAIN_REASONS,
    FIRST_PERSON_LATENCY_SECONDS,
    FIRST_PERSON_LLM_TOKENS_TOTAL,
    FIRST_PERSON_QUARANTINED_TOTAL,
    FIRST_PERSON_RELEVANCE_SCORE,
    FIRST_PERSON_REQUESTS_TOTAL,
)
from guardrails.lightweight_handler import _BLOCKED_TOPICS, SAFETY_TOPICS, match_blocked_topic
from ingest.verbatim.boundaries import boundary_defects
from services.crisis_helplines import format_helplines_block
from services.first_person_store import (
    _OUTCOME_PROMISE_CLIP_RE,
    BLOCKED_PROMISE_POINT_IDS,
    FirstPersonStore,
)
from services.memory.okf_store import match_okf_entries
from services.openrouter_service import ProviderRefusalError
from services.quote_fidelity import (
    UNTITLED_LINK_LABEL,
    sources_from_payloads,
)
from services.quote_weaver import (
    _SCAFFOLD_PROMPT_VERSION,
    QuoteWeaverService,
    audio_strip_for,
    verify_hero_clip,
)
from services.serene_mind_engine import DistressLevel, SereneMindEngine
from services.text_quality_filter import find_artifact, find_asr_repetition_artifacts
from services.youtube_availability import is_youtube_video_available

logger = logging.getLogger(__name__)

# Exact cache TTL: 24 hours
EXACT_CACHE_TTL = 86400

# Required, validated keys on a calibration profile JSON.
_PROFILE_REQUIRED_KEYS = {
    "threshold",
    "score_kind",
    "n",
    "ucb_risk",
    "target_risk",
    "collection",
    "fitted_at",
}

# Product risk bound on confident answers (>=99% precision, one-sided 95%).
MAX_TARGET_RISK = 0.01

# Playback pad around a clip, per the spec's 150-300 ms. Deliberately not a
# multi-second pre-roll: clips start at speaker-turn boundaries, so seconds of
# lead-in would play the host's question or the other teacher.
CITATION_PLAYBACK_PAD_S = 0.25

# Only a serve-time verified single-teacher recording may be quoted.

_BOTH_RE = re.compile(r"\b(?:both|either|each|all\s+(?:the\s+)?(?:gurus|teachers))\b", re.I)


def requested_teacher(query: str) -> Optional[str]:
    """The one guru the seeker named (registry id), else None.

    L-FP-SPEAKER-REQUEST-1: naming exactly one guru scopes retrieval to that guru and
    nothing else is served (no other-guru substitution). Naming several, saying "both",
    or naming none keeps the multi-guru search, each clip labelled with its own speaker.
    The guru list comes from config/gurus.yaml (services/guru_registry.py).
    """
    from services.guru_registry import requested_gurus

    named = requested_gurus(query)
    if len(named) != 1 or _BOTH_RE.search(query or ""):
        return None
    return named[0]


from services.guru_registry import allowed_speaker_labels as _allowed_labels  # noqa: E402

_ALLOWED_SPEAKERS = _allowed_labels()

# A cached entry missing any of these is malformed (e.g. written by an older
# schema, or corrupted) and must be treated as a cache miss, never raised.
_CACHE_ENTRY_REQUIRED_KEYS = {"answer_text", "citations", "status", "is_direct_answer"}


def load_calibration_profile(path: str, collection: str) -> Optional[dict[str, Any]]:
    """Load and validate a fitted calibration profile JSON.

    Returns None (logging a warning) unless the file exists, parses, carries
    all required keys, was fitted with cosine scoring against this exact
    collection, and its measured risk is within its own target.
    """
    if not path:
        return None

    p = Path(path)
    if not p.is_file():
        candidates = [
            Path("/config") / p.name,
            Path("/app/config") / p.name,
            Path(__file__).resolve().parent.parent.parent / "config" / p.name,
            Path(__file__).resolve().parent.parent / path,
            Path(__file__).resolve().parent.parent.parent / path,
        ]
        for c in candidates:
            if c.is_file():
                p = c
                break

    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[FirstPersonPipeline] Could not load calibration profile '%s': %s", path, e)
        return None
    if not isinstance(data, dict):
        return None

    # ponytail: (§C audit fix) Accept demoted operational profile (claims="none", no conformal guarantees)
    # only on the owner's explicit opt-in: it has no risk bound, so it cannot
    # earn is_direct_answer by default (invariant 3; 2026-10-05 root cause).
    if data.get("claims") == "none" and not getattr(
        settings, "first_person_uncalibrated_direct_enabled", False
    ):
        logger.warning(
            "[FirstPersonPipeline] Profile '%s' is demoted (claims=none, no risk bound); "
            "not used for direct answers. Every answer is 'Related, not a direct answer'.",
            path,
        )
        return None
    if data.get("claims") == "none":
        threshold = data.get("threshold")
        if (
            threshold is None
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
        ):
            logger.warning(
                "[FirstPersonPipeline] Demoted profile '%s' has non-numeric threshold: %s",
                path,
                threshold,
            )
            return None
        score_kind = data.get("score_kind")
        if score_kind not in ("cosine", "dense_cosine"):
            logger.warning(
                "[FirstPersonPipeline] Demoted profile '%s' score_kind '%s' != cosine; ignoring.",
                path,
                score_kind,
            )
            return None
        if data.get("collection") and data.get("collection") != collection:
            logger.warning(
                "[FirstPersonPipeline] Demoted profile collection '%s' != live collection '%s'; ignoring.",
                data.get("collection"),
                collection,
            )
            return None
        return data

    if not _PROFILE_REQUIRED_KEYS.issubset(data.keys()):
        logger.warning(
            "[FirstPersonPipeline] Calibration profile '%s' missing required keys %s",
            path,
            _PROFILE_REQUIRED_KEYS - data.keys(),
        )
        return None
    if data.get("score_kind") != "dense_cosine":
        logger.warning(
            "[FirstPersonPipeline] Calibration profile score_kind '%s' != 'dense_cosine'; ignoring.",
            data.get("score_kind"),
        )
        return None
    if data.get("collection") != collection:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile collection '%s' != live collection '%s'; ignoring.",
            data.get("collection"),
            collection,
        )
        return None
    numeric = ("threshold", "ucb_risk", "target_risk")
    if not all(
        isinstance(data.get(k), (int, float)) and not isinstance(data.get(k), bool) for k in numeric
    ):
        logger.warning(
            "[FirstPersonPipeline] Calibration profile '%s' has non-numeric %s; ignoring.",
            path,
            numeric,
        )
        return None
    # The product bound is 1% risk; a profile cannot relax it by declaring a looser target.
    if data["target_risk"] > MAX_TARGET_RISK:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile target_risk %s exceeds the %s product bound; ignoring.",
            data["target_risk"],
            MAX_TARGET_RISK,
        )
        return None
    if data["ucb_risk"] > data["target_risk"]:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile ucb_risk %s exceeds target_risk %s; ignoring.",
            data.get("ucb_risk"),
            data.get("target_risk"),
        )
        return None
    return data


def _cosine_similarity(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    if not a or not b:
        return 0.0
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


# Dangling coordinating conjunction regex: clips terminating on a conjunction
# (e.g. "...fear or", "...and,", "...so.") represent incomplete grammatical clauses
# and must never be served (CLAUDE.md Invariant 10, L-SENTENCE-SPLIT-CONJUNCTION-1).
_DANGLING_CONJUNCTION_RE = re.compile(
    r"\b(or|and|so|but|because)\s*[.,;:!?…—–-]*$",
    re.IGNORECASE,
)


# B4 (plan rev 2): a clip that stops mid-sentence or opens on stray punctuation is
# a severed thought, not a teaching. Gated by first_person_boundary_guard_enabled.
_SERVE_BLOCKING_BOUNDARY_DEFECTS = frozenset(
    {
        # Head defects: clip starts mid-clause, genuinely broken text
        "head_orphan_punctuation",
        "head_headless_predicate",
        "head_conjunction",
        "head_fragment",
        # Tail: dangling preposition/conjunction/article at the very end
        "tail_dangling_word",
        "tail_severed_relative_clause",
        # REMOVED tail_no_terminal (2026-10-10): v7 corpus has 25% non-terminal
        # clips from ASR mid-sentence cuts. Hard-blocking them causes 100%
        # abstention on many common queries (Beautiful State, anxiety, two
        # states). QuoteWeaver's assertion gate validates completeness;
        # a trailing comma is ugly but answerable, a headless predicate is not.
    }
)
_SEVERED_PREPOSITION_OPENER_RE = re.compile(
    r"^(?:for|in|of|to|with|as|if|at|on|by|from|into|onto|about|than|through)\s+",
    re.IGNORECASE,
)


def _passes_integrity_gate(
    clip: dict[str, Any],
    boundary_guard_enabled: Optional[bool] = None,
    check_availability: bool = True,
) -> bool:
    """Serve-time gate: hash match, allowlisted speaker, no extraction artifact,
    no spiritual/miracle promises (H4), YouTube video availability (FI-16),
    and no dangling trailing conjunction.

    All are required. A failing clip is never served.
    """
    verbatim_text = clip.get("verbatim_text") or ""
    transcript_hash = clip.get("transcript_hash") or ""
    speaker = clip.get("speaker")
    point_id_str = str(clip.get("point_id") or clip.get("id") or clip.get("clip_id") or "")
    vid_str = str(clip.get("video_id") or "")

    if clip.get("provenance_kind") == "curated_okf" or clip.get("is_verbatim") is False:
        return False
    if clip.get("first_person_eligible") is False:
        return False

    # Hard Stop H4: Blocked promise point IDs or video IDs
    if point_id_str in BLOCKED_PROMISE_POINT_IDS or vid_str in BLOCKED_PROMISE_POINT_IDS:
        logger.warning(
            "[FirstPersonPipeline] Clip %s rejected by integrity gate: in BLOCKED_PROMISE_POINT_IDS (H4)",
            point_id_str or vid_str,
        )
        return False

    # Hard Stop H4: Spiritual / Miracle outcome promises
    if _OUTCOME_PROMISE_CLIP_RE.search(verbatim_text):
        logger.warning(
            "[FirstPersonPipeline] Clip %s rejected by integrity gate: outcome promise detected (H4)",
            point_id_str or vid_str,
        )
        return False

    # Failure Injection FI-16: YouTube video availability check
    if check_availability and vid_str:
        if not is_youtube_video_available(vid_str):
            logger.warning(
                "[FirstPersonPipeline] Clip %s rejected by integrity gate: YouTube video %s unavailable (FI-16)",
                point_id_str or vid_str,
                vid_str,
            )
            return False

    if hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest() != transcript_hash:
        return False
    if speaker not in _ALLOWED_SPEAKERS:
        return False
    if find_artifact(verbatim_text) is not None:
        return False
    if _DANGLING_CONJUNCTION_RE.search(verbatim_text):
        logger.warning(
            "[FirstPersonPipeline] Clip %s rejected by integrity gate: trailing conjunction",
            clip.get("clip_id") or clip.get("id"),
        )
        return False
    guard_active = (
        boundary_guard_enabled
        if boundary_guard_enabled is not None
        else getattr(settings, "first_person_boundary_guard_enabled", False)
    )
    if guard_active:
        # Judged on verbatim_text only. display_text is NOT evidence of a whole
        # sentence: its punctuation restorer ends every clip with a period, so
        # it "repairs" real mid-sentence cuts (2026-10-05: ~1 in 3 sampled
        # display-only passes were cuts, e.g. "...sadness, oneness," -> "oneness.").
        tokens = verbatim_text.split()
        defects = set(boundary_defects(tokens)) & _SERVE_BLOCKING_BOUNDARY_DEFECTS
        if defects:
            logger.warning(
                "[FirstPersonPipeline] Clip %s rejected by integrity gate: %s",
                clip.get("point_id") or clip.get("id"),
                ",".join(sorted(defects)),
            )
            return False
        if (
            tokens
            and tokens[0][0].islower()
            and _SEVERED_PREPOSITION_OPENER_RE.match(verbatim_text.strip())
        ):
            logger.warning(
                "[FirstPersonPipeline] Clip %s rejected by integrity gate: severed preposition opener",
                clip.get("point_id") or clip.get("id"),
            )
            return False
    return True


# ponytail: content quality gate — rejects clips that pass hash/speaker checks
# but are contextually worthless: live-event instructions, thin rhetorical openers,
# or pure discourse acknowledgments. These destroy Ask Sadhguru-style quality.
# QBUG-5 (ruled 2026-10-14, agent): 15, matching invariant 14 (CLAUDE.md) —
# the 25-word value orphaned 161 v8 clips. Fragment protection comes from the
# standalone + relevance + answerability gates, not this floor; the frozen-29Q
# re-run after this change must show served-SHOW not falling.
_MIN_TEACHING_WORDS = 15  # below this a clip cannot carry a coherent teaching

# Live-event instructions: audience logistics, not teachings.
# One shared pattern with the chat path's excerpt fallback (2026-10-05, live s4).
from services.live_event_text import (
    LIVE_EVENT_INSTRUCTION_RE as _LIVE_EVENT_INSTRUCTION_RE,  # noqa: E402
)

# Discourse acknowledgment openers: the clip starts by referencing what
# someone else just said — incomprehensible without that prior context.
_DISCOURSE_ACKNOWLEDGMENT_RE = re.compile(
    r"^(?:"
    r"yes,?\s+as you mentioned|"
    r"yes,?\s+as I mentioned|"
    r"yes,?\s+as we mentioned|"
    r"as I was saying|"
    r"as we discussed|"
    r"so,?\s+as I said|"
    r"right,?\s+so|"
    r"exactly,?\s+so|"
    r"yeah,?\s+so"
    r")",
    re.IGNORECASE,
)

# ponytail: parable character filter — clips referencing Yasme/Nomi are meaningless without story context
_PARABLE_CHARACTER_RE = re.compile(r"\b(?:Yasme|Yesme|Yasmi|Nomi)\b")

# ponytail: core wisdom keywords exemption — if clip defines fundamental teachings, do not reject it
_CORE_WISDOM_KEYWORDS_RE = re.compile(
    r"(?i)\b(?:"
    r"beautiful state|"
    r"suffering state|"
    r"two states|"
    r"inner conflict|"
    r"connection|"
    r"inner peace|"
    r"presence|"
    r"preoccupation|"
    r"stressful state|"
    r"no\s*-?\s*stress state|"
    r"oneness"
    r")\b"
)

# ponytail: rhetorical opener filter — questions that hook audience without delivering wisdom
_RHETORICAL_OPENER_RE = re.compile(
    r"^(?:"
    r"I am sure you too have tried to|"
    r"have you ever wondered why"
    r")",
    re.IGNORECASE,
)


_ORPHAN_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:these\s+are\b|this\s+space\b|it\s+is\s+possible\b|because\b|in\s+that\b"
    r"|and\b|but\b|or\b|then\b|which\b|that\s+is\s+why\b"  # not "so": "So both Preethaji and I…" is a fine opener
    r"|the\s+(?:first|second|third|fourth|fifth)\s+(?:difference|one|thing|point)\b)",
    re.IGNORECASE,
)
# Medical/causal health claims: a fragment out of context reads as a healing claim or medical
# advice (live 2026-10-11 judge: infant colic, "bedridden ... come alive", sugar physiology).
_HEALTH_CLAIM_RE = re.compile(
    r"\bcur(?:e|es|ed|ing)\b|\bcolic\w*|\bbedridden\b|\bcancer\b|\bdiabet\w+|\btumou?rs?\b"
    r"|\bchemotherap\w+|\bantidepressants?\b|\bmedications?\b|\bwrong signal to the universe\b|\byou will (?:have a )?fall\b|\bflooded by huge loads of sugar\b|\bscientifically proven\b|\boxytocin\b|\bprevent(?:ing)?\s+depression\b",
    re.IGNORECASE,
)
# One-off event/audience markers: a clip that only makes sense in that room or on that day.
_EVENT_MARKER_RE = re.compile(
    r"can\s+someone\s+tell\s+me|congratulations,?\s+you\s+have|first\s+day\s+of\s+your"
    r"|that'?s\s+the\s+day\s+today|today\s+is\s+the\s+day\s+of",
    re.IGNORECASE,
)


def _standalone_problem(text: str) -> Optional[str]:
    """Deterministic 'does this clip stand on its own' backstop (zero LLM calls).

    Live 2026-10-11 an independent judge rejected 10/24 served clips; about half started or
    ended mid-thought or pointed at a one-off event. Casing is NOT used (Whisper's casing is
    unreliable and good clips start lowercase). Returns a short reason or None.
    """
    stripped = text.rstrip()
    # Whisper punctuation is unreliable (good guided-practice clips end with no full stop), so
    # only an explicit mid-sentence ending counts: a clip cut on "," ";" ":" or a dash.
    if stripped and stripped[-1] in ",;:-\u2014\u2013":
        return "ends_mid_sentence"
    if _ORPHAN_OPENER_RE.match(text):
        return "orphan_opener"
    if _EVENT_MARKER_RE.search(text):
        return "event_marker"
    if _HEALTH_CLAIM_RE.search(text):
        return "health_claim"
    return None


def _is_transient_connection_error(exc: BaseException) -> bool:
    """True for a dropped/reset connection that is safe to retry once (read-only search)."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(
        marker in text
        for marker in (
            "server disconnected",
            "remoteprotocolerror",
            "connection reset",
            "connectionerror",
            "readerror",
            "connecterror",
        )
    )


_ALLOWLIST_CACHE: dict[str, tuple[float, frozenset[str]]] = {}
_BLOCKLIST_CACHE: dict[str, tuple[float, frozenset[str]]] = {}


def _quality_allowlist() -> Optional[frozenset[str]]:
    """Approved clip ids from ``first_person_quality_allowlist_path``, or None when the feature is off.

    Fail closed: a configured path that is missing or unreadable returns an EMPTY set (nothing is served)
    and logs an error, so a broken deploy can never silently fall back to un-reviewed clips. Re-read when the
    file's mtime changes, so approving more clips needs no restart.
    """
    path = str(getattr(settings, "first_person_quality_allowlist_path", "") or "").strip()
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
        cached = _ALLOWLIST_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        ids = data.get("approved", data) if isinstance(data, dict) else data
        allow = frozenset(str(i) for i in ids)
        _ALLOWLIST_CACHE[path] = (mtime, allow)
        return allow
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.error(
            "[FirstPersonPipeline] Quality allowlist %s unreadable (%s); serving nothing", path, exc
        )
        return frozenset()


def _quality_blocklist() -> Optional[frozenset[str]]:
    """Quarantined clip ids from ``first_person_quality_blocklist_path``, or None.

    Returns None both when the feature is off (no path configured) and when a
    configured path is missing/unreadable. The Step 4 caller tells the two
    apart via the setting: off serves normally, unreadable serves nothing
    (fail closed). Re-read when the file's mtime changes, so quarantining a
    clip needs no restart. Accepts a bare JSON list or {"blocked": [...]}.
    """
    path = str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip()
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
        cached = _BLOCKLIST_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        ids = data.get("blocked", data) if isinstance(data, dict) else data
        blocked = frozenset(str(i) for i in ids)
        _BLOCKLIST_CACHE[path] = (mtime, blocked)
        return blocked
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.error(
            "[FirstPersonPipeline] Quality blocklist %s unreadable (%s); serving nothing",
            path,
            exc,
        )
        return None


def _passes_content_quality_gate(clip: dict[str, Any], gate_enabled: Optional[bool] = None) -> bool:
    """Content quality gate: filters clips that are technically valid but contextually
    worthless — live-event instructions, thin rhetorical openers, discourse acknowledgments.

    # ponytail: content quality gate — zero LLM calls, pure regex + word-count heuristics.
    Gated by first_person_content_quality_gate_enabled (same pattern as boundary_guard).
    Returns True if the clip is rich enough to serve as a first-person teaching.
    """
    active = (
        gate_enabled
        if gate_enabled is not None
        else getattr(settings, "first_person_content_quality_gate_enabled", True)
    )
    if not active:
        return True

    text = (clip.get("verbatim_text") or "").strip()
    words = text.split()

    # Clips with verified question context (interview Q&A) can be concise (min 5 words)
    is_interview = bool(clip.get("question_text") or clip.get("question_context"))
    effective_min_words = 5 if is_interview else _MIN_TEACHING_WORDS

    # Reject clips too thin to carry a coherent teaching
    if len(words) < effective_min_words:
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: only %d words (min %d)",
            clip.get("point_id") or clip.get("video_id"),
            len(words),
            effective_min_words,
        )
        return False

    # Reject live-event instructions — crowd/logistics management, not teachings
    if _LIVE_EVENT_INSTRUCTION_RE.search(text):
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: live-event instruction pattern",
            clip.get("point_id") or clip.get("video_id"),
        )
        return False

    # Reject clips that open with pure discourse acknowledgment
    # In interview Q&A contexts, teachers often start with conversational affirmations ("Right, so...", "Yes, as we said...")
    # Only reject if the clip has no question context.
    if _DISCOURSE_ACKNOWLEDGMENT_RE.match(text) and not is_interview:
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: discourse acknowledgment opener",
            clip.get("point_id") or clip.get("video_id"),
        )
        return False

    # ponytail: parable character filter — reject narrative-only clips, but preserve core wisdom definitions
    if _PARABLE_CHARACTER_RE.search(text) and not _CORE_WISDOM_KEYWORDS_RE.search(text):
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: parable character reference without core wisdom keywords",
            clip.get("point_id") or clip.get("video_id"),
        )
        return False

    if getattr(settings, "first_person_standalone_gate_enabled", True):
        problem = _standalone_problem(text)
        if problem:
            logger.info(
                "[FirstPersonPipeline] Clip %s rejected by content quality gate: not standalone (%s)",
                clip.get("point_id") or clip.get("video_id"),
                problem,
            )
            return False

    # ponytail: rhetorical opener filter
    if _RHETORICAL_OPENER_RE.search(text):
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: rhetorical opener pattern",
            clip.get("point_id") or clip.get("video_id"),
        )
        return False

    return True


# Caption statuses that mean a human checked the transcript. Mirrors
# src/lib/transcriptStatus.ts HUMAN_REVIEWED so both sides agree.
_HUMAN_REVIEWED_CAPTIONS = frozenset({"manual_caption", "human_reviewed", "reviewed"})


def transcript_label(verbatim_text: str, caption_status: Optional[str]) -> dict[str, Any]:
    """Transcript provenance label for a served clip (WP6 / H8, 2026-10-07).

    ``transcript_status`` is ``"auto_transcript"`` unless the stored caption
    status says a human reviewed it AND the text carries no ASR word restarts;
    then ``"reviewed"``. ``asr_artifacts`` lists the restarted words found
    ("relationships", "yourself", "seek"). Label only: the text is never edited
    (served text == stored text, L-SERVE-TIME-REWRITE-1).
    """
    artifacts = find_asr_repetition_artifacts(verbatim_text or "")
    reviewed = (caption_status or "").strip().lower() in _HUMAN_REVIEWED_CAPTIONS
    return {
        "transcript_status": "reviewed" if reviewed and not artifacts else "auto_transcript",
        "asr_artifacts": artifacts,
    }


# RP-A5: version of the relevance-scoring prompt. Bumped by hand whenever
# _RELEVANCE_SYSTEM_PROMPT's rubric changes; the policy fingerprint below also
# carries a hash of the prompt text, so an unbumped edit still re-keys.
_RELEVANCE_PROMPT_VERSION = "v1"

_RELEVANCE_SYSTEM_PROMPT = (
    "You judge whether recorded teaching clips ANSWER a seeker's question. Score each numbered "
    "clip: 3 = directly answers the question in the teacher's own words; 2 = partly answers "
    "it; 1 = same broad theme but does not answer it; 0 = unrelated, an announcement about "
    "one event/audience, or a fragment that cannot stand alone. Reply ONLY with comma-separated "
    "integers, one per clip, in order, e.g. 3,1,0. No other text."
)
# 12 s (was 6): Haiku 5.5 reasons internally; ~14% of real calls timed out at 6 s (live 2026-10-11)
_RELEVANCE_TIMEOUT_S = 12.0

# CA-1 (2026-10-13): anthropic/claude-haiku-5.5 rejects non-default sampling
# values on Anthropic's API, and OpenRouter passes `temperature` through, so
# the scorer sends NO temperature key for these models (`None` = omit at the
# service layer). Any other scorer model keeps explicit 0.0.
_SCORER_NO_TEMPERATURE_MODELS = frozenset({"anthropic/claude-haiku-5.5"})

# CA-3 (2026-10-13): schema-constrained JSON output for the scorer, gated on
# the scorer-model conditional — only models known to honour OpenRouter's
# response_format passthrough take this path. Every other model keeps the
# comma-separated path below byte-identical. One path per model: on the JSON
# path a non-JSON reply is indeterminate (no comma-parse fallback), so a
# broken constraint can never masquerade as strict judgement.
_SCORER_JSON_SCHEMA_MODELS = frozenset({"anthropic/claude-haiku-5.5"})

_RELEVANCE_JSON_SYSTEM_PROMPT = (
    "You judge whether recorded teaching clips ANSWER a seeker's question. Score each numbered "
    "clip: 3 = directly answers the question in the teacher's own words; 2 = partly answers "
    "it; 1 = same broad theme but does not answer it; 0 = unrelated, an announcement about "
    'one event/audience, or a fragment that cannot stand alone. Reply with a JSON object containing a "scores" array of integers.'
)

_RELEVANCE_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "relevance_scores",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 3},
                }
            },
            "required": ["scores"],
            "additionalProperties": False,
        },
    },
}


_RELEVANCE_INDETERMINATE = -1


def _estimate_fp_tokens(*texts: Any) -> int:
    """Heuristic token estimate for one first-person LLM call (RP-C10).

    Uses the same shared estimator the provider path uses when usage metadata
    is absent. A failure returns 0 with a warning — never raises into serving.
    """
    try:
        from rag.compressor import estimate_tokens

        return sum(estimate_tokens(t if isinstance(t, str) else str(t or "")) for t in texts)
    except Exception as e:  # noqa: BLE001 - metrics must not break serving
        logger.warning("[FirstPersonPipeline] Token estimate failed; counting 0: %s", e)
        return 0


def _relevance_select(
    query: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    request_loop: Optional[Any] = None,
    token_sink: Optional[list[int]] = None,
) -> Optional[int]:
    """Index of the best clip whose relevance score >= first_person_relevance_min_score.

    None = scored, but nothing reached the minimum. ``_RELEVANCE_INDETERMINATE`` (-1) = the
    check itself failed (no llm_service, timeout, provider/policy error, degraded output, wrong
    count, any non-0..3 token). Both abstain (fail closed); they are told apart so a broken
    scorer can never masquerade as strict judgement (live 2026-10-11: a policy-blocked scorer
    produced 29/29 'relevance_below_min'). The model returns scores only; no text is
    generated and no clip text is altered.

    CA-3: for scorer models in ``_SCORER_JSON_SCHEMA_MODELS`` the scores are
    requested as schema-constrained JSON (``response_format``) and parsed with
    strict ``json.loads`` validation — never the comma-separated grammar. CA-4:
    an explicit provider refusal (``ProviderRefusalError``) maps to
    ``_RELEVANCE_INDETERMINATE`` with its own log line, distinct from below-min.
    """
    if not clips or llm_service is None or not hasattr(llm_service, "generate"):
        return _RELEVANCE_INDETERMINATE
    minimum = int(getattr(settings, "first_person_relevance_min_score", 3))
    body = "\n".join(
        # QBUG-7 (2026-10-14): full clip text, never truncated mid-clip. An
        # answer in the second half used to score as off-topic under [:450].
        f"[{i}] {(c.get('verbatim_text') or '')}"
        for i, c in enumerate(clips, 1)
    )
    user_prompt = f"Question: {query}\n\nClips:\n{body}"
    use_json_schema = False
    # Bound before the try: the except branches below estimate tokens from it.
    system_prompt = _RELEVANCE_SYSTEM_PROMPT
    try:
        import inspect

        gen_kwargs: dict[str, Any] = {"temperature": 0.0}
        scorer_model = str(getattr(settings, "first_person_relevance_model", "") or "").strip()
        if scorer_model:
            # 1024, not 24/256: Haiku 5.5 reasons internally (provider caps reasoning at max_tokens/4) and an
            # empty visible reply came back at 256 for ~half of real clip groups (live 2026-10-11).
            gen_kwargs.update(model=scorer_model, max_tokens=1024)
            if scorer_model in _SCORER_NO_TEMPERATURE_MODELS:
                gen_kwargs["temperature"] = None  # omit the key (CA-1)
            if scorer_model in _SCORER_JSON_SCHEMA_MODELS:
                gen_kwargs["response_format"] = _RELEVANCE_JSON_SCHEMA  # CA-3
        use_json_schema = bool(gen_kwargs.get("response_format"))
        system_prompt = (
            _RELEVANCE_JSON_SYSTEM_PROMPT if use_json_schema else _RELEVANCE_SYSTEM_PROMPT
        )

        async def _call() -> str:
            res = llm_service.generate(
                system_prompt=system_prompt, user_prompt=user_prompt, **gen_kwargs
            )
            if inspect.isawaitable(res):
                res = await res
            return str(res)

        raw = run_llm_coroutine(_call, _RELEVANCE_TIMEOUT_S, request_loop)
    except ProviderRefusalError as e:  # noqa: BLE001 - CA-4: fail closed, distinct line
        logger.info("[FirstPersonPipeline] Relevance check refused by provider (%s); abstaining", e)
        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(system_prompt, user_prompt))
        return _RELEVANCE_INDETERMINATE
    except Exception as e:  # noqa: BLE001 - fail closed
        logger.info("[FirstPersonPipeline] Relevance check indeterminate (timeout/error): %s", e)
        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(system_prompt, user_prompt))
        return _RELEVANCE_INDETERMINATE
    if token_sink is not None:
        token_sink.append(_estimate_fp_tokens(system_prompt, user_prompt, raw))
    if use_json_schema:
        try:
            decoded = json.loads(str(raw).strip())
            candidate = decoded.get("scores") if isinstance(decoded, dict) else None
            if not isinstance(candidate, list):
                raise ValueError("missing scores array")
            scores = []
            for v in candidate:
                # bool is an int subclass — True must not pass as 1.
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError(f"non-integer score {v!r}")
                scores.append(v)
        except (ValueError, KeyError, TypeError, AttributeError):
            logger.info(
                "[FirstPersonPipeline] Relevance check unparseable JSON output %r; abstaining",
                str(raw)[:60],
            )
            return _RELEVANCE_INDETERMINATE
    else:
        try:
            scores = [int(tok) for tok in str(raw).strip().replace(" ", "").split(",")]
        except ValueError:
            # The reply is a model answer to a scoring prompt (never seeker words); cap and flatten it.
            logger.info(
                "[FirstPersonPipeline] Relevance check unparseable output %r; abstaining",
                str(raw)[:60],
            )
            return _RELEVANCE_INDETERMINATE
    if len(scores) != len(clips) or any(not 0 <= v <= 3 for v in scores):
        logger.info("[FirstPersonPipeline] Relevance check malformed scores %s; abstaining", scores)
        return _RELEVANCE_INDETERMINATE
    best = max(range(len(scores)), key=lambda i: (scores[i], -i))  # highest score, earliest wins
    # RP-C10: observe the best candidate's score for served answers AND
    # below-min abstentions alike (the margin is the signal); indeterminate
    # runs never reach here, so no valid score exists to observe.
    FIRST_PERSON_RELEVANCE_SCORE.observe(scores[best])
    return best if scores[best] >= minimum else None


# ponytail: LLM reranker — selects clip indices, never generates text. Timeout 2.5s, fallback = cosine order.
def _llm_rerank_clips(
    query: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    timeout_s: float = 2.5,
    token_sink: Optional[list[int]] = None,
) -> list[dict[str, Any]]:
    """Use LLM to rerank clips by relevance. Returns clips in reranked order.

    The LLM receives the query and clip verbatim texts and returns ONLY a
    comma-separated list of 1-indexed clip numbers (e.g. '2,1,3').
    No text is generated — the output is a ranking signal only.
    Falls back to cosine order if LLM times out or returns unparseable output.
    """
    if not clips or llm_service is None or len(clips) <= 1:
        return clips

    clip_texts = []
    for i, c in enumerate(clips[:8], 1):  # evaluate up to 8 candidate clips
        text = (c.get("verbatim_text") or "")[:350]
        clip_texts.append(f"[{i}] {text}")

    system_prompt = (
        "You are a spiritual teaching retrieval system. Given a seeker's query and "
        "verbatim clips from Sri Preethaji and Sri Krishnaji, rank the clips from "
        "most to least relevant to answering the seeker's query.\n"
        "Reply ONLY with a comma-separated list of clip numbers, e.g.: 2,1,3\n"
        "No other text. No explanation."
    )
    user_prompt = f"Query: {query}\n\nClips:\n" + "\n".join(clip_texts)

    try:
        import inspect

        async def _call() -> Optional[str]:
            if hasattr(llm_service, "generate"):
                res = llm_service.generate(system_prompt=system_prompt, user_prompt=user_prompt)
                if inspect.isawaitable(res):
                    res = await res
                return str(res).strip()
            return None

        raw = run_llm_coroutine(_call, timeout_s)

        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(system_prompt, user_prompt, raw))
        if not raw:
            return clips

        # Parse '2,1,3' -> [1, 0, 2] (0-indexed)
        indices = []
        for part in raw.replace(" ", "").split(","):
            try:
                idx = int(part) - 1  # 1-indexed to 0-indexed
                if 0 <= idx < len(clips):
                    indices.append(idx)
            except ValueError:
                pass

        if not indices:
            return clips

        # Reorder: ranked clips first, then any not mentioned
        mentioned = set(indices)
        reranked = [clips[i] for i in indices] + [
            clips[i] for i in range(len(clips)) if i not in mentioned
        ]
        logger.debug("[LLM rerank] order: %s", indices)
        return reranked

    except Exception as e:
        logger.debug("[LLM rerank] fallback (timeout/error): %s", e)
        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(system_prompt, user_prompt))
        return clips  # fallback: cosine order


# Phase 2 answerability gate (plan REVISION 2026-09-30): one named constant
# so tests and docs can cite it. Raised 2.5 -> 4.0 on 2026-10-03 after
# validation run 2: EVERY one of the 22/141 indeterminates was a cap-hit
# (>=2400ms, 0 fast-fails — the loop fix held), while real verdict latencies
# ran p90=1943ms / max=2470ms against deepseek-chat. 4.0s = ~1.6x observed
# max (Headroom), and a timeout still fails toward honest abstention.
# 6.0 s (was 4.0): live 2026-10-11 ~7% of on-topic questions timed out at 4 s on a
# slow provider response and were abstained (fail-closed). Only slow calls pay for it.
_ANSWERABILITY_TIMEOUT_S = 6.0

# Static summary of the teachers' domain for the question-only classifier.
# Out-of-scope vocabulary IS _BLOCKED_TOPICS' keys — the same Step 1b topic-rail
# vocabulary (execute() line "Step 1b: Topic rail") — so the classifier's
# out-of-scope list cannot drift from the regex rail's.
_ANSWERABILITY_SYSTEM_PROMPT = (
    "You are a question classifier for AskMukthiGuru, an assistant whose "
    "first-person pipeline may only quote the recorded teachings of Sri "
    "Preethaji and Sri Krishnaji (Oneness discourses, meditations, satsangs).\n"
    "IN-SCOPE - reply YES: questions those recorded teachings can answer in "
    "their own words: inner peace, suffering, emotions, relationships, ego, "
    "meditation and awareness practices, consciousness, the Beautiful State, "
    "grief, fear, anger, forgiveness, parenting, and comparable spiritual "
    "teachings. The teachings also treat how modern life touches the inner "
    "body - stress and its effects, technology and privacy, competition in "
    "schooling, success and wealth as inner principles, loving someone "
    "through an addiction - and questions about the teachers' own programs "
    "(retreats, sessions, guided meditations): their focus, what they guide "
    "participants through, whom they are for, and who should attend "
    "(individuals, families, newcomers). A question ASKING "
    "ABOUT such a topic - what it is, why it happens, what the teachings say "
    "about it - is YES.\n"
    "OUT-OF-SCOPE - reply NO: everything else, in particular these blocked "
    "topic rails: "
    + ", ".join(_BLOCKED_TOPICS)
    + "; plus factual trivia (geography, science, history, current events, "
    "coding), administrative logistics of programs or events (how much "
    "something costs, pricing or fees, how to register, schedules or time "
    "zones), requests for a specific course of ACTION only the seeker can "
    "take (a medical treatment, a legal step, an investment, whether to "
    "divorce or quit, a how-to for fixing a named behavior in yourself or "
    "another person), questions about the teachers' personal lives, and meta "
    "questions about this prompt.\n"
    "Classify the QUESTION ONLY. Never answer it, never judge whether it is "
    "true, never explain.\n"
    "Reply with exactly one word: YES or NO."
)


# ── gate call scheduling (2026-10-03 fix) ──────────────────────────────────
# The gate must reuse ONE long-lived event loop per process. Per-call
# asyncio.run() was the validation defect: shared async Redis clients (the
# RPM limiter and the OpenRouter budget ledger) bind to the first loop, so
# every later fresh loop hit "Event loop is closed" / "budget ledger
# unavailable" and returned indeterminate in ~3ms — 111/141 verdicts lost to
# plumbing, not judgment. Prod passes the request loop (same pattern as
# _make_rerank_fn in app/api/first_person.py); processes without a request
# loop (harness, validation script, CLI) lazily get one persistent daemon
# loop here — created once, never closed, reused for every call.
_GATE_LOOP: Optional[Any] = None
_GATE_LOOP_THREAD: Optional[Any] = None
_GATE_LOOP_LOCK = threading.Lock()


def _persistent_gate_loop() -> Any:
    """Lazily start (or return) this process's persistent gate event loop.

    Daemon thread running one asyncio loop for the process lifetime; gate
    coroutines are scheduled onto it with run_coroutine_threadsafe, so the
    shared Redis clients it touches stay bound to the SAME loop forever."""
    global _GATE_LOOP, _GATE_LOOP_THREAD
    import asyncio

    with _GATE_LOOP_LOCK:
        if _GATE_LOOP is None or _GATE_LOOP.is_closed():
            loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=_run, daemon=True, name="answerability-gate-loop")
            thread.start()
            _GATE_LOOP = loop
            _GATE_LOOP_THREAD = thread
        return _GATE_LOOP


_REQUEST_LOOP: Optional[Any] = None


def remember_request_loop(loop: Optional[Any]) -> None:
    """Remember the serving event loop so every sync first-person LLM call (gate,
    rerank, quote weaver) schedules onto it instead of a throwaway loop."""
    global _REQUEST_LOOP
    _REQUEST_LOOP = loop


def run_llm_coroutine(
    coro_factory: Any, timeout_s: float, request_loop: Optional[Any] = None
) -> Any:
    """Run an async LLM call from sync (worker-thread) code on ONE stable loop.

    Never asyncio.run(): a per-call loop leaves the provider's shared clients
    (RPM-limiter Redis, budget ledger, pooled HTTP) bound to a loop that is then
    closed, and every later call fails with "Event loop is closed" (live
    2026-10-11: 16/27 on-topic questions abstained on that). Raises on timeout/error.
    """
    import asyncio
    import concurrent.futures

    target = request_loop if request_loop is not None else _REQUEST_LOOP
    if target is None or target.is_closed():
        target = _persistent_gate_loop()
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is target:
        # Blocking on our own loop would deadlock; use the persistent loop.
        target = _persistent_gate_loop()
    fut = asyncio.run_coroutine_threadsafe(coro_factory(), target)
    try:
        return fut.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        fut.cancel()
        raise


def _answerability_check(
    query: str,
    llm_service: Any,
    request_loop: Optional[Any] = None,
    token_sink: Optional[list[int]] = None,
) -> Optional[bool]:
    """Phase 2 gate: can the recorded teachings answer THIS question?

    Classifies the question only (never answers it) through the same bounded
    call plumbing as _llm_rerank_clips: ``_ANSWERABILITY_TIMEOUT_S`` budget,
    strict parse (strip -> casefold -> exact token; "YES, because" is NOT a
    verdict).

    True = YES (in domain), False = NO (out of domain), None = indeterminate
    (no llm_service, timeout, provider error or degraded/canned output,
    unparseable). Callers must treat None exactly like False: fail toward the
    honest abstention — an abstention is recoverable, a served out-of-domain
    answer is not.
    """
    if llm_service is None or not hasattr(llm_service, "generate"):
        return None
    try:
        import inspect

        async def _call() -> Optional[str]:
            # Determinism gate (2026-10-03): the provider default temperature
            # (0.1 in openrouter/nim generate()) shuffled borderline YES/NO
            # verdicts — control probe at 0.1 stabilized only 5/15 rows vs
            # 13-14/15 at 0.0 (scripts/ops/answerability_stability_probe.py,
            # evidence in ~/mukthiguru_attribution_data/p0/phase2/). Greedy
            # decoding keeps the 26-30% leak band from re-opening between runs.
            res = llm_service.generate(
                system_prompt=_ANSWERABILITY_SYSTEM_PROMPT,
                user_prompt=query,
                temperature=0.0,
            )
            if inspect.isawaitable(res):
                res = await res
            return str(res)

        raw = run_llm_coroutine(_call, _ANSWERABILITY_TIMEOUT_S, request_loop)
    except Exception as e:
        # N4: never log the seeker's words — type of failure only. A provider
        # refusal is logged distinctly from an outage (review P3-4); both abstain.
        if isinstance(e, ProviderRefusalError):
            logger.info("[FirstPersonPipeline] Answerability check refused by provider")
        else:
            logger.info(
                "[FirstPersonPipeline] Answerability check indeterminate (timeout/error): %s", e
            )
        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(_ANSWERABILITY_SYSTEM_PROMPT, query))
        return None

    if token_sink is not None:
        token_sink.append(_estimate_fp_tokens(_ANSWERABILITY_SYSTEM_PROMPT, query, raw))
    if raw is None:
        return None
    token = str(raw).strip().casefold()
    if token == "yes":
        return True
    if token == "no":
        return False
    logger.info(
        "[FirstPersonPipeline] Answerability check unparseable output (len=%d); treating as indeterminate",
        len(str(raw)),
    )
    return None


class FirstPersonPipelineResult:
    """Structured response container for first-person queries."""

    def __init__(
        self,
        answer_text: str,
        citations: list[dict[str, Any]],
        status: str,  # 'success', 'crisis_redirect', 'abstained', 'weak_match', 'error'
        is_direct_answer: bool,
        latency_ms: float,
        cached: bool = False,
        error: Optional[str] = None,
        answerability: Optional[
            str
        ] = None,  # Phase 2 gate verdict: 'yes' | 'no' | 'indeterminate'; None = gate did not run
        abstain_reason: Optional[
            str
        ] = None,  # RP-C6: FIRST_PERSON_ABSTAIN_REASONS member; None = pre-reason legacy
        audio_playback_clip: Optional[dict[str, Any]] = None,
        audio_playback_clips: Optional[list[dict[str, Any]]] = None,
        detected_concepts: Optional[list[str]] = None,
        atma_vichara_inquiry: Optional[str] = None,
        practice_recommendation: Optional[dict[str, Any]] = None,
    ) -> None:
        self.answer_text = answer_text
        self.citations = citations
        self.status = status
        self.is_direct_answer = is_direct_answer
        self.latency_ms = latency_ms
        self.cached = cached
        self.error = error
        self.answerability = answerability
        self.abstain_reason = abstain_reason
        self.audio_playback_clip = audio_playback_clip
        if audio_playback_clips is not None:
            self.audio_playback_clips = audio_playback_clips
        elif audio_playback_clip is not None:
            self.audio_playback_clips = [audio_playback_clip]
        else:
            self.audio_playback_clips = []
        self.detected_concepts = detected_concepts if detected_concepts is not None else []
        self.atma_vichara_inquiry = atma_vichara_inquiry
        self.practice_recommendation = practice_recommendation

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_text": self.answer_text,
            "citations": self.citations,
            "status": self.status,
            "is_direct_answer": self.is_direct_answer,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
            "error": self.error,
            "answerability": self.answerability,
            "abstain_reason": self.abstain_reason,
            "audio_playback_clip": self.audio_playback_clip,
            "audio_playback_clips": self.audio_playback_clips,
            "detected_concepts": self.detected_concepts,
            "atma_vichara_inquiry": self.atma_vichara_inquiry,
            "practice_recommendation": self.practice_recommendation,
        }


_CALIBRATION_UNSET = object()


class FirstPersonPipeline:
    """
    Executes first-person verbatim retrieval, validation, and citation serving.
    """

    def __init__(
        self,
        store: Optional[FirstPersonStore] = None,
        redis_client: Optional[Any] = None,
        serene_mind_engine: Optional[SereneMindEngine] = None,
        calibration_profile: Any = _CALIBRATION_UNSET,
        rerank_fn: Optional[Callable[[str, list[str]], list[float]]] = None,
        weaver: Optional[QuoteWeaverService] = None,
        llm_service: Optional[Any] = None,
        llm_loop: Optional[Any] = None,
    ) -> None:
        self._store = store or FirstPersonStore()
        self._redis = redis_client
        self._serene_mind = serene_mind_engine or SereneMindEngine()
        # (query, clip texts) -> one relevance score per text, higher is better.
        self._rerank_fn = rerank_fn
        # ponytail: quote weaver with optional LLM or clean deterministic fallback
        # RP-A4 P1 (2026-10-13): the serving default is v8, so the auto-enable
        # must name it — otherwise the default flip silently turns this guard
        # off (QBUG-3's explicit-flag replacement still needs QA-5/QO-6).
        self._boundary_guard_enabled = getattr(
            settings, "first_person_boundary_guard_enabled", False
        ) or (
            bool(self._store)
            and getattr(self._store, "collection", "")
            in ("first_person_v6", "first_person_v7", "first_person_v8")
        )
        # ponytail: content quality gate auto-enabled for v7+ (same collection gating as boundary_guard)
        self._content_quality_gate_enabled = getattr(
            settings, "first_person_content_quality_gate_enabled", True
        ) or (
            bool(self._store)
            and getattr(self._store, "collection", "")
            in ("first_person_v6", "first_person_v7", "first_person_v8")
        )
        self._weaver = weaver or QuoteWeaverService(llm_service=llm_service)
        self._llm_service = llm_service
        self._servable_cache: dict[str, tuple[bool, float]] = {}
        # Loop the answerability gate schedules onto (captured on the request
        # loop by app/api/first_person.py, same pattern as the rerank fn);
        # None = scripts/harness use the persistent gate loop.
        self._llm_loop = llm_loop
        if llm_loop is not None:
            remember_request_loop(llm_loop)
        if calibration_profile is not _CALIBRATION_UNSET:
            self._profile = calibration_profile
        else:
            profile_path = getattr(settings, "first_person_calibration_path", "")
            if not profile_path:
                suffix = self._store.collection.replace("first_person_", "")
                candidates = [
                    Path("/config") / f"first_person_calibration_{self._store.collection}.json",
                    Path("/config") / f"first_person_calibration_{suffix}.json",
                    Path(__file__).resolve().parent.parent.parent
                    / "config"
                    / f"first_person_calibration_{self._store.collection}.json",
                    Path(__file__).resolve().parent.parent.parent
                    / "config"
                    / f"first_person_calibration_{suffix}.json",
                ]
                for cand in candidates:
                    if cand.is_file():
                        profile_path = str(cand)
                        break
            self._profile = load_calibration_profile(
                profile_path,
                self._store.collection,
            )

    @staticmethod
    def _allowlist_state() -> str:
        """The quality-allowlist component of the serving-policy fingerprint.

        Computed ONCE per request (see execute()) and passed into the cache
        key for both lookup and write: calling os.path.getmtime per key
        computation wastes two syscalls per request and could disagree
        between lookup and write if the file changes mid-request.
        """
        allow_path = str(getattr(settings, "first_person_quality_allowlist_path", "") or "").strip()
        if not allow_path:
            return "off"
        try:
            return f"{allow_path}@{os.path.getmtime(allow_path)}"
        except OSError:
            # Fail-closed elsewhere (empty set serves nothing); here the key
            # just needs to differ from the readable states, deterministically.
            return f"{allow_path}@unreadable"

    @staticmethod
    def _blocklist_state() -> str:
        """The quality-blocklist component of the serving-policy fingerprint.

        Same once-per-request contract as _allowlist_state() (see execute()):
        a quarantine add/remove/rewrite re-keys the exact cache instead of
        replaying an answer computed under different policy.
        """
        block_path = str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip()
        if not block_path:
            return "off"
        try:
            return f"{block_path}@{os.path.getmtime(block_path)}"
        except OSError:
            # Fail-closed elsewhere (serves nothing); here the key just needs
            # to differ from the readable states, deterministically.
            return f"{block_path}@unreadable"

    def _serving_policy_fingerprint(
        self, allow_state: str | None = None, block_state: str | None = None
    ) -> str:
        """One bounded digest over every serving-policy input that changes what may be served (RP-A5).

        A single sha256 over the sorted ``name=value`` tuple — not per-flag key
        edits — so adding a policy knob in future means one dict entry here, and
        any serving change re-keys the exact cache instead of replaying a stale
        answer computed under different policy. Mirrors the chat tier's bounded
        config fingerprint (graph_stage._assistant_config_fingerprint): raw text
        never enters a key, only the first 16 hex chars of the digest.
        ``allow_state`` is the precomputed _allowlist_state() for the request;
        ``block_state`` is the precomputed _blocklist_state() for the request;
        None recomputes (tests and one-off callers).
        """
        if allow_state is None:
            allow_state = self._allowlist_state()
        if block_state is None:
            block_state = self._blocklist_state()
        pairs = sorted(
            {
                "answerability": str(bool(settings.first_person_answerability_check_enabled)),
                "boundary_guard": str(bool(self._boundary_guard_enabled)),
                "content_gate": str(bool(self._content_quality_gate_enabled)),
                "editorial_rewrite": str(bool(settings.first_person_editorial_rewrite_enabled)),
                "llm_rerank": str(bool(settings.first_person_llm_rerank_enabled)),
                "mode": str(settings.first_person_mode or ""),
                "quality_allowlist": allow_state,
                "quality_blocklist": block_state,
                "relevance_gate": str(bool(settings.first_person_relevance_gate_enabled)),
                "relevance_min": str(int(settings.first_person_relevance_min_score)),
                "relevance_model": str(settings.first_person_relevance_model or ""),
                # Both scorer prompts and the JSON schema: which one runs
                # depends on the scorer model, and an edit to either must re-key.
                "relevance_prompt": (
                    f"{_RELEVANCE_PROMPT_VERSION}:"
                    + hashlib.sha256(
                        (
                            _RELEVANCE_SYSTEM_PROMPT
                            + _RELEVANCE_JSON_SYSTEM_PROMPT
                            + json.dumps(_RELEVANCE_JSON_SCHEMA, sort_keys=True)
                            + ",".join(sorted(_SCORER_JSON_SCHEMA_MODELS))
                        ).encode()
                    ).hexdigest()[:12]
                ),
                "scaffold_prompt": str(_SCAFFOLD_PROMPT_VERSION),
                "serve_weak_match": str(bool(settings.first_person_serve_weak_match)),
                "standalone_gate": str(bool(settings.first_person_standalone_gate_enabled)),
            }.items()
        )
        return hashlib.sha256("|".join(f"{k}={v}" for k, v in pairs).encode("utf-8")).hexdigest()[
            :16
        ]

    def _get_exact_cache_key(
        self,
        query: str,
        teacher_id: Optional[str] = None,
        language: str = "en",
        allow_state: str | None = None,
        block_state: str | None = None,
    ) -> str:
        # ponytail: language-sensitive exact cache key (D2 audit fix)
        norm = unicodedata.normalize("NFKC", query).strip().lower()
        t_id = (teacher_id or "both").strip().lower()
        lang = (language or "en").strip().lower().split("-")[0]
        fitted_at = (self._profile or {}).get("fitted_at") or (self._profile or {}).get(
            "calibrated_at", "none"
        )
        # Reranking changes which clip is served, so it is part of the key.
        rerank = "rerank" if self._rerank_fn else "fusion"
        # Phase 2: the answerability gate changes what may be served, so when it
        # is on it is part of the key too. Flag off appends nothing -> the
        # pre-gate key stays byte-identical (kill-switch = pre-change cache behavior),
        # and flipping the flag on can never serve a pre-gate cached direct answer.
        ans = ":ans" if settings.first_person_answerability_check_enabled else ""
        # RP-A5: every other serving-policy input rides one fingerprint (above),
        # so a min-score / scorer-model / gate-flag / allowlist / blocklist /
        # prompt change can never replay an answer computed under different
        # policy. This intentionally supersedes the Phase 2 byte-parity above
        # for those inputs (a stale pre-policy entry simply misses; 24 h TTL
        # bounds it).
        policy = self._serving_policy_fingerprint(allow_state, block_state)
        h = hashlib.sha256(
            f"{norm}:{t_id}:{lang}:{self._store.collection}:{fitted_at}:{rerank}{ans}:{policy}".encode()
        ).hexdigest()
        return f"cache:first_person_exact:{lang}:{h}"

    _exact_cache_key = _get_exact_cache_key

    def _points_servable_cached(self, point_ids: list[str]) -> bool:
        """Cache points_servable results for 300s to avoid synchronous Qdrant blasts on exact cache hits."""
        now = time.time()
        # Clean expired entries if cache grows
        if len(self._servable_cache) > 2000:
            self._servable_cache = {k: v for k, v in self._servable_cache.items() if v[1] > now}

        uncached: list[str] = []
        for pid in point_ids:
            cached = self._servable_cache.get(pid)
            if cached is None or cached[1] <= now:
                uncached.append(pid)
            elif not cached[0]:
                return False

        if uncached:
            is_servable = self._store.points_servable(uncached)
            expiry = now + 300.0  # 5-minute TTL
            for pid in uncached:
                self._servable_cache[pid] = (is_servable, expiry)
            if not is_servable:
                return False

        return True

    def check_exact_cache(
        self,
        query: str,
        teacher_id: Optional[str] = None,
        language: str = "en",
        allow_state: str | None = None,
        block_state: str | None = None,
    ) -> Optional[dict[str, Any]]:
        """Query Redis for an exact cached answer. Bypasses semantic cache."""
        if not self._redis:
            return None
        key = self._get_exact_cache_key(
            query, teacher_id, language=language, allow_state=allow_state, block_state=block_state
        )
        try:
            val = self._redis.get(key)
            if val:
                data = json.loads(val.decode("utf-8") if isinstance(val, bytes) else val)
                if not isinstance(data, dict) or not _CACHE_ENTRY_REQUIRED_KEYS.issubset(
                    data.keys()
                ):
                    logger.warning(
                        "[FirstPersonPipeline] Cached entry at %s missing required keys; treating as miss.",
                        key,
                    )
                    try:
                        self._redis.delete(key)
                    except Exception:
                        pass  # best-effort cleanup; a stuck malformed key just keeps missing
                    return None
                if not isinstance(data.get("citations"), list):
                    logger.warning(
                        "[FirstPersonPipeline] Cached citations are not a list; treating as miss."
                    )
                    return None
                # Re-run the integrity gate on cached citations before serving.
                for cit in data.get("citations", []):
                    if (
                        not isinstance(cit, dict)
                        or cit.get("provenance_kind") == "curated_okf"
                        or not cit.get("point_id")
                        or not cit.get("video_id")
                        or cit.get("is_verbatim") is False
                    ):
                        logger.warning(
                            "[FirstPersonPipeline] Cached non-video/OKF citation rejected."
                        )
                        return None
                    if not _passes_integrity_gate(
                        {
                            "point_id": cit.get("point_id"),
                            "video_id": cit.get("video_id"),
                            "verbatim_text": cit.get("verbatim_text", ""),
                            "transcript_hash": cit.get("transcript_hash", ""),
                            "speaker": cit.get("speaker"),
                        },
                        boundary_guard_enabled=self._boundary_guard_enabled,
                    ):
                        logger.warning(
                            "[FirstPersonPipeline] Cached citation failed integrity re-check; skipping cache."
                        )
                        return None
                # The index can change under a 24 h entry (clip deleted, rights
                # revoked): serve only if every cited point is still servable.
                point_ids = [
                    cit.get("point_id") for cit in data.get("citations", []) if cit.get("point_id")
                ]
                if data.get("citations") and (
                    not point_ids or not self._points_servable_cached(point_ids)
                ):
                    logger.warning(
                        "[FirstPersonPipeline] Cached clip no longer servable; skipping cache."
                    )
                    return None
                for cit in data.get("citations", []):
                    cit.update(
                        transcript_label(cit.get("verbatim_text", ""), cit.get("caption_status"))
                    )
                # RP-C6: the withhold reason rides the cached entry so a hit
                # counts the same reason the fresh path did. Pre-reason entries
                # (None) predate the label and count as "none"; a present but
                # unknown value is corrupt — miss, never a silent remap.
                stored_reason = data.get("abstain_reason") or "none"
                if stored_reason not in FIRST_PERSON_ABSTAIN_REASONS:
                    logger.warning(
                        "[FirstPersonPipeline] Cached abstain_reason %r unknown; treating as miss.",
                        data.get("abstain_reason"),
                    )
                    return None
                data["abstain_reason"] = stored_reason
                logger.info(f"[FirstPersonPipeline] Exact cache HIT for key {key}")
                return data
        except Exception as e:
            logger.warning(f"[FirstPersonPipeline] Redis exact cache lookup failed: {e}")
        return None

    def set_exact_cache(
        self,
        query: str,
        data: dict[str, Any],
        teacher_id: Optional[str] = None,
        language: str = "en",
        allow_state: str | None = None,
        block_state: str | None = None,
    ) -> None:
        """Store validated answer into Redis exact cache."""
        if not self._redis:
            return
        key = self._get_exact_cache_key(
            query, teacher_id, language=language, allow_state=allow_state, block_state=block_state
        )
        try:
            self._redis.set(key, json.dumps(data), ex=EXACT_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[FirstPersonPipeline] Redis exact cache set failed: {e}")

    def _log_and_count(
        self,
        status: str,
        latency_ms: float,
        confidence: float,
        n_quarantined: int,
        n_citations: int,
        reason: str,
        llm_tokens: int,
    ) -> None:
        # RP-C6: reason is required (no default) and must be a pinned vocabulary
        # member — an unknown value raises loudly instead of silently remapping.
        if reason not in FIRST_PERSON_ABSTAIN_REASONS:
            raise ValueError(f"unknown first-person abstain reason: {reason!r}")
        FIRST_PERSON_REQUESTS_TOTAL.labels(status=status, reason=reason).inc()
        FIRST_PERSON_LATENCY_SECONDS.observe(latency_ms / 1000.0)
        # RP-C10: estimated tokens for this request, split by final outcome.
        outcome = "answered" if status in ("success", "weak_match") else "abstained"
        FIRST_PERSON_LLM_TOKENS_TOTAL.labels(outcome=outcome).inc(max(0, int(llm_tokens)))
        logger.info(
            "[FirstPersonPipeline] status=%s reason=%s latency_ms=%.1f confidence=%.4f n_quarantined=%d n_citations=%d llm_tokens=%d",
            status,
            reason,
            latency_ms,
            confidence,
            n_quarantined,
            n_citations,
            max(0, int(llm_tokens)),
        )

    def execute(
        self,
        query: str,
        query_dense_vector: list[float],
        query_sparse_vector: Optional[dict[str, Any]] = None,
        teacher_id: Optional[str] = None,
        max_clips: int = 3,
        retrieval_query: Optional[str] = None,
        language: str = "en",
        cache_bypass: bool = False,
    ) -> FirstPersonPipelineResult:
        """
        Execute the end-to-end first-person verbatim serving pipeline.

        ``query`` is the seeker's own words (cache key, safety checks).
        ``retrieval_query`` is its English translation when the question was not
        in English; the dense/sparse vectors must already be computed from it.
        ``language`` is the seeker's requested language code (cache key scoping).
        ``cache_bypass`` skips the exact cache read AND write (evaluation cold
        path, incognito). The safety checks above the cache run either way.
        """
        start_time = time.monotonic()
        # RP-C10: per-request accumulator for estimated LLM tokens spent by the
        # gate calls below; flushed with the final outcome in _log_and_count.
        fp_llm_tokens: list[int] = []
        # Safety checks run on every form of the question: a translation can only
        # make them stricter (English-only regexes see an Indic question), never skip one.
        safety_texts = [query] + (
            [retrieval_query] if retrieval_query and retrieval_query != query else []
        )
        retrieval_query = retrieval_query or query

        if not teacher_id or teacher_id.strip().lower() in ("both", "all", ""):
            teacher_id = (
                requested_teacher(query) or requested_teacher(retrieval_query or "") or teacher_id
            )

        # Step 1: Crisis Pre-Check (Fails closed to safety redirect)
        # Same pre-emption rule as the chat DistressStage: assess_distress() >= SEVERE.
        # has_crisis_keywords is only a broad pre-screen ("does NOT mean the message is
        # actually crisis-level"); OR-ing it in redirected benign questions.
        assessments = [self._serene_mind.assess_distress(t) for t in safety_texts]
        distress_assessment = max(
            (a for a in assessments if a), key=lambda a: a.level.value, default=None
        )
        is_crisis = bool(
            distress_assessment and distress_assessment.level.value >= DistressLevel.SEVERE.value
        )
        if is_crisis:
            # N4: never log the seeker's words, only the level.
            logger.warning(
                "[FirstPersonPipeline] Crisis pre-emption (distress level %s).",
                distress_assessment.level.name,
            )
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count("crisis_redirect", latency, 0.0, 0, 0, "none", 0)
            return FirstPersonPipelineResult(
                answer_text=format_helplines_block(),
                citations=[],
                status="crisis_redirect",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="none",
            )

        # Step 1b: Topic rail (same regex list as chat, no LLM). A teacher's clip
        # served in reply to a political or abusive question reads as endorsement.
        blocked = next((b for b in map(match_blocked_topic, safety_texts) if b is not None), None)
        if blocked is not None:
            topic, response = blocked
            status = "crisis_redirect" if topic in SAFETY_TOPICS else "abstained"
            logger.info("[FirstPersonPipeline] Topic rail blocked input: topic=%s", topic)
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count(status, latency, 0.0, 0, 0, "topic_blocked", 0)
            return FirstPersonPipelineResult(
                answer_text=response,
                citations=[],
                status=status,
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="topic_blocked",
            )

        # Step 2: Check Exact-Match Cache. The benchmark cache switch every
        # other cache honours applies here too (2026-10-05). The allowlist and
        # blocklist states are computed once for the whole request so lookup
        # and write below key identically even if a file changes mid-request.
        cache_bypass = cache_bypass or bool(
            getattr(settings, "latency_benchmark_cache_disabled", False)
        )
        request_allow_state = self._allowlist_state()
        request_block_state = self._blocklist_state()
        cached_data = (
            None
            if cache_bypass
            else self.check_exact_cache(
                query,
                teacher_id,
                language=language,
                allow_state=request_allow_state,
                block_state=request_block_state,
            )
        )
        if cached_data:
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count(
                cached_data["status"],
                latency,
                0.0,
                0,
                len(cached_data.get("citations", [])),
                cached_data["abstain_reason"],
                0,  # cache hit spends no LLM tokens on this request
            )
            return FirstPersonPipelineResult(
                answer_text=cached_data["answer_text"],
                citations=cached_data["citations"],
                status=cached_data["status"],
                is_direct_answer=cached_data["is_direct_answer"],
                latency_ms=latency,
                cached=True,
                error=cached_data.get("error"),
                answerability=cached_data.get("answerability"),
                abstain_reason=cached_data.get("abstain_reason"),
                audio_playback_clip=cached_data.get("audio_playback_clip"),
                audio_playback_clips=cached_data.get("audio_playback_clips"),
                detected_concepts=cached_data.get("detected_concepts") or [],
                atma_vichara_inquiry=cached_data.get("atma_vichara_inquiry"),
                practice_recommendation=cached_data.get("practice_recommendation"),
            )

        # RC-D-2: start the question-only answerability gate in parallel with
        # retrieval. Crisis (Step 1), the topic rail, and the exact cache are
        # already past, so a redirect / blocked topic / cache hit never spends
        # this LLM call. The worker owns the single _answerability_check call;
        # the join sits before any rerank/scorer work so a firm NO skips both.
        _ans_box: dict[str, Any] = {}
        _ans_thread: Optional[threading.Thread] = None
        if bool(getattr(settings, "first_person_answerability_check_enabled", False)):

            def _run_answerability() -> None:
                try:
                    _ans_box["verdict"] = _answerability_check(
                        query,
                        self._llm_service,
                        request_loop=self._llm_loop,
                        token_sink=fp_llm_tokens,
                    )
                except Exception as e:  # noqa: BLE001 - belt-and-braces; the check itself swallows
                    logger.info("[FirstPersonPipeline] Answerability background error: %s", e)
                    _ans_box["verdict"] = None

            _ans_thread = threading.Thread(
                target=_run_answerability, daemon=True, name="fp-answerability"
            )
            _ans_thread.start()

        # Step 3: Retrieval from FirstPersonStore
        has_practice_intent = any(
            w in query.lower()
            for w in (
                "practice",
                "meditation",
                "how to",
                "technique",
                "exercise",
                "sadhana",
                "kriya",
            )
        )
        effective_max_clips = max(max_clips, 4) if has_practice_intent else max_clips

        def _search() -> list[dict[str, Any]]:
            return self._store.search_hybrid(
                query_dense_vector=query_dense_vector,
                query_sparse_vector=query_sparse_vector,
                teacher_id=teacher_id,
                limit=max(80, effective_max_clips * 16),
                # spare videos: a clip the integrity gate quarantines is backfilled
                dedup_limit=max(40, effective_max_clips * 8),
                allow_same_video_distinct_spans=has_practice_intent,
            )

        try:
            try:
                raw_clips = _search()
            except Exception as first_error:  # noqa: BLE001
                # One immediate retry for a dropped idle keep-alive connection (live 2026-10-11:
                # "Server disconnected without sending a response" -> a seeker saw a 503 for a
                # question that succeeded on the very next attempt). Not a retry loop.
                if not _is_transient_connection_error(first_error):
                    raise
                logger.warning(
                    "[FirstPersonPipeline] Transient retrieval error, retrying once: %s",
                    first_error,
                )
                raw_clips = _search()
        except Exception as e:
            logger.error(f"[FirstPersonPipeline] Hybrid retrieval failed: {e}")
            if _ans_thread is not None:
                # The gate overlapped retrieval; join it (bounded) so the
                # request never leaves a worker behind and the error metric
                # below still carries whatever tokens it spent.
                _ans_thread.join(_ANSWERABILITY_TIMEOUT_S)
                if _ans_thread.is_alive():
                    logger.info(
                        "[FirstPersonPipeline] Answerability worker still running "
                        "after retrieval error; counting tokens spent so far"
                    )
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count("error", latency, 0.0, 0, 0, "none", sum(fp_llm_tokens))
            return FirstPersonPipelineResult(
                answer_text="An error occurred while retrieving first-person teachings.",
                citations=[],
                status="error",
                is_direct_answer=False,
                latency_ms=latency,
                error=str(e),
                abstain_reason="none",
            )

        # Step 4: Serve-time Integrity Gate
        verified_clips: list[dict[str, Any]] = []
        n_quarantined = 0
        for clip in raw_clips:
            if _passes_integrity_gate(clip, boundary_guard_enabled=self._boundary_guard_enabled):
                # ponytail: content quality gate — rejects thin clips, live-event
                # instructions, and discourse acknowledgments after integrity passes
                if _passes_content_quality_gate(
                    clip, gate_enabled=self._content_quality_gate_enabled
                ):
                    verified_clips.append(clip)
                else:
                    n_quarantined += 1
                    FIRST_PERSON_QUARANTINED_TOTAL.inc()
            else:
                n_quarantined += 1
                FIRST_PERSON_QUARANTINED_TOTAL.inc()
                logger.warning(
                    f"[FirstPersonPipeline] Clip {clip.get('point_id')} for video {clip.get('video_id')} "
                    f"failed the serve-time integrity gate. Quarantined from serving."
                )

        # A named guru is a hard scope: even if the store filter were bypassed, a clip
        # by anyone else is never substituted (L-FP-SPEAKER-REQUEST-1).
        if teacher_id and teacher_id.strip().lower() not in ("both", "all", ""):
            _want = teacher_id.strip().lower()
            verified_clips = [
                c for c in verified_clips if str(c.get("teacher_id") or "").lower() == _want
            ]

        # Quality allowlist (opt-in): serve only clips a reviewer/grader approved. Applied before reranking so
        # an unapproved clip can never win a slot; an empty/unreadable list abstains (fail closed).
        _allow = _quality_allowlist()
        if _allow is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) in _allow]

        # Quality blocklist (opt-in quarantine, T-B12): a quarantined clip is
        # never served, even if allowlisted — quarantine wins. Applied AFTER
        # the allowlist intersect so a bad clip can never win a slot back. A
        # configured-but-unreadable file serves nothing (fail closed).
        _blocked = _quality_blocklist()
        if _blocked is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) not in _blocked]
        elif str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip():
            verified_clips = []

        # Served text is the stored verbatim_text, byte for byte (invariants 2
        # and 13). An earlier serve-time pass rewrote verbatim_text with the ASR
        # cleaner and recomputed transcript_hash AFTER the integrity gate, and
        # stamped hand-written titles, "discourse_context" and speaker labels onto
        # clips. That served words the store does not hold and metadata nobody
        # stored. Cleaning belongs at ingest (build_first_person_index,
        # FirstPersonStore.upsert_clips), where the hash is written with it.
        # Pinned by tests/test_fp_serves_stored_text_2026_10_06.py.

        # RC-D-2 join: the background gate overlapped retrieval above. Firm NO
        # skips rerank/scorer; YES runs the full path. (Seventh review set:
        # indeterminate — timed-out/failed worker — also skips, since it
        # abstains either way; the Step 6 gate below agrees on both labels.)
        # Zero verified clips still falls through to the Step 5 reason below,
        # preserving the no_verified_clips > answerability_withheld precedence.
        early_verdict: Optional[bool] = None
        if _ans_thread is not None:
            # Bounded join: a hung gate worker must never stall serving. A
            # timeout leaves early_verdict None = indeterminate, the same
            # fail-toward-abstention path as a gate timeout below.
            _ans_thread.join(_ANSWERABILITY_TIMEOUT_S)
            if _ans_thread.is_alive():
                logger.info(
                    "[FirstPersonPipeline] Answerability join timed out; "
                    "continuing as indeterminate"
                )
            else:
                early_verdict = _ans_box.get("verdict")
        if _ans_thread is not None and early_verdict is not True and verified_clips:
            # Anything other than a firm YES skips rerank/scorer: a NO verdict
            # and an indeterminate (timed-out/failed gate worker) both end in
            # abstention, so spending two more LLM calls cannot change the
            # outcome. Label honestly: "no" for a firm NO, "indeterminate"
            # otherwise (the Step 6 gate below agrees on both).
            _is_firm_no = early_verdict is False
            try:
                early_confidence = (
                    _cosine_similarity(query_dense_vector, verified_clips[0].get("passage_dense"))
                    if query_dense_vector
                    else 0.0
                )
            except Exception:  # noqa: BLE001 - logging confidence must not break serving
                early_confidence = 0.0
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count(
                "abstained",
                latency,
                early_confidence,
                n_quarantined,
                0,
                "answerability_withheld",
                sum(fp_llm_tokens),
            )
            logger.info(
                "[FirstPersonPipeline] Answerability %s before scoring; "
                "skipped rerank/scorer (saved up to 2 LLM calls)",
                "NO" if _is_firm_no else "indeterminate",
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                answerability="no" if _is_firm_no else "indeterminate",
                abstain_reason="answerability_withheld",
            )

        # Step 4b: optional cross-encoder reorder of the verified candidates. Reorders
        # only; confidence below stays dense cosine (the calibration contract).
        if self._rerank_fn and len(verified_clips) > 1:
            try:
                scores = self._rerank_fn(
                    retrieval_query, [c["verbatim_text"] for c in verified_clips]
                )
                order = sorted(range(len(verified_clips)), key=lambda i: scores[i], reverse=True)
                verified_clips = [verified_clips[i] for i in order]
            except Exception as e:
                # ponytail: fail open to fusion order — the flag is an unproven ranking
                # tweak, and a reranker outage must not take the whole route down.
                logger.error(f"[FirstPersonPipeline] Rerank failed; keeping fusion order: {e}")

        # Step 4c: LLM reranker (selection-only, zero text generation, 2.5s budget, fallback to cosine)
        # Reranks across top candidates (up to 8) before final truncation or balancing,
        # ensuring the most relevant teaching clip is selected into top position.
        if (
            getattr(settings, "first_person_llm_rerank_enabled", True)
            and self._llm_service is not None
            and len(verified_clips) > 1
        ):
            verified_clips = (
                _llm_rerank_clips(
                    retrieval_query,
                    verified_clips[:8],
                    self._llm_service,
                    token_sink=fp_llm_tokens,
                )
                + verified_clips[8:]
            )

        # Step 4d: Teacher diversity balancing when teacher_id is 'both' or None
        is_both_teachers = not teacher_id or teacher_id.lower() in ("both", "all", "")
        if is_both_teachers and len(verified_clips) > 1:
            top_clip = verified_clips[0]
            top_guru = str(top_clip.get("teacher_id") or top_clip.get("speaker") or "").lower()

            # Partition remaining candidates: any other guru vs the top clip's guru
            other_clips = [
                c
                for c in verified_clips[1:]
                if str(c.get("teacher_id") or c.get("speaker") or "").lower() != top_guru
            ]
            same_clips = [c for c in verified_clips[1:] if c not in other_clips]

            # Invariant: top-ranked match ALWAYS remains at index 0
            balanced: list[dict[str, Any]] = [top_clip]
            # ponytail: δ — plan-approved initial value (Task 1 Step B, 2026-09-29);
            # validate/fit by harness ablation, one δ only (see trace_1A.md for the
            # defect this gates: an other-teacher clip at cosine 0.5791 displaced a
            # same-teacher clip at 0.6837).
            max_cosine_gap = 0.05
            o_idx, s_idx = 0, 0
            while len(balanced) < effective_max_clips and (
                o_idx < len(other_clips) or s_idx < len(same_clips)
            ):
                # Alternate secondary slots: slot 1 gets other teacher if available, slot 2 gets same teacher, etc.
                want_other = o_idx < len(other_clips) and (
                    len(balanced) % 2 == 1 or s_idx >= len(same_clips)
                )
                if want_other and s_idx < len(same_clips):
                    # ponytail: promoting the other teacher displaces a same-teacher clip —
                    # allowed only on calibrated quality parity: candidate dense cosine must
                    # clear the fitted profile threshold (same value is_direct uses) AND the
                    # cosine gap to the displaced clip must stay within δ. No profile → no fit
                    # → never promote over a higher-cosine same-teacher clip.
                    if self._profile is not None:
                        candidate_cos = _cosine_similarity(
                            query_dense_vector, other_clips[o_idx].get("passage_dense")
                        )
                        displaced_cos = _cosine_similarity(
                            query_dense_vector, same_clips[s_idx].get("passage_dense")
                        )
                        promote_other = (
                            candidate_cos >= self._profile["threshold"]
                            and displaced_cos - candidate_cos <= max_cosine_gap
                        )
                    else:
                        promote_other = False
                    if promote_other:
                        balanced.append(other_clips[o_idx])
                        o_idx += 1
                    else:
                        balanced.append(same_clips[s_idx])
                        s_idx += 1
                elif want_other:
                    # nothing displaced (same-teacher partition exhausted) → plain append
                    balanced.append(other_clips[o_idx])
                    o_idx += 1
                else:
                    balanced.append(same_clips[s_idx])
                    s_idx += 1
            verified_clips = balanced
        else:
            verified_clips = verified_clips[:effective_max_clips]

        # Step 5: Abstention check if zero verified clips
        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            logger.info("[FirstPersonPipeline] Zero verified clips found. Honest abstention.")
            self._log_and_count(
                "abstained", latency, 0.0, n_quarantined, 0, "no_verified_clips", sum(fp_llm_tokens)
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="no_verified_clips",
            )

        # Step 6: Calibrated Confidence Decision
        # One cosine per clip, reused by the confidence decision, the per-clip filter and the citation.
        clip_scores = [
            _cosine_similarity(query_dense_vector, c.get("passage_dense")) for c in verified_clips
        ]

        # No keyword boost: the profile threshold is fitted on raw dense cosine
        # (invariant 3). A topic word in the QUESTION says nothing about whether
        # the CLIP answers it, and +0.1 on the score would let a fitted profile
        # promote a topic match to "direct answer" (removed 2026-10-05).

        # Relevance gate (2026-10-11): the answerability gate only reads the QUESTION, so an
        # in-domain question was always served its top clip whatever that clip said. Score
        # (question, clip) for the top candidates and serve the best >= min score, else abstain.
        if getattr(settings, "first_person_relevance_gate_enabled", True):
            candidates = verified_clips[:3]
            pick = _relevance_select(
                retrieval_query or query,
                candidates,
                self._llm_service,
                self._llm_loop,
                token_sink=fp_llm_tokens,
            )
            if pick is None or pick == _RELEVANCE_INDETERMINATE:
                latency = (time.monotonic() - start_time) * 1000.0
                abstain_answerability = (
                    "relevance_indeterminate" if pick is not None else "relevance_below_min"
                )
                self._log_and_count(
                    "abstained",
                    latency,
                    clip_scores[0],
                    n_quarantined,
                    0,
                    abstain_answerability,
                    sum(fp_llm_tokens),
                )
                return FirstPersonPipelineResult(
                    answer_text="No verified first-person discourse found for this question.",
                    citations=[],
                    status="abstained",
                    is_direct_answer=False,
                    latency_ms=latency,
                    answerability=abstain_answerability,
                    abstain_reason=abstain_answerability,
                )
            if pick != 0:
                verified_clips = [verified_clips[pick]] + [
                    c for i, c in enumerate(verified_clips) if i != pick
                ]
                clip_scores = [clip_scores[pick]] + [
                    s for i, s in enumerate(clip_scores) if i != pick
                ]

        top_clip = verified_clips[0]
        confidence = clip_scores[0]
        is_direct = self._profile is not None and confidence >= self._profile["threshold"]

        # Phase 2 (2026-09-30): answerability gate. Audit B served 3/3
        # out-of-corpus questions as direct answers (top-1 cosine 0.48-0.65 vs the
        # 0.45 threshold), so cosine alone cannot enforce the abstention contract.
        # An LLM classifies the QUESTION only (YES/NO, never answers it) before
        # is_direct=True is committed. Anything but YES — NO, timeout, provider
        # error, degraded/canned output, unparseable output, no llm_service —
        # fails toward the existing honest abstention shape (zero citations).
        # Gated by first_person_answerability_check_enabled (kill-switch: flag off
        # = exact pre-change behavior, no LLM call, byte-compatible cache keys).
        answerability: Optional[str] = None
        # 2026-10-11: the gate must cover EVERY clip about to be served, not only
        # is_direct ones. With no calibration profile is_direct is always False, so
        # the weak_match ("Related, not a direct answer") path skipped the gate and
        # served 'capital of France' a leadership quote and 'bake a cake' an
        # 'addicted to chocolate' quote (live, 2026-10-11).
        if settings.first_person_answerability_check_enabled:
            # RC-D-2: the verdict was already joined before rerank above; reuse
            # it so the gate costs exactly one LLM call. Fall back to a direct
            # call only if the flag flipped on mid-request (no thread started).
            if _ans_thread is not None:
                verdict = early_verdict
            else:
                verdict = _answerability_check(
                    query,
                    self._llm_service,
                    request_loop=self._llm_loop,
                    token_sink=fp_llm_tokens,
                )
            answerability = {True: "yes", False: "no"}.get(verdict, "indeterminate")
            logger.info(
                "[FirstPersonPipeline] Answerability verdict=%s direct_served=%s",
                answerability,
                verdict is True,
            )
            if verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                self._log_and_count(
                    "abstained",
                    latency,
                    confidence,
                    n_quarantined,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                return FirstPersonPipelineResult(
                    answer_text="No verified first-person discourse found for this question.",
                    citations=[],
                    status="abstained",
                    is_direct_answer=False,
                    latency_ms=latency,
                    answerability=answerability,
                    abstain_reason="answerability_withheld",
                )

        # ponytail: retrieve matching OKF entries using in-memory vector matching (<1ms)
        okf_entries: list[dict[str, Any]] = []
        if query_dense_vector and len(query_dense_vector) == 1024:
            try:
                okf_entries = match_okf_entries(
                    query_dense_vector=query_dense_vector,
                    top_k=2,
                    teacher=teacher_id,
                    preferred_type="practice" if has_practice_intent else None,
                )
            except Exception as e:
                logger.warning(
                    "[FirstPersonPipeline] OKF matching failed: %s; proceeding with clips only", e
                )

        citations: list[dict[str, Any]] = []

        def _build_citation(
            clip: dict[str, Any], clip_confidence: float, provenance_kind: str
        ) -> dict[str, Any]:
            if provenance_kind == "curated_okf":
                raise ValueError("OKF entries cannot become first-person citations")
            sec = clip["start_ms"] // 1000
            video_id = clip["video_id"]
            playback_start = max(0.0, clip["start_ms"] / 1000.0 - CITATION_PLAYBACK_PAD_S)
            playback_end = clip["end_ms"] / 1000.0 + CITATION_PLAYBACK_PAD_S
            if clip.get("duration_ms"):
                playback_end = min(playback_end, clip["duration_ms"] / 1000.0)
            start_sec = int(clip["start_ms"]) // 1000
            end_sec = -(-int(clip["end_ms"]) // 1000) if clip.get("end_ms") else start_sec + 60
            clip_title = clip.get("title") or clip.get("video_title") or UNTITLED_LINK_LABEL
            clip_url = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
            return {
                "point_id": clip.get("point_id"),
                "video_id": video_id,
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
                "start_sec": start_sec,
                "end_sec": end_sec,
                "timestamp_seconds": sec,
                "speaker": clip["speaker"],
                "title": clip_title,
                "url": clip_url,
                "teacher_id": clip.get("teacher_id"),
                # Provenance claim copied from the stored clip, never inferred: the builder
                # writes True only after a real voice check and omits the key otherwise, so
                # a missing key must reach the UI as False, not as "verified" (QA-1).
                "speaker_verified": clip.get("speaker_verified") is True,
                "channel": clip.get("channel"),
                "transcript_hash": clip["transcript_hash"],
                "verbatim_text": clip["verbatim_text"],
                "text_snippet": clip["verbatim_text"],
                # Always derived from the clip's own start: the stored source_url is the
                # plain video URL, which would open playback at 0:00.
                "source_url": clip_url,
                "video_url": clip.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
                "playback_start_seconds": round(playback_start, 2),
                "playback_end_seconds": round(playback_end, 2),
                "playback_url": f"https://www.youtube.com/watch?v={video_id}&t={int(playback_start)}s",
                "confidence": clip_confidence,
                "is_verbatim": True,
                "provenance_kind": provenance_kind,
                "caption_status": clip.get("caption_status") or "auto_transcript",
                **transcript_label(clip["verbatim_text"], clip.get("caption_status")),
            }

        # Every rendered quote (hero or weak match) is re-checked against the
        # payloads it was retrieved from: speaker label, link and t= must all be
        # backed by the stored record, or the quote is not shown (quote_fidelity).
        sources = sources_from_payloads(verified_clips)

        def _abstain_unverified() -> FirstPersonPipelineResult:
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count(
                "abstained",
                latency,
                confidence,
                n_quarantined,
                0,
                "no_verified_clips",
                sum(fp_llm_tokens),
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                answerability=answerability,
                abstain_reason="no_verified_clips",
            )

        if is_direct:
            status = "success"
            # Each served clip must clear the threshold itself; the top clip's
            # confidence says nothing about clips 2 and 3. Citations cover only
            # clips that will actually be rendered.
            threshold = self._profile["threshold"]
            confident = [
                (c, score)
                for c, score in zip(verified_clips, clip_scores)
                if score >= threshold
                and verify_hero_clip(c, sources) is not None
                and is_youtube_video_available(str(c.get("video_id") or ""))
            ]
            if not confident:
                return _abstain_unverified()
            confident_clips = [c for c, _ in confident]
            for clip, score in confident:
                cit = _build_citation(clip, score, clip.get("provenance_kind", "speech_turn_clip"))
                citations.append(cit)

            # ponytail: OKF entries are topic-matching signals only — never added to citations.
            # Citations must be 100% verbatim Qdrant clips. OKF summaries are LLM-generated
            # and must never appear as attributed guru words in the response or citation list.

            # ponytail: weave clips and OKF entries into structured answer
            intent = "PRACTICE" if has_practice_intent else "QUERY"
            weave_res = self._weaver.weave(
                query=query,
                clips=confident_clips,
                okf_entries=okf_entries,
                intent=intent,
                sources=sources,
                token_sink=fp_llm_tokens,
            )
            if not weave_res.passed_gate:
                return _abstain_unverified()
            final_text = weave_res.text
            audio_playback_clips = getattr(weave_res, "audio_playback_clips", None) or []
            if not audio_playback_clips and confident_clips:
                for c in confident_clips:
                    if not is_youtube_video_available(str(c.get("video_id") or "")):
                        continue
                    hero = verify_hero_clip(c, sources)
                    if hero:
                        strip = audio_strip_for(c, hero)
                        if strip:
                            audio_playback_clips.append(strip)
            audio_playback_clip = weave_res.audio_playback_clip or (
                audio_playback_clips[0] if audio_playback_clips else None
            )
            atma_vichara_inquiry = getattr(weave_res, "atma_vichara_inquiry", None)
            practice_recommendation = getattr(weave_res, "practice_recommendation", None)
            cit = citations[0] if citations else None
        else:
            status = "weak_match"
            hero = verify_hero_clip(top_clip, sources)
            if hero is None or not is_youtube_video_available(str(top_clip.get("video_id") or "")):
                return _abstain_unverified()
            cit = _build_citation(top_clip, confidence, "weak_match_fallback")
            citations.append(cit)
            final_text = (
                f'Related, not a direct answer:\n\n"{top_clip["verbatim_text"]}"\n'
                f"— {hero['label']} ({top_clip['video_id']}, {cit['timestamp_seconds']}s)"
            )
            atma_vichara_inquiry = None
            practice_recommendation = None
            audio_playback_clip = audio_strip_for(top_clip, hero)
            audio_playback_clips = [audio_playback_clip] if audio_playback_clip else []

        detected_concepts: list[str] = []
        seen_concepts = set()
        if okf_entries:
            for e in okf_entries:
                t = e.get("title")
                if t and t.lower() not in seen_concepts:
                    seen_concepts.add(t.lower())
                    detected_concepts.append(t)
        _CANONICAL_CONCEPTS = [
            "Beautiful State",
            "Suffering",
            "Breath Awareness",
            "Meditation",
            "Four Sacred Secrets",
            "Inner Awakening",
            "Witnessing",
            "Non-Duality",
            "Presence",
            "Ego",
            "Ekam",
            "Mukthi",
        ]
        q_lower = query.lower()
        clip_text = (top_clip.get("verbatim_text") or "").lower() if top_clip else ""
        for c in _CANONICAL_CONCEPTS:
            if c.lower() in q_lower or c.lower() in clip_text:
                if c.lower() not in seen_concepts:
                    seen_concepts.add(c.lower())
                    detected_concepts.append(c)
            if len(detected_concepts) >= 4:
                break

        res = FirstPersonPipelineResult(
            answer_text=final_text,
            citations=citations,
            status=status,
            is_direct_answer=is_direct,
            latency_ms=0.0,
            answerability=answerability,  # 'yes' when the Phase 2 gate passed; None when it did not run
            abstain_reason="none",
            audio_playback_clip=audio_playback_clip,
            audio_playback_clips=audio_playback_clips,
            detected_concepts=detected_concepts,
            atma_vichara_inquiry=atma_vichara_inquiry,
            practice_recommendation=practice_recommendation,
        )
        if not cache_bypass:
            self.set_exact_cache(
                query,
                res.to_dict(),
                teacher_id,
                language=language,
                allow_state=request_allow_state,
                block_state=request_block_state,
            )

        # Measured last so scoring, citation building and the cache write are all counted.
        res.latency_ms = (time.monotonic() - start_time) * 1000.0
        self._log_and_count(
            status,
            res.latency_ms,
            confidence,
            n_quarantined,
            len(citations),
            "none",
            sum(fp_llm_tokens),
        )
        return res


if __name__ == "__main__":
    # ponytail: minimal self-check, not a full test suite (see tests/test_first_person_pipeline.py)
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine_similarity(None, [1.0]) == 0.0
    text = "Suffering is resistance to what is."
    good_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": good_hash, "speaker": "Sri Preethaji"}
    )
    assert not _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": "0" * 64, "speaker": "Sri Preethaji"}
    )
    assert not _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": good_hash, "speaker": "Host"}
    )
    print("first_person_pipeline self-check ok")
