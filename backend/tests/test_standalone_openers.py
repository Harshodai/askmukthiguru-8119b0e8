"""Regression table: anaphoric openers the 2026-11-12 graded-6 strict review judged dangling.

Only anaphoric openers are gated here. Enumeration and event-wording defects (q068, q071, q072,
q079) are NOT covered by this rule and stay open; they are not claimed as fixed.

Each clip below was served to a seeker in graded-6 (rows.jsonl) and the strict end-to-end
reader marked it as a dangling opener. The standalone gate must refuse these openers.
Negative controls keep legitimate openers and mid-talk wording servable.
"""

import pytest

from services.first_person_evidence_policy import _standalone_problem

DANGLING_OPENERS = {
    "q029_here_you_receive": (
        "Here you receive three blessings. At Ekam, you have a direct experience of the Divine "
        "in the form you worship, and that experience changes how you live from one day to the next."
    ),
    "q081_since_your_fuel": (
        "Since your fuel is anger and hate, you have to constantly remind yourself of the badness of "
        "those feelings, and that constant effort wears down the energy you need for living."
    ),
    "q043_when_this_breaks_down": (
        "When this communication breaks down, let us say that this communication is not proper and "
        "that the person on the other side has stopped listening to what is being said at all."
    ),
}

NEGATIVE_CONTROLS = {
    "mid_clip_one_way_phrase": (
        "The mind is restless because it keeps chasing outcomes. One way to do it is to sit quietly "
        "and watch the breath for a few minutes each morning without judging any thought that arises."
    ),
    "plain_standalone_teaching": (
        "The way to free the mind is to stop feeding it with fear, because fear grows in the attention "
        "that is given to it and shrinks when the attention is quietly withdrawn from its stories."
    ),
}


@pytest.mark.parametrize("name", sorted(DANGLING_OPENERS))
def test_graded6_dangling_openers_are_refused(name):
    assert _standalone_problem(DANGLING_OPENERS[name]) == "orphan_opener", name


@pytest.mark.parametrize("name", sorted(NEGATIVE_CONTROLS))
def test_legitimate_clips_are_not_refused_as_openers(name):
    assert _standalone_problem(NEGATIVE_CONTROLS[name]) != "orphan_opener", name


if __name__ == "__main__":
    for key, text in DANGLING_OPENERS.items():
        assert _standalone_problem(text) == "orphan_opener", key
    for key, text in NEGATIVE_CONTROLS.items():
        assert _standalone_problem(text) != "orphan_opener", key
    print("standalone opener self-check passed")
