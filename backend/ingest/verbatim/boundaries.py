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
DANGLING_TAIL = CONJUNCTIONS | frozenset(
    {
        "to",
        "of",
        "in",
        "for",
        "with",
        "as",
        "if",
        "at",
        "on",
        "by",
        "from",
        "into",
        "onto",
        "about",
        "than",
        "through",
        "the",
        "a",
        "an",
        "your",
        "my",
        "our",
        "their",
        "his",
        "her",
        "its",
    }
)

# ponytail: auxiliary verbs that indicate a headless predicate clause if not followed by an inverted subject
AUXILIARY_VERBS = frozenset(
    {
        "have",
        "has",
        "had",
        "are",
        "is",
        "were",
        "was",
        "do",
        "did",
        "does",
        "would",
        "could",
        "should",
        "will",
        "shall",
        "can",
        "might",
        "must",
    }
)
INVERTED_SUBJECTS = frozenset(
    {
        "you",
        "we",
        "they",
        "i",
        "he",
        "she",
        "it",
        "there",
        "one",
        "this",
        "that",
        "these",
        "those",
        "anyone",
        "everyone",
        "someone",
        "nobody",
        "anybody",
        "somebody",
    }
)


def _bare(token: str) -> str:
    return token.strip(_STRIP).lower()


def _ends_sentence(token: str) -> bool:
    t = token.rstrip("\"'”’)]")
    return bool(t) and t[-1] in TERMINAL and _bare(token) not in CONJUNCTIONS


def _is_headless_predicate(tokens: list[str]) -> bool:
    """True if tokens begin with an auxiliary verb without an inverted subject pronoun.
    # ponytail: catches severed predicate clauses (e.g. "Have desired...") while
    # preserving legitimate inverted questions (e.g. "Have you ever desired peace?").
    """
    if not tokens:
        return False
    first = _bare(tokens[0])
    if first not in AUXILIARY_VERBS:
        return False
    if len(tokens) < 2:
        return True
    second = _bare(tokens[1])
    return second not in INVERTED_SUBJECTS


def _starts_sentence(tokens: list[str], i: int) -> bool:
    # Index 0 has no predecessor to read, so fall back to capitalisation.
    if i == 0:
        is_start = tokens[0].lstrip("\"'“‘(")[:1].isupper()
    else:
        is_start = _ends_sentence(tokens[i - 1])
    if not is_start:
        return False
    # ponytail: a headless predicate is never a valid sentence start
    if _is_headless_predicate(tokens[i:]):
        return False
    return True


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
    elif _is_headless_predicate(tokens):
        # ponytail: capitalized auxiliary verb without subject is a severed predicate
        defects.append("head_headless_predicate")
    # Capitalised "And/So/Or ..." opens a real spoken sentence (owner decision
    # delegated 2026-09-28: allow); lowercase means the clip joined mid-clause.
    if _bare(tokens[0]) in CONJUNCTIONS and not first[:1].isupper():
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
    # ponytail: if the span start itself opens with a capitalized thought (not a headless predicate),
    # accept it as the sentence start for this clip without requiring preceding cross-turn terminal punctuation.
    if tokens[s].lstrip("\"'“‘(")[:1].isupper() and not _is_headless_predicate(tokens[s:]):
        pass
    else:
        while s < end and not _starts_sentence(tokens, s):
            s += 1
    e = end
    while e > s and not _ends_sentence(tokens[e - 1]):
        e -= 1
    if e - s < min_words:
        return None
    return s, e


def grow_to_sentence_start(
    tokens: list[str], labels: list[str], start: int, speaker: str, max_back: int = 60
) -> Optional[int]:
    """Move ``start`` BACK to the nearest sentence start, keeping content that
    shrink would drop (plan card B3).

    Every word crossed must carry ``speaker``'s label -- a host ("O") or
    unknown ("?") word stops the walk, so growing can never attribute another
    voice to the teacher (FP invariant: abstain by default). Returns None when
    no sentence start is reachable within ``max_back`` words; callers then
    fall back to ``snap_to_sentences``.
    """
    if len(tokens) != len(labels):
        raise ValueError(f"{len(tokens)} tokens vs {len(labels)} labels")
    s = start
    while s >= 0 and start - s <= max_back and labels[s] == speaker:
        if _starts_sentence(tokens, s):
            return s
        s -= 1
    return None


def _self_check() -> None:
    assert boundary_defects("Suffering is not a fact.".split()) == []
    assert boundary_defects("This is who you are.".split()) == []
    assert boundary_defects("and then you let go of".split()) == [
        "head_lowercase",
        "head_conjunction",
        "tail_no_terminal",
        "tail_dangling_word",
    ]
    assert boundary_defects("roof. A family came,".split()) == [
        "head_lowercase",
        "tail_no_terminal",
    ]
    assert boundary_defects(["...and", "it", "ends."]) == [
        "head_orphan_punctuation",
        "head_conjunction",
    ]
    toks = "was agitated. You see the truth. Then it goes and".split()
    assert snap_to_sentences(toks, 0, len(toks), min_words=3) == (2, 6)
    assert snap_to_sentences(toks, 0, len(toks), min_words=5) is None
    assert snap_to_sentences(["A", "b."], 0, 2, min_words=1) == (0, 2)
    toks = "It hurts. You see the truth".split()
    assert grow_to_sentence_start(toks, ["K"] * 6, 4, "K") == 2
    assert grow_to_sentence_start(toks, ["K", "K", "O", "K", "K", "K"], 4, "K") is None
    print("boundaries.py self-check OK")


if __name__ == "__main__":
    _self_check()
