"""Showability gates added from the 2026-10-31 Haiku/Opus grading of 40 served answers.

Each rule is general (an opener class or a length window), not a list of graded questions.
They only make serving stricter: a rejected clip is abstained whole, its text never edited.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.first_person_context_harness import _not_standalone
from services.first_person_pipeline import _clip_length_problem, _standalone_problem

_BODY = (
    "Inner peace is not something you chase, it is what remains when the mind stops "
    "arguing with life, and from that stillness you can act with clarity and kindness."
)  # 31 words, no opener trouble


@pytest.fixture(autouse=True)
def _production_length_window(monkeypatch):
    from app.config import settings

    # The defaults the product ships with; conftest widens them for unrelated tests.
    monkeypatch.setattr(settings, "first_person_min_answer_words", 23)
    monkeypatch.setattr(settings, "first_person_max_answer_words", 300)


def test_shipped_defaults_are_23_and_300():
    from app.config import Settings

    fields = Settings.model_fields
    assert fields["first_person_min_answer_words"].default == 23
    assert fields["first_person_max_answer_words"].default == 300


def _span(text: str):
    return SimpleNamespace(verbatim_text=text)


@pytest.mark.parametrize(
    "opener", ["So, ", "Okay, ", "Okay. ", "Well, ", "Right, ", "Alright, ", "Now, ", '"So, ']
)
def test_discourse_openers_are_rejected_even_with_core_keywords(opener):
    text = (
        opener
        + "unconditional love is a connection that does not ask the other to change. "
        + _BODY
    )
    assert _standalone_problem(text) == "discourse_opener"
    assert _not_standalone((_span(text),)) is True


def test_so_without_a_comma_is_still_a_fine_opener():
    text = "So both Preethaji and I have seen this in thousands of people. " + _BODY
    assert _standalone_problem(text) is None
    assert _not_standalone((_span(text),)) is False


@pytest.mark.parametrize("ordinal", ["second", "third", "fourth", "fifth", "next", "last"])
def test_late_ordinal_openers_are_rejected(ordinal):
    text = f"The {ordinal} pillar is meditation for world peace. " + _BODY
    assert _standalone_problem(text) == "discourse_opener"
    assert _not_standalone((_span(text),)) is True


def test_first_ordinal_may_open_a_list():
    text = "The first step is to pause and breathe before you answer. " + _BODY
    assert _standalone_problem(text) is None


def test_length_window():
    assert _clip_length_problem("word " * 22) == "too_short"
    assert _clip_length_problem("word " * 23) is None
    assert _clip_length_problem("word " * 300) is None
    assert _clip_length_problem("word " * 301) == "too_long"


def test_harness_judges_length_on_the_whole_answer_not_per_span():
    half = " ".join(["peace"] * 14)
    assert _not_standalone((_span(half), _span(half))) is False  # 28 words together
    assert _not_standalone((_span(half),)) is True  # 14 words alone


def test_long_run_of_topics_is_rejected():
    text = "Stillness teaches us to listen. " * 80
    assert _not_standalone((_span(text),)) is True


def test_gate_off_switch_still_disables_the_harness_check(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_standalone_gate_enabled", False)
    assert _not_standalone((_span("So, " + _BODY),)) is False


def test_mocked_settings_never_become_a_one_word_cap(monkeypatch):
    from unittest.mock import MagicMock

    import services.first_person_pipeline as pipeline

    monkeypatch.setattr(pipeline, "settings", MagicMock())
    assert pipeline._clip_length_problem("word " * 40) is None  # defaults 25..300 apply


_Q071 = (
    "Every problem at the personal level has one root. Here, individuals would be healed "
    "physically, emotionally and spiritually, and the family relaxes into connection with "
    "each other and with the world around them."
)


def test_healing_claims_are_rejected_on_the_legacy_and_harness_paths():
    assert _standalone_problem(_Q071) == "health_claim"
    assert _not_standalone((_span(_Q071),)) is True


@pytest.mark.parametrize(
    "text",
    [
        "Only connection can heal, and that connection begins with the way you speak to yourself "
        "and to the people you love every single day of your life.",
        "Time and forgiveness heal a broken heart when you stop replaying the story and "
        "return to the present moment with an open and gentle awareness.",
    ],
)
def test_ordinary_use_of_heal_is_still_servable(text):
    assert _standalone_problem(text) is None
    assert _not_standalone((_span(text),)) is False
