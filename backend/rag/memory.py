"""
Conversation memory helpers for the RAG pipeline.

These helpers keep memory compact, deterministic, and safe to inject into
retrieval/generation prompts without requiring a new database migration.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Optional

logger = __import__("logging").getLogger(__name__)

from rag.compressor import cap_to_token_budget
from rag.prompts import COMPACT_SUMMARY_SYSTEM_PROMPT as _COMPACT_SUMMARY_SYSTEM
from services.text_quality_filter import find_artifact

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
        # Use the shared, container-managed OllamaService rather than a raw
        # AsyncOpenAI client — the shared service carries the retry,
        # circuit-breaker, and cost-tracking behavior every other provider
        # branch above gets for free via the OpenAI-compatible endpoint.
        from app.dependencies import get_container

        ollama = getattr(get_container(), "ollama", None)
        if ollama is None:
            return None
        return ollama, settings.model_for_classification, "ollama_native"
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
    client, model, *kind = cm
    is_ollama_native = kind == ["ollama_native"]

    system = _COMPACT_SUMMARY_SYSTEM.format(target_chars=target_chars)
    try:
        if is_ollama_native:
            raw = await client.generate(
                system_prompt=system,
                user_prompt=history_text,
                temperature=0.3,
                max_tokens=min(target_chars // 4, 800),
                timeout=settings.llm_timeout,
            )
        else:
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
    user_msgs = [
        short_text(m.get("content"), 200)
        for m in chat_history
        if m.get("role") == "user" and m.get("content")
    ]
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
        if (
            not emotional_arc
            and hasattr(memory, "state_category")
            and getattr(memory, "state_category", None)
        ):
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


# ---------------------------------------------------------------------------
# A3 — extract_memory_insights (handoff docs/MEMORY_BACKEND_HANDOFF.md §A3)
# ---------------------------------------------------------------------------
# One LLM call over the top reranked docs → up to k atomic one-sentence
# claims. The caller stores the output in state["evaluation_trace"]["insights"]
# for benchmark visibility; Track B's memory writer consumes the same
# function. Every LLM output passes find_artifact() before parsing —
# insights flow toward Qdrant via the memory writer, so the ingestion-safety
# invariant (every LLM .generate() output reaching Qdrant passes
# find_artifact()) applies here, not just in ingest/.
#
# Deviation from the handoff sketch (deliberate): the sketch builds one
# single-string prompt for llm.ainvoke(); this module follows the repo's
# established convention (summarize_chat_history above, canonical extractor)
# of system + user messages via _build_llm_client. The contract is unchanged:
# top-5 docs, 400-char snippets, JSON list of strings, [:k], [] on failure.

_INSIGHT_MAX_DOCS = 5
_INSIGHT_SNIPPET_CHARS = 400
_INSIGHT_MAX_K = 10

_INSIGHT_SYSTEM = (
    "You extract atomic factual claims for a spiritual-guru AI's memory layer. "
    "From the teachings below, extract up to {k} atomic, self-contained factual "
    "claims (one sentence each). Return ONLY a JSON list of strings."
)


def _insight_doc_text(doc: Any) -> str:
    """Best-effort text from a langchain Document or a pipeline doc dict."""
    if isinstance(doc, dict):
        for key in ("page_content", "text", "content"):
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return ""
    for attr in ("page_content", "text", "content"):
        val = getattr(doc, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _insight_snippets(top_docs: list) -> str:
    """Truncated snippets (top-5 docs × 400 chars); "" when nothing usable."""
    snippets = []
    for doc in (top_docs or [])[:_INSIGHT_MAX_DOCS]:
        text = _insight_doc_text(doc).strip()
        if text:
            snippets.append(text[:_INSIGHT_SNIPPET_CHARS])
    return "\n---\n".join(snippets)


def _parse_insight_list(raw_text: str, k: int) -> list[str]:
    """Parse a JSON list of strings; [] on any shape/content failure."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?(.*?)\n?```$", r"\1", text, flags=re.DOTALL).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    insights: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        claim = " ".join(item.split())
        if not claim or claim.casefold() in seen:
            continue
        seen.add(claim.casefold())
        insights.append(claim)
        if len(insights) >= k:
            break
    return insights


