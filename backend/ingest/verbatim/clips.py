"""Stage: label voted words with a speaker, then build sentence-bounded clips.

Thin glue over two already-tested pieces:
  - `speaker_verify.label_words_by_speaker` (this module) attaches per-word ``spk``.
  - `services.speaker_diarization.build_clips_from_labelled_words` (imported,
    never copied -- another agent owns that file) turns labelled words into
    quotable, sentence-bounded teacher clips.

This is the v2 clip builder (passages_C in the pilot's naming), not the older
fragment-prone run_clips.py builder (passages_B) -- see
`services/speaker_diarization.py`'s module docstring for why.
"""

from __future__ import annotations

from typing import Any

from ingest.verbatim.speaker_verify import label_words_by_speaker
from services.speaker_diarization import build_clips_from_labelled_words


def clips_stage(
    voted_words: list[dict[str, Any]],
    t_centres: list[float],
    win_lab: list[str],
    video_id: str,
    **clip_kwargs: Any,
) -> dict[str, Any]:
    """Label + segment one video's voted words into teacher clips.

    Returns ``{"labelled_words": [...], "clips": [...], "stats": {...},
    "host_leak_count": int}`` -- ``labelled_words`` is the verbatim transcript
    layer (nothing cleans it); ``clips`` is the derived, display-safe layer.
    """
    labelled = label_words_by_speaker(voted_words, t_centres, win_lab)
    clip_list, stats = build_clips_from_labelled_words(labelled, video_id, **clip_kwargs)
    host_leak = (
        sum(1 for c in clip_list if c["speaker"] not in ("preethaji", "krishnaji"))
        if clip_list
        else 0
    )
    return {
        "labelled_words": labelled,
        "clips": clip_list,
        "stats": stats,
        "host_leak_count": host_leak,
    }


def _self_check() -> None:
    words = [
        {"w": "Suffering", "start": 0.0, "end": 0.3},
        {"w": "is", "start": 0.3, "end": 0.5},
        {"w": "not", "start": 0.5, "end": 0.7},
        {"w": "a", "start": 0.7, "end": 0.8},
        {"w": "fact.", "start": 0.8, "end": 1.1},
        {"w": "question", "start": 1.2, "end": 1.6},
        {"w": "It", "start": 1.7, "end": 1.8},
        {"w": "is", "start": 1.8, "end": 1.9},
        {"w": "a", "start": 1.9, "end": 2.0},
        {"w": "perception.", "start": 2.0, "end": 2.5},
    ]
    t_centres = [0.55, 1.4, 2.25]
    win_lab = ["K", "O", "K"]
    r = clips_stage(words, t_centres, win_lab, "self_check_vid", min_words=3)
    assert len(r["clips"]) == 2
    assert all("question" not in c["verbatim_text"] for c in r["clips"])
    assert r["host_leak_count"] == 0
    print("clips.py self-check OK")


if __name__ == "__main__":
    _self_check()
