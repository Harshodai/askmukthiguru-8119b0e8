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

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

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
    t_starts: np.ndarray,
    embeddings: np.ndarray,
    voiceprints: dict[str, np.ndarray],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Pure: cluster embedding windows and name each cluster P/K/O/?.

    Returns the same shape as the pilot's raw/<id>_speaker.json (minus
    `ok`/`embed_time_s`, which the caller that owns timing/error-handling adds).
    """
    if len(embeddings) == 0:
        return {
            "t_centres": [],
            "win_lab": [],
            "n_windows": 0,
            "time_share": {"teacher_P": 0.0, "teacher_K": 0.0, "host_other": 0.0, "unknown": 0.0},
            "cluster_names": {},
        }

    lab = cluster(embeddings)
    names = {
        c: name_cluster(
            unit_mean(embeddings[lab == c]), int((lab == c).sum()), voiceprints, thresholds
        )
        for c in np.unique(lab)
    }
    win_lab = np.array([names[c] for c in lab])
    t_centres = t_starts + WIN_S / 2

    counts: dict[str, int] = {}
    for lbl in win_lab:
        counts[lbl] = counts.get(lbl, 0) + 1
    total = max(len(win_lab), 1)
    share = {
        "teacher_P": counts.get("P", 0) / total,
        "teacher_K": counts.get("K", 0) / total,
        "host_other": counts.get("O", 0) / total,
        "unknown": counts.get("?", 0) / total,
    }

    return {
        "t_centres": t_centres.tolist(),
        "win_lab": win_lab.tolist(),
        "n_windows": len(win_lab),
        "time_share": share,
        "cluster_names": {str(k): v for k, v in names.items()},
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


# ponytail: S1 turn-start prefix recovery — fixes mid-sentence heads without an LLM call
_TERMINAL_PUNCTUATION = (".", "?", "!")
_MAX_PREFIX_WORDS = 6
_MIN_TEACHER_WORDS = 3
_TEACHER_SPEAKERS = frozenset({"P", "K"})
_PREFIX_SPEAKERS = frozenset({"O", "?"})
_SENTENCE_STARTERS = frozenset(
    {
        "It",
        "The",
        "Your",
        "She",
        "He",
        "We",
        "They",
        "This",
        "That",
        "There",
        "Here",
        "What",
        "When",
        "Where",
        "Why",
        "How",
        "In",
        "On",
        "At",
        "If",
        "As",
        "So",
        "My",
        "Our",
        "His",
        "Her",
    }
)


def _is_terminal_word(w_str: str) -> bool:
    """Return True if word ends with terminal sentence punctuation (., ?, !)."""
    clean = w_str.rstrip("\"'”’) ")
    return bool(clean and clean[-1] in _TERMINAL_PUNCTUATION)


def relabel_turn_start_prefixes(
    words: list[dict[str, Any]],
    *,
    sentence_boundaries: list[tuple[float, float]] | None = None,
    max_prefix_words: int = _MAX_PREFIX_WORDS,
    min_teacher_words: int = _MIN_TEACHER_WORDS,
) -> list[dict[str, Any]]:
    """Relabel mislabelled turn-start opening words to the prevailing teacher.

    # ponytail: S1 turn-start prefix recovery — fixes mid-sentence heads without an LLM call

    When a sentence (or clause preceded by terminal punctuation `.`, `?`, `!`)
    begins with <= 6 words labelled 'O' or '?', and the remainder of that sentence
    (at least 3 words) is uniformly labelled by a single teacher ('P' or 'K'),
    relabel those <= 6 opening words to that teacher.
    """
    if not words:
        return []

    out = [{**w} for w in words]

    if sentence_boundaries is not None:
        sentences: list[list[int]] = []
        for b_start, b_end in sentence_boundaries:
            sent_indices = [
                i for i, w in enumerate(out) if b_start <= (w["start"] + w["end"]) / 2.0 <= b_end
            ]
            if sent_indices:
                sentences.append(sent_indices)
    else:
        sentences = []
        current: list[int] = []
        for i, w in enumerate(out):
            w_text = w.get("w", "").rstrip("\"'”’) ")
            # If current sentence already has tokens and this token is a capitalized
            # sentence starter (e.g. "It", "The", "Your"), start a new sentence boundary
            # even if the preceding word missed terminal punctuation (e.g. unpunctuated host utterance).
            if (
                current
                and w_text in _SENTENCE_STARTERS
                and not _is_terminal_word(out[current[-1]].get("w", ""))
            ):
                sentences.append(current)
                current = []

            current.append(i)
            if _is_terminal_word(w.get("w", "")):
                sentences.append(current)
                current = []
        if current:
            sentences.append(current)

    for indices in sentences:
        if not indices:
            continue
        prefix_len = 0
        while prefix_len < len(indices) and out[indices[prefix_len]].get("spk") in _PREFIX_SPEAKERS:
            prefix_len += 1

        if prefix_len == 0 or prefix_len > max_prefix_words:
            continue

        # Ask-5 host-exclusion gate (test_clips_v2::test_b): a sentence starting
        # immediately after a terminal-punctuated TEACHER word follows a COMPLETED
        # teacher turn, so an O-labelled word there is genuine host interjection
        # ("Right.", "question"), never a mislabelled teacher head. Never absorb
        # it -- precision over recall (host speech must never enter a clip).
        # Recovery stays open after host/unknown terminal words and at transcript
        # start (pred < 0), which is where turn-start mislabelling actually occurs.
        pred = indices[0] - 1
        if pred >= 0:
            prev = out[pred]
            if prev.get("spk") in _TEACHER_SPEAKERS and _is_terminal_word(prev.get("w", "")):
                continue

        remainder_indices = indices[prefix_len:]
        if len(remainder_indices) < min_teacher_words:
            continue

        remainder_spks = {out[i].get("spk") for i in remainder_indices}
        if len(remainder_spks) == 1:
            teacher = next(iter(remainder_spks))
            if teacher in _TEACHER_SPEAKERS:
                for p_idx in indices[:prefix_len]:
                    out[p_idx]["spk"] = teacher

    return out


def label_words_by_speaker(
    voted_words: list[dict[str, Any]],
    t_centres: list[float],
    win_lab: list[str],
    *,
    snap_radius_s: float = _SNAP_RADIUS_S,
    trim_radius_s: float = 0.5,
    sentence_boundaries: list[tuple[float, float]] | None = None,
    max_prefix_words: int = _MAX_PREFIX_WORDS,
    min_teacher_words: int = _MIN_TEACHER_WORDS,
) -> list[dict[str, Any]]:
    """Attach a per-word ``spk`` label from the nearest voice-embedding window.

    Ported from run_clips.py's ``label_speaker_for_words``: a word farther
    than `snap_radius_s` from its nearest window centre is unlabelled ("?").
    A second pass then unlabels any window-labelled word that sits within
    `trim_radius_s` of a *different* speaker-change boundary elsewhere in the
    transcript, which erases spurious one-word bleed at speaker-change edges
    (voice embeddings smear across a turn boundary more than word timing does).
    Finally, `relabel_turn_start_prefixes` recovers teacher opening words
    trimmed or mislabelled at turn start.
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
                if (
                    abs(out[j]["start"] - out[i]["start"]) <= trim_radius_s
                    and out[j]["spk"] != out[i]["spk"]
                    and out[j]["spk"] != out[i - 1]["spk"]
                ):
                    out[j]["spk"] = "?"

    # ponytail: S1 turn-start prefix recovery — fixes mid-sentence heads without an LLM call
    recovered = relabel_turn_start_prefixes(
        out,
        sentence_boundaries=sentence_boundaries,
        max_prefix_words=max_prefix_words,
        min_teacher_words=min_teacher_words,
    )
    return apply_transition_dilation_guardband(recovered, dilation_s=0.30)


