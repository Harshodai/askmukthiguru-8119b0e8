"""P1-AI-12 — citation grounding hardening.

Covers two related fixes:
1. ``_check_grounding`` no longer reports "grounded" for an empty context
   when the answer is non-empty (vacuous truth hid ungrounded answers).
2. ``_cite_sentences`` attaches citations only above the raised Jaccard
   threshold (0.30 base; intent overrides unchanged). The 0.18–0.30 band
   now stays uncited.
"""

from rag.nodes.generation import _cite_sentences
from services.citation_service import _check_grounding


def _jaccard_band_answer() -> tuple[str, list[dict]]:
    """Sentence with 3-gram Jaccard ~0.22 (above old 0.18, below new 0.30)."""
    docs = [
        {
            "title": "Ekam Teaching",
            "text": "meditation on the breath is the ancient teaching of ekam wisdom",
        },
    ]
    answer = "the practice of breathing teaches calm and wisdom to every seeker"
    return answer, docs


def test_empty_context_not_grounded():
    """Empty context + non-empty answer -> NOT grounded (was vacuous True)."""
    assert _check_grounding("The guru teaches breath awareness.", []) is False


def test_empty_context_empty_answer_still_grounded():
    """Empty context + empty answer stays trivially grounded (no claims)."""
    assert _check_grounding("", []) is True
    assert _check_grounding("   ", []) is True


def test_low_jaccard_not_cited():
    """Sentence at ~0.22 Jaccard (old 0.18 pass, new 0.30 reject) gets no citation.

    Uses an intent with no per-intent override (MEDITATION) so the raised
    base threshold (0.30) is the one applied.
    """
    answer, docs = _jaccard_band_answer()
    cited = _cite_sentences(answer, docs, intent="MEDITATION")
    assert "[[CITE:" not in cited


def test_high_jaccard_cited():
    """Sentence at ~0.65 Jaccard clears the new 0.30 threshold and is cited."""
    answer = "meditation on the breath and the teaching of ekam wisdom are one"
    docs = [
        {
            "title": "Ekam Teaching",
            "text": "meditation on the breath is the ancient teaching of ekam wisdom",
        },
    ]
    cited = _cite_sentences(answer, docs, intent="MEDITATION")
    assert "[[CITE:1]]" in cited
