"""A draft that fails verification should ship its grounded part, not excerpts.

Before this, a draft with 7 of 9 sentences grounded was discarded entirely and
the seeker got a dump of raw retrieved excerpts (`grounded_partial_evidence`).
Redaction keeps the invariant that matters — no ungrounded sentence reaches a
seeker — while still answering the question.
"""

from rag.nodes.generation import _redact_unsupported_sentences
from services.voice.register import REDACTION_NOTE_MANY, REDACTION_NOTE_ONE

FLOOR = 0.6


def _claims(supported: int, unsupported: int):
    out = [
        {
            "text": f"Grounded teaching sentence number {i} about the beautiful state.",
            "supported": True,
        }
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
    # The invariant is that the reader is TOLD something was removed, and how
    # many -- not the exact sentence used to say it.
    assert REDACTION_NOTE_MANY.format(n=2) in body
    singular, _ = _redact_unsupported_sentences({"claims": _claims(7, 1)}, floor=FLOOR)
    assert REDACTION_NOTE_ONE in singular


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
    assert r"\[\s*\]" in src, "the redaction path must strip emptied citation markers"

    # And the expression used must actually remove them.
    sample = "A grounded sentence. [] Another one. [2]"
    assert re.sub(r"[ \t]*\[\s*\]", "", sample) == "A grounded sentence. Another one. [2]"


def test_redacted_answer_is_scored_on_what_ships():
    """The rejected draft's score must not follow the redacted answer."""
    import inspect

    import rag.nodes.generation as generation

    src = inspect.getsource(generation.format_final_answer)
    assert "redacted_faithfulness" in src
    assert "_redacted_verification(" in src
    got = generation._redacted_verification({"faithfulness_score": 0.0}, 1, 0.92)
    assert got["faithfulness_score"] == 0.92, (
        "a redacted answer must report the score of the sentences it kept"
    )


def test_redacted_verdict_does_not_carry_the_drafts_failure_details():
    """passed=True must not ship next to "answer remains unverified".

    Live 2026-10-08 (clean Docker, s1-root-cause): CoVe timed out, the draft was
    redacted, and the response carried passed=True with details "Gateway CoVe
    deadline exceeded; answer remains unverified" spread from the draft verdict.
    """
    from rag.nodes.generation import _redacted_verification

    draft = {
        "passed": False,
        "details": "Gateway CoVe deadline exceeded; answer remains unverified",
        "claims": _claims(7, 1),
    }
    got = _redacted_verification(draft, 1, 1.0)
    assert got["passed"] is True
    assert got["method"] == "redacted_unsupported_claims"
    assert "unverified" not in got["details"]
    assert "1 unsupported sentence(s) removed" in got["details"]
    assert got["draft_details"] == draft["details"]
    assert got["claims"] == draft["claims"]
    assert draft["passed"] is False, "the draft verdict must not be mutated"