def apply_transition_dilation_guardband(
    words: list[dict[str, Any]],
    *,
    dilation_s: float = 0.30,
) -> list[dict[str, Any]]:
    """Dilation guardband for speaker turn boundaries (ICASSP 2024 / NIST ROVER SOTA).

    Identifies speaker turn transitions where spk changes (e.g. O -> P, P -> K).
    For any word whose midpoint falls within [t_trans - dilation_s, t_trans + dilation_s],
    mark with near_speaker_transition=True. If the turn involves a host or unknown speaker,
    mark with guardband_dilated=True and ensure it does not leak into a teacher clip.
    """
    if len(words) < 2:
        return words

    transition_times = []
    for i in range(1, len(words)):
        prev_spk = words[i - 1].get("spk")
        curr_spk = words[i].get("spk")
        if prev_spk and curr_spk and prev_spk != curr_spk:
            t_trans = (words[i - 1]["end"] + words[i]["start"]) / 2.0
            transition_times.append((t_trans, prev_spk, curr_spk))

    if not transition_times:
        return words

    out = [{**w} for w in words]
    for w in out:
        w_mid = (w["start"] + w["end"]) / 2.0
        for t_trans, s1, s2 in transition_times:
            if abs(w_mid - t_trans) <= dilation_s:
                w["near_speaker_transition"] = True
                if (s1 in _TEACHER_SPEAKERS and s2 not in _TEACHER_SPEAKERS) or (
                    s2 in _TEACHER_SPEAKERS and s1 not in _TEACHER_SPEAKERS
                ):
                    w["guardband_dilated"] = True
                    if w.get("spk") not in _TEACHER_SPEAKERS:
                        w["spk"] = "?"
    return out


