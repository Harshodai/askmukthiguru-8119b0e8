"""Scorer attempt budget: one provider latency spike must not poison the whole turn.

Measured 2026-11-10 on the live stack: two doctrine questions ended as
``relevance_indeterminate`` ("I couldn't finish checking the teachings") at 16.2 s and
16.5 s, each with 5-6 contexts reporting ``first-person LLM call exceeded 15.00s``,
while the same provider answered 16 concurrent scorer calls in <=5.1 s minutes later.
Under the sequential contract an indeterminate context blocks every later one, so a
single dithering provider call cost the seeker the whole answer.

The scorer asks a read-only digit question, so a timeout or a dropped connection is
repeated once (``first_person_relevance_max_attempts``) — but only when the failed
attempt died quickly. A call that consumed most of the deadline is provider congestion,
and repeating it doubled a live 15 s stall to 31.4 s (measured 2026-11-11). A refusal, a
rate-limit push-back, a budget denial or a malformed reply is never repeated, and a turn
where every attempt fails still abstains as indeterminate.
"""

from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _RELEVANCE_INDETERMINATE,
    _is_scorer_retryable,
    _relevance_select_scored_async,
)

_CLIPS = [
    {"verbatim_text": "When the mind is agitated it has separated itself from this moment."},
    {"verbatim_text": "A beautiful state is not a mood; it is the absence of seeking."},
]


@pytest.fixture(autouse=True)
def _isolate_relevance_scorer(monkeypatch):
    """Pin comma-separated scorer contract independent of local .env model/threshold overrides."""
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    monkeypatch.setattr(settings, "first_person_relevance_exact_n_enabled", False)


class _ScriptedScorer:
    """Fake provider: plays a scripted outcome per call, records the call count."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate(self, **_kwargs: object) -> str:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return str(outcome)


class _SlowScorer:
    """Fake provider whose call actually sleeps, so the deadline can expire for real."""

    def __init__(self, delay_s: float, outcome: object = "3,1") -> None:
        self.delay_s = delay_s
        self.outcome = outcome
        self.calls = 0

    async def generate(self, **_kwargs: object) -> str:
        self.calls += 1
        await asyncio.sleep(self.delay_s)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return str(self.outcome)


def _score(llm: object) -> int | None:
    return asyncio.run(
        _relevance_select_scored_async("Why is my mind restless?", _CLIPS, llm),
    )


def test_timeout_is_retried_once_and_the_turn_still_serves(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 2)
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 5.0)
    scorer = _ScriptedScorer(TimeoutError("first-person LLM call exceeded 15.00s"), "3,1")

    assert _score(scorer) == 0
    assert scorer.calls == 2


def test_two_timeouts_still_abstain_as_indeterminate(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 2)
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 5.0)
    scorer = _ScriptedScorer(
        TimeoutError("first-person LLM call exceeded 15.00s"),
        TimeoutError("first-person LLM call exceeded 15.00s"),
        "3,1",
    )

    assert _score(scorer) == _RELEVANCE_INDETERMINATE
    assert scorer.calls == 2, "the attempt budget is honoured, not exhausted by luck"


def test_dropped_connection_is_retried(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 2)
    scorer = _ScriptedScorer(ConnectionError("connection reset by peer"), "0,3")

    assert _score(scorer) == 1
    assert scorer.calls == 2


def test_malformed_reply_is_not_retried(monkeypatch):
    """A reply we cannot parse is a verdict about the scorer, not jitter."""
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 2)
    scorer = _ScriptedScorer("I think both are lovely", "3,1")

    assert _score(scorer) == _RELEVANCE_INDETERMINATE
    assert scorer.calls == 1


def test_full_deadline_stall_is_not_retried(monkeypatch):
    """A call that burned the whole deadline is congestion; repeating it doubles the wait.

    Measured live 2026-11-11: the retry re-timed-out and turned a 15 s stall into 31.4 s
    with zero benefit, so the retry is reserved for quick transport failures.
    """
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 2)
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 0.05)
    scorer = _SlowScorer(delay_s=1.0, outcome="3,1")

    assert _score(scorer) == _RELEVANCE_INDETERMINATE
    assert scorer.calls == 1, "a deadline-burning attempt must not be repeated"


def test_retry_budget_of_one_disables_the_retry(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_max_attempts", 1)
    scorer = _ScriptedScorer(TimeoutError("first-person LLM call exceeded 15.00s"), "3,1")

    assert _score(scorer) == _RELEVANCE_INDETERMINATE
    assert scorer.calls == 1


@pytest.mark.parametrize(
    ("exc", "retryable"),
    [
        (TimeoutError("deadline"), True),
        (ConnectionError("connection reset"), True),
        (ValueError("response is not a JSON object"), False),
        (RuntimeError("budget denied"), False),
    ],
)
def test_retryable_classifier(exc: BaseException, retryable: bool):
    assert _is_scorer_retryable(exc) is retryable


def test_attempt_budget_is_bounded_in_settings():
    field = settings.model_fields["first_person_relevance_max_attempts"]
    assert field.default == 2
    kinds = {type(m).__name__ for m in (field.metadata or ())}
    assert {"Ge", "Le"} <= kinds, "a bare int would let 0 or 99 attempts through"
