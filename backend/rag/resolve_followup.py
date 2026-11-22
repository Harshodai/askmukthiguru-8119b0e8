"""
Mukthi Guru — Follow-Up Query Resolution Node

Design Patterns:
  - Query Transformation: RAG Made Simple Ch.5 — Reshaping questions before search
  - Context-aware Reformulation: System Design for LLM Era §6.9

Resolves pronoun-heavy follow-up queries into standalone questions by
incorporating conversation history context.

Examples:
  History: "What is the Beautiful State?" → "Tell me more about that"
  Resolved: "Tell me more about the Beautiful State and its practices"

  History: "How do I meditate?" → "What about for anxiety?"
  Resolved: "How do I meditate specifically for anxiety?"
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from langchain_core.runnables import RunnableConfig

from app.config import settings
from rag.states import GraphState


def _q_tag(text: str) -> str:
    """Length + short sha256 prefix; never the seeker's words (SEC-003)."""
    return (
        f"len={len(text or '')} sha={hashlib.sha256((text or '').encode('utf-8')).hexdigest()[:8]}"
    )


logger = logging.getLogger(__name__)


_FOLLOWUP_PHRASES = [
    "tell me more",
    "what about",
    "how about",
    "explain more",
    "go deeper",
    "say more",
    "tell me about that",
    "more about",
    "what does that mean",
    "what do you mean",
    "why is that",
    "how is that",
    "what about that",
    "can you elaborate",
    "can you tell me more",
    "elaborate on that",
    "tell me about it",
    "explain that",
    "tell me more about",
    "further explain",
    "go into more detail",
]

_REFERENTIAL_WORDS = {
    "it",
    "that",
    "this",
    "these",
    "those",
    "they",
    "them",
    "there",
    "more",
    "also",
    "further",
}


def _is_heuristic_followup(question: str, chat_history: list) -> bool:
    """Cheap heuristic for follow-up detection — no LLM call."""
    if not chat_history:
        return False
    lower_q = question.lower().strip()
    if not lower_q:
        return False
    for phrase in _FOLLOWUP_PHRASES:
        if phrase in lower_q:
            return True
    words = set(re.sub(r"[^\w\s]", "", lower_q).split())
    ref_count = sum(1 for w in words if w in _REFERENTIAL_WORDS)
    if ref_count >= 1 and len(words) <= 8:
        return True
    if lower_q.startswith(("that ", "this ", "those ", "these ", "it ", "they ")):
        return True
    return False


_TOPIC_STOPWORDS = frozenset(
    {
        "the", "a", "an", "my", "your", "our", "his", "her", "their", "of", "in", "on",
        "to", "and", "or", "for", "with", "about", "me", "i", "is", "are", "be", "do",
        "does", "can", "you", "please", "tell", "more", "what", "how", "why", "say",
        "explain", "elaborate", "go", "deeper", "further", "detail", "into",
        "give", "share", "show", "example", "examples", "story", "stories", "instance", "illustration",
    }
)  # fmt: skip


def names_new_topic(question: str) -> bool:
    """True when a "follow-up" phrase already carries its own topic.

    "tell me more about the Beautiful State" matches a follow-up phrase, but it
    names its subject. Prepending the previous question to it pulled the wrong
    clip (Task list A28: a suffering clip came back for a Beautiful State
    follow-up). A topic needs two or more content words and no referential word,
    so "what about that" and "what about my husband" still resolve against the
    history.
    """
    words = re.sub(r"[^\w\s]", "", question.lower()).split()
    if not words or any(w in _REFERENTIAL_WORDS - {"more", "further"} for w in words):
        return False
    content = [w for w in words if w not in _TOPIC_STOPWORDS]
    return len(content) >= 2


