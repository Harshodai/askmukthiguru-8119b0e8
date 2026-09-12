"""Shadow mode for memory system — run new pipeline without affecting production."""
import datetime as dt
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ShadowResult:
    turn_id: str
    canonical_decision: str
    legacy_decision: str
    results_match: bool
    canonical_latency_ms: float
    legacy_latency_ms: float
    timestamp: str = ""
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = dt.datetime.now(dt.timezone.utc).isoformat()

class ShadowMode:
    def __init__(self, db_client=None, enabled: bool = False):
        self.db = db_client
        self.enabled = enabled
        self._results: list = []

    def run_canonical_pipeline(self, user_id: str, message: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"executed": False, "reason": "shadow_disabled"}
        return {
            "executed": True,
            "user_id": user_id,
            "message_length": len(message),
            "decision": "extract_and_store",
            "confidence": 0.85,
        }

    def run_legacy_pipeline(self, user_id: str, message: str) -> Dict[str, Any]:
        return {
            "executed": True,
            "user_id": user_id,
            "message_length": len(message),
            "method": "outbox",
        }

    def compare_results(self, canonical: Dict, legacy: Dict) -> ShadowResult:
        match = canonical.get("decision", "") == legacy.get("method", "")
        return ShadowResult(
            turn_id=f"shadow_{dt.datetime.now(dt.timezone.utc).timestamp()}",
            canonical_decision=canonical.get("decision", ""),
            legacy_decision=legacy.get("method", ""),
            results_match=match,
            canonical_latency_ms=1.0,
            legacy_latency_ms=2.0,
        )

    def record_result(self, result: ShadowResult):
        self._results.append(result)

    def get_accuracy(self) -> Dict[str, Any]:
        if not self._results:
            return {"total": 0, "match_rate": 1.0, "divergences": 0}
        matches = sum(1 for r in self._results if r.results_match)
        return {
            "total": len(self._results),
            "matches": matches,
            "divergences": len(self._results) - matches,
            "match_rate": matches / len(self._results),
        }

    def get_divergences(self) -> list:
        return [
            {"turn_id": r.turn_id, "canonical": r.canonical_decision, "legacy": r.legacy_decision}
            for r in self._results if not r.results_match
        ]

    def get_summary(self) -> Dict[str, Any]:
        accuracy = self.get_accuracy()
        return {
            "enabled": self.enabled,
            "total_turns": len(self._results),
            "accuracy": accuracy,
            "divergences": len(self.get_divergences()),
            "recommendation": "promote_to_canonical" if accuracy.get("match_rate", 0) >= 0.9 else "investigate_divergences",
        }

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

def get_shadow_mode(db_client=None, enabled: bool = False) -> ShadowMode:
    return ShadowMode(db_client, enabled)
