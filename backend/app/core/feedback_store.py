import json
import os
from datetime import datetime


class FeedbackStore:
    """Collect and analyze user feedback for continuous RAG improvement."""

    def __init__(self, db_path: str = "data/feedback.jsonl"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w"):
                pass

    async def record_feedback(
        self,
        session_id: str,
        query: str,
        response: str,
        feedback: str,  # "positive" | "negative" | "neutral"
        reason: str | None = None,
        chunks_used: list[str] = None,
        latency_ms: float = 0.0,
    ):
        """Record user feedback for RAG quality analysis."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "query": query,
            "response_preview": response[:500],
            "feedback": feedback,
            "reason": reason,
            "chunks_count": len(chunks_used) if chunks_used else 0,
            "latency_ms": latency_ms,
            "model_used": "sarvam-105b",
        }
        with open(self.db_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_negative_feedback_queries(self, limit: int = 50) -> list[dict]:
        """Get queries that got negative feedback — use these for RAG improvement."""
        negatives = []
        try:
            with open(self.db_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("feedback") == "negative":
                            negatives.append(entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return []
        return negatives[-limit:]

    def get_quality_score(self) -> dict:
        """Calculate quality metrics."""
        total = positive = negative = 0
        try:
            with open(self.db_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        total += 1
                        if entry.get("feedback") == "positive":
                            positive += 1
                        elif entry.get("feedback") == "negative":
                            negative += 1
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return {"total": 0, "positive_rate": 0, "negative_rate": 0, "needs_improvement": False}

        return {
            "total": total,
            "positive_rate": positive / total if total > 0 else 0,
            "negative_rate": negative / total if total > 0 else 0,
            "needs_improvement": negative > positive if total > 10 else False,
        }
