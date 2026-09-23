"""Quote gate for speaker attribution: abstain unless a sentence is safely one teacher's words."""

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "speaker_attribution", Path(__file__).resolve().parents[1] / "scripts/ops/speaker_attribution.py")
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)


def _w(text, start, end, spk, aligned=True):
    return {"w": text, "start": start, "end": end, "aligned": aligned, "spk": spk}


def _sentence(prefix, t0, spk, n=8):
    words = [_w(f"{prefix}{i}", t0 + i * 0.3, t0 + i * 0.3 + 0.2, spk) for i in range(n)]
    words[-1]["w"] += "."
    return words


def test_self_check_passes():
    sa._self_check()


def test_host_sentence_is_never_quotable():
    quotes, reasons = sa.quote_gate(_sentence("h", 0.0, "O"))
    assert quotes == [] and reasons["not_teacher"] == 1


def test_mixed_speaker_sentence_abstains():
    words = _sentence("a", 0.0, "P")
    words[3]["spk"] = "K"
    quotes, reasons = sa.quote_gate(words)
    assert quotes == [] and reasons["mixed_speaker"] == 1


def test_unaligned_word_abstains():
    words = _sentence("a", 0.0, "K")
    words[2]["aligned"] = False
    assert sa.quote_gate(words)[1]["unaligned_word"] == 1


def test_first_sentence_after_speaker_change_abstains_second_passes():
    words = _sentence("h", 0.0, "O") + _sentence("p", 5.0, "P") + _sentence("q", 9.0, "P")
    quotes, reasons = sa.quote_gate(words)
    assert reasons["first_after_change"] == 1
    assert [q["text"].split()[0] for q in quotes] == ["q0"]


def test_ambiguous_or_small_cluster_is_not_named():
    vp = {"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])}
    thr = {"P": 0.55, "K": 0.55}
    between = np.array([1.0, 1.0]) / np.sqrt(2)          # 0.71 to both teachers: no margin
    assert sa.name_cluster(between, 50, vp, thr) == "?"
    assert sa.name_cluster(np.array([1.0, 0.0]), 3, vp, thr) == "?"
    far = np.array([0.3, 0.3])                            # < 0.40 to both: a non-teacher voice
    assert sa.name_cluster(far, 50, vp, thr) == "O"
