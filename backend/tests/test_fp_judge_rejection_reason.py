"""Regression guard: a harness abstain must log the judge's real reason, not a fake '< min'.

Live 2026-11-12 the harness logged "scored [3] (< min)" for clips the judge scored 3, because
the judge rejected them on answers/standalone/complete, not on relevance.
"""

from services.first_person_judge import rejection_reason


def _score(i, relevance, **flags):
    base = {"i": i, "relevance": relevance, "answers": True, "content_safety": "clean"}
    base.update(flags)
    return base


def test_score_three_rejected_for_not_answering_is_not_blamed_on_minimum():
    reason = rejection_reason([_score(0, 3, answers=False)], answerable=True, minimum=3)
    assert "answers=false" in reason
    assert "relevance=3<min3" not in reason


def test_score_below_minimum_names_the_minimum():
    reason = rejection_reason([_score(0, 2)], answerable=True, minimum=3)
    assert "relevance=2<min3" in reason


def test_unanswerable_question_is_named():
    assert rejection_reason([_score(0, 3)], answerable=False, minimum=3) == "question_not_answerable"


def test_passing_clip_is_marked_passed():
    assert rejection_reason([_score(0, 3)], answerable=True, minimum=3) == "clip0[passed]"


def test_standalone_and_completeness_flags_are_named():
    reason = rejection_reason(
        [_score(0, 3, is_standalone=False, is_complete_thought=False)],
        answerable=True,
        minimum=3,
    )
    assert "not_standalone" in reason and "incomplete_thought" in reason


if __name__ == "__main__":
    test_score_three_rejected_for_not_answering_is_not_blamed_on_minimum()
    test_score_below_minimum_names_the_minimum()
    test_unanswerable_question_is_named()
    test_passing_clip_is_marked_passed()
    test_standalone_and_completeness_flags_are_named()
    print("judge rejection reason self-check passed")
