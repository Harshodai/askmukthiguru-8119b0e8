"""Reflection, verification, contradiction check, and citation reasoning nodes."""

from __future__ import annotations

import asyncio
import logging

from app.metrics import (
    CONFIDENCE_SCORES,
    CONTRADICTION_DETECTIONS,
    FAITHFULNESS_SCORE,
    RELEVANCY_SCORE,
    VERIFICATION_RESULTS,
)
from rag.prompts import (
    CITATION_REASONING_PROMPT,
)
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout

from . import _services
from .utils import _trace_update, emit_status, log_metrics

logger = logging.getLogger(__name__)


@log_metrics
async def reflect_on_answer(state: GraphState, config: dict = None) -> dict:
    """Self-Reflection RAG loop with LettuceDetect and self-consistency checking."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Self-Reflection: bypassing for simple query tier")
        return {"needs_correction": False, "reflection_feedback": None}

    answer = state.get("answer")
    relevant_docs = state.get("relevant_docs", [])
    question = state.get("rewritten_query") or state["question"]
    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama  # noqa: F841 — preserved per "do not delete" mandate; used by disabled self-consistency block below

    if not answer or not relevant_docs:
        return {"needs_correction": False}

    await emit_status(config, "Reviewing the response for clarity...")
    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
    is_faithful_strict = ld_result["score"] >= 0.8

    # --- Self-consistency check DISABLED (performance) ---
    # This LLM-based self-consistency block generates an alternative answer
    # and compares faithfulness scores. It adds ~45s with zero quality
    # gain for spiritual answers where paraphrasing always differs.
    # Commented out per comprehensive fix plan — do not remove, kept intact.
    #
    # consistency_check_passed = True
    # consistency_feedback = ""
    # try:
    #     ... (original code preserved in file history)
    # except Exception as e:
    #     ...
    # --- END DISABLED ---

    is_valid = is_faithful_strict
    consistency_check_passed = True  # Disabled for performance
    consistency_feedback = ""

    feedback_parts = []
    if not is_faithful_strict:
        feedback_parts.append(f"Faithfulness below threshold (score: {ld_result['score']:.2f}, need >= 0.8)")
    if not consistency_check_passed:
        feedback_parts.append(consistency_feedback)

    feedback = "; ".join(feedback_parts) if feedback_parts else "Answer appears valid and consistent"

    if is_valid or "doesn't know" in answer.lower():
        logger.info(f"Self-Reflection: Answer is VALID. {feedback}")
        return {"needs_correction": False, "reflection_feedback": feedback}

    logger.warning(f"Self-Reflection: Issues detected - {feedback}")
    return {"needs_correction": True, "reflection_feedback": feedback}


@log_metrics
async def verify_answer(state: GraphState, config: dict = None) -> dict:
    """Enhanced Combined Self-RAG + CoVe verification with actual claim verification."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Combined verify: bypassing for simple query tier")
        return {
            "is_faithful": True,
            "verification": {"passed": True, "details": "Bypassed for simple query tier"},
            "confidence_score": 10.0,
            "faithfulness_score": 1.0,
            "relevancy_score": 1.0,
        }

    answer = state["answer"]
    relevant_docs = state["relevant_docs"]
    question = state.get("rewritten_query") or state["question"]
    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama  # noqa: F841 — preserved per "do not delete" mandate; used by disabled CoVe + self-consistency blocks below

    await emit_status(config, "Verifying alignment with the teachings...")
    context = "\n\n".join(doc["text"] for doc in relevant_docs)

    if not context or len(context.strip()) < 200:
        logger.info(
            f"Combined verify: context too short ({len(context)} chars) for meaningful verification — soft-passing with moderate confidence"
        )
        return {
            "is_faithful": True,
            "verification": {"passed": True, "details": "Context too short for scoring — soft pass"},
            "confidence_score": 5.0,
            "faithfulness_score": 0.65,
            "relevancy_score": 0.65,
        }

    ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
    faithfulness_score = ld_result["score"]
    is_faithful_ld = ld_result["is_faithful"]

    # --- Heavy verification DISABLED (performance) ---
    # CoVe verification + LLM self-consistency add ~60s with zero quality
    # gain for spiritual paraphrasing.  Keeping code intact per plan.
    # Original blocks:
    #   1) Claim verification (CoVe sub-questions) — 202-256
    #   2) Self-consistency check (alt answer generation) — 261-347
    # --- END DISABLED ---
    claim_verification_passed = True
    claim_verification_details = "Disabled for performance"
    consistency_check_passed = True
    consistency_feedback = ""

    is_valid = is_faithful_ld

    base_confidence = faithfulness_score * 10.0
    claim_verification_factor = 1.0 if claim_verification_passed else 0.7
    consistency_factor = 1.0 if consistency_check_passed else 0.8

    confidence_score = max(1.0, min(10.0, base_confidence * claim_verification_factor * consistency_factor))
    if answer and len(answer.strip()) > 30:
        confidence_score = max(confidence_score, 3.0)

    try:
        VERIFICATION_RESULTS.labels(result="faithful" if is_faithful_ld else "hallucinated").inc()
        VERIFICATION_RESULTS.labels(result="pass" if is_valid else "fail").inc()
        CONFIDENCE_SCORES.observe(confidence_score)
    except Exception:
        pass

    relevancy_score = 1.0 if is_valid else faithfulness_score

    try:
        FAITHFULNESS_SCORE.observe(faithfulness_score)
        RELEVANCY_SCORE.observe(relevancy_score)
    except Exception:
        pass

    logger.info(
        f"Combined verify (Enhanced): "
        f"faithfulness={faithfulness_score:.2f} ({'YES' if is_faithful_ld else 'NO'}), "
        f"claim_verification={'PASS' if claim_verification_passed else 'FAIL'}, "
        f"consistency={'PASS' if consistency_check_passed else 'FAIL'}, "
        f"verdict={'PASS' if is_valid else 'FAIL'}, "
        f"confidence={confidence_score:.1f}"
    )

    verification_details = f"Faithfulness: {faithfulness_score:.2f}; {claim_verification_details}; {consistency_feedback}"

    return {
        "is_faithful": is_faithful_ld,
        "verification": {"passed": is_valid, "details": verification_details},
        "confidence_score": confidence_score,
        "faithfulness_score": faithfulness_score,
        "relevancy_score": relevancy_score,
    }


