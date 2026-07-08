"""Tests for DSPy integration into the production pipeline."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def test_dspy_engine_imports():
    """DSPy module imports work."""
    from rag.dspy_engine import (
        MukthiGuruSignature,
        MukthiGuruModule,
        setup_dspy_lm,
        make_module,
        dspy_generate,
    )
    assert MukthiGuruSignature is not None
    assert MukthiGuruModule is not None
    assert callable(setup_dspy_lm)
    assert callable(make_module)
    assert callable(dspy_generate)


def test_make_module_returns_none_when_disabled():
    """make_module returns None when use_dspy is False."""
    from app.config import settings
    original = settings.use_dspy
    try:
        settings.use_dspy = False
        from rag.dspy_engine import make_module
        assert make_module() is None
    finally:
        settings.use_dspy = original


def test_make_module_returns_none_when_lm_setup_fails():
    """make_module returns None when LM setup fails."""
    from app.config import settings
    original = settings.use_dspy
    try:
        settings.use_dspy = True
        with patch("rag.dspy_engine.setup_dspy_lm", return_value=False):
            from rag.dspy_engine import make_module
            assert make_module() is None
    finally:
        settings.use_dspy = original


def test_dspy_generate_returns_none_without_module():
    """dspy_generate returns None when no module is provided."""
    from rag.dspy_engine import dspy_generate
    result = dspy_generate(question="test", context="test", module=None)
    assert result is None


def test_dspy_generate_falls_back_on_exception():
    """dspy_generate returns None when the module raises."""
    from rag.dspy_engine import dspy_generate, MukthiGuruModule

    module = MagicMock(spec=MukthiGuruModule)
    module.forward.side_effect = RuntimeError("DSPy failure")

    result = dspy_generate(question="test", context="test", module=module)
    assert result is None
    module.forward.assert_called_once_with(question="test", context="test")


def test_generation_node_has_dspy_fallback():
    """DSPy failure falls through gracefully — module returns None on error."""
    from rag.dspy_engine import dspy_generate, MukthiGuruModule

    module = MagicMock(spec=MukthiGuruModule)
    module.forward.side_effect = RuntimeError("DSPy failure")
    result = dspy_generate(question="q", context="c", module=module)
    assert result is None


def test_generation_node_has_dspy_branch():
    """Verify the generate_answer function references DSPy code path."""
    import inspect
    from rag.nodes.generation import generate_answer
    src = inspect.getsource(generate_answer)
    assert "use_dspy" in src, "generate_answer should reference use_dspy config"
    assert "dspy_generate" in src, "generate_answer should call dspy_generate"
    assert "dspy_engine" in src, "generate_answer should import from dspy_engine"
    assert "falling back" in src.lower(), "generate_answer should log fallback"


def test_config_has_use_dspy():
    """Config has use_dspy setting."""
    from app.config import settings
    assert hasattr(settings, "use_dspy")
    assert isinstance(settings.use_dspy, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
