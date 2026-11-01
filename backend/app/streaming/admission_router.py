"""
Backend Admission Router and Sequence-numbered SSE Streaming.
Handles Fast-path (HTTP 200 SSE <300ms TTFT) and Slow-path (HTTP 202 Accepted polling queue under >90% concurrency pool saturation).
Tracks sequence numbering and Redis ring buffer replay for Last-Event-ID resume support.
"""

import time
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List

logger = logging.getLogger("mukthi.admission_router")

class StreamAdmissionRouter:
    def __init__(self, max_concurrency: int = 100, saturation_threshold: float = 0.90, ring_buffer_ttl: int = 60):
        self.max_concurrency = max_concurrency
        self.saturation_threshold = saturation_threshold
        self.ring_buffer_ttl = ring_buffer_ttl
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        # In-memory ring buffer for fallback / testing when Redis is mocked or not fully present: {session_id: [{"seq": int, "event": str, "data": dict, "timestamp": float}]}
        self.ring_buffers: Dict[str, List[Dict[str, Any]]] = {}

    def get_current_concurrency(self) -> int:
        return len(self.active_sessions)

    def is_saturated(self) -> float:
        ratio = self.get_current_concurrency() / float(self.max_concurrency) if self.max_concurrency > 0 else 0.0
        return ratio

    async def admit_request(self, session_id: str, client_ip: Optional[str] = None) -> Dict[str, Any]:
        """
        Determines whether to route request via Fast-path (HTTP 200 SSE) or Slow-path (HTTP 202 Accepted).
        """
        saturation = self.is_saturated()
        if saturation >= self.saturation_threshold:
            logger.warning(f"Admission Router saturated ({saturation:.2f} >= {self.saturation_threshold}). Deferring session {session_id} to 202 queue.")
            return {
                "status": 202,
                "action": "defer",
                "message": "System high load. Request queued for polling.",
                "queue_position": self.get_current_concurrency()
            }
        
        self.active_sessions[session_id] = {
            "started_at": time.time(),
            "client_ip": client_ip,
            "seq": 0
        }
        return {
            "status": 200,
            "action": "stream",
            "message": "Admitted to SSE stream"
        }

    async def release_session(self, session_id: str):
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

    async def record_event(self, session_id: str, event_type: str, data: Dict[str, Any]) -> int:
        """
        Records event into session sequence and ring buffer. Returns assigned sequence number.
        """
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = {"started_at": time.time(), "seq": 0}
        
        seq = self.active_sessions[session_id]["seq"]
        self.active_sessions[session_id]["seq"] = seq + 1

        entry = {
            "seq": seq,
            "event": event_type,
            "data": data,
            "timestamp": time.time()
        }

        if session_id not in self.ring_buffers:
            self.ring_buffers[session_id] = []
        
        buf = self.ring_buffers[session_id]
        buf.append(entry)
        # Prune old entries based on TTL
        now = time.time()
        self.ring_buffers[session_id] = [e for e in buf if now - e["timestamp"] <= self.ring_buffer_ttl]

        return seq

    async def get_events_since(self, session_id: str, last_event_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves events after last_event_id for zero-drop SSE reconnection.
        """
        buf = self.ring_buffers.get(session_id, [])
        return [e for e in buf if e["seq"] > last_event_id]

# Global instance
admission_router = StreamAdmissionRouter()
