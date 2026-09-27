"""Stage: clip boundary integrity -- detect and repair mid-sentence clip edges.

CLAUDE.md first-person invariants 10/11: every served clip must be a complete
thought -- it may not start mid-sentence or end on a dangling word.

Two pure functions over plain token lists (no models, no I/O):

- ``boundary_defects(tokens)`` -- generic head/tail defect labels. Deliberately
  NOT clip-specific: no phrase lists fitted to known-bad clips, so a defect rate
  measured with it is comparable across corpora and builders.
- ``snap_to_sentences(tokens, start, end, min_words)`` -- SHRINK-only snap of a
  token span to whole sentences. Shrinking can never pull in another speaker's
  words, so it is safe on speaker-labelled runs; returns None when too little
  of the span survives (quarantine, never serve a fragment).

Sentence boundaries are read from token punctuation. Pass the punctuation
display layer (``punct.json`` ``display_words``, 1:1 with the verbatim words
under ``zero_change_assert_passed``) when the verbatim ASR is unpunctuated;
the returned indices then apply to the verbatim words unchanged.
"""

from __future__ import annotations

from typing import Optional

TERMINAL = (".", "?", "!")
_STRIP = "\"'“”‘’()[]…,;:—–-.?!"

CONJUNCTIONS = frozenset({"and", "or", "so", "but", "because", "nor", "yet"})
# Closed-class words a complete English sentence cannot end on.
DANGLING_TAIL = CONJUNCTIONS | frozenset({
    "to", "of", "in", "for", "with", "as", "if", "at", "on", "by", "from",
    "into", "onto", "about", "than", "through", "the", "a", "an", "your",
    "my", "our", "their", "his", "her", "its",
})


def _bare(token: str) -> str:
    return token.strip(_STRIP).lower()


def _ends_sentence(token: str) -> bool:
    t = token.rstrip("\"'”’)]")
    return bool(t) and t[-1] in TERMINAL and _bare(token) not in CONJUNCTIONS


def _starts_sentence(tokens: list[str], i: int) -> bool:
    # Index 0 has no predecessor to read, so fall back to capitalisation.
    if i == 0:
        return tokens[0].lstrip("\"'“‘(")[:1].isupper()
    return _ends_sentence(tokens[i - 1])


def boundary_defects(tokens: list[str]) -> list[str]:
    """Head/tail defect labels for one clip's tokens; [] means clean."""
    if not tokens:
        return ["empty"]
    defects: list[str] = []
    first = tokens[0].lstrip("\"'“‘(")
    if first[:1] and not first[:1].isalnum():
        defects.append("head_orphan_punctuation")
    elif first[:1].islower():
        defects.append("head_lowercase")
    if _bare(tokens[0]) in CONJUNCTIONS:
        defects.append("head_conjunction")
    if not _ends_sentence(tokens[-1]):
        defects.append("tail_no_terminal")
        # Only unpunctuated: "This is who you are." / "Come in." are complete.
        if _bare(tokens[-1]) in DANGLING_TAIL:
            defects.append("tail_dangling_word")
    return defects


def snap_to_sentences(
    tokens: list[str], start: int, end: int, min_words: int = 12
) -> Optional[tuple[int, int]]:
    """Shrink [start, end) to whole sentences; None if < min_words remain.

    Start moves forward to the first sentence start (right after a terminal
    token, or a capitalised token at index 0); end moves back to just after the last
    terminal token. A span with no interior sentence boundary returns None.
    ponytail: shrink-only; growing back to the true sentence start needs the
    speaker labels (stay inside one teacher's run) -- add in the clip builder.
    """
    if not (0 <= start < end <= len(tokens)):
        raise ValueError(f"bad span [{start}, {end}) for {len(tokens)} tokens")
    s = start
    while s < end and not _starts_sentence(tokens, s):
        s += 1
    e = end
    while e > s and not _ends_sentence(tokens[e - 1]):
        e -= 1
    if e - s < min_words:
        return None
    return s, e


def _self_check() -> None:
    assert boundary_defects("Suffering is not a fact.".split()) == []
    assert boundary_defects("This is who you are.".split()) == []
    assert boundary_defects("and then you let go of".split()) == [
        "head_lowercase", "head_conjunction", "tail_no_terminal", "tail_dangling_word"]
    assert boundary_defects("roof. A family came,".split()) == ["head_lowercase", "tail_no_terminal"]
    assert boundary_defects(["...and", "it", "ends."]) == ["head_orphan_punctuation", "head_conjunction"]
    toks = "was agitated. You see the truth. Then it goes and".split()
    assert snap_to_sentences(toks, 0, len(toks), min_words=3) == (2, 6)
    assert snap_to_sentences(toks, 0, len(toks), min_words=5) is None
    assert snap_to_sentences(["A", "b."], 0, 2, min_words=1) == (0, 2)
    print("boundaries.py self-check OK")


if __name__ == "__main__":
    _self_check()
