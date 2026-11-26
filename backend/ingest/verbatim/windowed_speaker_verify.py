"""Windowed ECAPA v1 speaker verifier — injectable into corpus builders.

Provides ``WindowedEcapaVerifier``, a class that scores one span's audio with
the calibrated windowed-ECAPA method (W=3 s / H=1.5 s) and returns a payload
dict ready to unpack into a ``SourceSpan`` via ``**voice_fields``.

Design rules
------------
* Never copy code from ``windowed_ecapa_v1_scorer``.  Import its pure functions.
* Lazy model load: the SpeechBrain ECAPA model is loaded once on first call,
  not at import time.  Tests inject a fake embedder via ``embedder=``.
* Fail-closed: any audio error or missing calibration returns
  ``pending_voice_fields()`` — never a spurious ``speaker_verified=True``.
* No ``.env`` reading.  All paths are constructor arguments or env-override
  ``WINDOWED_ECAPA_CALIBRATION_PATH``.

Usage in ``build_full_corpus_v10.py``
--------------------------------------
    verifier = WindowedEcapaVerifier(
        references_path=args.references_npz,
        calibration_path=args.windowed_calibration,
        audio_dir=args.wav_dir,
    )
    voice_fields = verifier.verify_span(video_id, start_ms, end_ms, guru_id)
    span = SourceSpan(**voice_fields, ...)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths (overridable via env or constructor args)
# ---------------------------------------------------------------------------
_DEFAULT_CALIBRATION_PATH = (
    Path(__file__).resolve().parents[2]  # backend/
    / "config"
    / "windowed_ecapa_calibration.json"
)
_DEFAULT_REFERENCES_PATH = (
    Path(__file__).resolve().parents[2]  # backend/
    / "config"
    / "ecapa_guru_references.npz"
)
_FALLBACK_REFERENCES_PATH = (
    Path(os.path.expanduser("~/mukthiguru_attribution_data"))
    / "phase2_references_2026-10-30"
    / "references.npz"
)

#: Import names for ``backend/scripts/ops/windowed_ecapa_v1_scorer.py``.
#: ``scripts.ops`` works on the host (backend/ is on sys.path); some container
#: layouts expose the same tree as ``backend_scripts`` because the repo-root
#: ``scripts/`` bind mount shadows it (see ``load_scorer_module``).
_SCORER_MODULE_NAMES = (
    "scripts.ops.windowed_ecapa_v1_scorer",
    "backend_scripts.ops.windowed_ecapa_v1_scorer",
)

_SCORER_PACKAGE = "scripts.ops"
_SCORER_MODULE = f"{_SCORER_PACKAGE}.windowed_ecapa_v1_scorer"
_REGEN_MODULE = f"{_SCORER_PACKAGE}.regenerate_v10_span_ecapa_verdicts"


def _ops_dir() -> Path:
    """``backend/scripts/ops`` — where the scorer lives, whatever the sys.path is."""
    return Path(__file__).resolve().parents[2] / "scripts" / "ops"


def _ensure_package(name: str, package_dir: Path) -> None:
    """Register ``name`` as a namespace package pointing at ``package_dir``.

    Needed only on the path-loading fallback: the scorer's own
    ``from scripts.ops.regenerate_v10_span_ecapa_verdicts import …`` must resolve,
    and in the container the cached ``scripts`` package can point at the
    repo-root bind mount, which does not contain these files at all.
    """
    import sys
    import types

    if name in sys.modules:
        return
    parts = name.split(".")
    for depth in range(1, len(parts) + 1):
        sub = ".".join(parts[:depth])
        if sub in sys.modules:
            continue
        mod = types.ModuleType(sub)
        mod.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
        sys.modules[sub] = mod
    for depth in range(1, len(parts)):
        parent = ".".join(parts[:depth])
        child = ".".join(parts[: depth + 1])
        setattr(sys.modules[parent], parts[depth], sys.modules[child])


def _load_module_from_path(name: str, path: Path):
    """Execute a module file under ``name`` and register it in ``sys.modules``."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_scorer_module():
    """Import ``windowed_ecapa_v1_scorer`` under any supported layout.

    1. Ordinary import as ``scripts.ops…`` (host, backend/ on sys.path).
    2. Ordinary import as ``backend_scripts.ops…`` (container, second mount).
    3. Load the two files by absolute path from ``backend/scripts/ops`` and
       register them under ``scripts.ops…`` before executing the scorer, so its
       own sibling import resolves.

    Raises ``ModuleNotFoundError`` naming every attempt when the files are not
    present, so a caller can fail loudly instead of silently downgrading to the
    legacy verifier (review F7).
    """
    import importlib

    errors: list[str] = []
    for name in _SCORER_MODULE_NAMES:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            errors.append(f"import {name}: {exc}")

    ops_dir = _ops_dir()
    scorer_path = ops_dir / "windowed_ecapa_v1_scorer.py"
    regen_path = ops_dir / "regenerate_v10_span_ecapa_verdicts.py"
    if scorer_path.is_file() and regen_path.is_file():
        try:
            _ensure_package(_SCORER_PACKAGE, ops_dir)
            if _REGEN_MODULE not in __import__("sys").modules:
                _load_module_from_path(_REGEN_MODULE, regen_path)
            return _load_module_from_path(_SCORER_MODULE, scorer_path)
        except Exception as exc:  # pragma: no cover - layout dependent
            errors.append(f"path load {scorer_path}: {exc}")
    else:
        errors.append(f"missing files under {ops_dir}")

    raise ModuleNotFoundError(
        "windowed ECAPA scorer is not importable under any known layout "
        f"({'; '.join(errors)}). Expected {scorer_path} and {regen_path}."
    )


