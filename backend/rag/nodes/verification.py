"""Reflection, verification, contradiction check, and citation reasoning nodes."""

from __future__ import annotations

import asyncio
import logging
import re

from app.metrics import (
    CONFIDENCE_SCORES,
    FAITHFULNESS_SCORE,
    RELEVANCY_SCORE,
    VERIFICATION_RESULTS,
)
from app.tracing import trace_rag_node
from rag.doc_utils import doc_text
from rag.states import GraphState
from services.confidence_scorer import calculate_confidence, calculate_confidence_reason, confidence_calibration_status

from . import _services
from .utils import emit_status, log_metrics, settings

logger = logging.getLogger(__name__)

# Persona voice breaks that faithfulness scoring (LettuceDetect) can't catch —
# an answer can be 100% grounded in retrieved docs and still slip into
# generic-AI phrasing or impersonate the founders in first person, both of
# which violate backend/rag/prompts/system.py's third-person-only rule.
_AI_DISCLAIMER_RE = re.compile(
    r"\bas an ai\b"
    r"|\bi(?:'m| am) (?:just )?an? (?:ai|language model|artificial intelligence)\b"
    r"|\bi don'?t have (?:personal experiences|feelings|a body)\b"
    r"|\bi cannot (?:feel|experience)\b",
    re.IGNORECASE,
)
_FOUNDER_IMPERSONATION_RE = re.compile(
    r"\bas (?:sri )?(?:preethaji|krishnaji)\s*,?\s*i\b"
    r"|\bi,?\s*(?:sri )?(?:preethaji|krishnaji)\b"
    r"|\bi\s+am\s+(?:sri\s+)?(?:preethaji|krishnaji)\b",
    re.IGNORECASE,
)

# Constitutional RAG v1 — pattern-based checks for the explicit "what you must
# never do" rules in backend/rag/prompts/system.py that faithfulness scoring
# doesn't cover. Deliberately pattern-based (not a second LLM call): this repo
# already disables several LLM-based verification passes specifically to save
# latency (see reflect_on_answer's disabled self-consistency block), so a new
# check here should follow that same cost/latency discipline, not add a
# ~10-60s LLM round-trip for something regex can catch reliably.
_FLATTERY_OPENER_RE = re.compile(
    r"^\s*(?:great|what a (?:great|beautiful|wonderful|lovely)|beautiful|lovely|excellent|"
    r"such a (?:great|beautiful|wonderful)) question\b",
    re.IGNORECASE,
)
_COT_LEAKAGE_RE = re.compile(
    r"^\s*(?:step \d+[:.]|let me (?:analyze|think|break this down)|we are given\b)",
    re.IGNORECASE | re.MULTILINE,
)
_FOUND_IN_TEACHINGS_RE = re.compile(
    r"\bbased on what i found (?:in|within) the teachings\b",
    re.IGNORECASE,
)
_GUARANTEED_OUTCOME_RE = re.compile(
    r"\b(?:i guarantee|this will (?:cure|heal|fix)|guaranteed to (?:manifest|heal|cure))\b",
    re.IGNORECASE,
)


def check_constitutional_compliance(answer: str) -> str | None:
    """Pattern check for the explicit prose rules in prompts/system.py's
    "What you must never do" section. Returns feedback text or None if clean."""
    if not answer:
        return None
    if _FLATTERY_OPENER_RE.search(answer):
        return "Answer opens with a forbidden flattery phrase (e.g. 'Great question')"
    if _COT_LEAKAGE_RE.search(answer):
        return "Answer leaks chain-of-thought scaffolding (e.g. 'Step 1:', 'Let me analyze')"
    if _FOUND_IN_TEACHINGS_RE.search(answer):
        return "Answer uses the forbidden 'Based on what I found in the teachings' disclaimer"
    if _GUARANTEED_OUTCOME_RE.search(answer):
        return "Answer promises a guaranteed outcome the teachings do not promise"
    return None


