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
from rag.states import GraphState

logger = logging.getLogger(__name__)

# Module-level service reference (injected via init_services)
_ollama = None


def set_ollama(ollama_service):
    """Inject the OllamaService instance."""
    global _ollama
    _ollama = ollama_service


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


async def resolve_followup(state: GraphState) -> dict:
    """
    Resolve follow-up queries into standalone questions.

    This node sits between intent_router and decompose_query in the RAG pipeline.
    It examines the conversation history and, if the current question appears to
    be a follow-up (uses pronouns, references prior context), rewrites it into
    a standalone question that can be searched independently.

    Returns:
        dict with updated 'question' if resolved, or empty dict if no change needed.
    """
    chat_history = state.get("chat_history", [])
    question = state["question"]

    # No history → nothing to resolve against
    if not chat_history:
        return {}

    # Only resolve if Ollama is available
    if _ollama is None:
        logger.warning("resolve_followup: OllamaService not initialized, skipping")
        return {}

    # Build history string from last 4 messages (2 turns)
    recent = chat_history[-4:]
    history_lines = []
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")[:300]  # truncate long messages
        history_lines.append(f"{role}: {content}")

    history_str = "\n".join(history_lines)

    try:
        prompt = RESOLVE_FOLLOWUP_PROMPT.format(
            history=history_str,
            question=question,
        )

        resolved = await _ollama.generate(
            system_prompt="",
            user_prompt=prompt,
        )

        resolved = resolved.strip()

        # Only update if the LLM actually changed the question
        if resolved and resolved != question and len(resolved) > 3:
            logger.info(
                f"Follow-up resolved: '{question[:60]}' → '{resolved[:60]}'"
            )
            return {"question": resolved}
        else:
            logger.info(f"Follow-up resolution: no change needed for '{question[:60]}'")
            return {}

    except Exception as e:
        logger.warning(f"Follow-up resolution failed (non-fatal): {e}")
        return {}  # Graceful fallback — proceed with original question
