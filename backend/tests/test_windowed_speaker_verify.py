"""Tests for ingest/verbatim/windowed_speaker_verify.py.

All tests are pure-function tests that inject a fake embedder and calibration
so they never load SpeechBrain, never read real WAV files, and never hit Qdrant.

Naming convention: test_<what it tests>_<expected outcome>.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers — fake objects injected instead of real model/files
# ---------------------------------------------------------------------------


def _make_calibration(
    *,
    cosine_floor: float = 0.50,
    margin_threshold: float = 1e-6,
    max_failing_windows: int = 0,
    windowed_calibration_revision: str = "abc123",
    model_revision: str = "0f99f2d0",
    window_w_s: float = 3.0,
    window_h_s: float = 1.5,
) -> dict[str, Any]:
    return {
        "schema": "windowed-ecapa-calibration-v1",
        "calibration_available": True,
        "cosine_floor": cosine_floor,
        "margin_threshold": margin_threshold,
        "max_failing_windows": max_failing_windows,
        "windowed_calibration_revision": windowed_calibration_revision,
        "model_revision": model_revision,
        "window_w_s": window_w_s,
        "window_h_s": window_h_s,
    }


def _make_references(
    krishnaji: np.ndarray | None = None,
    preethaji: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Return 2-D reference vectors, L2-normalised."""
    kv = krishnaji if krishnaji is not None else np.array([1.0, 0.0], dtype=np.float32)
    pv = preethaji if preethaji is not None else np.array([0.0, 1.0], dtype=np.float32)
    return {"krishnaji": kv, "preethaji": pv}


class _FakeEmbedder:
    """Deterministic embedder for tests: always returns a fixed vector."""

    def __init__(self, vector: np.ndarray) -> None:
        self._vector = np.asarray(vector, dtype=np.float32)

    def encode_batch(self, batch):
        """Return a 2-D tensor with one row per sample in the batch."""
        import torch

        rows = batch.shape[0] if hasattr(batch, "shape") else 1
        return torch.from_numpy(np.stack([self._vector] * rows, axis=0)[:, np.newaxis, :])


def _make_wav(tmp_dir: Path, video_id: str, duration_s: float = 5.0) -> Path:
    """Write a minimal valid 16-bit mono 16 kHz WAV."""
    import wave

    wav_path = tmp_dir / f"{video_id}.wav"
    sr = 16000
    n_frames = int(duration_s * sr)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        # Write non-silent audio so silence-skip does not eat all windows.
        data = (np.sin(2 * np.pi * 440 * np.arange(n_frames) / sr) * 10000).astype(np.int16)
        wf.writeframes(data.tobytes())
    return wav_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture()
def cal_file(tmp_dir):
    cal = _make_calibration()
    p = tmp_dir / "windowed_ecapa_calibration.json"
    p.write_text(json.dumps(cal))
    return p


@pytest.fixture()
def ref_file(tmp_dir):
    refs = _make_references()
    p = tmp_dir / "references.npz"
    np.savez(p, **refs)
    return p


@pytest.fixture()
def wav_dir(tmp_dir):
    return tmp_dir  # WAV files written per test into this dir


# ---------------------------------------------------------------------------
# Tests: WindowedEcapaVerifier construction
# ---------------------------------------------------------------------------


class TestWindowedEcapaVerifierInit:
    def test_raises_on_missing_calibration(self, tmp_dir, ref_file):
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        with pytest.raises(FileNotFoundError, match="calibration"):
            WindowedEcapaVerifier(
                calibration_path=tmp_dir / "nonexistent.json",
                references_path=ref_file,
                audio_dir=tmp_dir,
            )

    def test_raises_on_missing_references(self, tmp_dir, cal_file):
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        with pytest.raises(FileNotFoundError, match="references"):
            WindowedEcapaVerifier(
                calibration_path=cal_file,
                references_path=tmp_dir / "nonexistent.npz",
                audio_dir=tmp_dir,
            )

    def test_constructs_successfully(self, tmp_dir, cal_file, ref_file):
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        v = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
        )
        assert v is not None


# ---------------------------------------------------------------------------
# Tests: verify_span outcomes
# ---------------------------------------------------------------------------