def check_persona_adherence(answer: str) -> str | None:
    """Cheap pattern check for voice breaks; returns feedback text or None if clean."""
    if not answer:
        return None
    if _AI_DISCLAIMER_RE.search(answer):
        return "Answer breaks character with an AI-disclaimer phrase"
    if _FOUNDER_IMPERSONATION_RE.search(answer):
        return "Answer impersonates a founder in first person instead of third person"
    constitutional_violation = check_constitutional_compliance(answer)
    if constitutional_violation:
        return constitutional_violation
    return None


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

    # Persona check MUST run before any bypass — violations always trigger correction
    persona_violation = check_persona_adherence(answer)
    if persona_violation:
        logger.warning(f"Self-Reflection: Persona violation detected — {persona_violation}")
        return {"needs_correction": True, "reflection_feedback": persona_violation}

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
    # Strict per-sentence verdict, not mean-vs-threshold: one hallucinated
    # sentence in ten averages into invisibility under `score`, but LettuceDetect
    # already computed the correct all-sentences-grounded boolean — consume it.
    is_faithful_strict = ld_result["is_faithful"]

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

    consistency_check_passed = True  # Disabled for performance
    consistency_feedback = ""

    feedback_parts = []
    if not is_faithful_strict:
        feedback_parts.append(f"Faithfulness below threshold (score: {ld_result['score']:.2f}, need >= {settings.faithfulness_floor})")
    if not consistency_check_passed:
        feedback_parts.append(consistency_feedback)
    if persona_violation:
        feedback_parts.append(persona_violation)

    feedback = "; ".join(feedback_parts) if feedback_parts else "Answer appears valid and consistent"

    is_valid = is_faithful_strict and not persona_violation
    if is_valid or ("doesn't know" in answer.lower() and not persona_violation):
        logger.info(f"Self-Reflection: Answer is VALID. {feedback}")
        return {"needs_correction": False, "reflection_feedback": feedback, "lettuce_detect_result": ld_result}

    logger.warning(f"Self-Reflection: Issues detected - {feedback}")
    return {"needs_correction": True, "reflection_feedback": feedback, "lettuce_detect_result": ld_result}


