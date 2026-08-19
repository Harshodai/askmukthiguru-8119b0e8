"""Optional empirical calibration for answer confidence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CalibrationResult:
    value: float
    status: str
    artifact: str | None = None


class ConfidenceCalibrator:
    """Use held-out calibration points; never fabricate a probability mapping."""

    def __init__(self, artifact_path: str | None = None) -> None:
        self.artifact_path = artifact_path or os.getenv("CONFIDENCE_CALIBRATION_PATH")
        self._points: tuple[tuple[float, float], ...] = ()
        self.status = "uncalibrated"
        self._load()

    def _load(self) -> None:
        if not self.artifact_path:
            return
        try:
            data = json.loads(Path(self.artifact_path).read_text())
            points = tuple((float(p["raw"]), float(p["calibrated"])) for p in data["points"])
            if len(points) < 3 or any(not 0 <= x <= 1 or not 0 <= y <= 1 for x, y in points):
                raise ValueError("calibration points must be in [0,1]")
            if any(
                points[i][0] >= points[i + 1][0] or points[i][1] > points[i + 1][1]
                for i in range(len(points) - 1)
            ):
                raise ValueError("calibration points must be monotonic")
            self._points = points
            self.status = "empirical"
        except Exception:
            self._points = ()
            self.status = "invalid_artifact"

    def calibrate(self, raw: float) -> CalibrationResult:
        raw = max(0.0, min(1.0, float(raw)))
        if not self._points:
            return CalibrationResult(raw, self.status, self.artifact_path)
        if raw <= self._points[0][0]:
            return CalibrationResult(self._points[0][1], self.status, self.artifact_path)
        if raw >= self._points[-1][0]:
            return CalibrationResult(self._points[-1][1], self.status, self.artifact_path)
        for (x0, y0), (x1, y1) in zip(self._points, self._points[1:]):
            if x0 <= raw <= x1:
                ratio = (raw - x0) / (x1 - x0)
                return CalibrationResult(y0 + ratio * (y1 - y0), self.status, self.artifact_path)
        return CalibrationResult(raw, "invalid_artifact", self.artifact_path)
