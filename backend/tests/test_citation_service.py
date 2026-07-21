"""Tests for the citation service."""

from services.citation_service import (
    CitationStyle,
    Source,
    resolve,
    format_reference,
    strip_orphan_markers,
)


def test_resolve_basic():
    ctx = [
        {"id": "d1", "title": "Breath Awareness", "teacher": "Sri Preethaji",
         "source": "Ekam Discourse", "year": "2023"},
        {"id": "d2", "title": "On Presence", "source": "Ekam Teaching", "year": "2022"},
    ]
    answer = (
        "When the mind is restless, return to the breath.[^1] "
        "From that steadiness, presence arises on its own.[^2]"
    )
    result = resolve(answer, ctx)
    assert result.citation_count == 2
    assert len(result.references) == 2


def test_orphan_marker_stripping():
    ctx = [{"id": "d1", "title": "Breath Awareness"}]
    answer = "This is grounded.[^1] This is a hallucinated citation.[^9]"
    cleaned = strip_orphan_markers(answer, ctx)
    assert "[^9]" not in cleaned
    assert "[^1]" in cleaned


def test_grounding_check():
    # Substantive paragraphs exceeding the 25-word threshold — all must be cited
    cited = (
        "First paragraph with more than twenty-five words so it passes the substantive threshold and requires a citation.[^1]\n\n"
        "Second paragraph also twenty-five plus words because it needs citation checking too not a short empty paragraph.[^2]"
    )
    result = resolve(cited, [
        {"id": "d1", "title": "First"},
        {"id": "d2", "title": "Second"},
    ])
    assert result.grounded is True

    # Uncited substantive paragraph — should NOT be grounded
    uncited = (
        "First paragraph with more than twenty-five words so it passes the substantive threshold and requires a citation.[^1]\n\n"
        "Second paragraph also twenty-five plus words and actually does not have any citation marker not a single one at all here now added more words to exceed threshold."
    )
    result = resolve(uncited, [
        {"id": "d1", "title": "First"},
        {"id": "d2", "title": "Second"},
    ])
    assert result.grounded is False


def test_format_reference():
    src = Source(
        id="d1",
        title="Breath Awareness",
        teacher="Sri Preethaji",
        year="2023",
    )
    label = format_reference(src)
    assert "Sri Preethaji" in label
    assert "Breath Awareness" in label
    assert "2023" in label


def test_resolve_dedup_references():
    ctx = [
        {"id": "d1", "title": "Breath Awareness", "teacher": "Sri Preethaji"},
    ]
    answer = "Start.[^1] Middle.[^1] End.[^1]"
    result = resolve(answer, ctx)
    assert result.citation_count == 1
    assert len(result.references) == 1


def test_resolve_empty_context():
    answer = "No citations here."
    result = resolve(answer, [])
    assert result.citation_count == 0
    assert result.grounded is True


def test_strip_orphan_all_bad():
    answer = "All fake.[^1][^2][^3]"
    assert strip_orphan_markers(answer, []) == "All fake."


def test_format_reference_author_title_style():
    src = Source(
        id="d1",
        title="Breath Awareness",
        teacher="Sri Preethaji",
        year="2023",
    )
    label = format_reference(src, CitationStyle.AUTHOR_TITLE)
    assert label == "Sri Preethaji, 2023"


def test_format_reference_minimal():
    src = Source(id="d1", title="Untitled")
    label = format_reference(src)
    assert label == "\u201cUntitled\u201d"


def test_verify_inline_citations_strips_orphans_and_unverified_sentences():
    """_verify_inline_citations strips out-of-range markers and drops sentences that remain ungrounded."""
    from rag.nodes.utils import _verify_inline_citations

    # Orphan marker [[CITE:9]] is stripped, leaving only [[CITE:1]]. The remaining
    # text is grounded because the single short paragraph has a valid marker.
    answer = "Breath awareness is the first step. [[CITE:1]] It calms the mind. [[CITE:9]]"
    docs = [{"title": "Breath Awareness", "source": "Ekam", "url": "https://ekam.org/breath"}]
    cleaned, verified, stripped = _verify_inline_citations(answer, docs)

    assert "[[CITE:9]]" not in cleaned
    assert "[[CITE:1]]" in cleaned
    assert verified is True
    assert stripped is True


def test_verify_inline_citations_keeps_valid_citations():
    """Valid in-range markers should pass verification with no stripping."""
    from rag.nodes.utils import _verify_inline_citations

    # Single short paragraph with an in-range marker: citation_service resolves
    # [[CITE:1]] and the grounding check accepts the single short paragraph.
    answer = "Breath awareness is the first step. [[CITE:1]]"
    docs = [{"title": "Breath Awareness", "source": "Ekam", "url": "https://ekam.org/breath"}]
    cleaned, verified, stripped = _verify_inline_citations(answer, docs)

    assert "[[CITE:1]]" in cleaned
    assert verified is True
    assert stripped is False


def test_verify_inline_citations_no_markers():
    """Answers without markers are trivially verified and not stripped."""
    from rag.nodes.utils import _verify_inline_citations

    cleaned, verified, stripped = _verify_inline_citations("Just a plain answer.", [])
    assert cleaned == "Just a plain answer."
    assert verified is True
    assert stripped is False
