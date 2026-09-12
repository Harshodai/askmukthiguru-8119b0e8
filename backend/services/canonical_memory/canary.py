"""Canary deployment strategy for rolling out memory system."""
import datetime as dt
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class CanaryStage(str, Enum):
    OFF = "off"
    INTERNAL_TESTING = "internal_testing"
    SMALL_PERCENTAGE = "small_percentage"
    HALF_ROLLOUT = "half_rollout"
    FULL_ROLLOUT = "full_rollout"
    ROLLED_BACK = "rolled_back"

@dataclass
class CanaryConfig:
    stage: CanaryStage = CanaryStage.OFF
    percentage: float = 0.0
    user_whitelist: List[str] = field(default_factory=list)
    error_threshold: float = 0.05
    latency_threshold_ms: float = 2000.0
    min_satisfaction_score: float = 0.8

class CanaryDeployment:
    def __init__(self, config: CanaryConfig = None):
        self.config = config or CanaryConfig()
        self._metrics: Dict[str, Any] = {"turns": 0, "errors": 0, "total_latency_ms": 0.0}

    def should_use_canonical(self, user_id: str) -> bool:
        if self.config.stage == CanaryStage.OFF:
            return False
        if self.config.stage == CanaryStage.FULL_ROLLOUT:
            return True
        if user_id in self.config.user_whitelist:
            return True
        if self.config.stage == CanaryStage.INTERNAL_TESTING:
            return user_id.startswith("internal_")
        return False

    def record_turn(self, latency_ms: float, success: bool):
        self._metrics["turns"] += 1
        self._metrics["total_latency_ms"] += latency_ms
        if not success:
            self._metrics["errors"] += 1

    def check_health(self) -> Dict[str, Any]:
        turns = self._metrics["turns"]
        errors = self._metrics["errors"]
        avg_latency = self._metrics["total_latency_ms"] / max(turns, 1)
        error_rate = errors / max(turns, 1)
        healthy = error_rate <= self.config.error_threshold and avg_latency <= self.config.latency_threshold_ms
        return {
            "stage": self.config.stage.value,
            "turns": turns,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency,
            "healthy": healthy,
            "should_promote": healthy and turns >= 100,
            "should_rollback": error_rate > self.config.error_threshold * 2,
        }

    def promote(self) -> Dict[str, Any]:
        order = [CanaryStage.OFF, CanaryStage.INTERNAL_TESTING, CanaryStage.SMALL_PERCENTAGE, CanaryStage.HALF_ROLLOUT, CanaryStage.FULL_ROLLOUT]
        if self.config.stage == CanaryStage.ROLLED_BACK:
            self.config.stage = CanaryStage.OFF
            return {"new_stage": self.config.stage.value, "promoted": True}
        idx = order.index(self.config.stage)
        if idx < len(order) - 1:
            self.config.stage = order[idx + 1]
        return {"new_stage": self.config.stage.value, "promoted": True}

    def rollback(self) -> Dict[str, Any]:
        self.config.stage = CanaryStage.ROLLED_BACK
        return {"stage": self.config.stage.value, "rolled_back": True}

    def get_status(self) -> Dict[str, Any]:
        return {
            "stage": self.config.stage.value,
            "percentage": self.config.percentage,
            "config": {
                "error_threshold": self.config.error_threshold,
                "latency_threshold_ms": self.config.latency_threshold_ms,
                "min_satisfaction": self.config.min_satisfaction_score,
            },
            "metrics": self._metrics,
        }

def get_canary_deployment(stage: CanaryStage = CanaryStage.OFF) -> CanaryDeployment:
    return CanaryDeployment(CanaryConfig(stage=stage))


if __name__ == "__main__":
    canary = get_canary_deployment(CanaryStage.OFF)
    assert canary.should_use_canonical("u1") is False
    canary.promote()
    assert canary.config.stage == CanaryStage.INTERNAL_TESTING
    assert canary.should_use_canonical("internal_1") is True
    assert canary.should_use_canonical("external_1") is False
    canary.record_turn(150.0, True)
    health = canary.check_health()
    assert health["turns"] == 1
    status = canary.get_status()
    assert status["stage"] == "internal_testing"
    result = canary.rollback()
    assert result["rolled_back"] is True
    print("canary.py self-check passed")
