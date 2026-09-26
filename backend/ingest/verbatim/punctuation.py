"""Stage: punctuation + truecasing DISPLAY layer, with a strict zero-word-change assert.

Ported unchanged from the pilot's run_punct.py
(~/mukthiguru_attribution_data/pilot50_2026-09-25/, fixed 2026-09-26 for the
pre-punctuated-input bug -- see the inline comment below and
test_run_punct.py, ported here as test_verbatim_punctuation.py).

This produces the DISPLAY layer only. The verbatim layer (`voted_words`) is
never touched -- ``run_verbatim_pipeline`` persists both, and callers must
render quotes from the verbatim layer, never this one.

The punctuation-restoration model is the only model call in this stage; it
sits behind the injectable `Punctuator` protocol so `diff_norm_word_sequences`
and `punctuate_stage`'s own bookkeeping are testable without loading it.
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from ingest.verbatim.vote import norm_word


def chunk(words: list[str], size: int = 200) -> Iterator[list[str]]:
    for i in range(0, len(words), size):
        yield words[i:i + size]


def diff_norm_word_sequences(verbatim_norm: list[str], display_norm: list[str]) -> list[dict]:
    """Case/punctuation-insensitive opcodes between two normalised word sequences."""
    diffs = []
    if verbatim_norm != display_norm:
        import difflib

        sm = difflib.SequenceMatcher(a=verbatim_norm, b=display_norm, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                diffs.append({"tag": tag, "verbatim": verbatim_norm[i1:i2], "display": display_norm[j1:j2]})
    return diffs


class Punctuator(Protocol):
    def infer(self, texts: list[str]) -> list:
        """`texts` is a length-1 list; returns a list whose [0] is either a
        sentence string or a list of sentence strings (model-version dependent,
        matching PunctCapSegModelONNX's actual output shape)."""
        ...


def default_punctuator() -> Punctuator:
    """Loads the ONNX punctuation-restoration model -- only called when a
    caller doesn't inject a fake one."""
    from punctuators.models import PunctCapSegModelONNX

    return PunctCapSegModelONNX.from_pretrained("pcs_en")


def punctuate_stage(voted_words: list[dict[str, Any]], *, model: Punctuator | None = None,
                     chunk_size: int = 200) -> dict[str, Any]:
    """Restore punctuation/case for display, asserting zero word change.

    Root cause (2026-09-26): voted words can already carry punctuation (ROVER
    voting keeps whichever ASR's token text won, and ASR output is not always
    bare words e.g. "heal.", "Krishnaji,"). Feeding that pre-punctuated text
    into the punctuation-restoration model confuses its sentence segmentation:
    it treats the embedded "." as a boundary and echoes a stray leading "."
    (or ",", "..") as its own token at the start of the next "sentence" -- a
    token with no counterpart in verbatim_words, which showed up as spurious
    `insert` diffs (99 on rGcNJ_Nsuy8: 2,392 -> 2,489). Fix: feed the model
    already-normalised (punctuation-stripped) words, so it only ever sees
    clean text to punctuate/case, never re-segments on punctuation we fed it
    ourselves.
    """
    if not voted_words:
        return {"ok": False, "reason": "no_voted_words"}
    if model is None:
        model = default_punctuator()

    verbatim_words = [w["w"].lower() for w in voted_words]
    verbatim_norm_all = [norm_word(w) for w in verbatim_words]
    # A tiny number of voted "words" are pure punctuation (e.g. a lone "%") and
    # normalise to "". They aren't words the punctuation model can restate, so
    # they're excluded from both the model input and the comparison -- not
    # silently dropped from one side only.
    model_input_words = [w for w in verbatim_norm_all if w]
    verbatim_norm = [w for w in verbatim_norm_all if w]

    display_words: list[str] = []
    for ch in chunk(model_input_words, chunk_size):
        out = model.infer([" ".join(ch)])
        sentences = out[0] if isinstance(out[0], list) else [out[0]]
        display_words.extend(" ".join(sentences).split())

    display_norm = [norm_word(w) for w in display_words]
    diffs = diff_norm_word_sequences(verbatim_norm, display_norm)

    return {
        "ok": True,
        "n_verbatim_words": len(verbatim_norm),
        "n_display_words": len(display_norm),
        "zero_change_assert_passed": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs_sample": diffs[:10],
        "display_words": display_words,
    }


def _self_check() -> None:
    class FakeModel:
        def infer(self, texts: list[str]) -> list:
            # Punctuates/cases only, never touches word identity.
            return [[" ".join(w.capitalize() for w in texts[0].split()) + "."]]

    voted = [{"w": "love"}, {"w": "and"}, {"w": "connection"}]
    r = punctuate_stage(voted, model=FakeModel())
    assert r["ok"] and r["zero_change_assert_passed"], r

    class BuggyModel:
        def infer(self, texts: list[str]) -> list:
            parts = texts[0].split(". ")
            return [[parts[0] + "."] + [". " + p for p in parts[1:]]]

    voted_pre_punct = [{"w": "to"}, {"w": "heal."}, {"w": "it"}, {"w": "is"}, {"w": "not"}]
    r2 = punctuate_stage(voted_pre_punct, model=BuggyModel())
    # Feeding norm_word-stripped input means the buggy model never sees an
    # embedded "." to mis-segment on, so this must stay clean even against a
    # model that reproduces the historical bug given raw punctuated input.
    assert r2["zero_change_assert_passed"], r2
    print("punctuation.py self-check OK")


if __name__ == "__main__":
    _self_check()
