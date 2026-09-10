"""
Conversation memory helpers for the RAG pipeline.

These helpers keep memory compact, deterministic, and safe to inject into
retrieval/generation prompts without requiring a new database migration.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Optional

logger = __import__("logging").getLogger(__name__)

_SESSION_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

_COMPACT_SUMMARY_SYSTEM = """You are a conversation summarizer. Given a chat history between a Seeker and a Guru, produce a structured summary with these fields:
- goal: The seeker's current spiritual or personal goal
- key_decisions: Decisions or commitments made during the conversation
- emotional_state: The seeker's emotional trajectory
- open_items: Unresolved questions or follow-ups
- user_preferences: Any preferences the seeker expressed

Be concise. Target {target_chars} characters or fewer. Output only the fields above, one per line like 'goal: ...'."""


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
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def _build_llm_client():
    from app.config import settings

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None

    provider = settings.llm_provider.lower()
    if settings.is_sarvam_cloud:
        return (
            AsyncOpenAI(
                base_url=settings.sarvam_base_url,
                api_key="api-key-not-used-by-bearer",
                default_headers={"api-subscription-key": settings.sarvam_api_key},
            ),
            settings.sarvam_cloud_classify_model or "sarvam-30b",
        )
    if provider == "openrouter":
        return AsyncOpenAI(
            base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key
        ), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(
            base_url=settings.nim_base_url, api_key=settings.nim_api_key
        ), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(
            base_url=settings.ollama_base_url, api_key="ollama"
        ), settings.model_for_classification
    return None


async def summarize_chat_history(
    chat_history: list[dict],
    target_chars: int | None = None,
) -> dict[str, str]:
    """Summarize merged chat history via LLM, returning structured fields.

    Returns dict with keys: goal, key_decisions, emotional_state, open_items,
    user_preferences, raw_summary. Falls back to extractive summary on LLM failure.
    """
    from app.config import settings

    if target_chars is None:
        target_chars = settings.chat_history_compaction_target

    history_text = "\n".join(
        f"{'Seeker' if m.get('role') == 'user' else 'Guru'}: {short_text(m.get('content'), 300)}"
        for m in chat_history
        if m.get("role") in {"user", "assistant"} and m.get("content")
    )

    fallback = _extractive_fallback(chat_history)

    cm = _build_llm_client()
    if not cm:
        return fallback
    client, model = cm

    system = _COMPACT_SUMMARY_SYSTEM.format(target_chars=target_chars)
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": history_text},
                ],
                temperature=0.3,
                max_tokens=min(target_chars // 4, 800),
            ),
            timeout=settings.llm_timeout,
        )
        raw = resp.choices[0].message.content or ""
        return _parse_structured_summary(raw) or fallback
    except Exception as e:
        logger.debug(f"Chat compaction LLM failed, using extractive fallback: {e}")
        return fallback


def _parse_structured_summary(raw: str) -> Optional[dict[str, str]]:
    fields = {}
    for line in raw.strip().splitlines():
        line = line.strip().lstrip("- ")
        for key in ("goal", "key_decisions", "emotional_state", "open_items", "user_preferences"):
            if line.lower().startswith(f"{key}:"):
                fields[key] = line.split(":", 1)[1].strip()
                break
    if fields:
        fields["raw_summary"] = raw.strip()
        return fields
    return None


def _extractive_fallback(chat_history: list[dict]) -> dict[str, str]:
    user_msgs = [short_text(m.get("content"), 200) for m in chat_history if m.get("role") == "user" and m.get("content")]
    summary = "; ".join(user_msgs[:5]) if user_msgs else "No conversation history available."
    return {
        "goal": "",
        "key_decisions": "",
        "emotional_state": "",
        "open_items": "",
        "user_preferences": "",
        "raw_summary": summary,
    }


def extract_entities_from_summary(summary: dict[str, str]) -> dict[str, Any]:
    """Extract user name, goals, and emotional patterns from a compacted summary."""
    entities: dict[str, Any] = {}
    raw = summary.get("raw_summary", "")

    name_match = re.search(
        r"(?i)\b(?:my name is|i'm|i am)\s+(?-i:([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))\b",
        raw,
    )
    if name_match:
        entities["user_name"] = name_match.group(1)

    goal = summary.get("goal", "")
    if goal:
        entities["stated_goals"] = [g.strip() for g in goal.split(";") if g.strip()]

    emotional = summary.get("emotional_state", "")
    if emotional:
        entities["emotional_patterns"] = [e.strip() for e in emotional.split(";") if e.strip()]

    prefs = summary.get("user_preferences", "")
    if prefs:
        entities["preferences"] = [p.strip() for p in prefs.split(";") if p.strip()]

    return entities


def weighted_memory_selection(
    recent_memories: list,
    max_memories: int = 3,
    decay_rate: float = 0.05,
) -> list:
    """Select memories using exponential recency decay weighting."""
    if not recent_memories:
        return []

    now = datetime.now(UTC)
    scored: list[tuple[float, Any]] = []
    for mem in recent_memories:
        created_str = getattr(mem, "started_at", None) or getattr(mem, "created_at", None)
        delta_days = 0.0
        if created_str:
            try:
                if isinstance(created_str, (int, float)):
                    created = datetime.fromtimestamp(created_str, tz=UTC)
                else:
                    created = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=UTC)
                delta_days = (now - created).total_seconds() / 86400.0
            except Exception as e:
                logger.debug("Failed to parse memory timestamp '%s': %s", created_str, e)
                delta_days = 0.0
        weight = math.exp(-decay_rate * delta_days)
        scored.append((weight, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [mem for _, mem in scored[:max_memories]]


def build_memory_context(
    *,
    recent_memories: list,
    chat_history: list[dict],
    max_memories: int = 3,
    max_history_messages: int = 6,
    char_budget: int | None = None,
    compacted_summary: Optional[dict[str, str]] = None,
) -> str:
    """
    Build a compact continuity block from current-thread history and stored memories.

    When a compacted_summary is provided (from summarize_chat_history), it is used
    instead of the full chat history for the summary section. Recent 6 turns are
    always preserved raw alongside the summary.
    """
    from app.config import settings

    if char_budget is None:
        char_budget = settings.chat_history_compaction_threshold
    sections: list[str] = []

    if compacted_summary:
        summary_text = compacted_summary.get("raw_summary", "")
        if summary_text:
            sections.append(f"Conversation summary:\n{short_text(summary_text, 600)}")

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
                sections.append("Recent thread:\n" + "\n".join(lines))
    else:
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
        if not emotional_arc and hasattr(memory, "state_category") and getattr(memory, "state_category", None):
            _sc = getattr(memory, "state_category", "")
            _distress = 0
            if _sc in ("Suffering State", "Shrinking Self", "Destructive Self"):
                _distress = 2 if _sc == "Suffering State" else 3
            emotional_arc = [{"topic": _sc, "distress_level": _distress}]
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


if __name__ == "__main__":
    history = [
        {"role": "user", "content": "I feel anxious about work"},
        {"role": "assistant", "content": "Let us practice breathing together."},
        {"role": "user", "content": "Thank you, I feel calmer now."},
        {"role": "assistant", "content": "That is beautiful. Remember this feeling."},
    ]
    result = _extractive_fallback(history)
    assert "anxious" in result["raw_summary"]
    print(f"Extractive fallback: {result}")

    entities = extract_entities_from_summary(result)
    print(f"Entities: {entities}")

    from services.user_profile_service import ConversationMemory
    mem_old = ConversationMemory(
        session_id="s1", user_id="u1", started_at=1000000, messages=[],
        key_insights=["peace"], emotional_arc=[], follow_up_suggestions=[],
    )
    mem_new = ConversationMemory(
        session_id="s2", user_id="u1", started_at=1700000000, messages=[],
        key_insights=["joy"], emotional_arc=[], follow_up_suggestions=[],
    )
    selected = weighted_memory_selection([mem_old, mem_new], max_memories=2)
    assert len(selected) == 2
    assert selected[0].session_id == "s2"
    print("Self-check passed")
