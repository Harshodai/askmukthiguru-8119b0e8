"""Mukthi Guru — Multi-Signal Confidence Scorer

Replaces single-signal verification confidence with a calibrated 5-signal
weighted ensemble:

  retrieval quality   20%  — how well top chunks matched the query
  faithfulness        25%  — LettuceDetect / lexical overlap score
  CoVe pass rate      15%  — fraction of claims that passed verification
  contradiction       10%  — 1.0 if no contradiction found, else 0.3
  source authority    10%  — citation quality heuristic
  recency             10%  — newer sources score higher (if published_date)
  llm uncertainty     10%  — 1.0 minus normalized verifier uncertainty

Final score is temperature-scaled (T=1.5) to prevent overconfidence, then
mapped back to the 1–10 scale expected by the rest of the system.

E3.2: also emits a one-line explainable reason string via calculate_confidence_reason.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math

logger = logging.getLogger(__name__)

# ── Weights must sum to 1.0 ───────────────────────────────────────────────
_WEIGHTS = {
    "retrieval":     0.20,
    "faithfulness":  0.25,
    "cove":          0.15,
    "contradiction": 0.10,
    "authority":     0.10,
    "recency":       0.10,
    "llm_unc":       0.10,
}

# Temperature scaling factor — values > 1 soften overconfident raw scores
_TEMPERATURE = 1.5

# Source-type authority ranking (E3.2): book > transcript > video > social > unknown
_SOURCE_AUTHORITY_RANK = {
    "book": 1.0,
    "transcript": 0.9,
    "article": 0.8,
    "video": 0.7,
    "audio": 0.65,
    "social": 0.4,
    "unknown": 0.5,
}


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


def _source_authority_from_docs(reranked_docs: list) -> float:
    """E3.2: authority from doc metadata source_type (book > video > social)."""
    if not reranked_docs:
        return 0.0
    ranks = []
    for doc in reranked_docs[:5]:
        meta = doc.get("metadata", {}) if isinstance(doc, dict) else getattr(doc, "metadata", {})
        if not isinstance(meta, dict):
            continue
        st = (meta.get("source_type") or meta.get("doc_type") or "unknown").lower()
        ranks.append(_SOURCE_AUTHORITY_RANK.get(st, 0.5))
    if not ranks:
        return 0.0
    return sum(ranks) / len(ranks)


def _recency(reranked_docs: list) -> float:
    """E3.2: recency signal from published_date metadata. 1.0 = this year."""
    if not reranked_docs:
        return 0.0
    now = _dt.datetime.utcnow()
    scores = []
    for doc in reranked_docs[:5]:
        meta = doc.get("metadata", {}) if isinstance(doc, dict) else getattr(doc, "metadata", {})
        if not isinstance(meta, dict):
            continue
        pd = meta.get("published_date") or meta.get("date") or meta.get("year")
        if not pd:
            continue
        try:
            if isinstance(pd, (int, float)):
                year = float(pd)
            else:
                s = str(pd)[:10]
                year = float(_dt.datetime.fromisoformat(s).year)
        except Exception:
            continue
        age_years = max(0.0, now.year - year)
        # linear decay: 0yr=1.0, 10yr=0.0
        scores.append(max(0.0, min(1.0, 1.0 - age_years / 10.0)))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _llm_uncertainty(verification: dict) -> float:
    """E3.2: 1.0 = no uncertainty, 0.0 = max uncertainty. Inverts verifier's
    uncertainty/difficulty estimate if present."""
    if not isinstance(verification, dict):
        return 0.0
    unc = verification.get("uncertainty") or verification.get("difficulty") or verification.get("llm_uncertainty")
    if unc is None:
        return 0.0
    try:
        u = float(unc)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, 1.0 - u))


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

        # Signal 5: source authority (0–1) — prefer doc-metadata version, fall back to citations
        authority_sig = _source_authority_from_docs(reranked_docs)
        if authority_sig == 0.0:
            authority_sig = _source_authority(state.get("citations") or [])

        # E3.2 Signal 6: recency (0–1)
        recency_sig = _recency(reranked_docs)

        # E3.2 Signal 7: LLM uncertainty (1.0 = confident, 0.0 = uncertain)
        llm_unc_sig = _llm_uncertainty(verification)

        signals = {
            "retrieval":     retrieval_sig,
            "faithfulness":  faithfulness_sig,
            "cove":          cove_sig,
            "contradiction": contradiction_sig,
            "authority":     authority_sig,
            "recency":       recency_sig,
            "llm_unc":       llm_unc_sig,
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


def calculate_confidence_reason(state: dict) -> str:
    """E3.2: produce a one-line explainable reason for the confidence score.

    Highlights the top contributing factor and any penalty signal.
    Returns a short string safe to surface to UI/debug traces.
    """
    try:
        verification = state.get("verification") or {}
        reranked_docs = state.get("reranked_docs") or state.get("documents") or []
        faithfulness = float(state.get("faithfulness_score") or verification.get("score", 0.0))
        retrieval = _retrieval_confidence(reranked_docs)
        cove = float(verification.get("cove_pass_ratio", 0.0))
        contradiction = (
            state.get("contradiction_found") or
            state.get("contradiction_detected") or
            (isinstance(state.get("evaluation_trace"), dict) and state.get("evaluation_trace").get("contradiction_detected"))
        )
        authority = _source_authority_from_docs(reranked_docs) or _source_authority(state.get("citations") or [])
        recency = _recency(reranked_docs)
        llm_unc = _llm_uncertainty(verification)

        parts = []
        # strongest positive driver
        positives = {
            "faithfulness": faithfulness,
            "retrieval": retrieval,
            "cove": cove,
            "authority": authority,
            "recency": recency,
            "llm_unc": llm_unc,
        }
        top = max(positives, key=positives.get)
        if positives[top] >= 0.7:
            parts.append(f"strong {top}={positives[top]:.2f}")

        # penalties
        if contradiction:
            parts.append("contradiction detected")
        if faithfulness < 0.5:
            parts.append(f"low faithfulness={faithfulness:.2f}")
        if retrieval < 0.4:
            parts.append(f"weak retrieval={retrieval:.2f}")
        if llm_unc < 0.5:
            parts.append(f"verifier uncertain={1 - llm_unc:.2f}")

        if not parts:
            return "balanced signals, no dominant factor"
        return "; ".join(parts)
    except Exception as exc:
        logger.warning("confidence_reason failed: %s", exc)
        return "reason unavailable"


if __name__ == "__main__":
    # Self-check
    s = {
        "reranked_docs": [
            {"score": 0.85, "metadata": {"source_type": "book", "published_date": "2023-05-01"}},
            {"score": 0.78, "metadata": {"source_type": "transcript"}},
        ],
        "faithfulness_score": 0.82,
        "verification": {"cove_pass_ratio": 0.9, "uncertainty": 0.2},
        "citations": ["https://ekam.org/teaching"],
    }
    print(f"confidence={calculate_confidence(s)} reason={calculate_confidence_reason(s)}")
