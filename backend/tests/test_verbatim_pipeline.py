"""Unit tests for ingest.verbatim.pipeline.run_verbatim_pipeline.

No models: the speaker embedder and punctuation model are always injected
fakes via VerbatimConfig. Uses a real IngestionCheckpoint against a tmp_path
file (no Redis/Supabase in this test env, so it exercises the local-JSON tier).
"""

import json

import numpy as np
import pytest

from ingest.handlers.checkpoint import IngestionCheckpoint
from ingest.verbatim.pipeline import VerbatimConfig, VerbatimPaths, run_verbatim_pipeline

_VP = {"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])}
_THR = {"P": 0.5, "K": 0.5}


class _FakePunctuator:
    def infer(self, texts):
        return [[texts[0].capitalize() + "."]]


def _five_windows_preethaji(wav, hop=1.0):
    # >= MIN_CLUSTER_WINDOWS(5) in speaker_attribution.py so the cluster
    # doesn't abstain, all matching the "preethaji" voiceprint.
    return np.array([0.5] * 5), np.array([[1.0, 0.0]] * 5)


def _write_asr(path, words, ok=True):
    path.write_text(json.dumps({"ok": ok, "words": words}))


@pytest.fixture
def paths_and_cfg(tmp_path):
    words = [
        {"w": "Suffering", "start": 0.0, "end": 0.3},
        {"w": "is", "start": 0.3, "end": 0.5},
        {"w": "not", "start": 0.5, "end": 0.7},
        {"w": "a", "start": 0.7, "end": 0.8},
        {"w": "fact.", "start": 0.8, "end": 1.1},
    ]
    whisper_json = tmp_path / "v_whisper.json"
    parakeet_json = tmp_path / "v_parakeet.json"
    _write_asr(whisper_json, words)
    _write_asr(parakeet_json, words)  # perfect agreement

    paths = VerbatimPaths(
        video_id="v",
        whisper_json=whisper_json,
        parakeet_json=parakeet_json,
        wav=tmp_path / "v.wav",
        out_dir=tmp_path,
    )
    cfg = VerbatimConfig(
        voiceprints=_VP,
        thresholds=_THR,
        embedder=_five_windows_preethaji,
        punctuator_factory=_FakePunctuator,
        clip_kwargs={"min_words": 3},
        checkpoint=IngestionCheckpoint(filepath=str(tmp_path / "checkpoint.json")),
    )
    return paths, cfg


def test_pipeline_end_to_end_produces_clips_and_passes_gate(paths_and_cfg):
    paths, cfg = paths_and_cfg
    summary = run_verbatim_pipeline("v", paths, cfg)
    assert summary["ok"] is True
    assert summary["asr_agreement_rate"] == 1.0
    assert summary["asr_agreement_gate_reason"] is None
    assert summary["n_clips"] == 1
    assert summary["punct_zero_change_assert_passed"] is True


def test_pipeline_writes_verbatim_and_display_layers_to_disk(paths_and_cfg):
    paths, cfg = paths_and_cfg
    run_verbatim_pipeline("v", paths, cfg)
    assert paths.transcript_json.exists()  # verbatim layer (nothing cleans it)
    assert paths.punct_json.exists()  # derived display layer
    transcript = json.loads(paths.transcript_json.read_text())
    assert transcript[0]["w"] == "Suffering"  # unmodified verbatim word


def test_pipeline_is_resumable_and_skips_recompute_on_second_call(paths_and_cfg):
    paths, cfg = paths_and_cfg
    first = run_verbatim_pipeline("v", paths, cfg)

    # A config whose embedder would blow up if called again -- the resumed
    # run must not call it, proving the checkpoint short-circuited recompute.
    def boom(wav, hop=1.0):
        raise AssertionError("speaker-verify should not re-run on a resumed pipeline")

    cfg.embedder = boom
    second = run_verbatim_pipeline("v", paths, cfg)
    assert second["n_clips"] == first["n_clips"]
    assert second["asr_agreement_rate"] == first["asr_agreement_rate"]


def test_pipeline_flags_low_agreement_without_blocking_other_stages(tmp_path):
    a_words = [{"w": "Suffering", "start": 0.0, "end": 0.3}, {"w": "is", "start": 0.3, "end": 0.5}]
    b_words = [
        {"w": "completely", "start": 0.0, "end": 0.3},
        {"w": "different", "start": 0.3, "end": 0.5},
    ]
    whisper_json = tmp_path / "v_whisper.json"
    parakeet_json = tmp_path / "v_parakeet.json"
    _write_asr(whisper_json, a_words)
    _write_asr(parakeet_json, b_words)

    paths = VerbatimPaths(
        video_id="v",
        whisper_json=whisper_json,
        parakeet_json=parakeet_json,
        wav=tmp_path / "v.wav",
        out_dir=tmp_path,
    )
    cfg = VerbatimConfig(
        voiceprints=_VP,
        thresholds=_THR,
        embedder=_five_windows_preethaji,
        punctuator_factory=_FakePunctuator,
        checkpoint=IngestionCheckpoint(filepath=str(tmp_path / "checkpoint.json")),
    )
    summary = run_verbatim_pipeline("v", paths, cfg)
    assert summary["asr_agreement_gate_reason"] is not None
    assert summary["asr_agreement_gate_reason"].startswith("asr_agreement_low:")
    # Punctuation/clip stages still ran despite the low-agreement flag.
    assert summary["punct_zero_change_assert_passed"] is True


def test_pipeline_handles_failed_asr_input(tmp_path):
    whisper_json = tmp_path / "v_whisper.json"
    parakeet_json = tmp_path / "v_parakeet.json"
    _write_asr(whisper_json, [], ok=False)
    _write_asr(parakeet_json, [], ok=True)
    paths = VerbatimPaths(
        video_id="v", whisper_json=whisper_json, parakeet_json=parakeet_json, out_dir=tmp_path
    )
    summary = run_verbatim_pipeline("v", paths)
    assert summary["ok"] is False
    assert summary["reason"] == "asr_inputs_missing_or_failed"