async def extract_memory_insights(top_docs: list, k: int = 3) -> list[str]:
    """Extract up to k atomic one-sentence claims from the top reranked docs.

    Args:
        top_docs: langchain Documents or pipeline doc dicts (page_content /
            text / content). Only the first 5 are read, 400 chars each.
        k: max claims to return (clamped to 1..10).

    Returns:
        Up to k claim strings; [] when there are no docs, no usable text, no
        LLM provider, or the LLM output is unusable/contaminated.
    """
    try:
        k = max(1, min(int(k), _INSIGHT_MAX_K))
    except (TypeError, ValueError):
        k = 3
    if not top_docs:
        return []
    snippets = _insight_snippets(top_docs)
    if not snippets:
        return []

    cm = _build_llm_client()
    if not cm:
        logger.debug("extract_memory_insights: no LLM provider — returning []")
        return []
    client, model, *kind = cm
    is_ollama_native = kind == ["ollama_native"]

    from app.config import settings

    try:
        if is_ollama_native:
            raw = await client.generate(
                system_prompt=_INSIGHT_SYSTEM.format(k=k),
                user_prompt=snippets,
                temperature=0.0,
                max_tokens=512,
                timeout=float(getattr(settings, "llm_timeout", 20.0)),
            )
        else:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _INSIGHT_SYSTEM.format(k=k)},
                        {"role": "user", "content": snippets},
                    ],
                    temperature=0.0,
                    max_tokens=512,
                ),
                timeout=float(getattr(settings, "llm_timeout", 20.0)),
            )
            raw = resp.choices[0].message.content or ""
    except Exception as exc:
        logger.debug("extract_memory_insights LLM call failed (fail-open): %s", exc)
        return []

    artifact = find_artifact(raw)
    if artifact:
        logger.warning("extract_memory_insights output contaminated (%s); rejecting", artifact[:80])
        return []
    return _parse_insight_list(raw, k)


# ---------------------------------------------------------------------------
# B3 — inject_memory_context + memory_relevance_gate (graph-ready nodes)
# ---------------------------------------------------------------------------
# Handoff docs/MEMORY_BACKEND_HANDOFF.md §B3 asked for these as LangGraph
# nodes wired after intent_router / before decompose_query, with a relevance
# gate skipping settings.memory_skip_intents.
#
# Current architecture note (2026-10-04): injection is ALREADY owned by
# prepare_user_memory (app/orchestrator_utils.py), which runs in the pipeline
# orchestrator before the graph with per-call 500ms timeouts, a 1.5s total
# budget, PII scrubbing, and fail-open semantics — and context_engineer
# already renders state["memory_context"] into the prompt. Wiring these nodes
# into graph_strategies.py now would double every memory fetch and add hot-path
# latency before the B8 p95-delta gate passes. So: the node functions below
# are implemented, unit-tested, and import-ready
# (from rag.memory import inject_memory_context, memory_relevance_gate),
# but the topology edit itself is DEFERRED — see the wiring proposal in the
# session report. No caller changes in this file; zero runtime behavior change.
#
# The node emits plain fact lines (no header): context_engineer owns the
# USER MEMORY prompt labeling via _fence('user_memory', ...).

_MEMORY_SKIP_INTENTS_DEFAULT = ("doctrine_lookup", "casual")
_MEMORY_TOKEN_BUDGET_DEFAULT = 830
_MEMORY_FETCH_TIMEOUT_S = 4.0
_MEMORY_CORE_LIMIT = 5
_MEMORY_SEMANTIC_LIMIT = 3
_MEMORY_SUMMARY_LIMIT = 2


