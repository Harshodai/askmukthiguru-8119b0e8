"""Guard: _clean_inline_citations strips dangling CTA phrases the LLM appends without an
inline URL (the link is emitted in the citations array, not the text). Regression for the
"upcoming programs from Ekam" answer ending on a bare "Watch more here:" / "…website:".
"""

from rag.nodes.generation import _clean_inline_citations as clean


def test_dangling_watch_more_here_is_stripped():
    out = clean("Consistent action creates your destiny. Watch more here:")
    assert "here:" not in out.lower()
    assert "creates your destiny." in out


def test_dangling_website_cta_is_stripped():
    out = clean("You'll find them on the Ekam website:")
    assert "website:" not in out.lower()


def test_legit_url_cta_leaves_no_dangling_colon():
    out = clean("You can watch more here: https://youtube.com/c/pkconsciousness")
    assert "http" not in out
    assert "here:" not in out.lower()


def test_normal_text_untouched():
    src = "The beautiful state is calm, joy and connection."
    assert clean(src) == src


def test_akam_transcription_normalized_to_ekam():
    assert clean("The universal energy at Akam pushes you into transcendence.") == (
        "The universal energy at Ekam pushes you into transcendence."
    )
    # lowercase Tamil "akam" (inner self) must be left untouched
    assert "akam" in clean("The Tamil word akam means the inner self.").lower()


def test_logistics_query_detection():
    from rag.nodes.intent import _is_logistics_query as logi

    # positives — event/program noun + logistics cue
    for q in (
        "What are the upcoming programs from Ekam?",
        "When is the next Ekam retreat and what is the ticket price?",
        "How do I register for the workshop?",
        "What is the schedule for upcoming events?",
    ):
        assert logi(q), f"should be logistics: {q}"

    # negatives — teaching questions must NOT be misrouted
    for q in (
        "What is the beautiful state?",
        "How do I practice soul sync?",
        "Tell me about the beautiful state program",  # noun but no logistics cue
        "Why do I keep suffering?",
    ):
        assert not logi(q), f"should NOT be logistics: {q}"


if __name__ == "__main__":
    for fn in (
        test_dangling_watch_more_here_is_stripped,
        test_dangling_website_cta_is_stripped,
        test_legit_url_cta_leaves_no_dangling_colon,
        test_normal_text_untouched,
        test_akam_transcription_normalized_to_ekam,
        test_logistics_query_detection,
    ):
        fn()
    print("ekam-answer-quality regressions: all asserts passed")