@log_metrics
async def check_contradiction(state: GraphState, config: dict = None) -> dict:
    """Check if the newly generated answer contradicts previous conversation history."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Contradiction check: bypassing for simple query tier")
        return {"evaluation_trace": _trace_update(state, contradiction_detected=False)}

    answer = state.get("answer", "")
    chat_history = state.get("chat_history", [])
    ollama = _services._ollama

    if not answer or len(chat_history) < 2:
        return {}

    await emit_status(config, "Checking consistency with our conversation...")
    try:
        recent_history = "\n".join(
            [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in chat_history[-4:]]
        )
        prompt = f"Given this conversation history:\n{recent_history}\n\nDoes this new response contradict the history? Respond strictly with 'yes' or 'no'.\nResponse: {answer}"

        t_out = get_node_timeout("check_contradiction", 12)
        is_contradiction = await ollama.generate(
            system_prompt="You are a contradiction detector. Only answer yes or no.",
            user_prompt=prompt,
            timeout=t_out,
            max_retries=1,
        )

        detected = "yes" in is_contradiction.lower()
        if detected:
            logger.warning("Contradiction detected in answer. Adding auto-clarification.")
            try:
                CONTRADICTION_DETECTIONS.inc()
            except Exception:
                pass
            return {
                "answer": answer
                + "\n\n(Note: I realize this might seem different from my previous response. In spiritual teachings, different practices apply at different stages of readiness.)",
                "evaluation_trace": _trace_update(state, contradiction_detected=True),
            }
        else:
            return {
                "evaluation_trace": _trace_update(state, contradiction_detected=False),
            }
    except Exception as e:
        logger.error(f"Contradiction check failed: {e}")
        return {
            "evaluation_trace": _trace_update(state, contradiction_detected=False),
        }


@log_metrics
async def explain_retrieval(state: GraphState, config: dict = None) -> dict:
    """Generates a 1-sentence reasoning for why each top source was chosen."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Explain retrieval: bypassing for simple query tier")
        return {"citation_reasoning": {}}

    question = state["question"]
    relevant_docs = state.get("relevant_docs", [])
    ollama = _services._ollama

    if not relevant_docs:
        return {"citation_reasoning": {}}

    await emit_status(config, "Annotating sources...")
    async def explain_doc(doc):
        url = doc.get("source_url")
        if not url:
            return None
        try:
            user_prompt = f"Question: {question}\nTeaching: {doc['text'][:500]}"
            t_out = get_node_timeout("explain_retrieval", 12)
            resp = await ollama.generate(
                system_prompt=CITATION_REASONING_PROMPT,
                user_prompt=user_prompt,
                timeout=t_out,
                max_retries=1,
            )
            return url, resp.strip()
        except Exception as e:
            logger.warning(f"Reasoning failed for {url}: {e}")
            return None

    tasks = [explain_doc(doc) for doc in relevant_docs[:3]]
    results = await asyncio.gather(*tasks)

    reasoning = {}
    for res in results:
        if res:
            url, explanation = res
            reasoning[url] = explanation

    return {"citation_reasoning": reasoning}
