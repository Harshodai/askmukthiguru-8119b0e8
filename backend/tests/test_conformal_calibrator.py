"""Unit tests for Split Conformal Risk Control Abstention Gate."""

import pytest

from services.conformal_calibrator import ConformalAbstentionGate, ConformalDecision


def test_conformal_gate_high_confidence_serves():
    gate = ConformalAbstentionGate(lambda_hat=0.35)
    # Strong dense match (0.85), high margin (0.25), good sparse (8.0)
    decision = gate.evaluate(dense_score=0.85, sparse_score=8.0, margin_score=0.25)
    assert decision.serve is True
    assert decision.confidence > 0.65
    assert decision.non_conformity <= 0.35
    assert "conformal_accepted" in decision.reason


def test_conformal_gate_low_confidence_abstains():
    gate = ConformalAbstentionGate(lambda_hat=0.35)
    # Weak dense match (0.40), flat margin (0.02), low sparse (1.0)
    decision = gate.evaluate(dense_score=0.40, sparse_score=1.0, margin_score=0.02)
    assert decision.serve is False
    assert decision.confidence < 0.65
    assert decision.non_conformity > 0.35
    assert "conformal_abstained" in decision.reason


def test_non_conformity_bounds():
    gate = ConformalAbstentionGate()
    # Test boundary inputs
    for d in [0.0, 0.5, 1.0]:
        for s in [0.0, 10.0, 50.0]:
            for m in [-0.5, 0.0, 0.5]:
                conf, nc = gate.compute_non_conformity(d, s, m)
                assert 0.0 <= conf <= 1.0
                assert 0.0 <= nc <= 1.0
                assert pytest.approx(conf + nc, 1e-6) == 1.0


def test_calibration_quantile_calculation():
    # Synthetic calibration set
    scores = [
        (0.85, 5.0, 0.20),
        (0.90, 8.0, 0.30),
        (0.80, 4.0, 0.15),
        (0.75, 3.0, 0.10),
        (0.92, 10.0, 0.35),
    ]
    lambda_hat = ConformalAbstentionGate.calibrate_quantile(scores, alpha=0.05)
    assert 0.0 < lambda_hat < 1.0
    # Calibrated gate with this threshold should accept the top scores
    gate = ConformalAbstentionGate(lambda_hat=lambda_hat)
    dec = gate.evaluate(0.92, 10.0, 0.35)
    assert dec.serve is True
