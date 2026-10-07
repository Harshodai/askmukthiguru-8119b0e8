"""Regression test for the 2026-09-24 segfault recurrence.

Root cause: `TransformerDetector` (lettucedetect) truncates only the CONTEXT
side (`truncation="only_first"`); an oversized ANSWER is never bounded by the
library. Reproduced live in-container: once the answer alone reaches ~4090+
tokens (max_length=4096 default), tokenization raises (observed as both
"Unable to create tensor... excessive nesting" and "Truncation error:
Sequence to truncate too short", depending on the fast/slow tokenizer
backend). Sequences just under that boundary still reach `model.forward()` at
close to the model's max supported length -- the most memory-hungry native
call in the process (attention is O(n^2)) -- the likeliest source of the
"Fatal Python error: Segmentation fault" with only one native call in flight.

`_bound_text_for_detector` truncates the answer up front so neither the
exception nor the near-max-length forward pass can happen, using the
detector's own tokenizer for an exact cut (falling back to a char cap if the
tokenizer isn't reachable).
"""

from __future__ import annotations

from services.lettuce_detect_service import (
    _ANSWER_TOKEN_BUDGET,
    LettuceDetectService,
    _bound_text_for_detector,
)


class _FakeTokenizer:
    """Whitespace tokenizer standing in for the real HF tokenizer."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": text.split()}

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(ids)


class _FakeTransformerDetector:
    def __init__(self):
        self.tokenizer = _FakeTokenizer()
        self.captured_kwargs = None

    def predict(self, **kwargs):
        self.captured_kwargs = kwargs
        return []


class _FakeHallucinationDetector:
    """Mirrors the real `HallucinationDetector` facade: `.detector` holds the
    concrete `TransformerDetector` with the tokenizer, and `.predict()` on the
    facade itself is what `_score_with_real_detector` actually calls."""

    def __init__(self):
        self.detector = _FakeTransformerDetector()

    def predict(self, **kwargs):
        return self.detector.predict(**kwargs)


def test_bound_text_for_detector_truncates_over_budget():
    detector = _FakeHallucinationDetector()
    long_answer = " ".join(f"word{i}" for i in range(5000))
    bounded = _bound_text_for_detector(detector, long_answer, _ANSWER_TOKEN_BUDGET)
    assert len(bounded.split()) == _ANSWER_TOKEN_BUDGET


def test_bound_text_for_detector_leaves_short_text_untouched():
    detector = _FakeHallucinationDetector()
    short_answer = "The Beautiful State is a state of inner wellbeing."
    assert _bound_text_for_detector(detector, short_answer, _ANSWER_TOKEN_BUDGET) == short_answer


def test_bound_text_for_detector_falls_back_to_char_cap_without_tokenizer():
    # Defensive path: some future/mocked detector may not expose .detector.tokenizer.
    bounded = _bound_text_for_detector(object(), "x" * 5000, 100)
    assert len(bounded) == 100


def test_score_with_real_detector_never_sends_oversized_answer_to_predict():
    """End-to-end: a pathologically long answer must reach detector.predict()
    already bounded, regardless of what produced it."""
    service = LettuceDetectService()
    fake = _FakeHallucinationDetector()
    long_answer = " ".join(f"word{i}" for i in range(5000))
    context = "The Beautiful State is described across many teachings."

    result = service._score_with_real_detector(fake, "question", context, long_answer)

    # Never truncated into predict() (that would leave the tail unchecked):
    # the full answer is scored lexically instead, with no native call.
    assert fake.detector.captured_kwargs is None
    assert isinstance(result, dict) and "is_faithful" in result
    assert result["is_faithful"] is False  # nonsense tail is not grounded


def test_score_with_real_detector_short_answer_unaffected():
    service = LettuceDetectService()
    fake = _FakeHallucinationDetector()
    answer = "The Beautiful State is a state of joy and connection."
    context = "The Beautiful State is a state of joy and connection with all."

    service._score_with_real_detector(fake, "question", context, answer)

    # Attribution stripping preserves ordinary text unchanged.
    assert fake.detector.captured_kwargs["answer"] == answer


if __name__ == "__main__":
    test_bound_text_for_detector_truncates_over_budget()
    test_bound_text_for_detector_leaves_short_text_untouched()
    test_bound_text_for_detector_falls_back_to_char_cap_without_tokenizer()
    test_score_with_real_detector_never_sends_oversized_answer_to_predict()
    test_score_with_real_detector_short_answer_unaffected()
    print("OK")
