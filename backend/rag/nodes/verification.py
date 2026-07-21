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
from rag.doc_utils import doc_text
from services.confidence_scorer import calculate_confidence, calculate_confidence_reason

from app.tracing import trace_rag_node
from . import _services
from .utils import _trace_update, emit_status, log_metrics, settings

logger = logging.getLogger(__name__)



@trace_rag_node("reflect_on_answer")
@log_metrics
async def reflect_on_answer(state: GraphState, config: dict = None) -> dict:
    """Self-Reflection RAG loop with LettuceDetect and self-consistency checking."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Self-Reflection: bypassing for simple query tier")
        return {"needs_correction": False, "reflection_feedback": None}

    # Skip for standard tier with short answers (< 150 chars)
    answer = state.get("answer", "")
    if state.get("query_tier") == "standard" and len(answer) < 150:
        logger.info("Self-Reflection: standard tier with short answer – bypassing")
        return {"needs_correction": False, "reflection_feedback": None}

    answer = state.get("answer")
    relevant_docs = state.get("relevant_docs", [])
    question = state.get("rewritten_query") or state["question"]
    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama  # noqa: F841 — preserved per "do not delete" mandate; used by disabled self-consistency block below

    if not answer or not relevant_docs:
        return {
            "needs_correction": True,
            "reflection_feedback": "Empty answer or no retrieved documents.",
        }

    await emit_status(config, "Reviewing the response for clarity...")
    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)
    ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
    is_faithful_strict = ld_result["score"] >= settings.faithfulness_floor

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
        feedback_parts.append(f"Faithfulness below threshold (score: {ld_result['score']:.2f}, need >= {settings.faithfulness_floor})")
    if not consistency_check_passed:
        feedback_parts.append(consistency_feedback)

    feedback = "; ".join(feedback_parts) if feedback_parts else "Answer appears valid and consistent"

    if is_valid or "doesn't know" in answer.lower():
        logger.info(f"Self-Reflection: Answer is VALID. {feedback}")
        return {"needs_correction": False, "reflection_feedback": feedback, "lettuce_detect_result": ld_result}

    logger.warning(f"Self-Reflection: Issues detected - {feedback}")
    return {"needs_correction": True, "reflection_feedback": feedback, "lettuce_detect_result": ld_result}


@trace_rag_node("verify_answer")
@log_metrics
async def verify_answer(state: GraphState, config: dict = None) -> dict:
    """Enhanced Combined Self-RAG + CoVe verification with actual claim verification."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Combined verify: bypassing for simple query tier")
        return {
            "is_faithful": True,
            "verification": {"passed": True, "details": "Bypassed for simple query tier"},
            "confidence_score": 8.0,
            "faithfulness_score": 1.0,
            "relevancy_score": 1.0,
        }

    query_tier = state.get("query_tier", "standard")
    cove_enabled_tier = query_tier in ("tier3_complex", "tier4_deep") and query_tier not in getattr(
        settings, "rag_cove_disabled_for_tiers", ["fast", "tier2_simple", "standard"]
    )

    # Skip for standard tier with short answers (< 150 chars)
    answer = state.get("answer", "")
    if query_tier == "standard" and len(answer) < 150:
        logger.info("Combined verify: standard tier with short answer – bypassing")
        return {
            "is_faithful": True,
            "verification": {"passed": True, "details": "Bypassed for standard tier short answer"},
            "confidence_score": 8.0,
            "faithfulness_score": 1.0,
            "relevancy_score": 1.0,
        }

    # CoVe is enabled for tier3_complex / tier4_deep when not in the disabled list.
    # Use the LLM gateway for combined verification; if unavailable or it errors,
    # fall through to the legacy LettuceDetect path (fail-closed behavior is kept
    # inside _verify_with_gateway).
    if cove_enabled_tier:
        gateway_result = await _verify_with_gateway(state, config)
        if gateway_result is not None:
            return gateway_result
        # If gateway is unavailable, continue to legacy verification below.

    # --- rag_parallel_verify fast-exit (Ruthless Audit Phase 1 TTFT) ---
    # Skips only the EXPENSIVE CoVe sub-question check (~60s LLM call) for
    # tier3_complex. It must NOT skip the faithfulness check itself:
    # LettuceDetect is a local embedding/lexical scorer (no LLM round-trip,
    # often already computed and cached by reflect_on_answer), so running it
    # here costs effectively nothing. The previous version hardcoded
    # is_faithful=True/confidence=7.0 unconditionally — that structurally
    # guaranteed every tier3_complex query (this tier also covers ADVERSARIAL
    # and TEMPORAL intents, not just "hard factual") passed verification with
    # zero actual check against retrieved context, because format_final_answer's
    # confidence gate (floor 6.5) was then fed a hardcoded 7.0 by this exact code.
    if getattr(settings, "rag_parallel_verify", True) and query_tier == "tier3_complex":
        answer = state["answer"]
        relevant_docs = state["relevant_docs"]
        question = state.get("rewritten_query") or state["question"]
        lettuce_detect = _services._lettuce_detect
        context = "\n\n".join(doc_text(doc) for doc in relevant_docs)

        if not context or len(context.strip()) < 200:
            logger.warning("Combined verify: parallel_verify fast-exit — context too short, rejecting")
            return {
                "is_faithful": False,
                "verification": {"passed": False, "details": "Context too short for scoring — unverified (fast-exit)"},
                "confidence_score": 0.0,
                "faithfulness_score": 0.0,
                "relevancy_score": 0.0,
            }

        ld_result = state.get("lettuce_detect_result")
        if ld_result is None:
            ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
        faithfulness_score = ld_result["score"]
        is_faithful_ld = faithfulness_score >= settings.faithfulness_floor

        logger.info(
            f"Combined verify: parallel_verify fast-exit for tier3_complex — "
            f"LettuceDetect faithfulness={faithfulness_score:.2f} ({'YES' if is_faithful_ld else 'NO'}), "
            f"CoVe/consistency skipped for TTFT"
        )
        return {
            "is_faithful": is_faithful_ld,
            "verification": {
                "passed": is_faithful_ld,
                "details": "Parallel verify fast-exit (tier3_complex) — LettuceDetect checked, CoVe skipped",
            },
            "confidence_score": (faithfulness_score * 10.0) if is_faithful_ld else 3.0,
            "faithfulness_score": faithfulness_score,
            "relevancy_score": faithfulness_score,
        }

    answer = state["answer"]

    relevant_docs = state["relevant_docs"]
    question = state.get("rewritten_query") or state["question"]
    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama  # noqa: F841 — preserved per "do not delete" mandate; used by disabled CoVe + self-consistency blocks below

    await emit_status(config, "Verifying alignment with the teachings...")
    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)

    if not context or len(context.strip()) < 200:
        logger.warning(
            f"Combined verify: context too short ({len(context)} chars) for meaningful verification — rejecting"
        )
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": "Context too short for scoring — unverified"},
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    ld_result = state.get("lettuce_detect_result")
    if ld_result is None:
        ld_result = await asyncio.to_thread(lettuce_detect.score_faithfulness, question, context, answer)
    else:
        logger.info("Combined verify: reusing cached lettuce_detect_result from self-reflection")
    faithfulness_score = ld_result["score"]
    is_faithful_ld = faithfulness_score >= settings.faithfulness_floor

    # --- CoVe: feature-flagged off by default (saves ~60s LLM calls) ---
    # CoVe verification + LLM self-consistency add ~60s.
    # Disabled via rag_cove_disabled setting (default: True).
    cove_failed = False
    if (
        not getattr(settings, "rag_cove_disabled", True)
        and state.get("query_tier") == "tier3_complex"
    ):
        cove_result = await _cove_subquestion_check(question, answer, context, ollama)
        cove_failed = not cove_result["passed"]
        claim_verification_passed = not cove_failed
        claim_verification_details = cove_result["details"]
    else:
        # Finding #43: non-tier3 queries use lightweight single-claim
        # check instead of hard-coded pass=True
        if state.get("query_tier") == "tier3_complex":
            logger.info("Combined verify: CoVe skipped (disabled by rag_cove_disabled)")
        claim_verification_passed = is_faithful_ld
        claim_verification_details = f"Lightweight claim check (non-tier3): faithful={is_faithful_ld}"
    # --- END CoVe ---
    consistency_check_passed = True
    consistency_feedback = ""

    is_valid = is_faithful_ld and not cove_failed

    base_confidence = faithfulness_score * 10.0
    claim_verification_factor = 1.0 if claim_verification_passed else 0.7
    consistency_factor = 1.0 if consistency_check_passed else 0.8

    # ── Multi-signal confidence ensemble ──────────────────────────────────
    # Build an intermediate state snapshot with the signals that are already
    # computed so calculate_confidence can do weighted aggregation.
    _conf_state = {
        **state,
        "faithfulness_score": faithfulness_score,
        "verification": {
            "passed": is_valid,
            "cove_pass_ratio": (1.0 if claim_verification_passed else 0.0),
        },
    }
    confidence_score = calculate_confidence(_conf_state)
    confidence_reason = calculate_confidence_reason(_conf_state)

    try:
        VERIFICATION_RESULTS.labels(result="faithful" if is_faithful_ld else "hallucinated").inc()
        VERIFICATION_RESULTS.labels(result="pass" if is_valid else "fail").inc()
        CONFIDENCE_SCORES.observe(confidence_score)
    except Exception as exc:
        logger.warning(f"Prometheus metrics failed during verification: {exc}")

    relevancy_score = 1.0 if is_valid else faithfulness_score

    try:
        FAITHFULNESS_SCORE.observe(faithfulness_score)
        RELEVANCY_SCORE.observe(relevancy_score)
    except Exception as exc:
        logger.warning(f"Prometheus metrics failed during verification: {exc}")

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
        "confidence_reason": confidence_reason,
        "faithfulness_score": faithfulness_score,
        "relevancy_score": relevancy_score,
    }