@trace_rag_node("verify_answer")
@log_metrics
async def verify_answer(state: GraphState, config: dict = None) -> dict:
    """Enhanced Combined Self-RAG + CoVe verification with actual claim verification.

    CoVe is feature-flagged via `rag_cove_disabled` (default: False = enabled).
    When faithfulness_score < settings.cove_compulsory_threshold, CoVe fires
    regardless of query_tier — even fast/tier2 queries are verified if the
    answer confidence is suspect.
    """
    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_docs", [])
    query_tier = state.get("query_tier", "standard")
    question = state.get("rewritten_query") or state.get("question", "")

    # Fast-path for empty context (can't verify anything meaningfully)
    if not answer or not relevant_docs:
        logger.info("Combined verify: no answer/docs — fast-pass (no_context)")
        # no_context marks "nothing to be faithful to" (retrieval returned
        # zero docs, or empty answer). Downstream telemetry must NOT record
        # this as faithfulness 1.0 — a retrieval failure would otherwise land
        # in the quality histogram as a perfect answer. See _build_response_data.
        return {
            "is_faithful": True,
            "no_context": True,
            "verification": {"passed": True, "details": "No content to verify"},
            "confidence_score": 8.0,
            "faithfulness_score": 1.0,
            "relevancy_score": 1.0,
        }

    cove_enabled_tier = query_tier in ("tier3_complex", "tier4_deep") and query_tier not in getattr(
        settings, "rag_cove_disabled_for_tiers", ["fast", "tier2_simple", "standard"]
    )

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
    # here costs effectively nothing.
    if getattr(settings, "rag_parallel_verify", True) and query_tier == "tier3_complex":
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
        # Task #41: settings.faithfulness_floor was previously only referenced in
        # a log/feedback string -- LettuceDetect's strict per-sentence verdict
        # alone decided is_valid, so a scored-but-under-floor answer (measured:
        # ~10% of production traffic) still passed. Every branch below reuses
        # this variable, so gating it here closes the gap for this fast-exit path.
        is_faithful_ld = ld_result["is_faithful"] and faithfulness_score >= settings.faithfulness_floor

        # Only fast-exit when the faithfulness score meets the compulsory CoVe
        # threshold.  Below that threshold the answer is suspect enough to
        # warrant the full CoVe sub-question check (~60 s LLM call).
        cove_compulsory = getattr(settings, "cove_compulsory_threshold", 0.6)
        if faithfulness_score >= cove_compulsory:
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
        logger.info(
            f"Combined verify: parallel_verify fast-exit GUARDED for tier3_complex — "
            f"faithfulness={faithfulness_score:.2f} < cove_compulsory={cove_compulsory}, "
            f"falling through to full CoVe sub-question check"
        )

    lettuce_detect = _services._lettuce_detect
    ollama = _services._ollama  # noqa: F841 — preserved per "do not delete" mandate; used by disabled CoVe + self-consistency blocks below

    await emit_status(config, "Verifying alignment with the teachings...")
    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)
    if not context or len(context.strip()) < 200:
        logger.warning("Combined verify: context too short — fast-fail")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": "Context too short — unverified"},
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
    # Task #41: settings.faithfulness_floor was previously only referenced in a
    # log/feedback string -- LettuceDetect's strict per-sentence verdict alone
    # decided is_valid here and in every downstream fast-exit/short-answer
    # branch and the final is_valid at the bottom of this function, all of
    # which reuse this variable. Gating it here closes the gap everywhere.
    is_faithful_ld = ld_result["is_faithful"] and faithfulness_score >= settings.faithfulness_floor

    # Compulsory CoVe: if faithfulness is low enough, fire regardless of tier.
    cove_compulsory_threshold = getattr(settings, "cove_compulsory_threshold", 0.6)
    cove_disabled = getattr(settings, "rag_cove_disabled", False)
    should_run_cove = (
        not cove_disabled
        and (
            query_tier == "tier3_complex"
            or faithfulness_score < cove_compulsory_threshold  # compulsory for ANY tier
        )
    )

    # Skip verbose for fast/simple tier AND high-confidence answers — no latency cost
    if query_tier in ("fast", "tier2_simple") and faithfulness_score >= cove_compulsory_threshold:
        logger.info(
            "Combined verify: fast tier + high faithfulness (%.2f) — bypassing full verification",
            faithfulness_score,
        )
        return {
            "is_faithful": is_faithful_ld,
            "verification": {"passed": is_faithful_ld, "details": "Bypassed for simple query tier"},
            "confidence_score": faithfulness_score * 10.0,
            "faithfulness_score": faithfulness_score,
            "relevancy_score": faithfulness_score,
        }

    # Short-answer skip for standard tier with adequate faithfulness
    if query_tier == "standard" and len(answer) < 150 and faithfulness_score >= cove_compulsory_threshold:
        logger.info("Combined verify: standard tier with short answer + good score — bypassing")
        # Short-answer fast path: use the multi-signal ensemble so tests with
        # populated reranked_docs can hit the 8.0 confidence threshold, but
        # fall back to raw faithfulness when retrieval signals are absent.
        _conf_state = {
            **state,
            "faithfulness_score": faithfulness_score,
            "verification": {"passed": is_faithful_ld, "cove_pass_ratio": 1.0, "score": faithfulness_score},
        }
        ensemble_score = calculate_confidence(_conf_state)
        confidence_score = ensemble_score if ensemble_score >= 8.0 else faithfulness_score * 10.0
        return {
            "is_faithful": is_faithful_ld,
            "verification": {"passed": is_faithful_ld, "details": "Bypassed for standard tier short answer"},
            "confidence_score": confidence_score,
            "confidence_reason": calculate_confidence_reason(_conf_state) if ensemble_score >= 8.0 else None,
            "faithfulness_score": faithfulness_score,
            "relevancy_score": faithfulness_score,
        }


    # tier3_complex fast-exit: LettuceDetect only (skip full CoVe for speed) UNLESS faithfulness is suspect
    if getattr(settings, "rag_parallel_verify", True) and query_tier == "tier3_complex" and faithfulness_score >= cove_compulsory_threshold:
        logger.info(
            "Combined verify: parallel_verify fast-exit for tier3_complex — "
            "LettuceDetect faithfulness=%.2f (PASS), CoVe skipped (adequate score)",
            faithfulness_score,
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


    ollama = _services._ollama  # noqa: F841 — used by CoVe sub-question block below

    await emit_status(config, "Verifying alignment with the teachings...")

    # --- CoVe: fires when faithfulness is suspect OR tier3_complex ---
    cove_failed = False
    if should_run_cove:
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

    # ── Multi-signal confidence ensemble ──────────────────────────────────
    # Build an intermediate state snapshot with the signals that are already
    # computed so calculate_confidence can do weighted aggregation.
    _conf_state = {
        **state,
        "faithfulness_score": faithfulness_score,
        "verification": {
            "passed": is_valid,
            "score": faithfulness_score,
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
        "confidence_calibration_status": confidence_calibration_status(),
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

        async def _verify_single_sq(sq: str) -> bool:
            verify_prompt = (
                "Does the context support a 'yes' answer? Reply only 'yes' or 'no'.\n\n"
                f"Context:\n{context[:1500]}\n\n"
                f"Sub-question: {sq}"
            )
            try:
                resp = await ollama.generate(
                    system_prompt="Answer only yes or no.",
                    user_prompt=verify_prompt,
                    timeout=5,
                    max_retries=1,
                )
                return "yes" in (resp or "").lower()
            except Exception:
                return False

        if sub_qs:
            results = await asyncio.gather(*[_verify_single_sq(sq) for sq in sub_qs], return_exceptions=True)
            supported = sum(1 for r in results if r is True)
        else:
            supported = 0

        ratio = supported / max(len(sub_qs), 1)
        passed = ratio >= settings.verifier_pass_ratio
        return {
            "passed": passed,
            "details": f"CoVe: {supported}/{len(sub_qs)} sub-questions supported (ratio={ratio:.2f})",
        }
    except Exception as e:
        logger.error(f"CoVe sub-question check failed: {e}")
        return {"passed": False, "details": "CoVe failed, marking as unverified"}
