"""Stage: ECAPA teacher-speaker verification, reusing scripts/ops/speaker_attribution.py.

Ported from the pilot's run_speaker.py + the speaker-labelling half of
run_clips.py (~/mukthiguru_attribution_data/pilot50_2026-09-25/).

The heavy model call (ECAPA embedding, `embed_windows`) is the only part that
loads a model. It sits behind the injectable `Embedder` protocol so every
other function here -- clustering, naming, and per-word speaker labelling --
is a pure function tests can exercise on synthetic fixtures without ever
loading SpeechBrain. `cluster`/`name_cluster`/`unit_mean` are imported (not
copied) from `scripts.ops.speaker_attribution`, which this module never edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from scripts.ops.speaker_attribution import WIN_S, cluster, name_cluster, unit_mean

_SNAP_RADIUS_S = 1.5  # a word farther than this from its nearest window centre is unlabelled ("?")


class Embedder(Protocol):
    def __call__(self, wav_path: str, hop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
        """Return (window start times, L2-normalised ECAPA embeddings)."""
        ...


def default_embedder(wav_path: str, hop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Loads SpeechBrain's ECAPA model -- only called when a caller doesn't inject a fake one."""
    from scripts.ops.speaker_attribution import embed_windows

    return embed_windows(Path(wav_path), hop=hop)


def cluster_and_name_windows(
    t_starts: np.ndarray, embeddings: np.ndarray, voiceprints: dict[str, np.ndarray], thresholds: dict[str, float],
) -> dict[str, Any]:
    """Pure: cluster embedding windows and name each cluster P/K/O/?.

    Returns the same shape as the pilot's raw/<id>_speaker.json (minus
    `ok`/`embed_time_s`, which the caller that owns timing/error-handling adds).
    """
    if len(embeddings) == 0:
        return {"t_centres": [], "win_lab": [], "n_windows": 0,
                "time_share": {"teacher_P": 0.0, "teacher_K": 0.0, "host_other": 0.0, "unknown": 0.0},
                "cluster_names": {}}

    lab = cluster(embeddings)
    names = {c: name_cluster(unit_mean(embeddings[lab == c]), int((lab == c).sum()), voiceprints, thresholds)
             for c in np.unique(lab)}
    win_lab = np.array([names[c] for c in lab])
    t_centres = t_starts + WIN_S / 2

    counts: dict[str, int] = {}
    for lbl in win_lab:
        counts[lbl] = counts.get(lbl, 0) + 1
    total = max(len(win_lab), 1)
    share = {"teacher_P": counts.get("P", 0) / total, "teacher_K": counts.get("K", 0) / total,
             "host_other": counts.get("O", 0) / total, "unknown": counts.get("?", 0) / total}

    return {
        "t_centres": t_centres.tolist(), "win_lab": win_lab.tolist(), "n_windows": len(win_lab),
        "time_share": share, "cluster_names": {str(k): v for k, v in names.items()},
    }


def verify_speakers(
    wav_path: str,
    voiceprints: dict[str, np.ndarray],
    thresholds: dict[str, float],
    *,
    hop: float = 1.0,
    embedder: Callable[[str, float], tuple[np.ndarray, np.ndarray]] = default_embedder,
) -> dict[str, Any]:
    """Full speaker-verify stage for one video's audio. Fails closed: any
    exception (including a missing/corrupt wav) is caught and returned as
    ``{"ok": False, "error": ...}`` rather than raised, matching the pilot's
    run_speaker.py behaviour so a bad video never kills a batch run."""
    import time

    try:
        t0 = time.time()
        t_starts, embeddings = embedder(wav_path, hop)
        embed_time_s = time.time() - t0
        result = cluster_and_name_windows(t_starts, embeddings, voiceprints, thresholds)
        return {"ok": True, "embed_time_s": embed_time_s, **result}
    except Exception as e:  # noqa: BLE001 - deliberate fail-closed, mirrors run_speaker.py
        return {"ok": False, "error": str(e)}


def label_words_by_speaker(
    voted_words: list[dict[str, Any]],
    t_centres: list[float],
    win_lab: list[str],
    *,
    snap_radius_s: float = _SNAP_RADIUS_S,
    trim_radius_s: float = 0.5,
) -> list[dict[str, Any]]:
    """Attach a per-word ``spk`` label from the nearest voice-embedding window.

    Ported from run_clips.py's ``label_speaker_for_words``: a word farther
    than `snap_radius_s` from its nearest window centre is unlabelled ("?").
    A second pass then unlabels any window-labelled word that sits within
    `trim_radius_s` of a *different* speaker-change boundary elsewhere in the
    transcript, which erases spurious one-word bleed at speaker-change edges
    (voice embeddings smear across a turn boundary more than word timing does).
    """
    if not voted_words:
        return []
    t = np.asarray(t_centres, dtype=float)
    out: list[dict[str, Any]] = []
    for w in voted_words:
        mid = (w["start"] + w["end"]) / 2
        if len(t) == 0:
            spk = "?"
        else:
            i = int(np.argmin(np.abs(t - mid)))
            spk = win_lab[i] if abs(t[i] - mid) <= snap_radius_s else "?"
        out.append({**w, "spk": spk})

    for i in range(1, len(out)):
        if out[i]["spk"] != out[i - 1]["spk"]:
            for j in range(len(out)):
                if (abs(out[j]["start"] - out[i]["start"]) <= trim_radius_s
                        and out[j]["spk"] != out[i]["spk"] and out[j]["spk"] != out[i - 1]["spk"]):
                    out[j]["spk"] = "?"
    return out


def _self_check() -> None:
    vp = {"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])}
    thr = {"P": 0.55, "K": 0.55}
    t_starts = np.array([0.0, 2.0, 4.0])
    e = np.array([[1.0, 0.0]] * 6 + [[0.0, 1.0]] * 6).reshape(-1, 2)
    # Fake embedder: no model load, matches the injectable-interface contract.
    fake_embed = lambda wav, hop=1.0: (t_starts, e[: len(t_starts)])  # noqa: E731
    r = verify_speakers("fake.wav", vp, thr, embedder=fake_embed)
    assert r["ok"] is True
    assert r["n_windows"] == 3

    words = [{"w": "hi", "start": 0.5, "end": 1.0}, {"w": "there", "start": 20.0, "end": 20.5}]
    labelled = label_words_by_speaker(words, [1.0, 21.0], ["P", "K"])
    assert labelled[0]["spk"] == "P" and labelled[1]["spk"] == "K"
    print("speaker_verify.py self-check OK")


if __name__ == "__main__":
    _self_check()
