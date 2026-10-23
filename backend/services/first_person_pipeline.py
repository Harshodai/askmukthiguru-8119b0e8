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
from domain.first_person_context import EDGE_ANNOTATION_VERSION as _FP_EDGE_VERSION
from domain.first_person_context import PARENT_VERSION as _FP_PARENT_VERSION
from domain.first_person_context import SCHEMA_VERSION as _FP_CONTEXT_SCHEMA_VERSION
from domain.first_person_context import (
    CitationSpan,
    HarnessDecision,
    ParentContext,
    SourceSpan,
)
from guardrails.lightweight_handler import _BLOCKED_TOPICS, SAFETY_TOPICS, match_blocked_topic
from ingest.verbatim.boundaries import boundary_defects
from services.attribution import resolve_attribution_label
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


from services.guru_registry import (
    allowed_speaker_labels as _allowed_labels,
)  # noqa: E402
from services.guru_registry import (
    label_for,
)

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
    r"^[\"'\u201c\u2018\s]*(?:yes(?:,|[^\w\s])\s*|(?:this|these|those|that)\s+(?:is|are|was|were)\b|these\s+are\b|this\s+space\b|it\s+is\s+possible\b|because\b|in\s+that\b"
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
    r"|that'?s\s+the\s+day\s+today|today\s+is\s+the\s+day\s+of"
    r"|\btoday,?\s+we\s+(?:will|shall|are\s+going\s+to)\b",
    re.IGNORECASE,
)


# Violence wording: a metaphor ("he doesn't mind being stabbed by his angry wife") read
# literally by a seeker asking about anger in a marriage is unsafe. Applied only to
# relationship/anger questions; the clip text is never edited, the clip is just not served.
_TARGET_PERSON_PHRASE = (
    r"(?:her|him|them|me|you|(?:(?:a|an|the|his|her|their|my|your|our)\s+)?"
    r"(?:(?:\w+\s+)?(?:woman|women|man|men|wife|wives|husband|husbands|spouse|spouses|"
    r"partner|partners|child|children|son|sons|daughter|daughters|mother|mothers|"
    r"father|fathers|mom|moms|dad|dads|boyfriend|boyfriends|girlfriend|girlfriends|"
    r"someone|anyone|anybody|person|people|girl|girls|boy|boys)))"
)
_PASSIVE_HIT_BY_PHRASE = (
    r"(?:(?:was|were|being|got|gets|is|are)\s+)?hit\s+by\s+"
    r"(?:(?:a|an|the|his|her|their|my|your|our)\s+)?"
    r"(?:(?:\w+\s+)?(?:woman|women|man|men|wife|wives|husband|husbands|spouse|spouses|"
    r"partner|partners|child|children|son|sons|daughter|daughters|mother|mothers|"
    r"father|fathers|mom|moms|dad|dads|boyfriend|boyfriends|girlfriend|girlfriends|"
    r"someone|anyone|anybody|person|people|girl|girls|boy|boys))"
)
_VIOLENCE_WORDING_RE = re.compile(
    r"\bstab(?:s|bed|bing)?\b|\bkill(?:s|ed|ing)?\b|\bmurder\w*|\bbeat(?:s|ing|en)?\b|\bslap\w*|\bpunch\w*|\bkick(?:s|ed|ing)?\b|\bchok\w+|\bmanhandl\w+"
    r"|\bstrangl\w+|\bhit(?:s|ting)?\s+"
    + _TARGET_PERSON_PHRASE
    + r"\b|\b"
    + _PASSIVE_HIT_BY_PHRASE
    + r"\b|\b(?:shoot(?:s|ing)?|shot)\b",
    re.IGNORECASE,
)