# Explicit topic shift: a closed set of leading markers (2026-11-19 battery:
# "Unrelated, what is the purpose of meditation?" abstained while the bare
# question served). The marker is dropped and history is never prepended.
_TOPIC_SHIFT_RE = re.compile(
    r"^\s*(?:(?:ok(?:ay)?|so|now|also)[,\s]+)?"
    r"(?:unrelated(?:\s+question)?|(?:a\s+)?(?:new|different|separate|another)\s+(?:question|topic)"
    r"|on\s+(?:a|an)\s+(?:different|unrelated|other|another)\s+(?:note|topic)"
    r"|chang(?:e|ing)\s+(?:the\s+)?(?:topic|subject)|switching\s+(?:topics?|gears)"
    r"|(?:totally\s+|completely\s+)?(?:something\s+)?different)"
    r"\s*[,:;.!?\-–—]+\s*",
    re.IGNORECASE,
)


def strip_topic_shift(question: str) -> Optional[str]:
    """The question without its explicit topic-shift marker, or None when there is none."""
    m = _TOPIC_SHIFT_RE.match(question or "")
    if not m:
        return None
    rest = question[m.end() :].strip()
    return rest if len(rest.split()) >= 2 else None


# Meta follow-ups: a request about the PREVIOUS answer, with no topic of its own.
# Order matters: the first match names the kind.
_META_FOLLOWUP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "shorter",
        re.compile(
            r"\b(?:shorter|briefer|briefly|too\s+long|in\s+short|summari[sz]e|tl;?dr"
            r"|in\s+(?:one|a\s+few|fewer)\s+(?:line|sentence|word)s?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "example",
        re.compile(
            r"\b(?:give|share|tell|show)\b.{0,20}\b(?:an?\s+)?(?:example|instance|story|illustration)\b"
            r"|^\s*(?:an?\s+|any\s+)?(?:example|story)s?\b|\bfor\s+example\s*\?",
            re.IGNORECASE,
        ),
    ),
    (
        "ordinal",
        re.compile(
            r"\bthe\s+(?:first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)"
            r"\s+(?:one|point|part|step|secret|thing|idea)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "elaborate",
        re.compile(
            r"\b(?:explain|say)\s+(?:it\s+|that\s+|this\s+)?(?:more|further|again|simpl[ey]r?|more\s+simply)\b"
            r"|\bexplain\s+(?:it|that|this)\b|\b(?:simpler|more\s+simply|simplify|in\s+simple\s+(?:words|terms))\b"
            r"|\bwhat\s+(?:did|do)\s+you\s+mean\b|\bgo\s+deeper\b|\belaborate\b|\btell\s+me\s+more\b"
            r"|\bhow\s+(?:do|can|should)\s+i\s+(?:practi[sc]e|apply|do|use)\s+(?:it|that|this)\b",
            re.IGNORECASE,
        ),
    ),
)
# A meta follow-up is short; a long turn carries its own question.
_META_FOLLOWUP_MAX_WORDS = 14


def meta_followup_kind(question: str) -> Optional[str]:
    """"shorter" | "example" | "ordinal" | "elaborate" for a meta follow-up, else None.

    Deterministic (no LLM). A turn with an explicit topic-shift marker is never meta.
    """
    q = (question or "").strip()
    if not q or len(q.split()) > _META_FOLLOWUP_MAX_WORDS or strip_topic_shift(q) is not None:
        return None
    for kind, pattern in _META_FOLLOWUP_PATTERNS:
        if pattern.search(q):
            return kind
    return None


def _get_last_user_message(chat_history: list) -> str:
    """Extract the most recent user message content from chat history."""
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content[:200] if content else ""
    return ""


