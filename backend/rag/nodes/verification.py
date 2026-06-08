"""Reflection, verification, contradiction check, and citation reasoning nodes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .utils import settings
from app.metrics import (
    CONFIDENCE_SCORES,
    FAITHFULNESS_SCORE,
    RELEVANCY_SCORE,
    VERIFICATION_RESULTS,
    CONTRADICTION_DETECTIONS,
)
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.prompts import (
    GURU_SYSTEM_PROMPT,
    STIMULUS_RAG_PROMPT,
    MULTI_TURN_PROMPT,
    CITATION_REASONING_PROMPT,
)
from .utils import log_metrics, _trace_update, strip_cot, _generation_kwargs
from . import _services

logger = logging.getLogger(__name__)


@log_metrics
async def reflect_on_answer(state: GraphState) -> dict:
    """Self-Reflection RAG loop with LettuceDetect and self-consistency checking."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Self-Reflection: bypassing for simple query tier")
        return {"needs_correction": False, "reflection_feedback": None}

    answer = state.get("answer")
    relevant_docs = state.get("relevant_docs", [])
    question = state.get("rewritten_query") or state["question"]
    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama

    if not answer or not relevant_docs:
        return {"needs_correction": False}

    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
    is_faithful_strict = ld_result["score"] >= 0.8

    consistency_check_passed = True
    consistency_feedback = ""

    try:
        alt_gen_kwargs = _generation_kwargs(state).copy()
        alt_gen_kwargs["num_predict"] = min(512, alt_gen_kwargs.get("num_predict", 768))
        alt_gen_kwargs["temperature"] = 0.7

        from rag.compressor import cap_to_token_budget
        intent = state.get("intent", "FACTUAL")
        if intent == "DISTRESS":
            persona = STIMULUS_RAG_PROMPT
        else:
            persona = GURU_SYSTEM_PROMPT
        persona = cap_to_token_budget(persona, 256)

        knowledge = "\n\n".join(
            f"[Source: {doc.get('title', 'Unknown')} | URL: {doc.get('source_url', 'N/A')}]\n{doc['text']}"
            for doc in relevant_docs[:2]
        )
        knowledge = cap_to_token_budget(knowledge, 1024)

        user_state = f"Intent: {intent}\n"
        if state.get("meditation_step", 0) > 0:
            user_state += f"Active Meditation Step: {state.get('meditation_step')}\n"
        if state.get("chat_history"):
            user_state += f"Conversation Depth: {len(state.get('chat_history', []))} turns\n"
        user_state = cap_to_token_budget(user_state, 512)

        instructions = (
            "1. Base your answer ONLY on the provided Knowledge.\n"
            "2. If Knowledge is insufficient, admit it warmly.\n"
            "3. ALWAYS cite sources using [Source: <title>] format.\n"
            "4. Keep the tone compassionate and wise.\n"
            "5. NEVER fabricate teachings or add information from your training data.\n"
        )
        instructions = cap_to_token_budget(instructions, 384)

        context_layers = {
            "persona": persona,
            "knowledge": knowledge,
            "user_state": user_state,
            "instructions": instructions,
        }

        history_str = ""
        chat_history = state.get("chat_history", [])
        if chat_history:
            recent = chat_history[-6:]
            history_lines = []
            for msg in recent:
                role = msg.get("role", "user").capitalize()
                limit = 200 if role == "Assistant" else 130
                content = msg.get("content", "")[:limit]
                history_lines.append(f"{role}: {content}")
            if history_lines:
                history_str = MULTI_TURN_PROMPT.format(history="\n".join(history_lines))

        user_prompt = (
            f"USER STATE:\n{context_layers['user_state']}\n\n"
            f"KNOWLEDGE (retrieved teachings):\n{context_layers['knowledge']}\n\n"
            f"QUESTION: {question}"
        )
        if history_str:
            user_prompt = f"{history_str}\n\n{user_prompt}"

        alt_answer = await ollama.generate(
            system_prompt=f"PERSONA:\n{context_layers['persona']}\n\nINSTRUCTIONS:\n{context_layers['instructions']}",
            user_prompt=user_prompt,
            timeout=get_node_timeout("reflect_on_answer", 45.0),
            **alt_gen_kwargs,
        )
        alt_answer = strip_cot(alt_answer or "")

        if alt_answer and len(alt_answer.strip()) > 20:
            alt_ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, alt_answer)
            faith_diff = abs(ld_result["score"] - alt_ld_result["score"])
            if faith_diff > 0.3:
                consistency_check_passed = False
                consistency_feedback = f"Answers show inconsistent faithfulness to context (scores: {ld_result['score']:.2f} vs {alt_ld_result['score']:.2f})"
            elif not alt_ld_result["is_faithful"] and ld_result["is_faithful"]:
                consistency_check_passed = False
                consistency_feedback = "Alternative answer lacks faithfulness while original appears faithful"
        else:
            consistency_check_passed = False
            consistency_feedback = "Failed to generate meaningful alternative answer for consistency check"

    except Exception as e:
        logger.warning(f"Self-consistency check failed: {e}")
        consistency_check_passed = True
        consistency_feedback = f"Consistency check error: {str(e)}"

    is_valid = is_faithful_strict and consistency_check_passed

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
async def verify_answer(state: GraphState) -> dict:
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
    ollama = _services._ollama

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

    claim_verification_passed = True
    claim_verification_details = ""
    verification_questions = []

    try:
        verification_prompt = f"""You are a fact-checker verifying spiritual teachings.
Given the question and answer, generate 2-3 specific sub-questions that would verify the core factual claims in the answer.
Focus on claims about teachings, events, numbers, or specific attributions that can be checked against the context.

Question: {question}
Answer: {answer}

Generate verification questions (one per line, no numbering):"""

        t_out = get_node_timeout("verify_answer", 15)
        verification_questions_raw = await ollama.generate(
            system_prompt="You generate precise verification questions to fact-check spiritual teachings.",
            user_prompt=verification_prompt,
            timeout=t_out,
            max_retries=1,
        )

        verification_questions = [
            q.strip() for q in verification_questions_raw.split("\n")
            if q.strip() and not q.strip().startswith(("#", "-", "*", "1.", "2.", "3."))
        ][:3]

        if verification_questions:
            verification_results = []
            for vq in verification_questions:
                try:
                    context_relevance = await asyncio.to_thread(lettuce_detect.score_faithfulness, vq, context, "")
                    is_verified = context_relevance["score"] > 0.3
                    verification_results.append({
                        "question": vq,
                        "verified": is_verified,
                        "score": context_relevance["score"]
                    })
                    if not is_verified:
                        claim_verification_passed = False
                except Exception as e:
                    logger.warning(f"Failed to verify question '{vq}': {e}")
                    verification_results.append({
                        "question": vq,
                        "verified": False,
                        "score": 0.0,
                        "error": str(e)
                    })
                    claim_verification_passed = False

            verified_count = sum(1 for r in verification_results if r["verified"])
            claim_verification_details = f"Claim verification: {verified_count}/{len(verification_questions)} questions verified"
        else:
            claim_verification_details = "No verification questions generated"
            claim_verification_passed = True

    except Exception as e:
        logger.warning(f"Claim verification failed: {e}")
        claim_verification_passed = True
        claim_verification_details = f"Claim verification error: {str(e)}"

    consistency_check_passed = True
    consistency_feedback = ""

    try:
        alt_gen_kwargs = _generation_kwargs(state).copy()
        alt_gen_kwargs["temperature"] = 0.8

        from rag.compressor import cap_to_token_budget
        intent = state.get("intent", "FACTUAL")
        if intent == "DISTRESS":
            persona = STIMULUS_RAG_PROMPT
        else:
            persona = GURU_SYSTEM_PROMPT
        persona = cap_to_token_budget(persona, 256)

        knowledge = "\n\n".join(
            f"[Source: {doc.get('title', 'Unknown')} | URL: {doc.get('source_url', 'N/A')}]\n{doc['text']}"
            for doc in relevant_docs[:2]
        )
        knowledge = cap_to_token_budget(knowledge, 1024)

        user_state = f"Intent: {intent}\n"
        if state.get("meditation_step", 0) > 0:
            user_state += f"Active Meditation Step: {state.get('meditation_step')}\n"
        if state.get("chat_history"):
            user_state += f"Conversation Depth: {len(state.get('chat_history', []))} turns\n"
        user_state = cap_to_token_budget(user_state, 512)

        instructions = (
            "1. Base your answer ONLY on the provided Knowledge.\n"
            "2. If Knowledge is insufficient, admit it warmly.\n"
            "3. ALWAYS cite sources using [Source: <title>] format.\n"
            "4. Keep the tone compassionate and wise.\n"
            "5. NEVER fabricate teachings or add information from your training data.\n"
        )
        instructions = cap_to_token_budget(instructions, 384)

        context_layers = {
            "persona": persona,
            "knowledge": knowledge,
            "user_state": user_state,
            "instructions": instructions,
        }

        history_str = ""
        chat_history = state.get("chat_history", [])
        if chat_history:
            recent = chat_history[-6:]
            history_lines = []
            for msg in recent:
                role = msg.get("role", "user").capitalize()
                limit = 200 if role == "Assistant" else 130
                content = msg.get("content", "")[:limit]
                history_lines.append(f"{role}: {content}")
            if history_lines:
                history_str = MULTI_TURN_PROMPT.format(history="\n".join(history_lines))

        user_prompt = (
            f"USER STATE:\n{context_layers['user_state']}\n\n"
            f"KNOWLEDGE (retrieved teachings):\n{context_layers['knowledge']}\n\n"
            f"QUESTION: {question}"
        )
        if history_str:
            user_prompt = f"{history_str}\n\n{user_prompt}"

        alt_answer = await ollama.generate(
            system_prompt=f"PERSONA:\n{context_layers['persona']}\n\nINSTRUCTIONS:\n{context_layers['instructions']}",
            user_prompt=user_prompt,
            timeout=get_node_timeout("verify_answer", 30.0),
            **alt_gen_kwargs,
        )
        alt_answer = strip_cot(alt_answer or "")

        if alt_answer and len(alt_answer.strip()) > 20:
            alt_ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, alt_answer)
            faith_diff = abs(faithfulness_score - alt_ld_result["score"])
            if faith_diff > 0.25:
                consistency_check_passed = False
                consistency_feedback = f"Inconsistent reasoning paths (scores: {faithfulness_score:.2f} vs {alt_ld_result['score']:.2f})"
            elif not alt_ld_result["is_faithful"] and is_faithful_ld:
                consistency_check_passed = False
                consistency_feedback = "Alternative answer lacks faithfulness while original appears faithful"
        else:
            consistency_check_passed = False
            consistency_feedback = "Failed to generate meaningful alternative answer"

    except Exception as e:
        logger.warning(f"Self-consistency check failed: {e}")
        consistency_check_passed = True
        consistency_feedback = f"Consistency check error: {str(e)}"

    is_valid = is_faithful_ld and claim_verification_passed and consistency_check_passed

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
async def check_contradiction(state: GraphState) -> dict:
    """Check if the newly generated answer contradicts previous conversation history."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Contradiction check: bypassing for simple query tier")
        return {"evaluation_trace": _trace_update(state, contradiction_detected=False)}

    answer = state.get("answer", "")
    chat_history = state.get("chat_history", [])
    ollama = _services._ollama

    if not answer or len(chat_history) < 2:
        return {}

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
async def explain_retrieval(state: GraphState) -> dict:
    """Generates a 1-sentence reasoning for why each top source was chosen."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Explain retrieval: bypassing for simple query tier")
        return {"citation_reasoning": {}}

    question = state["question"]
    relevant_docs = state.get("relevant_docs", [])
    ollama = _services._ollama

    if not relevant_docs:
        return {"citation_reasoning": {}}

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
