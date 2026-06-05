"""
Conversation memory helpers for the RAG pipeline.

These helpers keep memory compact, deterministic, and safe to inject into
retrieval/generation prompts without requiring a new database migration.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from typing import Optional

_SESSION_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def normalize_session_id(session_id: Optional[str], user_id: str) -> str:
    """
    Return a stable UUID for any frontend conversation id.

    Older local conversations use short random strings, while Supabase-backed
    tables expect UUIDs. uuid5 preserves continuity for those local ids without
    changing the frontend storage format.
    """
    if session_id:
        try:
            return str(uuid.UUID(str(session_id)))
        except (TypeError, ValueError):
            stable_key = f"{user_id}:{session_id}"
            return str(uuid.uuid5(_SESSION_NAMESPACE, stable_key))
    return str(uuid.uuid4())


def short_text(value: object, limit: int = 240) -> str:
    """Normalize whitespace and cap text length for prompt-budget control."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _memory_fingerprint(parts: Iterable[object]) -> str:
    joined = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def build_memory_context(
    *,
    recent_memories: list,
    chat_history: list[dict],
    max_memories: int = 3,
    max_history_messages: int = 6,
    char_budget: int = 1800,
) -> str:
    """
    Build a compact continuity block from current-thread history and stored memories.

    The output is intentionally extractive. It gives the generator continuity
    signals while avoiding an additional summarization LLM call on every turn.
    """
    sections: list[str] = []

    recent_turns = [
        msg
        for msg in chat_history[-max_history_messages:]
        if msg.get("role") in {"user", "assistant"}
    ]
    if recent_turns:
        lines = []
        for msg in recent_turns:
            role = "Seeker" if msg.get("role") == "user" else "Guru"
            content = short_text(msg.get("content"), 220)
            if content:
                lines.append(f"- {role}: {content}")
        if lines:
            sections.append("Current thread:\n" + "\n".join(lines))

    seen = set()
    prior_lines = []
    for memory in recent_memories[:max_memories]:
        fingerprint = _memory_fingerprint(
            [
                getattr(memory, "session_id", ""),
                getattr(memory, "key_insights", ""),
                getattr(memory, "follow_up_suggestions", ""),
            ]
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        parts = []
        insights = [
            short_text(item, 90) for item in (getattr(memory, "key_insights", None) or []) if item
        ]
        if insights:
            parts.append(f"topics: {', '.join(insights[:3])}")

        emotional_arc = getattr(memory, "emotional_arc", None) or []
        if emotional_arc:
            latest = emotional_arc[-1] or {}
            topic = short_text(latest.get("topic", "unknown"), 80)
            level = latest.get("distress_level", 0)
            parts.append(f"last emotional signal: {topic} (distress {level})")

        followups = [
            short_text(item, 90)
            for item in (getattr(memory, "follow_up_suggestions", None) or [])
            if item
        ]
        if followups:
            parts.append(f"possible follow-up: {followups[0]}")

        if parts:
            prior_lines.append("- " + "; ".join(parts))

    if prior_lines:
        sections.append("Earlier sessions:\n" + "\n".join(prior_lines))

    if not sections:
        return ""

    context = "Conversation continuity context:\n" + "\n\n".join(sections)
    return context[:char_budget].rstrip()