class WindowedEcapaVerifier:
    """Score one span's audio with windowed ECAPA v1 and return voice payload fields.

    Parameters
    ----------
    references_path:
        Path to ``references.npz`` (pinned ECAPA guru reference centroids).
    calibration_path:
        Path to ``windowed_ecapa_calibration.json``.  Falls back to
        the bundled ``backend/config/windowed_ecapa_calibration.json``.
    audio_dir:
        Directory containing ``<video_id>.wav`` files at 16 kHz mono.
    embedder:
        Injectable for tests.  Must be a SpeechBrain-style model with an
        ``encode_batch(batch_tensor) -> Tensor`` method, identical to what
        ``load_embedder`` returns.  Defaults to loading the real model on
        first ``verify_span`` call.
    model_cache:
        Cache directory for the SpeechBrain model download.
    """

    def __init__(
        self,
        references_path: str | Path | None = None,
        calibration_path: str | Path | None = None,
        audio_dir: str | Path | None = None,
        embedder=None,
        model_cache: str | Path | None = None,
    ) -> None:
        # Resolve calibration path
        cal_path = Path(calibration_path or _DEFAULT_CALIBRATION_PATH)
        if not cal_path.is_file():
            raise FileNotFoundError(
                f"Windowed ECAPA calibration not found: {cal_path}. "
                "Set WINDOWED_ECAPA_CALIBRATION_PATH or pass calibration_path=."
            )
        self._calibration_path = cal_path
        self._calibration: dict[str, Any] | None = None  # loaded lazily

        # References
        ref_default = (
            _DEFAULT_REFERENCES_PATH
            if _DEFAULT_REFERENCES_PATH.is_file()
            else _FALLBACK_REFERENCES_PATH
        )
        ref_path = Path(references_path or ref_default)
        if not ref_path.is_file():
            raise FileNotFoundError(
                f"ECAPA references not found: {ref_path}. Pass references_path=."
            )
        self._references_path = ref_path
        self._references: dict[str, np.ndarray] | None = None  # loaded lazily

        self._audio_dir = Path(audio_dir) if audio_dir else None
        self._embedder = embedder  # None → load real model on first use
        self._model_cache = Path(model_cache) if model_cache else None
        self._scorer: Any = None  # lazy import of windowed_ecapa_v1_scorer

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def _load_calibration(self) -> dict[str, Any]:
        if self._calibration is None:
            self._calibration = json.loads(self._calibration_path.read_text(encoding="utf-8"))
        return self._calibration

    def _load_references(self) -> dict[str, np.ndarray]:
        if self._references is None:
            with np.load(self._references_path) as f:
                self._references = {
                    str(k).lower(): np.asarray(f[k], dtype=np.float32) for k in f.files
                }
        return self._references

    def _load_scorer(self) -> Any:
        """Lazily import the scorer module so this file loads without torch.

        The module lives in ``backend/scripts/ops/``, which resolves as
        ``scripts.ops`` only while ``backend/`` is on ``sys.path`` (the host
        editable install). Inside the container, repo-root ``scripts/`` is
        bind-mounted at ``/app/scripts`` and *shadows* the image's baked
        ``backend/scripts``, which compose exposes separately as
        ``/app/backend_scripts``. Importing blindly therefore raised
        ``ModuleNotFoundError`` in the container and every caller silently fell
        back to the legacy verifier (review F7). Try both names, then fail loudly
        with the paths that were searched.
        """
        if self._scorer is None:
            self._scorer = load_scorer_module()
        return self._scorer

    def _get_embedder(self):
        """Return the real SpeechBrain embedder, loading it on first call."""
        if self._embedder is None:
            scorer = self._load_scorer()
            self._embedder = scorer.load_embedder(cache_dir=self._model_cache, device="auto")
        return self._embedder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify_span(
        self,
        video_id: str,
        start_ms: int | float,
        end_ms: int | float,
        guru_id: str,
    ) -> dict[str, Any]:
        """Score one span and return a voice-fields payload dict.

        Returns ``automated_voice_fields(verified=True, method=windowed_v1, ...)``
        on a full pass, ``automated_voice_fields(verified=False, ...)`` on a
        ECAPA refusal, or ``pending_voice_fields()`` when scoring is impossible
        (audio missing, calibration unavailable, etc.).

        The returned dict is safe to unpack as ``**voice_fields`` into a
        ``SourceSpan`` constructor.

        Fail-closed invariants:
        - Missing calibration → pending
        - Missing audio dir → pending
        - Missing WAV → pending
        - Scorer import failure → pending
        - 0 non-silent windows scored → pending (indeterminate, not refused)
        - Any other exception → pending (never raises)
        """
        from domain.speaker_provenance import pending_voice_fields as _pv  # noqa: E402

        try:
            if self._audio_dir is None:
                logger.warning("windowed_verify: no audio_dir configured for %s", video_id)
                return _pv()
            wav_path = self._audio_dir / f"{video_id}.wav"
            if not wav_path.is_file():
                logger.debug("windowed_verify: wav missing %s", wav_path)
                return _pv()
            return self._verify_audio_inner(wav_path, start_ms, end_ms, guru_id)
        except Exception as exc:
            logger.warning(
                "windowed_verify: unexpected error for %s [%s-%s]: %s",
                video_id,
                start_ms,
                end_ms,
                exc,
            )
            return _pv()

    def verify_audio_file(
        self,
        wav_path: str | Path,
        start_ms: int | float,
        end_ms: int | float,
        guru_id: str,
    ) -> dict[str, Any]:
        """Score one span from an explicit 16 kHz mono PCM WAV.

        This is the ingestion entry point: a file upload or a downloaded video has
        no stable ``<video_id>.wav`` in a known audio directory, but it does have
        a WAV on disk for the length of the job. Same rules and same fail-closed
        behaviour as :meth:`verify_span`.
        """
        from domain.speaker_provenance import pending_voice_fields as _pv  # noqa: E402

        try:
            return self._verify_audio_inner(Path(wav_path), start_ms, end_ms, guru_id)
        except Exception as exc:
            logger.warning(
                "windowed_verify: unexpected error for %s [%s-%s]: %s",
                wav_path,
                start_ms,
                end_ms,
                exc,
            )
            return _pv()

    def _verify_audio_inner(
        self,
        wav_path: Path,
        start_ms: int | float,
        end_ms: int | float,
        guru_id: str,
    ) -> dict[str, Any]:
        from domain.speaker_provenance import (  # noqa: E402
            METHOD_ECAPA_WINDOWED_V1,
            automated_voice_fields,
            pending_voice_fields,
        )

        # 1. Calibration
        try:
            cal = self._load_calibration()
        except Exception as exc:
            logger.warning("windowed_verify: calibration load failed: %s", exc)
            return pending_voice_fields()

        if not cal.get("calibration_available", True):
            logger.warning("windowed_verify: calibration marked unavailable")
            return pending_voice_fields()

        cosine_floor = float(cal["cosine_floor"])
        margin_threshold = float(cal["margin_threshold"])
        max_failing = int(cal.get("max_failing_windows", 0))
        windowed_cal_revision = str(cal.get("windowed_calibration_revision", ""))
        model_revision = str(cal.get("model_revision", ""))
        window_w_s = float(cal.get("window_w_s", 3.0))
        window_h_s = float(cal.get("window_h_s", 1.5))

        # 3. Load scorer + references
        try:
            scorer = self._load_scorer()
            references = self._load_references()
        except Exception as exc:
            logger.warning("windowed_verify: scorer/references load failed: %s", exc)
            return pending_voice_fields()

        if not wav_path.is_file():
            logger.debug("windowed_verify: wav missing %s", wav_path)
            return pending_voice_fields()

        # 4. Read the served window slice (pad matches the citation player)
        pad_ms = scorer.SERVED_PAD_MS
        s_start_ms = max(0, int(start_ms) - pad_ms)
        s_end_ms = int(end_ms) + pad_ms

        audio, err = scorer.read_slice(wav_path, s_start_ms, s_end_ms)
        if audio is None or len(audio) == 0:
            logger.debug(
                "windowed_verify: read_slice failed for %s [%s-%s]: %s",
                wav_path.name,
                s_start_ms,
                s_end_ms,
                err,
            )
            return pending_voice_fields()

        # 5. Score windows — use scorer's score_span_windows (never re-implement)
        try:
            embedder = self._get_embedder()
            window_scores, silent = scorer.score_span_windows(
                audio=audio,
                expected_guru=guru_id,
                references=references,
                embedder=embedder,
                window_s=window_w_s,
                hop_s=window_h_s,
            )
        except Exception as exc:
            logger.warning(
                "windowed_verify: scoring failed for %s [%s-%s]: %s",
                wav_path.name,
                start_ms,
                end_ms,
                exc,
            )
            return pending_voice_fields()

        # 6. Span-level verdict (pure function from scorer)
        verdict, reason, stats = scorer.windowed_verdict(
            window_scores=window_scores,
            expected_guru=guru_id,
            cosine_floor=cosine_floor,
            margin_threshold=margin_threshold,
            max_failing_windows=max_failing,
        )

        verified = verdict == scorer.VERDICT_VERIFIED

        # indeterminate_no_windows → pending (not a refusal, may be retried)
        if verdict == scorer.VERDICT_INDETERMINATE:
            return pending_voice_fields()

        cosine_min = stats.get("span_cosine_min")
        margin_min = stats.get("span_margin_min")

        if cosine_min is None:
            return pending_voice_fields()

        # The gate is per-window: the recorded score must be the WORST window, so
        # the stored score and the stored floor can be re-checked against the same
        # rule (review F2 — the mean was 0.1055 above the worst window on average).
        evidence = {
            "cosine": float(cosine_min),
            "margin": float(margin_min) if margin_min is not None else 0.0,
            "cosine_floor": cosine_floor,
            "margin_threshold": margin_threshold,
        }

        fields = automated_voice_fields(
            verified=verified,
            evidence=evidence,
            model_revision=model_revision or None,
            calibration_id=windowed_cal_revision or None,
            verified_at=datetime.now(UTC).isoformat(timespec="seconds"),
            window_check="pass" if verified else "fail",
            method=METHOD_ECAPA_WINDOWED_V1 if verified else None,
        )
        if verified and fields.get("speaker_verified") is not True:
            # The write rule refused its own record: report it, never claim.
            logger.warning(
                "windowed_verify: verified verdict failed the write rule for %s [%s-%s] "
                "(verdict=%s reason=%s, windows=%s silent=%s); demoting to pending",
                wav_path.name,
                start_ms,
                end_ms,
                verdict,
                reason,
                stats.get("windows_scored"),
                silent,
            )
            return pending_voice_fields()
        if not verified:
            logger.debug(
                "windowed_verify: refused %s [%s-%s] verdict=%s windows=%s silent=%s",
                wav_path.name,
                start_ms,
                end_ms,
                verdict,
                stats.get("windows_scored"),
                silent,
            )
        return fields
