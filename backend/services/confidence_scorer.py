"""Mukthi Guru — Multi-Signal Confidence Scorer

Replaces single-signal verification confidence with a calibrated 5-signal
weighted ensemble:

  retrieval quality   25%  — how well top chunks matched the query
  faithfulness        30%  — LettuceDetect / lexical overlap score
  CoVe pass rate      20%  — fraction of claims that passed verification
  contradiction       15%  — 1.0 if no contradiction found, else 0.3
  source authority    10%  — citation quality heuristic

Final score is temperature-scaled (T=1.5) to prevent overconfidence, then
mapped back to the 1–10 scale expected by the rest of the system.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# ── Weights must sum to 1.0 ───────────────────────────────────────────────
_WEIGHTS = {
    "retrieval":     0.25,
    "faithfulness":  0.30,
    "cove":          0.20,
    "contradiction": 0.15,
    "authority":     0.10,
}

# Temperature scaling factor — values > 1 soften overconfident raw scores
_TEMPERATURE = 1.5


def _temperature_scale(raw: float, temperature: float = _TEMPERATURE) -> float:
    """Soften raw probability via temperature scaling (prevents overconfidence)."""
    p = max(1e-6, min(1 - 1e-6, raw))
    logit = math.log(p / (1 - p))
    return 1.0 / (1.0 + math.exp(-logit / temperature))


def _retrieval_confidence(reranked_docs: list) -> float:
    """Estimate retrieval quality from reranked document scores."""
    if not reranked_docs:
        return 0.0
    scores = []
    for doc in reranked_docs[:5]:
        if isinstance(doc, dict):
            score = doc.get("score") or doc.get("rerank_score") or 0.0
        else:
            score = getattr(doc, "score", 0.0) or 0.0
        scores.append(float(score))
    if not scores:
        return 0.5
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def _source_authority(citations: list[str]) -> float:
    """Heuristic authority score based on citation quality and count."""
    if not citations:
        return 0.3
    _HIGH_AUTH_DOMAINS = (
        "ekam.org", "onenessuniversity.org", "theonenessmovement.org",
        "isha.sadhguru.org", "iskcon.org",
    )
    boost = sum(
        1 for c in citations
        if any(d in c.lower() for d in _HIGH_AUTH_DOMAINS)
    )
    base = min(1.0, len(citations) / 5.0)
    return min(1.0, base + boost * 0.1)


def calculate_confidence(state: dict) -> float:
    """Compute calibrated confidence score (1–10) from multi-signal ensemble.

    Args:
        state: LangGraph GraphState dict containing verification results,
               reranked docs, citations, and contradiction flag.

    Returns:
        float in [1.0, 10.0] — consistent with existing confidence_score field.
    """
    try:
        verification = state.get("verification") or {}

        # Signal 1: retrieval quality (0–1)
        reranked_docs = state.get("reranked_docs") or state.get("documents") or []
        retrieval_sig = _retrieval_confidence(reranked_docs)

        # Signal 2: faithfulness from LettuceDetect / lexical overlap (0–1)
        faithfulness_sig = float(
            state.get("faithfulness_score") or verification.get("score", 0.0)
        )
        faithfulness_sig = max(0.0, min(1.0, faithfulness_sig))

        # Signal 3: CoVe pass ratio (0–1); proxy from faithfulness if absent
        cove_sig = float(verification.get("cove_pass_ratio", 0.0))
        cove_sig = max(0.0, min(1.0, cove_sig))
        if cove_sig == 0.0 and faithfulness_sig > 0.0:
            cove_sig = faithfulness_sig * 0.9

        # Signal 4: contradiction (1.0 = clean, 0.3 = contradiction found)
        contradiction_found = (
            state.get("contradiction_found") or 
            state.get("contradiction_detected") or
            (isinstance(state.get("evaluation_trace"), dict) and state.get("evaluation_trace").get("contradiction_detected"))
        )
        contradiction_sig = 0.3 if contradiction_found else 1.0

        # Signal 5: source authority (0–1)
        authority_sig = _source_authority(state.get("citations") or [])

        signals = {
            "retrieval":     retrieval_sig,
            "faithfulness":  faithfulness_sig,
            "cove":          cove_sig,
            "contradiction": contradiction_sig,
            "authority":     authority_sig,
        }

        raw = sum(signals[k] * _WEIGHTS[k] for k in signals)
        calibrated = _temperature_scale(raw)

        # Map (0,1) → [1.0, 10.0] to match existing convention
        score = max(1.0, min(10.0, 1.0 + calibrated * 9.0))

        logger.debug(
            "Confidence ensemble: signals=%s raw=%.3f calibrated=%.3f → %.1f/10",
            {k: round(v, 3) for k, v in signals.items()},
            raw, calibrated, score,
        )
        return round(score, 2)

    except Exception as exc:
        logger.warning("Confidence scorer failed (returning neutral 5.0): %s", exc)
        return 5.0