def _memory_enabled() -> bool:
    """Master read switch; defaults True to mirror app/config.py."""
    from app.config import settings

    return bool(getattr(settings, "feature_memory_enabled", True))


def _memory_skip_intents() -> tuple:
    """Intents that bypass injection; local default (app/config.py is shared).

    The handoff (§B7) declares memory_skip_intents in config, but that file
    is owned by a parallel session — until it lands, the default lives here
    and a deployed config value (when present) wins via getattr.
    """
    from app.config import settings

    return tuple(getattr(settings, "memory_skip_intents", None) or _MEMORY_SKIP_INTENTS_DEFAULT)


def _memory_token_budget() -> int:
    """Prompt budget for the injected block; config value wins when present."""
    from app.config import settings

    try:
        budget = int(getattr(settings, "memory_token_budget", _MEMORY_TOKEN_BUDGET_DEFAULT))
    except (TypeError, ValueError):
        return _MEMORY_TOKEN_BUDGET_DEFAULT
    return budget if budget > 0 else _MEMORY_TOKEN_BUDGET_DEFAULT


def _memory_skip_reason(state: dict) -> str | None:
    """None when memory should be injected; otherwise a stable skip reason."""
    if not _memory_enabled():
        return "memory_disabled"
    try:
        from services.user_profile_service import _is_persistable_user_id

        persistable = _is_persistable_user_id(state.get("user_id"))
    except ImportError:
        uid = state.get("user_id")
        persistable = bool(uid) and str(uid) != "anonymous" and not str(uid).startswith("anon:")
    if not persistable:
        return "anonymous_user"
    if state.get("memory_context"):
        # An upstream stage (today: the orchestrator's prepare_user_memory)
        # already placed context — never pay for a second fetch, and never
        # let a later gate wipe it. Checked before intent so a present block
        # survives even on skip-listed intents.
        return "already_present"
    skip_norm = {str(s).casefold() for s in _memory_skip_intents()}
    intent = str(state.get("intent") or "")
    if intent.casefold() in skip_norm:
        return f"skip_intent:{intent}"
    return None


def memory_relevance_gate(state: dict) -> str:
    """LangGraph conditional-edge predicate: "inject" or "skip".

    Case-insensitive against the skip-intent list so pipeline intents
    ("CASUAL") match handoff-style entries ("casual").
    """
    return "skip" if _memory_skip_reason(state) is not None else "inject"


def _memory_row_text(row: Any, *keys: str) -> str:
    if not isinstance(row, dict):
        return ""
    for key in keys:
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return " ".join(val.split())
    return ""


def _shape_memory_block(core: list | None, semantic: list | None, summaries: list | None) -> str:
    """Merge the three memory layers into plain fact lines (deduplicated)."""
    lines: list[str] = []
    for row in (core or [])[:_MEMORY_CORE_LIMIT]:
        text = _memory_row_text(row, "content", "claim")
        if text:
            lines.append(f"- {text}")
    for row in (semantic or [])[:_MEMORY_SEMANTIC_LIMIT]:
        text = _memory_row_text(row, "claim", "content")
        if text:
            lines.append(f"- {text}")
    for row in (summaries or [])[:_MEMORY_SUMMARY_LIMIT]:
        text = _memory_row_text(row, "summary", "content")
        if not text:
            continue
        topics = row.get("topics") if isinstance(row, dict) else None
        if isinstance(topics, list) and topics:
            text += f" (topics: {', '.join(str(t) for t in topics[:3])})"
        lines.append(f"- Earlier session: {text}")
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    return "\n".join(deduped)


