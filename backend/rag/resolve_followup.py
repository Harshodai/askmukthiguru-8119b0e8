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

import logging

from app.config import settings
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout

logger = logging.getLogger(__name__)

# Module-level service reference (injected via init_services)
_ollama = None


def set_ollama(ollama_service):
    """Inject the OllamaService instance."""
    global _ollama
    _ollama = ollama_service


_FOLLOWUP_PHRASES = [
    "tell me more", "what about", "how about", "explain more",
    "go deeper", "say more", "tell me about that", "more about",
    "what does that mean", "what do you mean", "why is that",
    "how is that", "what about that", "can you elaborate",
    "can you tell me more", "elaborate on that", "tell me about it",
    "explain that", "tell me more about", "further explain",
    "go into more detail",
]

_REFERENTIAL_WORDS = {
    "it", "that", "this", "these", "those", "they", "them",
    "there", "more", "also", "further",
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
    words = set(lower_q.split())
    ref_count = sum(1 for w in words if w in _REFERENTIAL_WORDS)
    if ref_count >= 1 and len(words) <= 8:
        return True
    if lower_q.startswith(("that ", "this ", "those ", "these ", "it ", "they ")):
        return True
    return False


def _get_last_user_message(chat_history: list) -> str:
    """Extract the most recent user message content from chat history."""
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content[:200] if content else ""
    return ""


RESOLVE_FOLLOWUP_PROMPT = """You are a query resolver for a multi-turn spiritual chat system.

Given the conversation history and the user's latest question, determine if the question
is a follow-up that refers to previous context (using words like "that", "it", "this",
"more", "also", "what about", pronouns, or continuations).

If it IS a follow-up: Rewrite it as a STANDALONE question that includes all necessary
context from the history. Return ONLY the rewritten question, nothing else.

If it is NOT a follow-up (it's a completely new topic): Return the original question unchanged.

CONVERSATION HISTORY:
{history}

LATEST QUESTION: {question}

STANDALONE QUESTION:"""


async def resolve_followup(state: GraphState, config: dict = None) -> dict:
    """
    Resolve follow-up queries into standalone questions.

    This node sits between intent_router and decompose_query in the RAG pipeline.
    It examines the conversation history and, if the current question appears to
    be a follow-up (uses pronouns, references prior context), rewrites it into
    a standalone question that can be searched independently.

    When rag_heuristic_followup is True, uses pronoun/regex matching instead of
    an LLM call — saves 1 LLM call per follow-up query.

    Returns:
        dict with updated 'question' if resolved, or empty dict if no change needed.
    """
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Resolve Follow-up: fast path query, skipping LLM resolution.")
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
                    f"Follow-up resolved (heuristic): '{question[:60]}' → '{contextualized[:60]}'"
                )
                return {"question": contextualized}
        logger.info(f"Follow-up resolution (heuristic): no change needed for '{question[:60]}'")
        return {}

    # --- LLM path (legacy) ---
    # SSE status — let the user see that we're consulting the prior turn
    try:
        from rag.nodes.utils import emit_status
        await emit_status(config, "Connecting this to your previous question...")
    except Exception:
        pass

    # Build history string from last 10 messages (5 turns) so benchmark follow-ups
    # retain the doctrine anchors from earlier answers.
    recent = chat_history[-10:]
    history_lines = []
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        limit = 400 if role == "Assistant" else 260
        content = msg.get("content", "")[:limit]
        history_lines.append(f"{role}: {content}")

    history_str = "\n".join(history_lines)

    if _ollama is None:
        logger.warning("resolve_followup: OllamaService not initialized, skipping")
        return {}

    try:
        prompt = RESOLVE_FOLLOWUP_PROMPT.format(
            history=history_str,
            question=question,
        )

        t_out = get_node_timeout("resolve_followup", 15)
        resolved = await _ollama._generate_fast(
            system_prompt="",
            user_prompt=prompt,
            timeout=t_out,
            max_retries=1,
        )

        resolved = resolved.strip()

        # Guard against models that emit code/markup instead of the rewritten question.
        # Treat the LLM output as unusable and fall back to the original question.
        if resolved.startswith("def ") or resolved.startswith("class ") or "```" in resolved or "import " in resolved:
            logger.warning(
                f"Follow-up resolution returned code/markup instead of text; using original question. "
                f"Output preview: {resolved[:80]!r}"
            )
            return {}

        # Only update if the LLM actually changed the question
        if resolved and resolved != question and len(resolved) > 3:
            logger.info(f"Follow-up resolved: '{question[:60]}' → '{resolved[:60]}'")
            return {"question": resolved}
        else:
            logger.info(f"Follow-up resolution: no change needed for '{question[:60]}'")
            return {}

    except Exception as e:
        logger.warning(f"Follow-up resolution failed (non-fatal): {e}")
        return {}  # Graceful fallback — proceed with original question