class TestVerifySpan:
    def _make_verifier(self, tmp_dir, cal_file, ref_file, embedder):
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        return WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=embedder,
        )

    def test_verified_span_returns_windowed_v1_method(self, tmp_dir, cal_file, ref_file, wav_dir):
        """Good audio where every window scores high → method=ecapa_voxceleb_windowed_v1."""
        video_id = "vid_good"
        _make_wav(wav_dir, video_id, duration_s=6.0)

        # Embedder returns a vector perfectly matching krishnaji reference
        kv = np.array([1.0, 0.0], dtype=np.float32)
        embedder = _FakeEmbedder(kv)

        verifier = self._make_verifier(tmp_dir, cal_file, ref_file, embedder)
        # Calibration cosine_floor=0.50; krishnaji cosine will be 1.0 → passes
        result = verifier.verify_span(video_id, start_ms=500, end_ms=4000, guru_id="krishnaji")

        assert result.get("speaker_verified") is True
        assert result.get("voice_verification_method") == "ecapa_voxceleb_windowed_v1"
        assert result.get("speaker_verification_status") == "verified"
        assert result.get("voice_window_check") == "pass"

    def test_refused_span_returns_ecapa_failed(self, tmp_dir, cal_file, ref_file, wav_dir):
        """Audio where every window scores low → speaker_verified=False, ecapa_failed."""
        video_id = "vid_low"
        _make_wav(wav_dir, video_id, duration_s=6.0)

        # Embedder returns a vector matching preethaji (wrong guru for a krishnaji claim)
        pv = np.array([0.0, 1.0], dtype=np.float32)
        embedder = _FakeEmbedder(pv)

        verifier = self._make_verifier(tmp_dir, cal_file, ref_file, embedder)
        result = verifier.verify_span(video_id, start_ms=500, end_ms=4000, guru_id="krishnaji")

        assert result.get("speaker_verified") is False
        assert result.get("speaker_verification_status") == "ecapa_failed"

    def test_missing_wav_returns_pending(self, tmp_dir, cal_file, ref_file):
        """WAV file not found → pending_voice_fields (pending_voice_check)."""
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_FakeEmbedder(np.array([1.0, 0.0])),
        )
        result = verifier.verify_span("missing_video", start_ms=0, end_ms=3000, guru_id="krishnaji")

        # pending_voice_fields returns speaker_verified=False + pending_voice_check status
        assert result.get("speaker_verified") is False
        assert result.get("speaker_verification_status") == "pending_voice_check"
        assert result.get("voice_verification_method") is None

    def test_no_audio_dir_returns_pending(self, tmp_dir, cal_file, ref_file):
        """No audio_dir configured → pending."""
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=None,
            embedder=_FakeEmbedder(np.array([1.0, 0.0])),
        )
        result = verifier.verify_span("any_video", start_ms=0, end_ms=3000, guru_id="krishnaji")

        assert result.get("speaker_verified") is False
        assert result.get("speaker_verification_status") == "pending_voice_check"

    def test_unavailable_calibration_returns_pending(self, tmp_dir, ref_file):
        """calibration_available=False in JSON → pending."""
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        cal = _make_calibration()
        cal["calibration_available"] = False
        cal_path = tmp_dir / "cal_unavail.json"
        cal_path.write_text(json.dumps(cal))

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_path,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_FakeEmbedder(np.array([1.0, 0.0])),
        )
        result = verifier.verify_span("any", start_ms=0, end_ms=3000, guru_id="krishnaji")
        assert result.get("speaker_verification_status") == "pending_voice_check"

    def test_all_required_fields_present_on_verified(self, tmp_dir, cal_file, ref_file, wav_dir):
        """Verified result carries all AUTOMATED_PROVENANCE_KEYS."""
        from domain.speaker_provenance import AUTOMATED_PROVENANCE_KEYS

        video_id = "vid_prov"
        _make_wav(wav_dir, video_id, duration_s=6.0)
        kv = np.array([1.0, 0.0], dtype=np.float32)

        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_FakeEmbedder(kv),
        )
        result = verifier.verify_span(video_id, start_ms=500, end_ms=4000, guru_id="krishnaji")

        # All AUTOMATED_PROVENANCE_KEYS must be present (value may be None for non-verified)
        for key in AUTOMATED_PROVENANCE_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_verified_span_has_model_and_calibration_id(self, tmp_dir, cal_file, ref_file, wav_dir):
        """Verified result carries model_revision and calibration_id from calibration JSON."""
        video_id = "vid_ids"
        _make_wav(wav_dir, video_id, duration_s=6.0)

        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_FakeEmbedder(np.array([1.0, 0.0])),
        )
        result = verifier.verify_span(video_id, start_ms=500, end_ms=4000, guru_id="krishnaji")

        assert result.get("voice_model_revision") == "0f99f2d0"
        assert result.get("voice_calibration_id") == "abc123"

    def test_exception_in_embedder_returns_pending_not_raises(
        self, tmp_dir, cal_file, ref_file, wav_dir
    ):
        """An exception from the embedder must not propagate — returns pending."""
        video_id = "vid_exc"
        _make_wav(wav_dir, video_id, duration_s=6.0)

        class _ExplodingEmbedder:
            def encode_batch(self, batch):
                raise RuntimeError("embedder exploded")

        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_ExplodingEmbedder(),
        )
        result = verifier.verify_span(video_id, start_ms=500, end_ms=4000, guru_id="krishnaji")
        assert result.get("speaker_verification_status") == "pending_voice_check"
        assert result.get("speaker_verified") is False


# ---------------------------------------------------------------------------
# Tests: the recorded score is the WORST window, and refused rows carry no
# verification timestamp (review F2 / F3).
# ---------------------------------------------------------------------------


