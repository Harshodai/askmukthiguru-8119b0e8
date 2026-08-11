"""S3: tests for the real LettuceDetect detector path and the heuristic fallback.

Two regimes:

1. **Real detector** — exercised only when ``lettucedetect`` is importable,
   ``torch``/``transformers`` are available, and the model can be loaded
   (monkeypatches ``settings.lettucedetect_enabled`` True). Skips gracefully
   in CI / on hosts without the package.
2. **Fallback heuristic** — exercised when the package is not importable
   (monkeypatches ``ImportError``) and confirms the contract shape is
   preserved.

Run: ``cd backend && python -m pytest tests/test_lettuce_detect_real.py -v``
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest


def _lettucedetect_importable() -> bool:
    """True iff the ``lettucedetect`` package can be imported right now."""
    try:
        importlib.import_module("lettucedetect")  # noqa: F401
        importlib.import_module("torch")  # noqa: F401
        importlib.import_module("transformers")  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Real detector path
# ---------------------------------------------------------------------------


@pytest.fixture
def _enabled_real(monkeypatch):
    """Force the real-detector flag on for tests that opt into it."""
    from app.config import settings

    monkeypatch.setattr(settings, "lettucedetect_enabled", True)


@pytest.mark.integration
def test_real_detector_flags_hallucinated_number(_enabled_real):
    """A faithful answer passes; a wrong number is flagged as a hallucinated span."""
    if not _lettucedetect_importable():
        pytest.skip("lettucedetect/torch/transformers not installed in this env")

    from services.lettuce_detect_service import LettuceDetectService

    svc = LettuceDetectService(embedder=None)
    detector = svc._load_real_detector()
    if detector is None:
        pytest.skip("LettuceDetect model could not be loaded (offline / CI sandbox)")

    ctx = "The capital of France is Paris. The population of France is 67 million."
    question = "What is the capital of France? What is the population?"

    # Faithful: both claims match the context.
    faithful = svc.score_faithfulness(question, ctx, "The capital of France is Paris.")
    assert faithful["is_faithful"] is True, faithful
    assert faithful["score"] == 1.0

    # Hallucinated: wrong population number.
    fabricated = svc.score_faithfulness(
        question, ctx, "The capital of France is Paris. The population of France is 69 million."
    )
    assert fabricated["is_faithful"] is False, fabricated
    # At least one span returned; span text present.
    assert fabricated["unsupported_sentences"], fabricated


@pytest.mark.integration
def test_real_detector_empty_inputs(_enabled_real):
    """Empty answer/context are rejected even with the real detector wired."""
    if not _lettucedetect_importable():
        pytest.skip("lettucedetect/torch/transformers not installed in this env")

    from services.lettuce_detect_service import LettuceDetectService

    svc = LettuceDetectService(embedder=None)
    assert svc.score_faithfulness("q", "ctx", "")["is_faithful"] is False
    assert svc.score_faithfulness("q", "", "answer")["is_faithful"] is False


# ---------------------------------------------------------------------------
# Heuristic fallback path
# ---------------------------------------------------------------------------


def test_fallback_when_import_fails(monkeypatch):
    """When ``lettucedetect`` is not importable, the heuristic still works.

    Simulates a host where the package isn't installed by hiding the import
    via ``sys.modules`` poisoning. The service must fall back without
    raising and return the contract shape.
    """
    # Force the flag ON so we exercise the real path first, then prove the
    # fallback fires when the import fails.
    from app.config import settings

    monkeypatch.setattr(settings, "lettucedetect_enabled", True)

    # Poison the import: insert a failing importer for ``lettucedetect`` and
    # the ``huggingface_hub`` snapshot path. ``_load_real_detector`` catches
    # ImportError and returns None, which routes to the heuristic.
    real_modules = {k: sys.modules.get(k) for k in list(sys.modules) if k.startswith("lettucedetect")}
    for k in list(sys.modules):
        if k.startswith("lettucedetect"):
            del sys.modules[k]

    import builtins

    real_import = builtins.__import__

    def _fail_import(name, *args, **kwargs):
        if name == "lettucedetect" or name.startswith("lettucedetect."):
            raise ImportError(f"simulated missing package: {name}")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _fail_import
    try:
        from services.lettuce_detect_service import LettuceDetectService

        svc = LettuceDetectService(embedder=None)
        result = svc.score_faithfulness(
            "what is deeksha",
            "Deeksha is a sacred initiation transferring divine grace.",
            "Deeksha transfers divine grace through initiation.",
        )
        # Heuristic path: lexical overlap clears the 0.45 bar.
        assert result["is_faithful"] is True, result
        assert "is_faithful" in result and "score" in result and "details" in result
        assert isinstance(result["score"], float)
    finally:
        builtins.__import__ = real_import
        # Restore any modules we removed (best effort).
        sys.modules.update({k: v for k, v in real_modules.items() if v is not None})


def test_fallback_when_disabled(monkeypatch):
    """With the flag OFF (default), the heuristic runs unconditionally."""
    from app.config import settings

    monkeypatch.setattr(settings, "lettucedetect_enabled", False)

    from services.lettuce_detect_service import LettuceDetectService

    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness(
        "what is deeksha",
        "Deeksha is a sacred initiation transferring divine grace.",
        "Deeksha transfers divine grace through initiation.",
    )
    assert result["is_faithful"] is True, result
    assert "unsupported_sentences" in result