async def inject_memory_context(
    state: dict,
    *,
    memory_service: Any | None = None,
    timeout_s: float = _MEMORY_FETCH_TIMEOUT_S,
) -> dict:
    """Graph-ready node: fan-out memory fetch → state["memory_context"].

    Reads user_id/question from state, fetches get_core / search_semantic /
    recent_summaries concurrently (each fail-open with its own timeout),
    truncates to the memory token budget, PII-scrubs, and returns the
    LangGraph state update. Never raises: without a service, a user, or
    results it returns a no-op update with a traceable skip reason.
    """
    reason = _memory_skip_reason(state)
    if reason is not None:
        # No "memory_context" key: a skip must never wipe context an upstream
        # stage (e.g. the orchestrator) already placed.
        return {"evaluation_trace": {"memory_injected": False, "memory_skip": reason}}

    user_id = state.get("user_id")
    svc = memory_service
    if svc is None:
        try:
            from app.dependencies import get_container

            svc = getattr(get_container(), "memory_service", None)
        except Exception as exc:
            logger.debug("inject_memory_context: container unavailable (%s)", exc)
            svc = None
    if svc is None:
        return {"evaluation_trace": {"memory_injected": False, "memory_skip": "no_service"}}

    question = (state.get("question") or state.get("rewritten_query") or "").strip()

    async def _safe_fetch(coro_factory: Any, label: str) -> list:
        try:
            result = await asyncio.wait_for(coro_factory(), timeout=timeout_s)
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.debug("inject_memory_context: %s fetch failed (fail-open): %s", label, exc)
            return []

    core, semantic, summaries = await asyncio.gather(
        _safe_fetch(lambda: svc.get_core(user_id), "core"),
        _safe_fetch(
            lambda: svc.search_semantic(user_id, question, limit=3, min_similarity=0.6),
            "semantic",
        )
        if question
        else asyncio.sleep(0, result=[]),
        _safe_fetch(lambda: svc.recent_summaries(user_id, limit=2), "summaries"),
    )

    block = _shape_memory_block(core, semantic, summaries)
    if not block:
        return {"evaluation_trace": {"memory_injected": False, "memory_skip": "no_results"}}

    language = state.get("detected_language") or "en"
    block = cap_to_token_budget(block, _memory_token_budget(), language)

    try:
        from app.orchestrator_utils import _scrub_memory_context

        scrubbed = _scrub_memory_context(block)
        scrub_ok = True
    except Exception as exc:
        logger.warning(
            "inject_memory_context: PII scrub unavailable (%s); shipping unscrubbed", exc
        )
        scrubbed = block
        scrub_ok = False

    return {
        "memory_context": scrubbed,
        "evaluation_trace": {
            "memory_injected": bool(scrubbed),
            "memory_chars": len(scrubbed),
            "memory_unscrubbed": not scrub_ok,
        },
    }


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
        session_id="s1",
        user_id="u1",
        started_at=1000000,
        messages=[],
        key_insights=["peace"],
        emotional_arc=[],
        follow_up_suggestions=[],
    )
    mem_new = ConversationMemory(
        session_id="s2",
        user_id="u1",
        started_at=1700000000,
        messages=[],
        key_insights=["joy"],
        emotional_arc=[],
        follow_up_suggestions=[],
    )
    selected = weighted_memory_selection([mem_old, mem_new], max_memories=2)
    assert len(selected) == 2
    assert selected[0].session_id == "s2"

    assert _parse_insight_list('["Deeksha awakens inner stillness.", 42, ""]', 3) == [
        "Deeksha awakens inner stillness."
    ]
    assert _parse_insight_list("not json", 3) == []
    assert _insight_snippets([{"text": "abc"}, {"page_content": ""}]) == "abc"
    assert _insight_snippets([]) == ""
    shaped = _shape_memory_block(
        [{"content": "User lives in Pune."}],
        [{"claim": "User lives in Pune.", "content": "dup"}],
        [{"summary": "Talked about Ekam.", "topics": ["Ekam", "stillness"]}],
    )
    assert "User lives in Pune." in shaped
    assert shaped.count("User lives in Pune.") == 1
    assert "Earlier session: Talked about Ekam." in shaped
    print("Self-check passed")
