"""P1-AI-15: confidence_scorer temperature — docstring/code consistency pin.

Regression guard for the P1-AI-15 finding: the module docstring claimed
T=1.5 while the code set _TEMPERATURE = 1.0. The docstring was corrected to
1.0 (behavior kept stable); these tests pin both so they cannot drift again.
"""

from __future__ import annotations

import inspect
import re

import services.confidence_scorer as cs


def _docstring_temperature() -> float | None:
    """Parse the T=... claim out of the module docstring."""
    doc = inspect.getdoc(cs) or ""
    m = re.search(r"temperature-scaled \(T=([0-9.]+)\)", doc)
    return float(m.group(1)) if m else None


def test_docstring_claims_a_temperature():
    """The module docstring must state the temperature it uses."""
    assert _docstring_temperature() is not None


def test_docstring_and_constant_agree():
    """Docstring T= must equal _TEMPERATURE — P1-AI-15 drift guard."""
    assert _docstring_temperature() == cs._TEMPERATURE


def test_temperature_constant_value():
    """Pin the reconciled value: 1.0 (doc corrected, behavior unchanged)."""
    assert cs._TEMPERATURE == 1.0


def test_temperature_scale_is_identity_at_1_0():
    """T=1.0 is the logistic-softmax no-op: score is unchanged by scaling."""
    assert cs._temperature_scale(0.5) == 0.5
    assert abs(cs._temperature_scale(0.8) - 0.8) < 1e-3
