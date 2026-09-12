"""The real-detector adapter must report a score the floor can be compared to.

Measured live 2026-09-12: with the ModernBERT detector enabled, every answer
carrying a single flagged span scored ~0.00 against faithfulness_floor=0.60,
because `score` was `1 - max_span_confidence` rather than a grounded
proportion. Separately, spans were matched against claims without normalising
whitespace/case, so `claims` reported every sentence supported while
`unsupported_sentences` listed the flagged spans.
"""

from services.lettuce_detect_service import LettuceDetectService, _norm_for_span_match


class _FakeDetector:
    def __init__(self, spans):
        self._spans = spans

    def predict(self, **kwargs):
        return self._spans


CONTEXT = "Sri Preethaji teaches that the Beautiful State is a state of inner connection. " * 6
ANSWER = (
    "The Beautiful State is a state of inner connection. "
    "It is marked by calm and clarity. "
    "Mars was colonised in 1823 by the founders."
)


def _score(spans):
    svc = LettuceDetectService(embedder=None)
    return svc._score_with_real_detector(_FakeDetector(spans), "q", CONTEXT, ANSWER)


def test_score_is_grounded_proportion_not_confidence_complement():
    r = _score([{"text": " Mars was colonised in 1823 by the founders.", "confidence": 0.99}])
    # Two of three claims are grounded; the old formula returned 1 - 0.99 = 0.01.
    assert r["score"] > 0.6, r["score"]
    assert r["max_span_confidence"] == 0.99


def test_claims_and_unsupported_sentences_agree():
    r = _score([{"text": " Mars was colonised in 1823 by the founders.", "confidence": 0.99}])
    unsupported = [c for c in r["claims"] if not c["supported"]]
    assert len(unsupported) == 1
    assert "Mars" in unsupported[0]["text"]


def test_still_fails_closed_when_a_span_is_flagged():
    r = _score([{"text": " Mars was colonised in 1823 by the founders.", "confidence": 0.99}])
    assert r["is_faithful"] is False


def test_wholly_fabricated_answer_scores_low():
    spans = [
        {"text": " The Beautiful State is a state of inner connection.", "confidence": 0.9},
        {"text": " It is marked by calm and clarity.", "confidence": 0.9},
        {"text": " Mars was colonised in 1823 by the founders.", "confidence": 0.99},
    ]
    assert _score(spans)["score"] == 0.0


def test_norm_collapses_whitespace_and_case():
    assert _norm_for_span_match("  The  Beautiful   STATE ") == "the beautiful state"


def test_inline_citation_markers_are_not_scored_as_claims():
    """`[Source: ...]` is formatter output; a detector cannot ground it."""
    from services.lettuce_detect_service import _strip_attribution_markup

    raw = (
        "The Beautiful State is inner connection. [Source: A TEDx Talk]\n\n"
        "Suffering is self-centric thinking [CITE:2] and separation [3].\n"
        "📚 *Sources & Teachings:* ...trailer..."
    )
    cleaned = _strip_attribution_markup(raw)
    assert "Source:" not in cleaned
    assert "CITE" not in cleaned
    assert "📚" not in cleaned
    assert "Beautiful State is inner connection" in cleaned
    assert "self-centric thinking" in cleaned


def test_marker_only_difference_does_not_change_the_verdict():
    plain = "The Beautiful State is a state of inner connection."
    marked = "The Beautiful State is a state of inner connection. [Source: A Talk]"
    svc = LettuceDetectService(embedder=None)
    a = svc._score_heuristic("q", CONTEXT, plain)
    b = svc._score_heuristic("q", CONTEXT, marked)
    assert a["is_faithful"] == b["is_faithful"]
    assert round(a["score"], 6) == round(b["score"], 6)