class TestRecordedScoreIsGatedStatistic:
    def _verifier(self, tmp_dir, cal_file, ref_file):
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        return WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=tmp_dir,
            embedder=_FakeEmbedder(np.array([1.0, 0.0], dtype=np.float32)),
        )

    def test_voice_score_is_min_window_cosine_not_mean(
        self, monkeypatch, tmp_dir, cal_file, ref_file, wav_dir
    ):
        """The gate is per-window, so the stored score must be the worst window.

        A mean above the floor with one window below it is not a pass, and a stored
        mean cannot be re-checked against the stored floor.
        """
        video_id = "vid_spread"
        wav = _make_wav(wav_dir, video_id, duration_s=7.0)
        verifier = self._verifier(tmp_dir, cal_file, ref_file)
        scorer = verifier._load_scorer()

        rows = [
            {"predicted": "krishnaji", "cosine": 0.90, "margin": 0.30},
            {"predicted": "krishnaji", "cosine": 0.55, "margin": 0.20},
            {"predicted": "krishnaji", "cosine": 0.72, "margin": 0.25},
        ]
        monkeypatch.setattr(scorer, "score_span_windows", lambda **_: (rows, 0))

        result = verifier.verify_audio_file(wav, start_ms=500, end_ms=6000, guru_id="krishnaji")

        assert result["speaker_verified"] is True
        assert result["voice_score"] == pytest.approx(0.55, abs=1e-6)
        assert result["voice_score"] != pytest.approx(0.723333, abs=1e-4)

    def test_verified_record_stamps_verified_at_but_refusal_does_not(
        self, monkeypatch, tmp_dir, cal_file, ref_file, wav_dir
    ):
        video_id = "vid_stamp"
        wav = _make_wav(wav_dir, video_id, duration_s=7.0)
        verifier = self._verifier(tmp_dir, cal_file, ref_file)
        scorer = verifier._load_scorer()

        passing = [{"predicted": "krishnaji", "cosine": 0.80, "margin": 0.30}]
        monkeypatch.setattr(scorer, "score_span_windows", lambda **_: (passing, 0))
        ok = verifier.verify_audio_file(wav, start_ms=500, end_ms=6000, guru_id="krishnaji")
        assert ok["speaker_verified"] is True
        assert ok["voice_verified_at"]

        failing = [{"predicted": "preethaji", "cosine": 0.80, "margin": 0.30}]
        monkeypatch.setattr(scorer, "score_span_windows", lambda **_: (failing, 0))
        refused = verifier.verify_audio_file(wav, start_ms=500, end_ms=6000, guru_id="krishnaji")
        assert refused["speaker_verified"] is False
        assert refused["speaker_verification_status"] == "ecapa_failed"
        assert refused["voice_verified_at"] is None

    def test_verify_audio_file_needs_no_audio_dir(self, tmp_dir, cal_file, ref_file, wav_dir):
        """The upload route passes an explicit WAV; no <video_id>.wav dir is required."""
        from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

        wav = _make_wav(wav_dir, "explicit", duration_s=6.0)
        verifier = WindowedEcapaVerifier(
            calibration_path=cal_file,
            references_path=ref_file,
            audio_dir=None,
            embedder=_FakeEmbedder(np.array([1.0, 0.0], dtype=np.float32)),
        )
        result = verifier.verify_audio_file(wav, start_ms=500, end_ms=4000, guru_id="krishnaji")
        assert result["speaker_verified"] is True


# ---------------------------------------------------------------------------
# Tests: container import layout (review F7)
# ---------------------------------------------------------------------------


class TestScorerImportLayout:
    def test_shadowed_scripts_package_still_resolves_the_scorer(self, monkeypatch, tmp_path):
        """When ``scripts`` points at the repo-root bind mount, load by path instead.

        This is the container failure mode: ``/app/scripts`` (repo root) shadows
        ``/app/backend/scripts``, so ``import scripts.ops.windowed_ecapa_v1_scorer``
        raises ModuleNotFoundError and every caller silently fell back to the
        legacy verifier.
        """
        import sys
        import types

        from ingest.verbatim import windowed_speaker_verify as wsv

        # Simulate the container: a ``scripts`` package whose __path__ is a tree that
        # does not contain the scorer, already present in sys.modules.
        fake_root = tmp_path / "repo_scripts"
        (fake_root / "ops").mkdir(parents=True)
        pkg = types.ModuleType("scripts")
        pkg.__path__ = [str(fake_root)]
        ops = types.ModuleType("scripts.ops")
        ops.__path__ = [str(fake_root / "ops")]
        monkeypatch.setitem(sys.modules, "scripts", pkg)
        monkeypatch.setitem(sys.modules, "scripts.ops", ops)
        for name in (
            "scripts.ops.windowed_ecapa_v1_scorer",
            "backend_scripts.ops.windowed_ecapa_v1_scorer",
        ):
            monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr(wsv, "_SCORER_MODULE_NAMES", ("scripts.ops.windowed_ecapa_v1_scorer",))

        module = wsv.load_scorer_module()

        assert hasattr(module, "score_span_windows")
        assert hasattr(module, "windowed_verdict")