@dataclass(frozen=True)
class FollowupResolution:
    """What the follow-up resolver decided for one turn. Routing metadata only.

    ``kind`` / ``reason_code`` name the deterministic rule that matched. Nothing here
    may change what a gate decides: ``retrieval_query`` feeds retrieval and scoring
    exactly as the raw query did, and no answer text is ever built from this object.
    """

    retrieval_query: str
    kind: str
    reason_code: str
    note: str | None = None
    max_context_spans: int | None = None
    history_used: bool = True

    def log_fields(self, raw_query: str) -> dict[str, object]:
        """Primitives for telemetry: the kind, the rule, and a hash — never the words."""
        text = raw_query or ""
        return {
            "kind": self.kind,
            "reason": self.reason_code,
            "history_used": self.history_used,
            "raw_len": len(text),
            "raw_sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        }


FOLLOWUP_KINDS = frozenset(
    {
        "topic_shift",
        "continuation",
        "shorter",
        "example",
        "ordinal",
        "elaborate",
        "new_topic",
        "unknown",
    }
)


def followup_metadata(
    raw_query: str,
    chat_history: list,
    *,
    continuation: bool = False,
) -> FollowupResolution:
    """The non-resolving half of the classification: why nothing was resolved.

    Used when neither a topic shift nor a meta follow-up fired. ``continuation`` is the
    history-prepended branch the bridge already took; the rest are the honest
    "no rewrite happened" reasons. Deterministic, no LLM.
    """
    if continuation:
        return FollowupResolution(
            retrieval_query=raw_query,
            kind="continuation",
            reason_code="referential_followup",
        )
    if not chat_history:
        return FollowupResolution(
            retrieval_query=raw_query,
            kind="unknown",
            reason_code="no_history",
            history_used=False,
        )
    if names_new_topic(raw_query):
        return FollowupResolution(
            retrieval_query=raw_query,
            kind="new_topic",
            reason_code="topic_named_in_followup",
            history_used=False,
        )
    return FollowupResolution(
        retrieval_query=raw_query,
        kind="unknown",
        reason_code="no_rule_matched",
        history_used=False,
    )


async def resolve_followup(state: GraphState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Resolve follow-up queries into standalone questions (general graph tier).

    This node sits between intent_router and decompose_query in the RAG pipeline.
    It examines the conversation history and, if the current question appears to be
    a follow-up (pronouns, references to prior context), rewrites it into a
    standalone question that can be searched independently.

    Two documented behaviours only:

    - ``rag_heuristic_followup=True``: pronoun/regex matching rewrites the query
      with the previous user turn. No LLM call.
    - ``rag_heuristic_followup=False`` (default): a documented no-op. The LLM
      rewrite path was retired on 2026-11-22 — its provider (Ollama) was removed
      2026-11-16, so the node only logged "OllamaService not initialized" and
      returned ``{}`` on every call. Behaviour is byte-identical to that path.

    The first-person lane does not use this node; it resolves follow-ups in
    ``app/pipeline/stages/first_person_bridge.py``.

    Returns:
        dict with updated 'question' if resolved, or empty dict if no change needed.
    """
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Resolve Follow-up: fast path query, skipping resolution.")
        return {}

    # DEF-R2-02: Bypass follow-up resolution on personalize turns to preserve
    # the grounded question and verbatim quote intact.
    if state.get("personalize_clip"):
        logger.info("Resolve Follow-up: personalize teaching turn active; preserving grounded question.")
        return {}

    chat_history = state.get("chat_history", [])
    question = state["question"]

    # No history → nothing to resolve against
    if not chat_history:
        return {}

    # If intent_router already flagged this as a heuristic follow-up, skip entirely
    if state.get("follow_up_detected"):
        logger.info("Resolve Follow-up: already detected by intent_router, skipping.")
        return {}

    # --- Heuristic path (no LLM call) ---
    if getattr(settings, "rag_heuristic_followup", False):
        if _is_heuristic_followup(question, chat_history):
            last_user = _get_last_user_message(chat_history)
            if last_user:
                contextualized = f"{last_user} - {question}"
                logger.info(
                    "Follow-up resolved (heuristic): %s -> %s",
                    _q_tag(question),
                    _q_tag(contextualized),
                )
                return {"question": contextualized}
        logger.info("Follow-up resolution (heuristic): no change needed for %s", _q_tag(question))
        return {}

    # --- No-op path (LLM rewrite retired 2026-11-22) ---
    logger.info(
        "Follow-up resolution: disabled (rag_heuristic_followup=false) for %s", _q_tag(question)
    )
    return {}
