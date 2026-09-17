"""A question cannot hallucinate, and neither can an invitation to reflect.

`rag/prompts/system.py:90` instructs the persona to "End with a reflective or
encouraging closing sentence." The faithfulness gate was scoring that closing
sentence as an unsupported factual claim, so following the persona's own
instruction cost roughly one claim in eight and pushed grounded answers below
`faithfulness_floor` -- a live 2026-09-15 trace on "Explain the first sacred
secret." scored "Reflect on this deeply." at 0.348/unsupported and shipped
excerpt boilerplate in place of the teaching.
"""

from services.lettuce_detect_service import _is_assertion, _split_claims


def test_questions_are_not_claims():
    assert not _is_assertion("What spiritual vision is calling you?")


def test_pastoral_imperatives_are_not_claims():
    assert not _is_assertion("Reflect on this deeply.")
    assert not _is_assertion("Take a moment to sit with that.")


def test_statements_about_the_teachings_are_still_claims():
    assert _is_assertion("The first sacred secret is holding a spiritual vision for yourself.")
    # Second person is not by itself an imperative -- this asserts something.
    assert _is_assertion("You experience the Beautiful State when division ends.")


def test_split_drops_non_assertions_but_keeps_the_substance():
    answer = (
        "The first secret is holding a spiritual vision. "
        "Reflect on this deeply. "
        "What spiritual vision is calling you? "
        "Holding it transforms collective consciousness."
    )
    claims = _split_claims(answer)
    assert claims == [
        "The first secret is holding a spiritual vision.",
        "Holding it transforms collective consciousness.",
    ]


def test_an_all_non_assertion_answer_is_not_scored_as_perfect():
    """Filtering to an empty list would score a content-free answer 1.0."""
    answer = "Reflect on this deeply. What is calling you right now?"
    assert len(_split_claims(answer)) == 2


def test_markdown_paren_links_are_stripped_not_scored():
    """`_BRACKETED_URL_RE` had no paren twin, so `(url)` fell to the greedy
    `_URL_RE` (`\\S+`), which ate the closing paren and left a bare "(".
    That fragment then missed the end-of-line CTA pattern and was scored as a
    claim -- a live 2026-09-15 trace shows "Watch more here:(" alone taking a
    fully grounded answer from 1.0 to 0.88 and forcing a redaction pass.
    """
    from services.lettuce_detect_service import _strip_attribution_markup

    answer = (
        "The Four Sacred Secrets are teachings of Sri Preethaji and Sri Krishnaji.\n"
        "Watch more here:(https://youtube.com/watch?v=abc)"
    )
    cleaned = _strip_attribution_markup(answer)
    assert "Watch more here" not in cleaned
    assert "(" not in cleaned
    assert _split_claims(cleaned) == [
        "The Four Sacred Secrets are teachings of Sri Preethaji and Sri Krishnaji."
    ]