def check_clip_transition_guardband(
    clip_start: float,
    clip_end: float,
    transition_times: list[float],
    *,
    dilation_s: float = 0.30,
) -> bool:
    """Return True if clip boundaries violate the transition dilation guardband.

    A clip violates the guardband if its start or end time falls within
    dilation_s of an acoustic speaker turn boundary.
    """
    for t in transition_times:
        if abs(clip_start - t) < dilation_s or abs(clip_end - t) < dilation_s:
            return True
    return False


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

    # ponytail: S1 turn-start prefix recovery — verify against real transcript fixture
    # Primary: evals/grounding/fixtures/x-mTRlE0TC4.md (committed to git)
    repo_root = Path(__file__).resolve().parents[3]
    fixture_path = repo_root / "evals" / "grounding" / "fixtures" / "x-mTRlE0TC4.md"
    if not fixture_path.is_file():
        # Fallback to backend-local test fixture if repo root evals is not mounted
        fixture_path = (
            Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "data_quality"
            / "corpus"
            / "clean_vid_001"
            / "canonical_segments.json"
        )

    assert fixture_path.is_file(), f"Transcript fixture missing: {fixture_path}"
    fixture_text = fixture_path.read_text(encoding="utf-8")

    # Real Krishnaji sentence from fixture:
    # "Individual transformation is at the crux of our work."
    teacher_sent = "Individual transformation is at the crux of our work."
    assert teacher_sent in fixture_text, f"Sentence '{teacher_sent}' missing from fixture"
    raw_teacher_words = teacher_sent.split()
    # Simulate first 2 words mislabelled as 'O' (host bleed), remaining 7 as 'K' (Krishnaji)
    t_words = [
        {"w": w, "start": i * 0.4, "end": i * 0.4 + 0.35, "spk": "O" if i < 2 else "K"}
        for i, w in enumerate(raw_teacher_words)
    ]
    recovered = relabel_turn_start_prefixes(t_words)
    assert all(w["spk"] == "K" for w in recovered), (
        f"Expected all 'K', got {[w['spk'] for w in recovered]}"
    )

    # Real host question from fixture:
    # "Sri Krishnaji, what do you mean by this transformation?"
    if "Sri Krishnaji, what do you mean by this transformation?" in fixture_text:
        host_sent = "Sri Krishnaji, what do you mean by this transformation?"
        h_words = [
            {"w": w, "start": i * 0.4, "end": i * 0.4 + 0.35, "spk": "O"}
            for i, w in enumerate(host_sent.split())
        ]
        host_checked = relabel_turn_start_prefixes(h_words)
        assert all(w["spk"] == "O" for w in host_checked), (
            "Host sentence was erroneously relabelled"
        )

    print("speaker_verify.py self-check OK")


if __name__ == "__main__":
    _self_check()
