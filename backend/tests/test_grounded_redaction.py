"""A draft that fails verification should ship its grounded part, not excerpts.

Before this, a draft with 7 of 9 sentences grounded was discarded entirely and
the seeker got a dump of raw retrieved excerpts (`grounded_partial_evidence`).
Redaction keeps the invariant that matters — no ungrounded sentence reaches a
seeker — while still answering the question.
"""

import pytest

from rag.nodes.generation import _redact_unsupported_sentences

FLOOR = 0.6


def _claims(supported: int, unsupported: int):
    out = [
        {"text": f"Grounded teaching sentence number {i} about the beautiful state.", "supported": True}
        for i in range(supported)
    ]
    out += [{"text": f"Fabricated sentence {i}.", "supported": False} for i in range(unsupported)]
    return out


def test_drops_unsupported_and_keeps_the_rest():
    got = _redact_unsupported_sentences({"claims": _claims(7, 2)}, floor=FLOOR)
    assert got is not None
    body, removed = got
    assert removed == 2
    assert "Fabricated" not in body
    assert "Grounded teaching sentence number 0" in body


def test_tells_the_reader_something_was_removed():
    body, _ = _redact_unsupported_sentences({"claims": _claims(7, 2)}, floor=FLOOR)
    assert "left out" in body
    singular, _ = _redact_unsupported_sentences({"claims": _claims(7, 1)}, floor=FLOOR)
    assert "One line was left out" in singular


def test_no_redaction_when_everything_is_grounded():
    assert _redact_unsupported_sentences({"claims": _claims(5, 0)}, floor=FLOOR) is None


def test_mostly_ungrounded_draft_is_not_salvaged():
    # 2 of 9 grounded is below the floor — excerpts are the honest answer there.
    assert _redact_unsupported_sentences({"claims": _claims(2, 7)}, floor=FLOOR) is None


def test_too_little_surviving_text_is_not_salvaged():
    claims = [
        {"text": "Yes.", "supported": True},
        {"text": "Indeed.", "supported": True},
        {"text": "Fabricated sentence.", "supported": False},
    ]
    assert _redact_unsupported_sentences({"claims": claims}, floor=FLOOR) is None


def test_missing_or_empty_claims_are_handled():
    assert _redact_unsupported_sentences({}, floor=FLOOR) is None
    assert _redact_unsupported_sentences({"claims": []}, floor=FLOOR) is None
    assert _redact_unsupported_sentences({"claims": "nonsense"}, floor=FLOOR) is None


def test_single_supported_sentence_is_not_enough():
    assert _redact_unsupported_sentences({"claims": _claims(1, 1)}, floor=FLOOR) is None


def test_empty_citation_markers_are_stripped_from_redacted_prose():
    """Dropping a sentence can orphan its citation marker into a bare "[]"."""
    import re

    import rag.nodes.generation as generation

    src = __import__("inspect").getsource(generation.format_final_answer)
    assert r'\[\s*\]' in src, "the redaction path must strip emptied citation markers"

    # And the expression used must actually remove them.
    sample = "A grounded sentence. [] Another one. [2]"
    assert re.sub(r"[ \t]*\[\s*\]", "", sample) == "A grounded sentence. Another one. [2]"


def test_redacted_answer_is_scored_on_what_ships():
    """The rejected draft's score must not follow the redacted answer."""
    import inspect

    import rag.nodes.generation as generation

    src = inspect.getsource(generation.format_final_answer)
    assert "redacted_faithfulness" in src
    head, _, tail = src.partition('"method": "redacted_unsupported_claims"')
    assert '"faithfulness_score": redacted_faithfulness' in tail[:400], (
        "a redacted answer must report the score of the sentences it kept"
    )
