"""The verbatim-excerpt fallback promises the teachers' own words. Live
2026-09-26 (mul-012): a QF-1-contaminated chunk (stitched [Context: ...] and
[Potential Questions: ...] blocks, quotes nested inside) showed an LLM
paraphrase as the teaching. Shapes below mirror the real stored chunks."""

from rag.nodes.generation import _grounded_partial_answer

URL = "https://www.youtube.com/watch?v=abc"


def _answer(text: str) -> str | None:
    built = _grounded_partial_answer([{"text": text, "source_url": URL, "title": "T"}])
    return built[0] if built else None


def test_clean_chunk_with_header_and_footer_shows_only_the_teaching():
    answer = _answer(
        "[Source: A talk | Speaker: X | Topic: Y]\nLife itself becomes a miracle.\n\n"
        "[Potential Questions: Here are three questions:\n1. How?\n2. Why?]"
    )
    assert "Life itself becomes a miracle." in answer
    assert "Potential Questions" not in answer and "Source:" not in answer


def test_leading_context_line_is_removed():
    answer = _answer(
        "[Context: A summary sentence.]\nWhen your state is love, it is never limited."
    )
    assert "summary sentence" not in answer
    assert "When your state is love" in answer


def test_stitched_contaminated_chunk_is_never_shown_as_their_words():
    stitched = (
        "[Context: The chunk introduces a question.]\n"
        '[Potential Questions: Here are questions: 1. **"I feel stuck?"**\n'
        '2. **"] [Context: This chunk highlights a paraphrase.] Paraphrased line.\n'
        "Real last line."
    )
    assert _answer(stitched) is None


def test_unterminated_header_document_is_skipped():
    assert _answer("[Context: This chunk summary never closes and runs on") is None


def test_plain_teaching_is_untouched():
    assert "Suffering is not a blessing." in _answer("Suffering is not a blessing.")
