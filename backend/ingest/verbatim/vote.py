"""Stage: ROVER-style word vote between two ASR outputs (e.g. whisper=A, parakeet=B).

Ported from the pilot's common.py + run_vote.py
(~/mukthiguru_attribution_data/pilot50_2026-09-25/), unchanged in behaviour.
Pure functions only -- no model calls, no I/O.

Input:  two word lists ``[{"w": str, "start": float, "end": float, ...}, ...]``
        for the same audio from two independent ASR engines.
Output: ``vote_stage(a_words, b_words)`` -> dict with the voted word sequence
        (each word tagged ``disputed``/``alt``), agreement/disputed rates,
        hallucination-span flags, repeated-ngram flags, WER(A vs B), and
        glossary hit counts -- the same shape as the pilot's raw/<id>_vote.json
        (plus the voted words themselves, which the pilot wrote to a sibling
        file; this stage returns them together since callers persist as they see fit).
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from services.doctrine_terms import load_doctrine_terms

_NUM = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def norm_word(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def is_numeral_pair(a: str, b: str) -> bool:
    return _NUM.get(a) == b or _NUM.get(b) == a


def rover_vote(words_a: list[dict], words_b: list[dict]) -> list[dict[str, Any]]:
    """Diff-align two word lists; A's tokens/timing win, tagged with B's dispute status.

    A word absent from B's aligned span ("insert" in B, i.e. B has extra
    words A lacks) is not itself a word of A's, so it is not emitted.
    """
    na = [norm_word(w["w"]) for w in words_a]
    nb = [norm_word(w["w"]) for w in words_b]
    sm = difflib.SequenceMatcher(a=na, b=nb, autojunk=False)
    out: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                out.append({**words_a[k], "disputed": False, "alt": None})
        elif tag == "replace":
            alt_text = " ".join(w["w"] for w in words_b[j1:j2]) if j2 > j1 else None
            for k in range(i1, i2):
                out.append({**words_a[k], "disputed": True, "alt": alt_text})
        elif tag == "delete":
            for k in range(i1, i2):
                out.append({**words_a[k], "disputed": True, "alt": "(absent in B)"})
        # "insert": B-only tokens have no A word to attach to; skipped.
    return out


def repeated_ngram_flags(
    words: list[str], nmin: int = 3, nmax: int = 6, min_repeats: int = 3
) -> list[dict]:
    """Flag runs of a repeated n-gram (a common ASR hallucination pattern)."""
    flags = []
    for n in range(nmin, nmax + 1):
        i = 0
        while i + n * min_repeats <= len(words):
            gram = tuple(words[i : i + n])
            reps = 1
            j = i + n
            while tuple(words[j : j + n]) == gram and j + n <= len(words):
                reps += 1
                j += n
            if reps >= min_repeats:
                flags.append({"ngram": " ".join(gram), "n": n, "repeats": reps, "start_idx": i})
                i = j
            else:
                i += 1
    return flags


def wer(ref: list[str], hyp: list[str]) -> float:
    """Word error rate (Levenshtein distance / len(ref)) between two token lists."""
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            cur = dp[j]
            dp[j] = prev if ref[i - 1] == hyp[j - 1] else 1 + min(prev, dp[j - 1], dp[j])
            prev = cur
    return dp[m] / max(n, 1)


def glossary_hits(words: list[str]) -> dict[str, int]:
    """Count occurrences of each canonical doctrine term (backend/services/doctrine_terms.py
    is the single source of the term list -- never a second hand-kept glossary)."""
    text = " ".join(words)
    terms = [t.lower() for t in load_doctrine_terms()]
    return {t: text.count(t) for t in terms}


def hallucination_flags(voted: list[dict], b_words: list[dict]) -> list[dict]:
    """Flag runs of >4 consecutive disputed words with zero B-word overlap in
    their time span -- A said something B has no evidence for at all."""
    flags: list[dict] = []
    run: list[dict] = []

    def flush() -> None:
        if len(run) > 4:
            s, e = run[0]["start"], run[-1]["end"]
            if not [bw for bw in b_words if bw["start"] < e and bw["end"] > s]:
                flags.append(
                    {
                        "start": s,
                        "end": e,
                        "text": " ".join(x["w"] for x in run),
                        "reason": "no_B_support_in_span",
                    }
                )

    for w in voted:
        if w["disputed"]:
            run.append(w)
        else:
            flush()
            run = []
    flush()
    return flags


def vote_stage(a_words: list[dict], b_words: list[dict]) -> dict[str, Any]:
    """Full vote stage: rover_vote + all derived metrics, in one dict.

    ``voted_words`` is included directly (the pilot wrote it to a sibling
    file; the orchestrator here persists whichever pieces it needs).
    """
    voted = rover_vote(a_words, b_words)
    n_total = len(voted)
    n_disputed = sum(w["disputed"] for w in voted)
    numeral_disputes = sum(
        1
        for w in voted
        if w["disputed"]
        and w["alt"]
        and any(is_numeral_pair(norm_word(w["w"]), t) for t in norm_word(w["alt"]).split())
    )
    disputed_examples = [
        {"word": w["w"], "start": w["start"], "end": w["end"], "alt": w["alt"]}
        for w in voted
        if w["disputed"]
    ][:15]

    return {
        "ok": True,
        "voted_words": voted,
        "n_words_A": len(a_words),
        "n_words_B": len(b_words),
        "n_voted": n_total,
        "agreement_rate": 1 - (n_disputed / max(n_total, 1)),
        "disputed_rate": n_disputed / max(n_total, 1),
        "numeral_false_disputes": numeral_disputes,
        "disputed_examples": disputed_examples,
        "hallucination_spans": hallucination_flags(voted, b_words),
        "repeated_ngram_flags": repeated_ngram_flags([norm_word(w["w"]) for w in a_words]),
        "wer_A_vs_B": wer(
            [norm_word(w["w"]) for w in a_words], [norm_word(w["w"]) for w in b_words]
        ),
        "glossary_hits_A": glossary_hits([norm_word(w["w"]) for w in a_words]),
        "glossary_hits_B": glossary_hits([norm_word(w["w"]) for w in b_words]),
    }


def _self_check() -> None:
    a = [
        {"w": "Suffering", "start": 0.0, "end": 0.3},
        {"w": "is", "start": 0.3, "end": 0.5},
        {"w": "not", "start": 0.5, "end": 0.7},
        {"w": "a", "start": 0.7, "end": 0.8},
        {"w": "fact", "start": 0.8, "end": 1.1},
    ]
    b = [
        {"w": "Suffering", "start": 0.0, "end": 0.3},
        {"w": "is", "start": 0.3, "end": 0.5},
        {"w": "not", "start": 0.5, "end": 0.7},
        {"w": "a", "start": 0.7, "end": 0.8},
        {"w": "fat", "start": 0.8, "end": 1.1},
    ]
    r = vote_stage(a, b)
    assert r["n_voted"] == 5
    assert r["disputed_rate"] == 1 / 5
    assert r["voted_words"][-1]["disputed"] is True
    assert wer(["a", "b", "c"], ["a", "b", "c"]) == 0.0
    assert wer(["a", "b", "c"], ["a", "x", "c"]) == 1 / 3
    print("vote.py self-check OK")


if __name__ == "__main__":
    _self_check()