def _violent_for_context(query: str, text: str, retrieval_query: str = "") -> bool:
    """True when a relationship/anger question would be served a clip with violence wording."""
    from guardrails.lightweight_handler import needs_relationship_safety_boundary

    return bool(_VIOLENCE_WORDING_RE.search(text)) and (
        needs_relationship_safety_boundary(query)
        or (bool(retrieval_query) and needs_relationship_safety_boundary(retrieval_query))
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
    if _ORPHAN_OPENER_RE.match(text) and not _CORE_WISDOM_KEYWORDS_RE.search(text):
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
# Negative cache for unreadable blocklist paths: path -> monotonic() of the
# last failed read. While fresh, _quality_blocklist() fails closed without
# touching disk or logging again.
_BLOCKLIST_NEG_CACHE: dict[str, float] = {}
_BLOCKLIST_NEG_TTL_S = 60.0


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
    A path that fails to read is negative-cached for _BLOCKLIST_NEG_TTL_S:
    a missing file must fail closed without re-hitting disk and re-logging
    on every request (log flood) until the TTL expires.
    """
    path = str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip()
    if not path:
        return None
    now = time.monotonic()
    neg = _BLOCKLIST_NEG_CACHE.get(path)
    if neg is not None and now - neg < _BLOCKLIST_NEG_TTL_S:
        return None
    try:
        mtime = os.path.getmtime(path)
        cached = _BLOCKLIST_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Accept only the two documented shapes. A dict WITHOUT a "blocked"
        # list used to fall through to `data` itself, and iterating a dict
        # yields its KEY names — silently "quarantining" nothing real.
        if isinstance(data, list):
            ids = data
        elif isinstance(data, dict) and isinstance(data.get("blocked"), list):
            ids = data["blocked"]
        else:
            raise ValueError(
                'expected a JSON list of ids or {"blocked": [...]}, '
                f"got {type(data).__name__}"
                + (" without a 'blocked' list" if isinstance(data, dict) else "")
            )
        blocked = frozenset(str(i) for i in ids)
        _BLOCKLIST_CACHE[path] = (mtime, blocked)
        _BLOCKLIST_NEG_CACHE.pop(path, None)
        return blocked
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        now = time.monotonic()
        # Throttle the error log to one line per TTL: the negative cache
        # above already suppresses re-reads, so only the first failure in
        # each window is worth logging.
        _last = _BLOCKLIST_NEG_CACHE.get(path)
        _BLOCKLIST_NEG_CACHE[path] = now
        if _last is None or now - _last >= _BLOCKLIST_NEG_TTL_S:
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

    # Reject clips too long to read as one answer (setting; 0 = off). Unknown timing = no cap.
    max_s = float(getattr(settings, "first_person_max_clip_seconds", 0) or 0)
    start_ms, end_ms = clip.get("start_ms"), clip.get("end_ms")
    if (
        max_s
        and isinstance(start_ms, (int, float))
        and isinstance(end_ms, (int, float))
        and (end_ms - start_ms) / 1000.0 > max_s
    ):
        logger.info(
            "[FirstPersonPipeline] Clip %s rejected by content quality gate: %.0fs exceeds the %.0fs cap",
            clip.get("point_id") or clip.get("video_id"),
            (end_ms - start_ms) / 1000.0,
            max_s,
        )
        return False

    # Reject live-event instructions — crowd/logistics management, not teachings.
    # Guided meditation practices contain valid practice instructions and must not be discarded.
    is_practice = bool(
        clip.get("category") == "practice"
        or clip.get("type") == "Practice"
        or (isinstance(clip.get("tags"), list) and "practice" in clip.get("tags"))
    )
    if _LIVE_EVENT_INSTRUCTION_RE.search(text) and not is_practice:
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
# 25 s default (was 12): Haiku 5.5 reasons internally and provider latency during peak hours reaches 13-18s
_RELEVANCE_TIMEOUT_S = float(getattr(settings, "first_person_relevance_timeout_s", 25.0))

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
    "one event/audience, or a fragment that cannot stand alone. Reply ONLY with a JSON object "
    'of the form {"scores": [3, 1, 0]}, one integer per clip, in order. No other text.'
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


def _relevance_select_jev(
    query: str,
    clips: list[dict[str, Any]],
    request_loop: Optional[Any] = None,
) -> Optional[int]:
    """Select the best candidate clip using TypeSafe Jev discrete decision model.

    Returns the integer index of the selected clip, None if Jev decided NONE (no clip
    answers), or _RELEVANCE_INDETERMINATE (-1) on error/timeout to trigger fallback.
    """
    if not (
        getattr(settings, "jev_enabled", True)
        and getattr(settings, "first_person_relevance_jev_enabled", False)
    ):
        return _RELEVANCE_INDETERMINATE

    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key or not clips:
        return _RELEVANCE_INDETERMINATE

    import httpx

    model = getattr(settings, "jev_model", "typesafe/jev-1.14")
    timeout_s = float(getattr(settings, "jev_timeout_s", 1.5))
    threshold = float(getattr(settings, "jev_confidence_threshold", 0.70))

    criteria: dict[str, str] = {}
    for i, c in enumerate(clips[:4]):
        text = (c.get("verbatim_text") or "").strip()[:300]
        criteria[f"clip_{i + 1}"] = f"Clip {i + 1}: {text}"
    criteria["NONE"] = "None of the candidate clips directly answer the seeker's question."

    payload = {
        "model": model,
        "state": {
            "question": query,
        },
        "questions": {
            "best_clip": {
                "type": "choice",
                "instructions": "Select which candidate clip directly answers the seeker's question, or NONE.",
                "criteria": criteria,
            }
        },
    }

    async def _call_jev() -> Optional[int]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://askmukthiguru.com",
            "X-Title": "AskMukthiGuru",
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://openrouter.ai/api/alpha/decisions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                logger.info("Jev clip selection HTTP %d: %s", resp.status_code, resp.text[:100])
                return _RELEVANCE_INDETERMINATE
            data = resp.json()
            answers = data.get("answers", {})
            best_clip = answers.get("best_clip", {})
            choice = best_clip.get("choice")
            probs = best_clip.get("probabilities", {})
            conf = float(probs.get(choice, 0.0)) if isinstance(probs, dict) else 0.0

            if conf < threshold:
                logger.info(
                    "Jev clip selection confidence %.2f < %.2f; indeterminate", conf, threshold
                )
                return _RELEVANCE_INDETERMINATE

            if choice == "NONE":
                return None
            if choice and choice.startswith("clip_"):
                try:
                    idx = int(choice.split("_")[1]) - 1
                    if 0 <= idx < len(clips):
                        logger.info(
                            "Jev clip selection chosen clip_%d (confidence=%.2f)", idx + 1, conf
                        )
                        return idx
                except (ValueError, IndexError):
                    pass
            return _RELEVANCE_INDETERMINATE

    try:
        return run_llm_coroutine(_call_jev, timeout_s, request_loop)
    except Exception as exc:
        logger.info("Jev clip selection failed: %s; falling back", type(exc).__name__)
        return _RELEVANCE_INDETERMINATE


def _relevance_select(
    query: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    request_loop: Optional[Any] = None,
    token_sink: Optional[list[int]] = None,
    scores_out: Optional[list[int]] = None,
) -> Optional[int]:
    """Scorer entry point. The optional Jev picker only reorders candidates (its pick is
    scored first); the min-score scorer still decides and its real scores are kept."""
    order = list(range(len(clips)))
    if (
        clips
        and getattr(settings, "jev_enabled", True)
        and getattr(settings, "first_person_relevance_jev_enabled", False)
    ):
        pick = _relevance_select_jev(query, clips, request_loop=request_loop)
        if pick is not None and pick != _RELEVANCE_INDETERMINATE and 0 <= pick < len(clips):
            order = [pick] + [i for i in order if i != pick]
    local_scores: list[int] = []
    chosen = _relevance_select_scored(
        query,
        [clips[i] for i in order],
        llm_service,
        request_loop=request_loop,
        token_sink=token_sink,
        scores_out=local_scores if scores_out is not None else None,
    )
    if scores_out is not None and local_scores:
        restored = [0] * len(clips)
        for pos, orig in enumerate(order):
            restored[orig] = local_scores[pos]
        scores_out.extend(restored)
    if chosen is None or chosen == _RELEVANCE_INDETERMINATE:
        return chosen
    return order[chosen]


def _relevance_select_scored(
    query: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    request_loop: Optional[Any] = None,
    token_sink: Optional[list[int]] = None,
    scores_out: Optional[list[int]] = None,
) -> Optional[int]:
    """Index of the best clip whose relevance score >= first_person_relevance_min_score.

    ``scores_out``, when given, receives the validated per-clip scores (used to pick an optional
    second quote); it is left untouched on every failure path.

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
            clean_raw = str(raw).strip()
            if clean_raw.startswith("```"):
                lines = clean_raw.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                clean_raw = "\n".join(lines).strip()
            # Only an enclosing Markdown fence is tolerated. Prose around the
            # object means the model did not honour the schema, so the reply is
            # rejected rather than mined for a JSON-looking substring.
            if not (clean_raw.startswith("{") and clean_raw.endswith("}")):
                raise ValueError("response is not a JSON object")
            decoded = json.loads(clean_raw)
            candidate = decoded.get("scores") if isinstance(decoded, dict) else None
            if not isinstance(candidate, list):
                raise ValueError("missing scores array")
            scores = []
            for v in candidate:
                # bool is an int subclass — True must not pass as 1.
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError(f"non-integer score {v!r}")
                scores.append(v)
        except (ValueError, KeyError, TypeError, AttributeError) as json_err:
            logger.info(
                "[FirstPersonPipeline] Relevance check unparseable JSON output %r (err=%s); abstaining",
                str(raw)[:120],
                json_err,
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
    if scores_out is not None:
        scores_out[:] = scores
    best = max(range(len(scores)), key=lambda i: (scores[i], -i))  # highest score, earliest wins
    logger.info(
        "[FirstPersonPipeline] Relevance check parsed scores: %s (minimum=%s, best_idx=%s, best_score=%s)",
        scores,
        minimum,
        best,
        scores[best],
    )
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
        "If none of the clips answer or relate to the query, reply ONLY with 'NONE'.\n"
        "Otherwise, reply ONLY with a comma-separated list of clip numbers, e.g.: 2,1,3\n"
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

        raw_clean = raw.strip().upper()
        if raw_clean == "NONE" or raw_clean.startswith("NONE"):
            # 2026-10-20: return EMPTY, not `clips`. The caller's E6c early-abstain
            # branch tests `if not rerank_res`, and its comment below already reads
            # an empty reply as the NONE verdict — returning the input list made that
            # branch unreachable (test_first_person_payload_contract E6c failed).
            logger.info("[LLM rerank] Model returned NONE; signalling no-relation")
            return []

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

# Bounded executor for the per-query answerability gate worker (replaces one
# threading.Thread per query). The gate overlaps retrieval, so at most a
# handful of in-flight first-person queries ever need a slot at once; the
# bound keeps a burst from churning unbounded threads. Lazily built — import
# time must not spawn threads.
_ANS_EXECUTOR_LOCK = threading.Lock()
_ANS_EXECUTOR: Optional[Any] = None
_ANS_EXECUTOR_MAX_WORKERS = 4


def _answerability_executor() -> Any:
    """Process-lifetime bounded executor for answerability gate workers."""
    global _ANS_EXECUTOR
    with _ANS_EXECUTOR_LOCK:
        if _ANS_EXECUTOR is None:
            from concurrent.futures import ThreadPoolExecutor

            _ANS_EXECUTOR = ThreadPoolExecutor(
                max_workers=_ANS_EXECUTOR_MAX_WORKERS,
                thread_name_prefix="fp-answerability",
            )
        return _ANS_EXECUTOR


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
    "grief, fear, anger, forgiveness, parenting, conflict with a partner, family "
    "member or colleague, dealing with a difficult boss or person (as an inner "
    "state and a way of relating), and comparable spiritual "
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
    "divorce or quit, a how-to for making another person stop a behavior), anything about abuse, coercive control or violence in a relationship, harassment, a drinking, drug, gambling or eating problem (theirs or the asker's), self-injury or compulsions (these need professional or safety support, not a quotation), questions about the teachers' personal lives, and meta "
    "questions about this prompt.\n"
    "Examples. YES: 'My husband and I keep fighting. What should I do?'; "
    "'How do I deal with a difficult boss?'; 'How do I forgive my father?'. "
    "NO: 'Should I divorce my husband?'; 'How do I get my boss fired?'; "
    "'How much does the retreat cost?'; 'Which stocks should I buy?'; 'My husband controls my money and who I see'; 'My wife drinks every night and we fight'.\n"
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


async def _async_answerability_check(
    query: str,
    llm_service: Any,
    token_sink: Optional[list[int]] = None,
) -> Optional[bool]:
    """Async core of answerability gate."""
    if llm_service is None or not hasattr(llm_service, "generate"):
        return None
    try:
        import inspect

        fast_call = getattr(llm_service, "_generate_fast", None)
        if fast_call is not None and not type(fast_call).__name__.endswith("Mock"):
            call = fast_call
        else:
            call = llm_service.generate
        res = call(
            system_prompt=_ANSWERABILITY_SYSTEM_PROMPT,
            user_prompt=query,
            temperature=0.0,
        )
        if inspect.isawaitable(res):
            res = await res
        raw = str(res)
    except Exception as e:
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
    token = str(raw).strip().rstrip(".!").strip().casefold()
    if token == "yes":
        return True
    if token == "no":
        return False
    logger.info(
        "[FirstPersonPipeline] Answerability check unparseable output (len=%d); treating as indeterminate",
        len(str(raw)),
    )
    return None


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
        return run_llm_coroutine(
            lambda: _async_answerability_check(query, llm_service, token_sink),
            _ANSWERABILITY_TIMEOUT_S,
            request_loop,
        )
    except Exception as e:
        if isinstance(e, ProviderRefusalError):
            logger.info("[FirstPersonPipeline] Answerability check refused by provider")
        else:
            logger.info(
                "[FirstPersonPipeline] Answerability check indeterminate (timeout/error): %s", e
            )
        if token_sink is not None:
            token_sink.append(_estimate_fp_tokens(_ANSWERABILITY_SYSTEM_PROMPT, query))
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
        stage_timings: Optional[dict[str, float]] = None,
        related_clips: Optional[list[dict[str, Any]]] = None,
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
        self.stage_timings = stage_timings or {}
        # A25: related (never answer) clips offered on a below-min abstain; [] when
        # the feature is off, so callers and to_dict stay byte-identical.
        self.related_clips = related_clips or []

    def to_dict(self) -> dict[str, Any]:
        data = {
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
            "stage_timings": self.stage_timings,
        }
        if self.related_clips:
            data["related_clips"] = self.related_clips
        return data


def _build_citation_dict(
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
        "speaker_verified": clip.get("speaker_verified") is True,
        "channel": clip.get("channel"),
        "transcript_hash": clip["transcript_hash"],
        "verbatim_text": clip["verbatim_text"],
        "text_snippet": clip["verbatim_text"],
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


# ---------------------------------------------------------------------------
# A25 (2026-10-19) — abstain "related clips". When
# `first_person_abstain_related_clips_enabled` is on, an abstain whose candidates
# were integrity-verified but scored below the relevance minimum carries the
# closest few as explicitly related, never as answers. Built from the SAME
# retrieval result the served path uses, through the SAME URL and attribution
# helpers (`_build_citation_dict` + `resolve_attribution_label`), so this list can
# never invent a link or a teacher name the stored payload lacks
# (L-NO-INVENTED-CREDIT-1 / L-FP-HYBRID-SCAFFOLD-1).
# ---------------------------------------------------------------------------

# The served path offers at most `max_clips` (3) clips; the abstain offer mirrors
# that bound so "the closest few" never becomes a topic dump.
_RELATED_CLIPS_CAP = 3

# Existing repo vocabulary for a clip that is offered but does not answer it
# (the weak_match copy below and the bridge's verification["direct"]=False).
_RELATED_LABEL = "Related, not a direct answer"

# Canonical concept vocabulary, matched deterministically against a clip's own
# stored text/tags (the served path's `detected_concepts` uses the same list).
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


def _clip_topics(clip: dict[str, Any]) -> list[str]:
    """Deterministic topics for a clip, from data already stored (no LLM call).

    Reuses what exists: the clip payload's own concept tags/labels when present
    (`tags`, `okf_title`, `discourse_context`), plus the canonical-concept
    vocabulary matched against the stored verbatim text. Never invents a topic.
    """
    topics: list[str] = []
    raw_tags = clip.get("tags")
    if isinstance(raw_tags, (list, tuple)):
        topics.extend(t.strip() for t in raw_tags if isinstance(t, str) and t.strip())
    for key in ("okf_title", "discourse_context"):
        value = clip.get(key)
        if isinstance(value, str) and value.strip():
            topics.append(value.strip())
    text = str(clip.get("verbatim_text") or "").lower()
    topics.extend(c for c in _CANONICAL_CONCEPTS if c.lower() in text)
    seen: set[str] = set()
    ordered: list[str] = []
    for topic in topics:
        if topic.lower() not in seen:
            seen.add(topic.lower())
            ordered.append(topic)
    return ordered[:4]


def _build_related_clip(clip: dict[str, Any], score: float) -> Optional[dict[str, Any]]:
    """One abstain "related" clip: served-path URL + attribution, marked not-an-answer.

    Attribution obeys ``resolve_attribution_label`` with the served path's
    ``route_gated=True`` (quote_weaver.verify_hero_clip): an unverified clip reads
    ``shared in <channel>`` (or ``unverified clip``), and the bare ``speaker``
    field is dropped unless ``speaker_verified is True`` — never upgraded.
    """
    try:
        cit = _build_citation_dict(clip, float(score), "abstain_related_clip")
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "[FirstPersonPipeline] Related clip dropped (damaged point %s): %s",
            clip.get("point_id"),
            exc,
        )
        return None
    verified = cit.get("speaker_verified") is True
    entry: dict[str, Any] = {
        "point_id": cit.get("point_id"),
        "video_id": cit.get("video_id"),
        "title": cit.get("title"),
        # Raw speaker only when voice-verified; otherwise the resolved label alone
        # (a bare teacher name on an unverified clip is an invented credit).
        "speaker": cit.get("speaker") if verified else None,
        "speaker_verified": verified,
        "attribution": resolve_attribution_label(
            cit.get("speaker"),
            speaker_verified=cit.get("speaker_verified"),
            channel=cit.get("channel"),
            route_gated=True,
        ),
        "channel": cit.get("channel"),
        "timestamp_seconds": cit.get("timestamp_seconds"),
        "start_sec": cit.get("start_sec"),
        "text_snippet": cit.get("text_snippet"),
        "url": cit.get("url"),
        # Absolute URL of the FULL talk (no t= offset) — the repo's existing
        # video_url derivation, reused, never re-implemented.
        "full_talk_url": cit.get("video_url"),
        "confidence": cit.get("confidence"),
        "related": True,
        "is_answer": False,
        "label": _RELATED_LABEL,
    }
    topics = _clip_topics(clip)
    if topics:
        entry["topics"] = topics
    return entry


def _related_clips_for(
    clips: list[dict[str, Any]], scores: Optional[list[float]] = None
) -> list[dict[str, Any]]:
    """Bounded related-clip list for an abstain, or [] when the flag is off.

    Flag off returns [] and the caller attaches nothing, so the abstain payload
    stays byte-identical to before the feature.
    """
    if not getattr(settings, "first_person_abstain_related_clips_enabled", False):
        return []
    if not clips:
        return []
    out: list[dict[str, Any]] = []
    for i, clip in enumerate(clips[:_RELATED_CLIPS_CAP]):
        score = (
            scores[i]
            if scores and i < len(scores) and isinstance(scores[i], (int, float))
            else float(clip.get("score") or 0.0)
        )
        entry = _build_related_clip(clip, score)
        if entry is not None:
            out.append(entry)
    return out


_COMPOUND_SPLIT_RE = re.compile(
    r"(?:\s*,\s*and\s+(?:how|why|what|can|does|is|will|should|could)\b"
    r"|\s+and\s+(?:how|why|what|can|does|is|will|should|could)\b"
    r"|\s*\?\s+(?=[A-Z])"
    r"|\s*;\s*)",
    re.IGNORECASE,
)


def _decompose_query_facets(
    query: str,
    llm_service: Optional[Any] = None,
    timeout_s: float = 2.5,
    token_sink: Optional[list[int]] = None,
) -> list[str]:
    """Split a compound question into up to 3 distinct sub-questions (Task F1).

    Uses fast model call when available, falling back to deterministic regex split.
    Always capped at 3 facets. If single-facet, returns [query].
    """
    clean_q = query.strip()
    if not clean_q:
        return []

    has_compound_pattern = bool(_COMPOUND_SPLIT_RE.search(clean_q)) or (
        " and " in clean_q.lower() and len(clean_q.split()) > 10
    )
    if not has_compound_pattern:
        return [clean_q]

    if llm_service is not None:
        system_prompt = (
            "You are a query analysis assistant. Given a compound spiritual query, "
            "break it down into 2 or at most 3 distinct single-focus sub-questions.\n"
            "Reply ONLY with the sub-questions, one per line.\n"
            "No bullet points, no numbering, no intro or outro text."
        )
        user_prompt = f"Query: {clean_q}"
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

            if raw:
                lines = []
                for line in raw.splitlines():
                    cleaned = re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
                    if cleaned and len(cleaned) > 5:
                        lines.append(cleaned)
                if 2 <= len(lines) <= 3:
                    return lines[:3]
        except Exception as e:
            logger.debug(
                "[_decompose_query_facets] LLM decomposition failed: %s; falling back to regex", e
            )

    parts = [p.strip() for p in _COMPOUND_SPLIT_RE.split(clean_q) if p.strip()]
    if len(parts) >= 2:
        return parts[:3]
    return [clean_q]


_CALIBRATION_UNSET = object()

# Sentinel for the lazily-computed B4 serving-contract verdict ("" = no
# violation, computed once per pipeline instance).
_CONTRACT_UNSET = object()


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
        context_store: Optional[Any] = None,
        context_harness: Optional[Any] = None,
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
        # B4 serving contract: computed lazily, cached per pipeline instance.
        self._serving_contract_error_cache: Any = _CONTRACT_UNSET
        self._collection_contract_cache: Optional[dict[str, str]] = None
        # Loop the answerability gate schedules onto (captured on the request
        # loop by app/api/first_person.py, same pattern as the rerank fn);
        # None = scripts/harness use the persistent gate loop.
        self._llm_loop = llm_loop
        if llm_loop is not None:
            remember_request_loop(llm_loop)
        self._context_store = context_store
        self._context_harness = context_harness
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

    def _get_context_store(self) -> Optional[Any]:
        if self._context_store is not None:
            return self._context_store
        collection = str(getattr(settings, "first_person_context_collection", "") or "").strip()
        if collection:
            from services.first_person_context_store import FirstPersonContextStore

            client = getattr(self._store, "_client", None)
            if client is None:
                from qdrant_client import QdrantClient

                client = QdrantClient(url=settings.qdrant_url)
            self._context_store = FirstPersonContextStore(client=client, collection=collection)
            return self._context_store
        return None

    def _get_context_harness(self) -> Any:
        if self._context_harness is not None:
            return self._context_harness
        from services.first_person_context_harness import (
            FirstPersonContextHarness,
            policy_from_settings,
        )

        self._context_harness = FirstPersonContextHarness(policy_from_settings())
        return self._context_harness

    @staticmethod
    def _build_context_citation(
        span: SourceSpan,
        cite_span: Optional[CitationSpan] = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        from services.first_person_context_store import point_id_for_record

        sec = span.start_ms // 1000
        video_id = span.video_id
        start_sec = span.start_ms // 1000
        end_sec = -(-span.end_ms // 1000)
        playback_start = max(0.0, span.start_ms / 1000.0 - CITATION_PLAYBACK_PAD_S)
        playback_end = span.end_ms / 1000.0 + CITATION_PLAYBACK_PAD_S
        clip_url = span.source_url or f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
        speaker_name = label_for(span.guru_id) or span.speaker_id
        title = f"Discourse by {speaker_name}"
        label = cite_span.label if cite_span else None
        return {
            # The Qdrant point id (UUIDv5 of the span id), NOT the sha256 span
            # id: the servability re-check and the quality allow/block lists
            # are keyed by point id, and a sha256 is not a valid Qdrant point
            # id (the lookup would 400 and silently disable the exact cache).
            "point_id": point_id_for_record(span.source_span_id),
            "source_span_id": span.source_span_id,
            "video_id": video_id,
            "start_ms": span.start_ms,
            "end_ms": span.end_ms,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "timestamp_seconds": sec,
            "speaker": speaker_name,
            "title": title,
            "url": clip_url,
            "teacher_id": span.guru_id,
            "speaker_verified": span.speaker_verified is True,
            "channel": None,
            "transcript_hash": span.source_text_hash,
            "source_text_hash": span.source_text_hash,
            "video_transcript_hash": span.transcript_hash,
            "verbatim_text": span.verbatim_text,
            "text_snippet": span.verbatim_text,
            "source_url": clip_url,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "playback_start_seconds": round(playback_start, 2),
            "playback_end_seconds": round(playback_end, 2),
            "playback_url": f"https://www.youtube.com/watch?v={video_id}&t={int(playback_start)}s",
            "confidence": confidence,
            "is_verbatim": True,
            "provenance_kind": (
                span.provenance_kind.value
                if hasattr(span.provenance_kind, "value")
                else str(span.provenance_kind)
            ),
            "caption_status": span.caption_status,
            "label": label,
            **transcript_label(span.verbatim_text, span.caption_status),
        }

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

    def _serving_contract_error(self) -> str:
        """The B4 serving-contract violation for this pipeline's collection, if any.

        Offline and cached: the contract is a declared file, not a live probe,
        so this costs one dict lookup per request after the first.

        The gate applies to the REAL serving path — a real
        :class:`FirstPersonStore`, or any store pointed at a first-person
        collection name. A test double that stands in for a store (and names
        nothing like a first-person collection) is not gated: it cannot read a
        real collection, so a contract check on it would only break tests
        without protecting a deployment.
        """
        if self._serving_contract_error_cache is not _CONTRACT_UNSET:
            return self._serving_contract_error_cache
        error = ""
        collection = str(getattr(self._store, "collection", "") or "")
        gated = isinstance(self._store, FirstPersonStore) or collection.startswith(
            ("first_person", "fp_context")
        )
        if not gated:
            self._serving_contract_error_cache = ""
            return ""
        try:
            from services.first_person_serving_contract import (
                legacy_store_preflight,
                load_contract_cached,
            )

            report = legacy_store_preflight(
                contract=load_contract_cached(
                    str(getattr(settings, "first_person_serving_contract_path", "") or "") or None
                ),
                legacy_collection=collection,
            )
            if report.errors:
                error = "; ".join(report.errors)
        except Exception as exc:  # noqa: BLE001 - a broken contract must fail closed
            error = f"serving_contract_unreadable: {exc}"
        self._serving_contract_error_cache = error
        return error

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
        components = self._serving_policy_components(allow_state, block_state)
        pairs = sorted(components.items())
        return hashlib.sha256("|".join(f"{k}={v}" for k, v in pairs).encode("utf-8")).hexdigest()[
            :16
        ]

    def _serving_policy_components(
        self, allow_state: str | None = None, block_state: str | None = None
    ) -> dict[str, str]:
        """The serving-policy inputs that make up the exact-cache fingerprint.

        Split out of :meth:`_serving_policy_fingerprint` so the B4 contract
        gate can assert that the collection, its payload schema, its corpus
        version and its evidence policy all ride in the fingerprint (a
        repointed or re-versioned collection must never replay an answer
        computed under a different contract).
        """
        if allow_state is None:
            allow_state = self._allowlist_state()
        if block_state is None:
            block_state = self._blocklist_state()
        contract = self._collection_contract_components()
        pairs = sorted(
            {
                "answerability": str(bool(settings.first_person_answerability_check_enabled)),
                "boundary_guard": str(bool(self._boundary_guard_enabled)),
                "content_gate": str(bool(self._content_quality_gate_enabled)),
                "editorial_rewrite": str(bool(settings.first_person_editorial_rewrite_enabled)),
                "llm_rerank": str(bool(settings.first_person_llm_rerank_enabled)),
                "second_quote": str(
                    bool(getattr(settings, "first_person_second_quote_enabled", False))
                ),
                "answerability_prompt": hashlib.sha256(
                    _ANSWERABILITY_SYSTEM_PROMPT.encode()
                ).hexdigest()[:12],
                "max_clip_s": str(
                    float(getattr(settings, "first_person_max_clip_seconds", 0) or 0)
                ),
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
                # Phase-D context harness. Present BEFORE the harness is wired
                # (its flag is still false) so the future wiring cannot replay a
                # pre-harness answer from the 24 h exact cache: flipping any of
                # these re-keys the cache instead of serving stale policy.
                "context_harness": str(bool(settings.first_person_context_harness_enabled)),
                # The collection the harness reads IS answer-shaping: pointing
                # it at a different fp-context corpus changes which spans can
                # be served. Without it in the digest, a repointed collection
                # would replay the previous collection's answer from the exact
                # cache for the full TTL.
                "context_collection": str(
                    str(getattr(settings, "first_person_context_collection", "") or "").strip()
                ),
                "context_max_spans": str(int(settings.first_person_context_max_spans)),
                "context_selector": str(bool(settings.first_person_context_selector_enabled)),
                "context_schema": (
                    f"{_FP_CONTEXT_SCHEMA_VERSION}/{_FP_PARENT_VERSION}/{_FP_EDGE_VERSION}"
                ),
                # B4: the legacy collection's own contract. A repointed
                # collection, a schema change, a corpus-version change or an
                # evidence-policy change all change what may be served, so all
                # four ride in the fingerprint.
                "legacy_collection": contract.get("collection", ""),
                "legacy_schema": contract.get("schema", ""),
                "legacy_corpus_version": contract.get("corpus_version", ""),
                "evidence_policy": contract.get("evidence_policy", ""),
                "violence_safety_policy": "v2",
            }.items()
        )
        return dict(pairs)

    def _collection_contract_components(self) -> dict[str, str]:
        """The declared contract of the collection this pipeline reads."""
        cached = getattr(self, "_collection_contract_cache", None)
        if cached is not None:
            return cached
        components = {"collection": "", "schema": "", "corpus_version": "", "evidence_policy": ""}
        try:
            from services.first_person_serving_contract import (
                fingerprint_components,
                load_contract_cached,
            )

            collection = str(getattr(self._store, "collection", "") or "")
            components = fingerprint_components(
                load_contract_cached(
                    str(getattr(settings, "first_person_serving_contract_path", "") or "") or None
                ).get(collection)
            )
            components["collection"] = collection
        except Exception as exc:  # noqa: BLE001 - a broken contract fails closed
            logger.error("[FirstPersonPipeline] serving contract unreadable: %s", exc)
        self._collection_contract_cache = components
        return components

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

    def _points_servable_cached(self, point_ids: list[str], *, fp_context: bool = False) -> bool:
        """Cache points_servable results for 300s to avoid synchronous Qdrant blasts on exact cache hits.

        ``fp_context`` selects the fp-context-v1 check: the legacy clip store
        keys on ``first_person_eligible``, a field the context schema does not
        carry, so a harness citation would otherwise be treated as unservable
        and the exact cache would never serve it.
        """
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
            if fp_context:
                context_store = self._get_context_store()
                if context_store is None:
                    return False
                is_servable = bool(context_store.points_servable(uncached))
            else:
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
        retrieval_query: str = "",
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
                # Citation-free teaching cannot be source-verified. Empty citations are
                # valid only for explicit abstentions or crisis redirects.
                if not data["citations"] and data.get("status") not in {
                    "abstained",
                    "crisis_redirect",
                }:
                    logger.warning(
                        "[FirstPersonPipeline] Citation-free cached teaching rejected; skipping cache."
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
                    if _violent_for_context(
                        query, str(cit.get("verbatim_text") or ""), retrieval_query=retrieval_query
                    ):
                        logger.warning(
                            "[FirstPersonPipeline] Cached citation failed violence-for-context re-check; skipping cache."
                        )
                        return None
                # The index can change under a 24 h entry (clip deleted, rights
                # revoked): serve only if every cited point is still servable.
                point_ids = [
                    cit.get("point_id") for cit in data.get("citations", []) if cit.get("point_id")
                ]
                # A harness citation carries a source_span_id; a legacy clip
                # citation does not. They live in different schemas and are
                # re-checked with the matching store.
                context_ids = [
                    cit.get("point_id")
                    for cit in data.get("citations", [])
                    if cit.get("point_id") and cit.get("source_span_id")
                ]
                legacy_ids = [
                    cit.get("point_id")
                    for cit in data.get("citations", [])
                    if cit.get("point_id") and not cit.get("source_span_id")
                ]
                if data.get("citations") and (
                    not point_ids
                    or not self._points_servable_cached(legacy_ids)
                    or not self._points_servable_cached(context_ids, fp_context=True)
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
            if not isinstance(data, dict) or not isinstance(data.get("citations"), list):
                logger.warning("[FirstPersonPipeline] Refusing to cache malformed result.")
                return
            if not data["citations"] and data.get("status") not in {
                "abstained",
                "crisis_redirect",
            }:
                logger.warning(
                    "[FirstPersonPipeline] Refusing to cache citation-free teaching result."
                )
                return
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

        # Step 1c: Serving-contract gate (B4). The legacy clip store and the
        # fp-context store must not share a collection, and neither may point at
        # a collection whose payload schema it cannot read. When the contract
        # is violated this path serves NOTHING (fail closed) instead of reading
        # context records through a legacy filter. It sits AFTER the crisis and
        # topic rails on purpose: a crisis query must still get the helplines
        # even when the first-person corpus is mis-configured.
        contract_error = self._serving_contract_error()
        if contract_error:
            logger.error(
                "[FirstPersonPipeline] Serving contract violated; serving nothing: %s",
                contract_error,
            )
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count("abstained", latency, 0.0, 0, 0, "serving_contract_violation", 0)
            return FirstPersonPipelineResult(
                answer_text=(
                    "First-person verbatim teaching is temporarily unavailable while its "
                    "serving contract is being repaired. No clip is served."
                ),
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="serving_contract_violation",
                error="serving_contract_violation",
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
                retrieval_query=retrieval_query,
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

        # Step 2b: Compound question decomposition (Tasks F1 & F2)
        if getattr(settings, "first_person_facet_split_enabled", False):
            facets = _decompose_query_facets(query, self._llm_service, token_sink=fp_llm_tokens)
            if len(facets) > 1:
                return self._execute_compound(
                    query=query,
                    facets=facets,
                    query_dense_vector=query_dense_vector,
                    query_sparse_vector=query_sparse_vector,
                    teacher_id=teacher_id,
                    max_clips=max_clips,
                    start_time=start_time,
                    cache_bypass=cache_bypass,
                    request_allow_state=request_allow_state,
                    request_block_state=request_block_state,
                    fp_llm_tokens=fp_llm_tokens,
                    language=language,
                    retrieval_query=retrieval_query,
                )

        _ans_box: dict[str, Any] = {}
        _ans_tokens: list[int] = []
        _ans_future: Optional[Any] = None
        t_retrieval_ms = 0.0
        t_integrity_ms = 0.0
        t_rerank_ms = 0.0
        t_scorer_ms = 0.0
        t_assembly_ms = 0.0

        # Step 2c: First-Person Context Harness (fp-context-v1)
        # When enabled and configured, retrieve parent contexts via FirstPersonContextStore
        # and evaluate through FirstPersonContextHarness. If a context qualifies for direct
        # serving (serve_single_span or serve_parent_context), construct the result
        # deterministically from stored spans.
        # Otherwise, fall back gracefully to the existing first-person logic.
        harness_enabled = bool(
            getattr(settings, "first_person_context_harness_enabled", False)
        ) or (self._context_store is not None)
        ctx_store = self._get_context_store() if harness_enabled else None
        if ctx_store is not None and query_dense_vector:
            t_ctx_start = time.monotonic()
            contexts: list[ParentContext] = []
            try:
                max_spans = min(
                    int(getattr(settings, "first_person_context_max_spans", 3)),
                    self._get_context_harness()._policy.max_context_spans,
                )
                contexts = ctx_store.retrieve(
                    query_dense=query_dense_vector,
                    query_sparse=query_sparse_vector,
                    guru_id=teacher_id,
                    limit_parents=max_clips,
                    spans_per_parent=max_spans,
                )
            except Exception as exc:
                logger.warning(
                    "[FirstPersonPipeline] Context store retrieval failed: %s; falling back to legacy",
                    exc,
                )
                contexts = []
            t_ctx_ret_ms = (time.monotonic() - t_ctx_start) * 1000.0

            if contexts:
                t_ans_start = time.monotonic()
                if bool(getattr(settings, "first_person_answerability_check_enabled", False)):
                    ans_verdict = _answerability_check(
                        query,
                        self._llm_service,
                        request_loop=self._llm_loop,
                        token_sink=fp_llm_tokens,
                    )
                    ans_str = {True: "yes", False: "no"}.get(ans_verdict, "indeterminate")
                else:
                    ans_verdict = True
                    ans_str = "yes"
                t_ans_ms = (time.monotonic() - t_ans_start) * 1000.0
                _ans_box["verdict"] = ans_verdict
                _ans_box["duration_ms"] = t_ans_ms

                harness = self._get_context_harness()
                # Serve-time quality files are read ONCE per request, exactly as
                # the legacy path does, so the two paths cannot disagree about
                # which clips are approved/quarantined within one request.
                _harness_allow = _quality_allowlist()
                _harness_blocked = _quality_blocklist()
                _harness_blocklist_configured = bool(
                    str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip()
                )
                for ctx in contexts:
                    selected_span_ids = None
                    if bool(getattr(settings, "first_person_context_selector_enabled", False)):
                        from services.first_person_context_selector import select_span_ids

                        selected_span_ids = select_span_ids(
                            query, ctx.spans, llm_service=self._llm_service
                        )

                    decision = harness.decide(
                        ctx,
                        requested_teacher=teacher_id,
                        answerability=ans_str,
                        selected_span_ids=selected_span_ids,
                    )

                    if decision.decision in (
                        HarnessDecision.SERVE_SINGLE_SPAN,
                        HarnessDecision.SERVE_PARENT_CONTEXT,
                    ):
                        t_asm_start = time.monotonic()
                        span_by_id = {s.source_span_id: s for s in ctx.spans}
                        served_spans = [
                            span_by_id[sid] for sid in decision.source_span_ids if sid in span_by_id
                        ]
                        # A decision naming span IDs this parent does not hold is a
                        # harness contract failure. Substituting ctx.spans here (the
                        # previous behaviour) served citations that did not match the
                        # decision, so fail toward the legacy path instead.
                        if len(served_spans) != len(decision.source_span_ids):
                            logger.warning(
                                "[FirstPersonPipeline] Context harness decision for parent %s cited %d unknown span id(s); treating as contract failure and skipping this context",
                                getattr(getattr(ctx, "parent", None), "parent_unit_id", "unknown"),
                                len(decision.source_span_ids) - len(served_spans),
                            )
                            continue
                        if not served_spans:
                            logger.warning(
                                "[FirstPersonPipeline] Context harness decision for parent %s served no spans; skipping this context",
                                getattr(getattr(ctx, "parent", None), "parent_unit_id", "unknown"),
                            )
                            continue

                        citations = []
                        audio_playback_clips = []
                        cite_by_id = {c.source_span_id: c for c in decision.citations}
                        confidence = float(getattr(ctx, "score", 1.0) or 1.0)
                        _span_failed_gate = False
                        for span in served_spans:
                            c_span = cite_by_id.get(span.source_span_id)
                            cit_dict = self._build_context_citation(
                                span, c_span, confidence=confidence
                            )
                            # The harness guarantees provenance gates, not the
                            # legacy serve-time gates (hash, allowed speaker,
                            # artifacts, promise/boundary defects, thin or
                            # live-event text, quality allow/block lists). Run
                            # them on the same cache-shaped dict the legacy path
                            # uses so both paths agree on what may be served.
                            if not _passes_integrity_gate(
                                cit_dict, boundary_guard_enabled=self._boundary_guard_enabled
                            ) or not _passes_content_quality_gate(
                                cit_dict, gate_enabled=self._content_quality_gate_enabled
                            ):
                                _span_failed_gate = True
                                break
                            if _violent_for_context(
                                query,
                                str(cit_dict.get("verbatim_text") or ""),
                                retrieval_query=retrieval_query,
                            ):
                                logger.info(
                                    "[FirstPersonPipeline] Harness span rejected: violence wording for a relationship question"
                                )
                                _span_failed_gate = True
                                break
                            point_id = str(cit_dict.get("point_id") or "")
                            if _harness_allow is not None and point_id not in _harness_allow:
                                _span_failed_gate = True
                                break
                            # Quarantine wins over approval; a configured but
                            # unreadable blocklist serves nothing (fail closed).
                            if _harness_blocked is not None:
                                if point_id in _harness_blocked:
                                    _span_failed_gate = True
                                    break
                                # The operator's blocklist is keyed by legacy
                                # clip ids. A harness span carries a different
                                # id scheme, so "not on the blocklist" is NOT
                                # evidence that this clip is clear. Fail closed:
                                # with a blocklist configured, only an id that
                                # an allowlist explicitly approves may be served.
                                if _harness_allow is None:
                                    logger.warning(
                                        "[FirstPersonPipeline] Context harness span %s cannot be matched against the configured quality blocklist; failing closed",
                                        point_id,
                                    )
                                    _span_failed_gate = True
                                    break
                            elif _harness_blocklist_configured:
                                _span_failed_gate = True
                                break
                            citations.append(cit_dict)
                            audio_playback_clips.append(
                                {
                                    "video_id": span.video_id,
                                    "url": span.source_url or cit_dict["url"],
                                    "speaker": cit_dict["speaker"],
                                    "start_sec": cit_dict["start_sec"],
                                    "end_sec": cit_dict["end_sec"],
                                    "duration_sec": cit_dict["end_sec"] - cit_dict["start_sec"],
                                    "title": cit_dict["title"],
                                }
                            )
                        if _span_failed_gate:
                            # Partial serving would desynchronise the harness's
                            # reconstructed answer_text from its citations, so a
                            # single failed span sends the whole context to the
                            # legacy path instead of a misaligned answer.
                            FIRST_PERSON_QUARANTINED_TOTAL.inc()
                            logger.warning(
                                "[FirstPersonPipeline] Context harness span failed a serve-time gate for parent %s; falling back to legacy",
                                getattr(getattr(ctx, "parent", None), "parent_unit_id", "unknown"),
                            )
                            continue

                        t_assembly_ms = (time.monotonic() - t_asm_start) * 1000.0
                        latency = (time.monotonic() - start_time) * 1000.0
                        # The harness has no calibrated threshold of its own;
                        # mirror the legacy directness rule so an uncalibrated
                        # or low-confidence context is served as "related",
                        # never as a direct answer. The STATUS must follow the
                        # same rule: a non-direct answer is a "weak_match",
                        # because the bridge only serves a "success" answer
                        # when is_direct_answer is true. Labelling it
                        # "success" while is_direct_answer is false made the
                        # bridge discard every harness answer and replace it
                        # with a static abstention.
                        is_direct = (
                            self._profile is not None and confidence >= self._profile["threshold"]
                        )

                        stage_timings = {
                            "answerability_ms": round(float(t_ans_ms), 2),
                            "retrieval_ms": round(float(t_ctx_ret_ms), 2),
                            "integrity_ms": 0.0,
                            "rerank_ms": 0.0,
                            "scorer_ms": 0.0,
                            "assembly_ms": round(float(t_assembly_ms), 2),
                            "total_ms": round(latency, 2),
                        }

                        res = FirstPersonPipelineResult(
                            answer_text=decision.answer_text or "",
                            citations=citations,
                            status="success" if is_direct else "weak_match",
                            is_direct_answer=is_direct,
                            latency_ms=latency,
                            answerability=ans_str,
                            abstain_reason="none",
                            audio_playback_clip=(
                                audio_playback_clips[0] if audio_playback_clips else None
                            ),
                            audio_playback_clips=audio_playback_clips,
                            stage_timings=stage_timings,
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

                        self._log_and_count(
                            res.status,
                            latency,
                            float(getattr(ctx, "score", 1.0) or 1.0),
                            0,
                            len(citations),
                            "none",
                            sum(fp_llm_tokens),
                        )
                        return res

                logger.info(
                    "[FirstPersonPipeline] Context harness evaluated %d contexts with no direct answer; falling back to legacy",
                    len(contexts),
                )

        # RC-D-2: start the question-only answerability gate in parallel with
        # retrieval. Crisis (Step 1), the topic rail, and the exact cache are
        # already past, so a redirect / blocked topic / cache hit never spends
        # this LLM call. The worker owns the single _answerability_check call;
        # the join sits before any rerank/scorer work so a firm NO skips both.
        # Capacity: the worker runs on the bounded _answerability_executor
        # (one slot per concurrent query, never a separate pool), joined at
        # the retrieval rendezvous with a bounded timeout.
        # Token accounting: the worker appends to its own _ans_tokens list;
        # the request's fp_llm_tokens is extended on the serving thread only
        # AFTER the future completes, so sum(fp_llm_tokens) never races a
        # cross-thread append. A timed-out worker's tokens are dropped, not
        # guessed.
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

        spec_val = getattr(settings, "first_person_speculative_parallelism_enabled", False)
        ans_val = getattr(settings, "first_person_answerability_check_enabled", False)

        def is_mock(v):
            return type(v).__name__.endswith("Mock")

        speculative_enabled = (
            spec_val is True or str(spec_val).lower() in ("true", "1")
        ) and not is_mock(spec_val)
        ans_enabled = (ans_val is True or str(ans_val).lower() in ("true", "1")) and not is_mock(
            ans_val
        )

        if speculative_enabled and ans_enabled:
            # Speculative Parallelism (Track 1):
            # Run Answerability Gate and Vector Retrieval (39ms) concurrently at t=0 using asyncio.gather.
            async def _speculative_gather():
                async def _task_ans():
                    ans_start = time.monotonic()
                    try:
                        verdict = await _async_answerability_check(
                            query,
                            self._llm_service,
                            token_sink=_ans_tokens,
                        )
                        _ans_box["verdict"] = verdict
                    except Exception as exc:
                        logger.info(
                            "[FirstPersonPipeline] Speculative answerability error: %s", exc
                        )
                        _ans_box["verdict"] = None
                    finally:
                        _ans_box["duration_ms"] = (time.monotonic() - ans_start) * 1000.0
                    return _ans_box.get("verdict")

                async def _task_ret():
                    ret_start = time.monotonic()
                    try:
                        import asyncio

                        loop = asyncio.get_running_loop()
                        try:
                            res = await loop.run_in_executor(None, _search)
                        except Exception as first_error:
                            if not _is_transient_connection_error(first_error):
                                raise
                            logger.warning(
                                "[FirstPersonPipeline] Transient retrieval error, retrying once: %s",
                                first_error,
                            )
                            res = await loop.run_in_executor(None, _search)
                        return res
                    except Exception as exc:
                        logger.error("[FirstPersonPipeline] Speculative retrieval error: %s", exc)
                        raise
                    finally:
                        _ans_box["retrieval_duration_ms"] = (time.monotonic() - ret_start) * 1000.0

                import asyncio

                return await asyncio.gather(_task_ans(), _task_ret(), return_exceptions=True)

            try:
                ans_res, ret_res = run_llm_coroutine(
                    _speculative_gather,
                    timeout_s=_ANSWERABILITY_TIMEOUT_S + 2.0,
                    request_loop=self._llm_loop,
                )
                fp_llm_tokens.extend(_ans_tokens)
            except Exception as exc:
                logger.warning("[FirstPersonPipeline] Speculative gather failed: %s", exc)
                ans_res = None
                ret_res = exc

            t_retrieval_ms = float(_ans_box.get("retrieval_duration_ms", 0.0))
            early_verdict = ans_res if isinstance(ans_res, (bool, type(None))) else None

            # If Answerability Gate returns 'no' or indeterminate:
            # immediately discard retrieval candidates and return honest abstention without calling reranker or scorer.
            if early_verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                is_no = early_verdict is False
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
                    0,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                logger.info(
                    "[FirstPersonPipeline] Speculative answerability %s; "
                    "discarded retrieval candidates, skipped rerank/scorer",
                    "NO" if is_no else "indeterminate",
                )
                return FirstPersonPipelineResult(
                    answer_text="No verified first-person discourse found for this question.",
                    citations=[],
                    status="abstained",
                    is_direct_answer=False,
                    latency_ms=latency,
                    answerability="no" if is_no else "indeterminate",
                    abstain_reason="answerability_withheld",
                    stage_timings=stage_timings,
                )

            # If Answerability Gate returns 'yes', candidates are already pre-fetched in memory
            if isinstance(ret_res, Exception):
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count("error", latency, 0.0, 0, 0, "none", sum(fp_llm_tokens))
                return FirstPersonPipelineResult(
                    answer_text="An error occurred while retrieving first-person teachings.",
                    citations=[],
                    status="error",
                    is_direct_answer=False,
                    latency_ms=latency,
                    error=str(ret_res),
                    abstain_reason="none",
                    stage_timings=stage_timings,
                )
            raw_clips = ret_res
        else:
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and _ans_box.get("verdict") is None
            ):

                def _run_answerability() -> None:
                    ans_start = time.monotonic()
                    try:
                        _ans_box["verdict"] = _answerability_check(
                            query,
                            self._llm_service,
                            request_loop=self._llm_loop,
                            token_sink=_ans_tokens,
                        )
                    except Exception as e:
                        logger.info("[FirstPersonPipeline] Answerability background error: %s", e)
                        _ans_box["verdict"] = None
                    finally:
                        _ans_box["duration_ms"] = (time.monotonic() - ans_start) * 1000.0

                _ans_future = _answerability_executor().submit(_run_answerability)

            t_ret_start = time.monotonic()
            try:
                try:
                    raw_clips = _search()
                except Exception as first_error:
                    if not _is_transient_connection_error(first_error):
                        raise
                    logger.warning(
                        "[FirstPersonPipeline] Transient retrieval error, retrying once: %s",
                        first_error,
                    )
                    raw_clips = _search()
            except Exception as e:
                t_retrieval_ms = (time.monotonic() - t_ret_start) * 1000.0
                logger.error(f"[FirstPersonPipeline] Hybrid retrieval failed: {e}")
                if _ans_future is not None:
                    try:
                        _ans_future.result(timeout=_ANSWERABILITY_TIMEOUT_S)
                        fp_llm_tokens.extend(_ans_tokens)
                    except TimeoutError:
                        logger.info(
                            "[FirstPersonPipeline] Answerability worker still running "
                            "after retrieval error; its tokens are dropped"
                        )
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count("error", latency, 0.0, 0, 0, "none", sum(fp_llm_tokens))
                return FirstPersonPipelineResult(
                    answer_text="An error occurred while retrieving first-person teachings.",
                    citations=[],
                    status="error",
                    is_direct_answer=False,
                    latency_ms=latency,
                    error=str(e),
                    abstain_reason="none",
                    stage_timings=stage_timings,
                )
            t_retrieval_ms = (time.monotonic() - t_ret_start) * 1000.0

        # Step 4: Serve-time Integrity Gate
        t_int_start = time.monotonic()
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
        verified_clips = [
            c
            for c in verified_clips
            if not _violent_for_context(
                query, str(c.get("verbatim_text") or ""), retrieval_query=retrieval_query
            )
        ]
        t_integrity_ms = (time.monotonic() - t_int_start) * 1000.0

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
        if not speculative_enabled:
            early_verdict = _ans_box.get("verdict")
            if _ans_future is not None:
                # Bounded join: a hung gate worker must never stall serving. A
                # timeout leaves early_verdict None = indeterminate, the same
                # fail-toward-abstention path as a gate timeout below. Tokens
                # merge only after the future completes, so every sum() below
                # reads a serving-thread-only list.
                try:
                    _ans_future.result(timeout=_ANSWERABILITY_TIMEOUT_S)
                    fp_llm_tokens.extend(_ans_tokens)
                    early_verdict = _ans_box.get("verdict")
                except TimeoutError:
                    logger.info(
                        "[FirstPersonPipeline] Answerability join timed out; "
                        "continuing as indeterminate"
                    )
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and early_verdict is not True
                and verified_clips
                and (_ans_future is not None or _ans_box.get("verdict") is not None)
            ):
                # Anything other than a firm YES skips rerank/scorer: a NO verdict
                # and an indeterminate (timed-out/failed gate worker) both end in
                # abstention, so spending two more LLM calls cannot change the
                # outcome. Label honestly: "no" for a firm NO, "indeterminate"
                # otherwise (the Step 6 gate below agrees on both).
                _is_firm_no = early_verdict is False
                try:
                    early_confidence = (
                        _cosine_similarity(
                            query_dense_vector, verified_clips[0].get("passage_dense")
                        )
                        if query_dense_vector
                        else 0.0
                    )
                except Exception:  # noqa: BLE001 - logging confidence must not break serving
                    early_confidence = 0.0
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
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
                    stage_timings=stage_timings,
                )

        # Step 4b: optional cross-encoder reorder of the verified candidates. Reorders
        # only; confidence below stays dense cosine (the calibration contract).
        t_rerank_start = time.monotonic()
        if self._rerank_fn and len(verified_clips) >= (1 if speculative_enabled else 2):
            try:
                scores = self._rerank_fn(
                    retrieval_query, [c["verbatim_text"] for c in verified_clips]
                )
                if speculative_enabled:
                    min_rerank_score = float(
                        getattr(settings, "first_person_cross_encoder_min_score", 0.30)
                    )
                    pairs = [
                        (verified_clips[i], scores[i])
                        for i in range(len(verified_clips))
                        if scores[i] >= min_rerank_score
                    ]
                    if not pairs:
                        pairs = [(verified_clips[i], scores[i]) for i in range(len(verified_clips))]
                    pairs.sort(key=lambda p: p[1], reverse=True)
                    verified_clips = [p[0] for p in pairs]
                else:
                    order = sorted(
                        range(len(verified_clips)), key=lambda i: scores[i], reverse=True
                    )
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
            rerank_res = _llm_rerank_clips(
                retrieval_query,
                verified_clips[:8],
                self._llm_service,
                token_sink=fp_llm_tokens,
            )
            if not rerank_res and getattr(
                settings, "first_person_rerank_none_abstain_enabled", False
            ):
                # E6c early abstention: model indicated NONE of the top candidate clips relate/answer
                t_rerank_ms = (time.monotonic() - t_rerank_start) * 1000.0
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                logger.info(
                    "[FirstPersonPipeline] Reranker returned NONE; early abstaining without scorer."
                )
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
                    n_quarantined,
                    0,
                    "relevance_below_min",
                    sum(fp_llm_tokens),
                )
                return FirstPersonPipelineResult(
                    answer_text="No verified first-person discourse found for this question.",
                    citations=[],
                    status="abstained",
                    is_direct_answer=False,
                    latency_ms=latency,
                    abstain_reason="relevance_below_min",
                    stage_timings=stage_timings,
                )
            # An empty reply is the reranker's NONE verdict. With the early-abstain flag
            # off it must NOT drop the candidates it was shown (rerank_res + [8:] would
            # silently discard the top 8); keep their retrieval order instead.
            verified_clips = (rerank_res or verified_clips[:8]) + verified_clips[8:]

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
        t_rerank_ms = (time.monotonic() - t_rerank_start) * 1000.0

        # Step 5: Abstention check if zero verified clips
        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings = {
                "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                "retrieval_ms": round(t_retrieval_ms, 2),
                "integrity_ms": round(t_integrity_ms, 2),
                "rerank_ms": round(t_rerank_ms, 2),
                "scorer_ms": 0.0,
                "assembly_ms": 0.0,
                "total_ms": round(latency, 2),
            }
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
                stage_timings=stage_timings,
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
        t_scorer_start = time.monotonic()
        second_clip: Optional[dict[str, Any]] = None
        second_score = 0.0
        if getattr(settings, "first_person_relevance_gate_enabled", True):
            candidates = verified_clips[:3]
            rel_scores: list[int] = []
            if speculative_enabled and candidates:
                min_rel = int(getattr(settings, "first_person_relevance_min_score", 3))
                # Cascade Reranker-to-Scorer Filtering (Track 1):
                # Only score candidate #1 first. If candidate #1 passes with score >= min_rel,
                # serve it immediately. Only evaluate candidate #2 on tie/rejection.
                scores_c1: list[int] = []
                pick_c1 = _relevance_select(
                    retrieval_query or query,
                    [candidates[0]],
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=scores_c1,
                )
                if pick_c1 == 0 and scores_c1 and scores_c1[0] >= min_rel:
                    pick = 0
                    rel_scores = scores_c1
                elif pick_c1 == _RELEVANCE_INDETERMINATE:
                    pick = _RELEVANCE_INDETERMINATE
                    rel_scores = []
                elif len(candidates) > 1:
                    scores_c2: list[int] = []
                    pick_c2 = _relevance_select(
                        retrieval_query or query,
                        [candidates[1]],
                        self._llm_service,
                        self._llm_loop,
                        token_sink=fp_llm_tokens,
                        scores_out=scores_c2,
                    )
                    if pick_c2 == 0 and scores_c2 and scores_c2[0] >= min_rel:
                        pick = 1
                        rel_scores = [scores_c1[0] if scores_c1 else 0, scores_c2[0]]
                    elif pick_c2 == _RELEVANCE_INDETERMINATE:
                        pick = _RELEVANCE_INDETERMINATE
                        rel_scores = []
                    else:
                        pick = None
                        rel_scores = [
                            scores_c1[0] if scores_c1 else 0,
                            scores_c2[0] if scores_c2 else 0,
                        ]
                else:
                    pick = None
                    rel_scores = scores_c1
            else:
                pick = _relevance_select(
                    retrieval_query or query,
                    candidates,
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=rel_scores,
                )
            if pick is None or pick == _RELEVANCE_INDETERMINATE:
                t_scorer_ms = (time.monotonic() - t_scorer_start) * 1000.0
                latency = (time.monotonic() - start_time) * 1000.0
                abstain_answerability = (
                    "relevance_indeterminate" if pick is not None else "relevance_below_min"
                )
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": round(t_scorer_ms, 2),
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
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
                    stage_timings=stage_timings,
                    # A25: the candidates are integrity-verified; they simply did
                    # not reach the relevance minimum, so they are offered as
                    # explicitly related, not-answer clips (flag-gated). Indeterminate
                    # is a scorer failure, not a below-min verdict — offer nothing there.
                    related_clips=(
                        _related_clips_for(verified_clips, clip_scores) if pick is None else []
                    ),
                )
            if getattr(settings, "first_person_second_quote_enabled", False) and len(
                rel_scores
            ) == len(candidates):
                minimum = int(getattr(settings, "first_person_relevance_min_score", 3))
                others = [
                    i
                    for i in range(len(candidates))
                    if i != pick
                    and rel_scores[i] >= minimum
                    and candidates[i].get("video_id") != candidates[pick].get("video_id")
                ]
                if others:
                    best_other = max(others, key=lambda i: (rel_scores[i], -i))
                    second_clip, second_score = candidates[best_other], clip_scores[best_other]
            if pick != 0:
                verified_clips = [verified_clips[pick]] + [
                    c for i, c in enumerate(verified_clips) if i != pick
                ]
                clip_scores = [clip_scores[pick]] + [
                    s for i, s in enumerate(clip_scores) if i != pick
                ]
        t_scorer_ms = (time.monotonic() - t_scorer_start) * 1000.0

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
            # call only if the flag flipped on mid-request (no future started).
            if _ans_future is not None or speculative_enabled or early_verdict is not None:
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
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": round(t_scorer_ms, 2),
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
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
                    stage_timings=stage_timings,
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
            stage_timings = {
                "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                "retrieval_ms": round(t_retrieval_ms, 2),
                "integrity_ms": round(t_integrity_ms, 2),
                "rerank_ms": round(t_rerank_ms, 2),
                "scorer_ms": round(t_scorer_ms, 2),
                "assembly_ms": 0.0,
                "total_ms": round(latency, 2),
            }
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
                stage_timings=stage_timings,
            )

        t_asm_start = time.monotonic()
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
            if getattr(settings, "first_person_continuous_layout_enabled", False):
                from services.quote_weaver import (
                    _format_continuous_quote_block,
                    _format_continuous_sources_footer,
                )

                top_clip_with_hero = {**top_clip, "_hero": hero}
                quote_block = _format_continuous_quote_block(top_clip_with_hero)
                footer = _format_continuous_sources_footer([top_clip_with_hero])
                final_text = f"{quote_block}\n\nRelated, not a direct answer" + (
                    f"\n{footer}" if footer else ""
                )
            else:
                final_text = (
                    f'Related, not a direct answer:\n\n"{top_clip["verbatim_text"]}"\n'
                    f"— {hero['label']} ({top_clip['video_id']}, {cit['timestamp_seconds']}s)"
                )
            atma_vichara_inquiry = None
            practice_recommendation = None
            audio_playback_clip = audio_strip_for(top_clip, hero)
            audio_playback_clips = [audio_playback_clip] if audio_playback_clip else []
            # Optional second quote: a separate recording that also answers, quoted exactly and
            # labelled as a different video that does not continue the first. Never merged text.
            # .get() reads throughout: a damaged point missing verbatim_text /
            # video_id / timing keys must drop the second quote (single-quote
            # path stands), never raise KeyError into a 500.
            second_hero = (
                verify_hero_clip(second_clip, sources) if second_clip is not None else None
            )
            second_text = (
                second_clip.get("verbatim_text") if isinstance(second_clip, dict) else None
            )
            second_vid = second_clip.get("video_id") if isinstance(second_clip, dict) else None
            top_text = top_clip.get("verbatim_text") if isinstance(top_clip, dict) else None
            top_vid = top_clip.get("video_id") if isinstance(top_clip, dict) else None
            if (
                second_clip is not None
                and second_hero is not None
                and second_text
                and second_vid
                and top_text
                and top_vid
                and is_youtube_video_available(str(second_vid))
            ):
                try:
                    cit2 = _build_citation(second_clip, second_score, "weak_match_fallback")
                except (KeyError, TypeError) as exc:
                    logger.warning(
                        "[FirstPersonPipeline] Second quote dropped (damaged point %s): %s",
                        second_clip.get("point_id"),
                        exc,
                    )
                    cit2 = None
                if cit2 is not None:
                    citations.append(cit2)
                    if getattr(settings, "first_person_continuous_layout_enabled", False):
                        from services.quote_weaver import (
                            _format_continuous_quote_block,
                            _format_continuous_sources_footer,
                        )

                        c1_with_hero = {**top_clip, "_hero": hero}
                        c2_with_hero = {**second_clip, "_hero": second_hero}
                        qb1 = _format_continuous_quote_block(c1_with_hero, facet="first recording")
                        qb2 = _format_continuous_quote_block(c2_with_hero, facet="second recording")
                        footer = _format_continuous_sources_footer([c1_with_hero, c2_with_hero])
                        final_text = f"{qb1}\n\n{qb2}\n\nRelated, not a direct answer" + (
                            f"\n{footer}" if footer else ""
                        )
                    else:
                        final_text = (
                            "Related, not a direct answer. Two separate recordings, each quoted exactly:\n\n"
                            f'Recording 1 of 2:\n"{top_text}"\n'
                            f"— {hero['label']} ({top_vid}, {cit['timestamp_seconds']}s)\n\n"
                            "Recording 2 of 2 (a different video; it does not continue the first):\n"
                            f'"{second_text}"\n'
                            f"— {second_hero['label']} ({second_vid}, {cit2['timestamp_seconds']}s)"
                        )
                    strip2 = audio_strip_for(second_clip, second_hero)
                    if strip2:
                        audio_playback_clips.append(strip2)

        detected_concepts: list[str] = []
        seen_concepts = set()
        if okf_entries:
            for e in okf_entries:
                t = e.get("title")
                if t and t.lower() not in seen_concepts:
                    seen_concepts.add(t.lower())
                    detected_concepts.append(t)
        # _CANONICAL_CONCEPTS is module-level (A25) so the abstain related-clip
        # topic list reuses the exact same vocabulary.
        q_lower = query.lower()
        clip_text = (top_clip.get("verbatim_text") or "").lower() if top_clip else ""
        for c in _CANONICAL_CONCEPTS:
            if c.lower() in q_lower or c.lower() in clip_text:
                if c.lower() not in seen_concepts:
                    seen_concepts.add(c.lower())
                    detected_concepts.append(c)
            if len(detected_concepts) >= 4:
                break

        t_assembly_ms = (time.monotonic() - t_asm_start) * 1000.0

        stage_timings = {
            "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
            "retrieval_ms": round(t_retrieval_ms, 2),
            "integrity_ms": round(t_integrity_ms, 2),
            "rerank_ms": round(t_rerank_ms, 2),
            "scorer_ms": round(t_scorer_ms, 2),
            "assembly_ms": round(t_assembly_ms, 2),
            "total_ms": round((time.monotonic() - start_time) * 1000.0, 2),
        }

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
            stage_timings=stage_timings,
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
        res.stage_timings["total_ms"] = round(res.latency_ms, 2)
        logger.info(
            "[FirstPersonPipeline] Stage timings: ans=%.1fms, ret=%.1fms, int=%.1fms, rerank=%.1fms, scorer=%.1fms, asm=%.1fms, total=%.1fms",
            res.stage_timings["answerability_ms"],
            res.stage_timings["retrieval_ms"],
            res.stage_timings["integrity_ms"],
            res.stage_timings["rerank_ms"],
            res.stage_timings["scorer_ms"],
            res.stage_timings["assembly_ms"],
            res.stage_timings["total_ms"],
        )
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

    def _execute_compound(
        self,
        query: str,
        facets: list[str],
        query_dense_vector: Optional[list[float]],
        query_sparse_vector: Optional[dict[str, list[float]]],
        teacher_id: Optional[str],
        max_clips: int,
        start_time: float,
        cache_bypass: bool,
        request_allow_state: str,
        request_block_state: str,
        fp_llm_tokens: list[int],
        language: str = "en",
        retrieval_query: str = "",
    ) -> FirstPersonPipelineResult:
        """Execute per-part retrieval, gating and continuous layout assembly for compound questions (Tasks F1 & F2)."""
        stage_timings: dict[str, float] = {
            "answerability_ms": 0.0,
            "retrieval_ms": 0.0,
            "integrity_ms": 0.0,
            "rerank_ms": 0.0,
            "scorer_ms": 0.0,
            "assembly_ms": 0.0,
            "total_ms": 0.0,
        }
        t_ret_start = time.monotonic()
        try:
            raw_clips = self._store.search_hybrid(
                query_dense_vector=query_dense_vector,
                query_sparse_vector=query_sparse_vector,
                teacher_id=teacher_id,
                limit=max(80, max_clips * 16),
                dedup_limit=max(40, max_clips * 8),
            )
        except Exception as e:
            logger.error(f"[FirstPersonPipeline] Compound retrieval failed: {e}")
            stage_timings["retrieval_ms"] = round((time.monotonic() - t_ret_start) * 1000.0, 2)
            stage_timings["total_ms"] = round((time.monotonic() - start_time) * 1000.0, 2)
            return FirstPersonPipelineResult(
                answer_text="An error occurred while retrieving first-person teachings.",
                citations=[],
                status="error",
                is_direct_answer=False,
                latency_ms=stage_timings["total_ms"],
                error=str(e),
                abstain_reason="none",
                stage_timings=stage_timings,
            )
        stage_timings["retrieval_ms"] = round((time.monotonic() - t_ret_start) * 1000.0, 2)

        # Integrity Gate
        t_int_start = time.monotonic()
        verified_clips: list[dict[str, Any]] = []
        n_quarantined = 0
        for clip in raw_clips:
            if _passes_integrity_gate(clip, boundary_guard_enabled=self._boundary_guard_enabled):
                if _passes_content_quality_gate(
                    clip, gate_enabled=self._content_quality_gate_enabled
                ):
                    verified_clips.append(clip)
                else:
                    n_quarantined += 1
            else:
                n_quarantined += 1

        if teacher_id and teacher_id.strip().lower() not in ("both", "all", ""):
            _want = teacher_id.strip().lower()
            verified_clips = [
                c for c in verified_clips if str(c.get("teacher_id") or "").lower() == _want
            ]
        _allow = _quality_allowlist()
        if _allow is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) in _allow]
        _blocked = _quality_blocklist()
        if _blocked is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) not in _blocked]
        elif str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip():
            # Configured-but-unreadable blocklist serves nothing (same fail-closed
            # contract as the single-question path).
            verified_clips = []
        verified_clips = [
            c
            for c in verified_clips
            if not _violent_for_context(
                query, str(c.get("verbatim_text") or ""), retrieval_query=retrieval_query
            )
        ]
        stage_timings["integrity_ms"] = round((time.monotonic() - t_int_start) * 1000.0, 2)

        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        # Answerability gate (invariant 22: it covers EVERY served clip). The compound
        # path used to skip it, so an out-of-scope compound question could be served
        # whatever clips the per-facet relevance scorer happened to accept.
        if getattr(settings, "first_person_answerability_check_enabled", False):
            t_ans_start = time.monotonic()
            verdict = _answerability_check(
                query, self._llm_service, request_loop=self._llm_loop, token_sink=fp_llm_tokens
            )
            stage_timings["answerability_ms"] = round((time.monotonic() - t_ans_start) * 1000.0, 2)
            if verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings["total_ms"] = round(latency, 2)
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
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
                    answerability="no" if verdict is False else "indeterminate",
                    abstain_reason="answerability_withheld",
                    stage_timings=stage_timings,
                )

        # Per-part Scoring & Selection (Task F2)
        t_scorer_start = time.monotonic()
        minimum_score = int(getattr(settings, "first_person_relevance_min_score", 3))
        used_video_ids: set[str] = set()
        part_results: list[dict[str, Any]] = []

        from services.quote_weaver import (
            _format_continuous_quote_block,
            _format_continuous_sources_footer,
            audio_strip_for,
            verify_hero_clip,
        )

        sources = sources_from_payloads(verified_clips)

        for facet in facets:
            avail_clips = [c for c in verified_clips if c.get("video_id") not in used_video_ids]
            if not avail_clips:
                avail_clips = verified_clips

            candidates = avail_clips[:3]
            rel_scores: list[int] = []
            pick = _relevance_select(
                facet,
                candidates,
                self._llm_service,
                self._llm_loop,
                token_sink=fp_llm_tokens,
                scores_out=rel_scores,
            )
            if pick is not None and pick != _RELEVANCE_INDETERMINATE:
                selected_clip = candidates[pick]
                used_video_ids.add(selected_clip.get("video_id"))
                part_results.append(
                    {
                        "facet": facet,
                        "clip": selected_clip,
                        "score": rel_scores[pick]
                        if (rel_scores and pick < len(rel_scores))
                        else minimum_score,
                    }
                )
            else:
                part_results.append(
                    {
                        "facet": facet,
                        "clip": None,
                        "score": 0,
                    }
                )
        stage_timings["scorer_ms"] = round((time.monotonic() - t_scorer_start) * 1000.0, 2)

        successful_parts = [p for p in part_results if p["clip"] is not None]
        if not successful_parts:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            self._log_and_count(
                "abstained",
                latency,
                0.0,
                n_quarantined,
                0,
                "relevance_below_min",
                sum(fp_llm_tokens),
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="relevance_below_min",
                stage_timings=stage_timings,
                # A25: below-min but integrity-verified — offer as related.
                related_clips=_related_clips_for(verified_clips),
            )

        # Assembly (Task F4 / Section 4 continuous layout)
        t_asm_start = time.monotonic()
        rendered_blocks: list[str] = []
        citations: list[dict[str, Any]] = []
        audio_playback_clips: list[dict[str, Any]] = []
        served_clips: list[dict[str, Any]] = []

        for p in part_results:
            facet = p["facet"]
            clip = p["clip"]
            if clip is not None:
                hero = verify_hero_clip(clip, sources)
                if not hero:
                    rendered_blocks.append(
                        f"### On {facet}\nI don't have a recording that answers this part yet."
                    )
                    continue
                clip_with_hero = {**clip, "_hero": hero}
                block = _format_continuous_quote_block(clip_with_hero, facet=facet)
                rendered_blocks.append(block)
                served_clips.append(clip_with_hero)

                cit = _build_citation_dict(
                    clip, clip_confidence=0.85, provenance_kind="compound_facet_clip"
                )
                citations.append(cit)
                strip = audio_strip_for(clip, hero)
                if strip:
                    audio_playback_clips.append(strip)
            else:
                rendered_blocks.append(
                    f"### On {facet}\nI don't have a recording that answers this part yet."
                )

        if not served_clips:
            # Every selected clip failed hero verification: nothing quotable was
            # rendered, so serving the "Related, not a direct answer" shell with
            # zero citations (and caching it) would be an empty weak match.
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            self._log_and_count(
                "abstained",
                latency,
                0.0,
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
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        footer = _format_continuous_sources_footer(served_clips)
        final_text = (
            "\n\n".join(rendered_blocks)
            + "\n\nRelated, not a direct answer"
            + (f"\n{footer}" if footer else "")
        )

        stage_timings["assembly_ms"] = round((time.monotonic() - t_asm_start) * 1000.0, 2)
        stage_timings["total_ms"] = round((time.monotonic() - start_time) * 1000.0, 2)

        res = FirstPersonPipelineResult(
            answer_text=final_text,
            citations=citations,
            status="weak_match",
            is_direct_answer=False,
            latency_ms=stage_timings["total_ms"],
            answerability="yes",
            abstain_reason="none",
            audio_playback_clip=audio_playback_clips[0] if audio_playback_clips else None,
            audio_playback_clips=audio_playback_clips,
            stage_timings=stage_timings,
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

        logger.info(
            "[FirstPersonPipeline] Compound Timings: ans=%.1fms, ret=%.1fms, int=%.1fms, rerank=%.1fms, scorer=%.1fms, asm=%.1fms, total=%.1fms",
            res.stage_timings["answerability_ms"],
            res.stage_timings["retrieval_ms"],
            res.stage_timings["integrity_ms"],
            res.stage_timings["rerank_ms"],
            res.stage_timings["scorer_ms"],
            res.stage_timings["assembly_ms"],
            res.stage_timings["total_ms"],
        )
        self._log_and_count(
            "weak_match",
            res.latency_ms,
            0.85,
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
