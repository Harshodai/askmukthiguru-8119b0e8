"""The lexicon replaces hand-typed ASR variant lists with derived vocabulary.

Every assertion here encodes a failure measured against the live 89,061-chunk
corpus while building it. The corpus-scale numbers quoted are from a 12,000-chunk
random sample.
"""

from __future__ import annotations

import pytest

from services.doctrine_lexicon import DoctrineLexicon, build_lexicon


@pytest.fixture
def lexicon() -> DoctrineLexicon:
    """Books (OCR'd), a clean site, and general English — the real shape."""
    return build_lexicon(
        {
            # OCR'd source: carries genuine fragments, as the real PDF does.
            "books": ["Peace is not a piece. The soul is not soil. ealth ense"],
            # Clean HTML: no OCR damage, so every word is a valid target.
            "site": [
                "The Ojas Shakti practice builds immunity. Chanting Humsa follows the breath."
            ],
            "english": ["peace piece soul soil soar steel knots vows breath immunity"],
        },
        corpus_texts=[("v1", "Ojas is strength.")],
        min_consensus_sources=20,
    )


def test_computes_variants_that_were_never_written_down(lexicon):
    """`Ojas Shakti` is a named Ekam practice that no hand list contained, so the
    corpus holds "Ojas" in 15 chunks and "Ujash" in 4 FROM THE SAME VIDEO. ASR
    invents new forms (Ujash, Ujasi, Ojasi) faster than anyone can enumerate."""
    for variant in ("Ujash", "Ujasi", "Ojasi"):
        decision = lexicon.explain(variant)
        assert decision.replacement == "Ojas", f"{variant}: {decision.reason}"


def test_never_rewrites_ordinary_english(lexicon):
    """Similarity CANNOT separate the classes: measured, piece/peace scores 0.880
    against ujash/ojas at 0.783. Safety comes from vocabulary membership, not
    from a threshold — rewriting `peace` to `piece` in doctrine is unrecoverable."""
    for word in ("peace", "piece", "soul", "soil", "soar", "steel", "knots", "vows"):
        decision = lexicon.explain(word)
        assert decision.replacement is None, f"{word} -> {decision.replacement}"


def test_possessives_and_hyphenated_compounds_are_left_alone(lexicon):
    """Rewriting `chakra's`->`chakras` or `pre-conditioned`->`preconditioned`
    changes grammar and house style while claiming to fix transcription."""
    for token in ("chakra's", "breath's", "pre-conditioned", "best-selling"):
        assert lexicon.explain(token).replacement is None


def test_truncations_complete_rather_than_swap(lexicon):
    """Edit distance alone picked a SHORTER neighbour for a cut-off word —
    `coura`->`core`, `succe`->`such`. A fragment's truth is a completion."""
    assert lexicon.explain("breat").replacement == "breath"


def test_ocr_fragments_in_the_books_cannot_become_targets(lexicon):
    """The book PDF is OCR'd, so `ealth` and `ense` are in its text. Before the
    support rule they attracted `alth`->`ealth`, repairing one fragment into
    another. Words seen only in an OCR'd source must recur to attract."""
    assert lexicon.explain("alth").replacement != "ealth"
    assert lexicon.explain("eness").replacement != "ense"


def test_clean_sites_need_no_repetition(lexicon):
    """`ojas` appears only twice on ekam.org. Requiring repetition of every
    non-English target silently disabled the case this exists for."""
    assert "ojas" in lexicon.clean_curated
    assert lexicon.explain("Ujash").replacement == "Ojas"


def test_consensus_cannot_launder_a_systematic_asr_error():
    """Measured: `akam` is absent from the books yet appears in 26 sources / 401
    uses because Whisper mishears `Ekam` the same way every time. Admitting it
    would make the error permanent, since vocabulary membership is treated as
    proof of correctness. Repetition is not evidence when the cause is common."""
    lex = build_lexicon(
        {"site": ["Ekam " * 300]},
        corpus_texts=[(f"src{i}", "Akam is the place") for i in range(30)],
        min_consensus_sources=20,
    )
    assert "akam" not in lex.vocabulary, "a dominated variant must stay correctable"


def test_proper_nouns_only_map_to_proper_nouns():
    """Capitalised tokens are the words no general vocabulary contains, so they
    reach the matcher looking exactly like ASR errors — which produced
    `Rome`->`room`, `Maori`->`more` and `preeta`->`pretty`."""
    lex = build_lexicon({"english": ["room more pretty remain"]})
    for name in ("Rome", "Maori", "Preeta"):
        assert lex.explain(name).replacement is None
