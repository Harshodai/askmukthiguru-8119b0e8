import json

from services.confidence_calibrator import ConfidenceCalibrator


def test_without_artifact_score_is_honestly_uncalibrated():
    result = ConfidenceCalibrator(artifact_path=None).calibrate(0.75)
    assert result.value == 0.75
    assert result.status == "uncalibrated"


def test_valid_artifact_interpolates_monotonically(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "points": [
                    {"raw": 0.0, "calibrated": 0.0},
                    {"raw": 0.5, "calibrated": 0.4},
                    {"raw": 1.0, "calibrated": 0.9},
                ]
            }
        )
    )
    calibrator = ConfidenceCalibrator(str(path))
    result = calibrator.calibrate(0.75)
    assert result.status == "empirical"
    assert result.value == 0.65


def test_invalid_artifact_fails_safe(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"points": [{"raw": 0.5, "calibrated": 0.8}]}))
    result = ConfidenceCalibrator(str(path)).calibrate(0.75)
    assert result.status == "invalid_artifact"
    assert result.value == 0.75
