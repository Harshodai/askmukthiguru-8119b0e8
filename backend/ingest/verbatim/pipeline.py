"""Orchestrator: run_verbatim_pipeline(video_id, paths, cfg).

Wires the stage functions in this package into one resumable per-video run:

    vote -> asr_agreement gate (recorded, not a hard stop -- matches the
            pilot, where the gate is applied downstream at index-build time,
            not at clip-build time) -> speaker_verify -> clips -> punctuation

ASR itself (whisper/parakeet) is out of scope for this module -- `paths`
points at ALREADY-PRODUCED ASR word lists (see README.md). That is also why
this orchestrator has no ASR-invocation branch to keep injectable: the only
model calls left are the ECAPA speaker embedder (`speaker_verify.Embedder`)
and the punctuation-restoration model (`punctuation.Punctuator`), both
already injectable in their own stage modules.

Idempotent/resumable per stage via `ingest.handlers.checkpoint.IngestionCheckpoint`
(no new checkpoint format): each stage's checkpoint key is
``verbatim:<video_id>:<stage>``; a stage already marked processed is skipped
and its prior output re-loaded from `paths` instead of recomputed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from ingest.handlers.checkpoint import IngestionCheckpoint
from ingest.verbatim.clips import clips_stage
from ingest.verbatim.gates import check_asr_agreement
from ingest.verbatim.punctuation import Punctuator, default_punctuator, punctuate_stage
from ingest.verbatim.speaker_verify import Embedder, default_embedder, verify_speakers
from ingest.verbatim.vote import vote_stage


@dataclass
class VerbatimPaths:
    """Every path this pipeline reads or writes for one video.

    ``whisper_json``/``parakeet_json`` are pre-existing ASR outputs (each a
    dict with a ``"words"`` list, as produced by the pilot's run_asr.py or an
    equivalent production ASR step -- not built by this module). ``wav`` is
    only needed if the speaker-verify stage isn't given a fake embedder.
    Output paths are created under ``out_dir`` if not given explicitly.
    """

    video_id: str
    whisper_json: Path
    parakeet_json: Path
    wav: Optional[Path] = None
    out_dir: Optional[Path] = None
    vote_json: Path = field(init=False, default=None)  # type: ignore[assignment]
    speaker_json: Path = field(init=False, default=None)  # type: ignore[assignment]
    clips_json: Path = field(init=False, default=None)  # type: ignore[assignment]
    transcript_json: Path = field(init=False, default=None)  # type: ignore[assignment]
    punct_json: Path = field(init=False, default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        d = Path(self.out_dir) if self.out_dir else Path(self.whisper_json).parent
        d.mkdir(parents=True, exist_ok=True)
        self.vote_json = d / f"{self.video_id}_vote.json"
        self.speaker_json = d / f"{self.video_id}_speaker.json"
        self.clips_json = d / f"{self.video_id}_clips.json"
        self.transcript_json = d / f"{self.video_id}_transcript.json"
        self.punct_json = d / f"{self.video_id}_punct.json"


@dataclass
class VerbatimConfig:
    voiceprints: dict[str, np.ndarray] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    min_asr_agreement: float = 0.80
    embedder: Callable[..., Any] = default_embedder
    punctuator_factory: Callable[[], Punctuator] = default_punctuator
    clip_kwargs: dict[str, Any] = field(default_factory=dict)
    checkpoint: Optional[IngestionCheckpoint] = None


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def _write_json(path: Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=1))


def _run_stage(checkpoint: IngestionCheckpoint, key: str, out_path: Path, compute: Callable[[], Any]) -> Any:
    """Skip `compute` and reload `out_path` if the checkpoint says this stage
    already ran; otherwise compute, persist, and mark it done."""
    if checkpoint.is_processed(key) and Path(out_path).exists():
        return _load_json(out_path)
    result = compute()
    _write_json(out_path, result)
    checkpoint.save(key, {"path": str(out_path)})
    return result


def run_verbatim_pipeline(video_id: str, paths: VerbatimPaths, cfg: Optional[VerbatimConfig] = None) -> dict[str, Any]:
    """Run the full verbatim pipeline for one video. Returns a summary dict
    with every stage's status, the ASR-agreement gate result, and the output
    paths (so a caller -- or `build_first_person_index.py` -- can find the
    clips/transcript layers this run produced)."""
    cfg = cfg or VerbatimConfig()
    checkpoint = cfg.checkpoint or IngestionCheckpoint()

    whisper = _load_json(paths.whisper_json)
    parakeet = _load_json(paths.parakeet_json)
    if not whisper.get("ok", True) or not parakeet.get("ok", True):
        return {"video_id": video_id, "ok": False, "reason": "asr_inputs_missing_or_failed"}

    vote_result = _run_stage(
        checkpoint, f"verbatim:{video_id}:vote", paths.vote_json,
        lambda: vote_stage(whisper["words"], parakeet["words"]),
    )
    agreement_reason = check_asr_agreement(vote_result, cfg.min_asr_agreement)

    speaker_result = _run_stage(
        checkpoint, f"verbatim:{video_id}:speaker", paths.speaker_json,
        lambda: verify_speakers(str(paths.wav), cfg.voiceprints, cfg.thresholds, embedder=cfg.embedder),
    )

    clips_result: Optional[dict[str, Any]] = None
    if speaker_result.get("ok"):
        clips_result = _run_stage(
            checkpoint, f"verbatim:{video_id}:clips", paths.clips_json,
            lambda: clips_stage(
                vote_result["voted_words"], speaker_result["t_centres"], speaker_result["win_lab"],
                video_id, **cfg.clip_kwargs,
            ),
        )
        if not Path(paths.transcript_json).exists():
            _write_json(paths.transcript_json, clips_result["labelled_words"])

    punct_result = _run_stage(
        checkpoint, f"verbatim:{video_id}:punct", paths.punct_json,
        lambda: punctuate_stage(vote_result["voted_words"], model=cfg.punctuator_factory()),
    )

    return {
        "video_id": video_id,
        "ok": True,
        "asr_agreement_rate": vote_result.get("agreement_rate"),
        "asr_agreement_gate_reason": agreement_reason,
        "speaker_ok": speaker_result.get("ok"),
        "n_clips": len(clips_result["clips"]) if clips_result else 0,
        "punct_zero_change_assert_passed": punct_result.get("zero_change_assert_passed"),
        "paths": {
            "vote": str(paths.vote_json), "speaker": str(paths.speaker_json),
            "clips": str(paths.clips_json), "transcript": str(paths.transcript_json),
            "punct": str(paths.punct_json),
        },
    }


def _self_check() -> None:
    """End-to-end run on tiny synthetic fixtures -- no models, no real files
    left behind outside a temp dir, no network."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whisper_words = [
            {"w": "Suffering", "start": 0.0, "end": 0.3}, {"w": "is", "start": 0.3, "end": 0.5},
            {"w": "not", "start": 0.5, "end": 0.7}, {"w": "a", "start": 0.7, "end": 0.8},
            {"w": "fact.", "start": 0.8, "end": 1.1},
        ]
        parakeet_words = whisper_words  # perfect agreement for this fixture
        _write_json(tmp_path / "v_whisper.json", {"ok": True, "words": whisper_words})
        _write_json(tmp_path / "v_parakeet.json", {"ok": True, "words": parakeet_words})

        paths = VerbatimPaths(
            video_id="v", whisper_json=tmp_path / "v_whisper.json", parakeet_json=tmp_path / "v_parakeet.json",
            wav=tmp_path / "v.wav", out_dir=tmp_path,
        )

        # 5 identical windows (>= MIN_CLUSTER_WINDOWS in speaker_attribution.py,
        # else the cluster abstains as "?" regardless of voiceprint match) all
        # centred near the fixture words' timing, matching the "preethaji" voiceprint.
        fake_embed: Embedder = lambda wav, hop=1.0: (  # noqa: E731
            np.array([0.5, 0.5, 0.5, 0.5, 0.5]), np.array([[1.0, 0.0]] * 5)
        )

        class FakePunctuator:
            def infer(self, texts: list[str]) -> list:
                return [[texts[0].capitalize() + "."]]

        cfg = VerbatimConfig(
            voiceprints={"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])},
            thresholds={"P": 0.5, "K": 0.5},
            embedder=fake_embed,
            punctuator_factory=FakePunctuator,
            clip_kwargs={"min_words": 3},
            checkpoint=IngestionCheckpoint(filepath=str(tmp_path / "checkpoint.json")),
        )

        summary = run_verbatim_pipeline("v", paths, cfg)
        assert summary["ok"] is True
        assert summary["asr_agreement_rate"] == 1.0
        assert summary["asr_agreement_gate_reason"] is None
        assert summary["n_clips"] == 1

        # Resuming must skip recompute and reload identical output.
        summary2 = run_verbatim_pipeline("v", paths, cfg)
        assert summary2["n_clips"] == summary["n_clips"]

    print("pipeline.py self-check OK")


if __name__ == "__main__":
    _self_check()
