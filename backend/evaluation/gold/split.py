"""Deterministic video-level held-out split.

A video's questions must all land on the same side of the split, or a system
that has seen half a video's clips during dev could look good on the other
half. Splitting is a salted hash of the video id, not randomness, so the
split is reproducible across machines and runs without storing a mapping.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_SALT = "askmukthiguru-gold-v1"


def _bucket(video_id: str, salt: str) -> float:
    """Deterministic float in [0, 1) for a video id."""
    digest = hashlib.sha256(f"{salt}:{video_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0x100000000


def split_videos(
    video_ids: list[str],
    held_out_frac: float = 0.2,
    salt: str = DEFAULT_SALT,
) -> dict[str, str]:
    """Map each video id to 'held_out' or 'dev_pool'. Deterministic, order-
    independent, no video ever appears on both sides."""
    return {
        vid: "held_out" if _bucket(vid, salt) < held_out_frac else "dev_pool"
        for vid in sorted(set(video_ids))
    }


def held_out_videos(
    video_ids: list[str],
    held_out_frac: float = 0.2,
    salt: str = DEFAULT_SALT,
    exclude: set[str] | None = None,
) -> list[str]:
    """Held-out video ids, excluding any (e.g. already-used bake-off videos)."""
    exclude = exclude or set()
    split = split_videos([v for v in video_ids if v not in exclude], held_out_frac, salt)
    return sorted(v for v, side in split.items() if side == "held_out")


def load_corpus_video_ids(corpus_dir: str | Path) -> list[str]:
    """Video ids = subdirectory names under scripts/ingestion/corpus/."""
    root = Path(corpus_dir)
    return sorted(p.name for p in root.iterdir() if p.is_dir())


if __name__ == "__main__":
    ids = [f"vid{i}" for i in range(1000)]
    split_a = split_videos(ids)
    split_b = split_videos(ids)
    assert split_a == split_b, "split must be deterministic"
    assert set(split_a) == set(ids)
    held = [v for v, s in split_a.items() if s == "held_out"]
    frac = len(held) / len(ids)
    assert 0.15 < frac < 0.25, f"held-out fraction drifted: {frac}"
    excluded = held_out_videos(ids, exclude={held[0]})
    assert held[0] not in excluded
    print("ok", round(frac, 3))