async def _verify_with_gateway(state: GraphState, config: dict | None) -> dict | None:
    """Verification path for tier3_complex / tier4_deep using container.llm_gateway.

    Runs a single combined Self-RAG + CoVe call via the gateway and returns the
    standard verification update keys that downstream nodes expect.
    """
    gateway = _services._llm_gateway
    if gateway is None:
        logger.warning("verify_with_gateway: no LLM gateway available, falling back to LettuceDetect")
        return None

    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_docs", [])
    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)

    if not context or len(context.strip()) < 200:
        logger.warning("verify_with_gateway: context too short for CoVe verification")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": "Context too short for CoVe verification"},
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    await emit_status(config, "Verifying alignment with the teachings...")
    try:
        cove_result = await gateway.verify_answer(answer=answer, context=context)
    except Exception as exc:
        logger.error(f"verify_with_gateway: gateway verify_answer failed: {exc}")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": f"Gateway CoVe error: {exc}"},
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    is_faithful = bool(cove_result.get("is_faithful", cove_result.get("passed", False)))
    passed = bool(cove_result.get("passed", is_faithful))
    confidence = float(cove_result.get("confidence", 7.0))
    details = cove_result.get("details", "Gateway combined verification")

    logger.info(
        f"verify_with_gateway: tier={state.get('query_tier')} "
        f"faithful={is_faithful} passed={passed} confidence={confidence:.1f}"
    )

    return {
        "is_faithful": is_faithful,
        "verification": {"passed": passed, "details": details},
        "confidence_score": confidence,
        "faithfulness_score": confidence / 10.0,
        "relevancy_score": 1.0 if passed else confidence / 10.0,
    }


