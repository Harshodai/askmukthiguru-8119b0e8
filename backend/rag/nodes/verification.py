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
from services.confidence_scorer import (
    calculate_confidence,
    calculate_confidence_reason,
    confidence_calibration_status,
)

from . import _services
from .utils import emit_status, log_metrics, settings

logger = logging.getLogger(__name__)


async def _score_faithfulness_bounded(
    lettuce_detect,
    question: str,
    context: str,
    answer: str,
    *,
    semantic: bool = False,
) -> dict:
    """Run the local faithfulness scorer under a hard wall-clock budget."""
    if lettuce_detect is None:
        return {
            "score": 0.0,
            "is_faithful": False,
            "details": "LettuceDetect service not available",
            "claims": [],
            "unsupported_sentences": [],
        }
    timeout = float(getattr(settings, "faithfulness_verification_timeout", 8.0))
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                lettuce_detect.score_faithfulness,
                question,
                context,
                answer,
                semantic=semantic,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.warning(
            "Faithfulness scorer exceeded %.1fs deadline; returning unverified verdict",
            timeout,
        )
        return {
            "score": 0.0,
            "is_faithful": False,
            "timed_out": True,
            "claims": [],
            "unsupported_sentences": [],
        }
    except Exception as exc:
        # production-audit finding F2: this used to catch ONLY TimeoutError, so
        # any other LettuceDetect exception (a bug, an unexpected input shape)
        # propagated past this function to the generic per-node error boundary
        # (log_metrics in utils.py), whose fallback dict does not set
        # is_faithful/verification at all — it just preserves whatever state
        # already held, which is not the same as an explicit fail-closed
        # verdict. Return the same unverified shape as the timeout branch so
        # the caller always gets a real, fail-closed verdict from this
        # function rather than an uncaught exception.
        logger.warning("Faithfulness scorer raised %s; returning unverified verdict", exc)
        return {
            "score": 0.0,
            "is_faithful": False,
            "error": str(exc),
            "claims": [],
            "unsupported_sentences": [],
        }


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
_BOUNDED_ABSTENTION_RE = re.compile(
    r"(?:i\s+(?:don['’]t|do not)\s+have\s+that\s+specific\s+teaching|"
    r"please\s+try\s+asking\s+another\s+question|"
    r"i\s+don['’]t\s+have\s+enough\s+(?:reliable\s+)?information)",
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
    verification = state.get("verification") or {}
    ver_method = verification.get("method") if isinstance(verification, dict) else None
    if (
        state.get("route_decision") == "no_context_short_circuit"
        or (state.get("evaluation_trace") or {}).get("route_decision") == "no_context_short_circuit"
        or ver_method == "no_context_short_circuit"
    ):
        return {
            "is_valid": True,
            "needs_correction": False,
            "grounding_state": "abstained",
            "verification": {"passed": True, "method": "no_context_short_circuit"},
        }

    # Persona and faithfulness checks run for every generated answer. Fast/simple
    # tiers may use the bounded local scorer, but never skip verification structurally.
    answer = state.get("answer", "")
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
    # Deep verification remains semantic and authoritative below; reflection is
    # a correction hint only, so keep its pass bounded and avoid duplicate CPU
    # embedding work on complex answers.
    reflection_semantic = state.get("query_tier") not in ("tier3_complex", "deep")
    ld_result = await _score_faithfulness_bounded(
        lettuce_detect,
        question,
        context,
        answer,
        semantic=reflection_semantic,
    )
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
        feedback_parts.append(
            f"Faithfulness below threshold (score: {ld_result['score']:.2f}, need >= {settings.faithfulness_floor})"
        )
    if not consistency_check_passed:
        feedback_parts.append(consistency_feedback)
    if persona_violation:
        feedback_parts.append(persona_violation)

    feedback = (
        "; ".join(feedback_parts) if feedback_parts else "Answer appears valid and consistent"
    )

    is_valid = is_faithful_strict and not persona_violation
    if is_valid or ("doesn't know" in answer.lower() and not persona_violation):
        logger.info(f"Self-Reflection: Answer is VALID. {feedback}")
        return {
            "needs_correction": False,
            "reflection_feedback": feedback,
            "lettuce_detect_result": ld_result,
        }

    logger.warning(f"Self-Reflection: Issues detected - {feedback}")
    return {
        "needs_correction": True,
        "reflection_feedback": feedback,
        "lettuce_detect_result": ld_result,
    }


@trace_rag_node("verify_answer")
@log_metrics
async def verify_answer(state: GraphState, config: dict = None) -> dict:
    """Enhanced Combined Self-RAG + CoVe verification with actual claim verification.

    Local NLI claim entailment (LettuceDetect) directly informs is_valid and
    the returned verification dictionary. When claim-level support passes
    (faithfulness >= settings.faithfulness_floor and no unsupported claims),
    verification is accepted locally without dispatching an expensive secondary
    LLM round-trip.
    """
    verification = state.get("verification") or {}
    ver_method = verification.get("method") if isinstance(verification, dict) else None
    if (
        state.get("route_decision") == "no_context_short_circuit"
        or (state.get("evaluation_trace") or {}).get("route_decision") == "no_context_short_circuit"
        or ver_method == "no_context_short_circuit"
    ):
        return {
            "is_valid": True,
            "needs_correction": False,
            "grounding_state": "abstained",
            "verification": {"passed": True, "method": "no_context_short_circuit"},
        }

    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_docs", [])
    query_tier = state.get("query_tier", "standard")
    question = state.get("rewritten_query") or state.get("question", "")

    # Safety redirects and canonical bounded abstentions contain no doctrine
    # claim to verify. Do not spend a compulsory CoVe/embedding pass on them.
    # This removes the observed 40–70s dead-end path while keeping the response
    # explicitly ungrounded and non-cacheable downstream.
    if answer and (
        state.get("intent") in {"SAFETY_VIOLATION", "ERROR"}
        or _BOUNDED_ABSTENTION_RE.search(answer)
    ):
        return {
            "is_faithful": True,
            "verification": {
                "passed": True,
                "details": "Bounded safety/abstention response; claim verification skipped",
                "claims": [],
            },
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

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
            "grounding_state": "abstained",
            "verification": {
                "passed": True,
                "details": "No content to verify",
                "claims": [],
            },
            "confidence_score": 2.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)
    if not context or len(context.strip()) < 200:
        logger.warning("Combined verify: context too short — fast-fail")
        return {
            "is_faithful": False,
            "verification": {
                "passed": False,
                "details": "Context too short — unverified",
                "claims": [],
            },
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    lettuce_detect = _services._lettuce_detect
    ld_result = state.get("lettuce_detect_result")
    if ld_result is None:
        await emit_status(config, "Verifying alignment with the teachings...")
        ld_result = await _score_faithfulness_bounded(
            lettuce_detect, question, context, answer, semantic=True
        )
    else:
        logger.info("Combined verify: reusing cached lettuce_detect_result from self-reflection")

    faithfulness_score = float(ld_result.get("score", 0.0))
    claims = list(ld_result.get("claims", []))
    unsupported_sentences = list(ld_result.get("unsupported_sentences", []))

    # Evaluate claim-level support
    unsupported_claims = [c for c in claims if not c.get("supported", False)]
    has_unsupported_claims = bool(unsupported_claims) or bool(unsupported_sentences)
    faithfulness_floor = float(getattr(settings, "faithfulness_floor", 0.70))
    meets_faithfulness_floor = faithfulness_score >= faithfulness_floor
    claim_level_passed = (
        bool(ld_result.get("is_faithful", False))
        and meets_faithfulness_floor
        and not has_unsupported_claims
    )

    # A2.6 / A2.7: When claim-level support passes (faithfulness >= settings.faithfulness_floor
    # and no unsupported critical claims), accept the verification locally without dispatching
    # an expensive secondary LLM verification round-trip.
    if claim_level_passed:
        logger.info(
            "Combined verify: Local NLI claim entailment passed — "
            "faithfulness=%.2f (floor=%.2f), claims=%d/%d supported. "
            "Skipping expensive secondary LLM round-trip.",
            faithfulness_score,
            faithfulness_floor,
            len(claims) - len(unsupported_claims),
            len(claims),
        )
        _conf_state = {
            **state,
            "faithfulness_score": faithfulness_score,
            "verification": {
                "passed": True,
                "score": faithfulness_score,
                "cove_pass_ratio": 1.0,
                "claims": claims,
            },
        }
        ensemble_score = calculate_confidence(_conf_state)
        confidence_score = ensemble_score if ensemble_score >= 8.0 else faithfulness_score * 10.0
        confidence_reason = calculate_confidence_reason(_conf_state) if ensemble_score >= 8.0 else None

        try:
            VERIFICATION_RESULTS.labels(result="faithful").inc()
            VERIFICATION_RESULTS.labels(result="pass").inc()
            CONFIDENCE_SCORES.observe(confidence_score)
            FAITHFULNESS_SCORE.observe(faithfulness_score)
            RELEVANCY_SCORE.observe(1.0)
        except Exception as exc:
            logger.warning(f"Prometheus metrics failed during verification: {exc}")

        details = (
            f"Local NLI claim verification passed "
            f"({len(claims)} claims grounded, score: {faithfulness_score:.2f})"
            if claims
            else f"Local NLI verification passed (score: {faithfulness_score:.2f})"
        )

        return {
            "is_faithful": True,
            "verification": {
                "passed": True,
                "details": details,
                "cove_pass_ratio": 1.0,
                "claims": claims,
            },
            "confidence_score": confidence_score,
            "confidence_reason": confidence_reason,
            "confidence_calibration_status": confidence_calibration_status(),
            "faithfulness_score": faithfulness_score,
            "relevancy_score": 1.0,
        }

    # When claim-level support fails (low faithfulness score or unsupported claims):
    # Check if secondary LLM verification via gateway is configured for complex queries.
    cove_enabled_tier = (
        not getattr(settings, "rag_cove_disabled", False)
        and query_tier in ("tier3_complex", "tier4_deep")
        and query_tier
        not in getattr(
            settings, "rag_cove_disabled_for_tiers", ["fast", "tier2_simple", "standard"]
        )
    )

    if cove_enabled_tier and _services._llm_gateway is not None:
        state_with_ld = dict(state)
        state_with_ld["lettuce_detect_result"] = ld_result
        gateway_result = await _verify_with_gateway(state_with_ld, config)
        if gateway_result is not None:
            if "verification" in gateway_result:
                if not gateway_result["verification"].get("claims"):
                    gateway_result["verification"]["claims"] = claims
            return gateway_result

    # Compulsory CoVe check with Ollama if configured
    cove_compulsory_threshold = float(getattr(settings, "cove_compulsory_threshold", 0.6))
    cove_disabled = bool(getattr(settings, "rag_cove_disabled", False))
    should_run_cove = not cove_disabled and (
        query_tier in ("tier3_complex", "tier4_deep")
        or faithfulness_score < cove_compulsory_threshold
    )

    cove_failed = True
    cove_pass_ratio = 0.0
    cove_details = ""
    ollama = _services._ollama
    if should_run_cove and ollama:
        try:
            cove_result = await asyncio.wait_for(
                _cove_subquestion_check(question, answer, context, ollama),
                timeout=float(getattr(settings, "cove_verification_timeout", 12.0)),
            )
            cove_failed = not cove_result["passed"]
            cove_pass_ratio = float(cove_result.get("ratio", 0.0 if cove_failed else 1.0))
            cove_details = cove_result.get("details", "")
        except TimeoutError:
            logger.warning("Combined verify: CoVe deadline exceeded; using bounded unverified verdict")
            cove_details = "CoVe deadline exceeded"
        except Exception as e:
            logger.warning(f"Combined verify: CoVe check failed: {e}")
            cove_details = f"CoVe error: {e}"

    is_valid = claim_level_passed and not cove_failed

    _conf_state = {
        **state,
        "faithfulness_score": faithfulness_score,
        "verification": {
            "passed": is_valid,
            "score": faithfulness_score,
            "cove_pass_ratio": cove_pass_ratio,
            "claims": claims,
        },
    }
    confidence_score = calculate_confidence(_conf_state)
    confidence_reason = calculate_confidence_reason(_conf_state) if is_valid else None

    try:
        VERIFICATION_RESULTS.labels(result="faithful" if is_valid else "hallucinated").inc()
        VERIFICATION_RESULTS.labels(result="pass" if is_valid else "fail").inc()
        CONFIDENCE_SCORES.observe(confidence_score)
        FAITHFULNESS_SCORE.observe(faithfulness_score)
        RELEVANCY_SCORE.observe(1.0 if is_valid else faithfulness_score)
    except Exception as exc:
        logger.warning(f"Prometheus metrics failed during verification: {exc}")

    unsupported_summary = (
        "; ".join(f"'{c.get('text', '')}'" for c in unsupported_claims)
        if unsupported_claims
        else "; ".join(f"'{s}'" for s in unsupported_sentences)
    )
    verification_details = (
        f"Faithfulness: {faithfulness_score:.2f} (floor={faithfulness_floor:.2f}); "
        f"Unsupported claims: {unsupported_summary or 'none'}"
    )
    if cove_details:
        verification_details += f"; {cove_details}"

    return {
        "is_faithful": is_valid,
        "verification": {
            "passed": is_valid,
            "details": verification_details,
            "cove_pass_ratio": cove_pass_ratio,
            "claims": claims,
        },
        "confidence_score": confidence_score,
        "confidence_reason": confidence_reason,
        "confidence_calibration_status": confidence_calibration_status(),
        "faithfulness_score": faithfulness_score,
        "relevancy_score": 1.0 if is_valid else faithfulness_score,
    }


async def _verify_with_gateway(state: GraphState, config: dict | None) -> dict | None:
    """Verification path for tier3_complex / tier4_deep using container.llm_gateway.

    Runs a single combined Self-RAG + CoVe call via the gateway and returns the
    standard verification update keys that downstream nodes expect.
    """
    gateway = _services._llm_gateway
    if gateway is None:
        logger.warning(
            "verify_with_gateway: no LLM gateway available, falling back to LettuceDetect"
        )
        return None

    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_docs", [])
    context = "\n\n".join(doc_text(doc) for doc in relevant_docs)

    ld_result = state.get("lettuce_detect_result")
    claims = list(ld_result.get("claims", [])) if isinstance(ld_result, dict) else []

    if not context or len(context.strip()) < 200:
        logger.warning("verify_with_gateway: context too short for CoVe verification")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": "Context too short for CoVe verification", "claims": claims},
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }

    await emit_status(config, "Verifying alignment with the teachings...")
    try:
        cove_result = await asyncio.wait_for(
            gateway.verify_answer(answer=answer, context=context),
            timeout=float(getattr(settings, "cove_verification_timeout", 12.0)),
        )
    except TimeoutError:
        logger.warning("verify_with_gateway: gateway verification exceeded bounded deadline")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": "Gateway CoVe deadline exceeded; answer remains unverified", "claims": claims},
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "relevancy_score": 0.0,
        }
    except Exception as exc:
        logger.error(f"verify_with_gateway: gateway verify_answer failed: {exc}")
        return {
            "is_faithful": False,
            "verification": {"passed": False, "details": f"Gateway CoVe error: {exc}", "claims": claims},
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
        "verification": {"passed": passed, "details": details, "claims": claims},
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
            results = await asyncio.gather(
                *[_verify_single_sq(sq) for sq in sub_qs], return_exceptions=True
            )
            supported = sum(1 for r in results if r is True)
        else:
            supported = 0

        ratio = supported / max(len(sub_qs), 1)
        supported_threshold = float(getattr(settings, "cove_supported_threshold", 0.8))
        partial_threshold = float(getattr(settings, "cove_partial_threshold", 0.5))
        # Normalize ordering: a partial threshold above the supported threshold
        # would dead-code the partially_supported branch.
        partial_threshold = min(partial_threshold, supported_threshold)

        if ratio >= supported_threshold:
            passed = True
            verdict = "supported"
        elif ratio >= partial_threshold:
            passed = True
            verdict = "partially_supported"
        else:
            passed = False
            verdict = "unsupported"

        return {
            "passed": passed,
            "ratio": ratio,
            "verdict": verdict,
            "details": f"CoVe: {supported}/{len(sub_qs)} sub-questions supported (ratio={ratio:.2f}, verdict={verdict})",
        }
    except Exception as e:
        logger.error(f"CoVe sub-question check failed: {e}")
        return {"passed": False, "details": "CoVe failed, marking as unverified"}