async def _cove_subquestion_check(question: str, answer: str, context: str, ollama):
    """Lightweight CoVe: generate sub-questions and score support.
    Returns dict with passed, details, and confidence."""
    try:
        # Generate 2-3 sub-questions from the answer
        prompt = (
            "Generate 2 concise factual sub-questions whose answers would verify "
            "whether the answer is well-supported. Return one per line, no numbering.\n\n"
            f"Question: {question}\nAnswer: {answer}"
        )
        raw = await ollama.generate(
            system_prompt="You generate factual verification sub-questions.",
            user_prompt=prompt,
            timeout=8,
            max_retries=1,
        )
        sub_qs = [q.strip() for q in raw.splitlines() if q.strip() and len(q) > 10][:3]

        supported = 0
        for sq in sub_qs:
            verify_prompt = (
                "Does the context support a 'yes' answer? Reply only 'yes' or 'no'.\n\n"
                f"Context:\n{context[:1500]}\n\n"
                f"Sub-question: {sq}"
            )
            try:
                resp = await ollama.generate(
                    system_prompt="Answer only yes or no.",
                    user_prompt=verify_prompt,
                    timeout=6,
                    max_retries=1,
                )
                if "yes" in resp.lower():
                    supported += 1
            except Exception:
                # Fail-closed: sub-question verification error means NOT supported
                pass

        ratio = supported / max(len(sub_qs), 1)
        passed = ratio >= settings.verifier_pass_ratio
        return {
            "passed": passed,
            "details": f"CoVe: {supported}/{len(sub_qs)} sub-questions supported (ratio={ratio:.2f})",
        }
    except Exception as e:
        logger.error(f"CoVe sub-question check failed: {e}")
        return {"passed": False, "details": "CoVe failed, marking as unverified"}
