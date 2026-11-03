# DORMANT (2026-11-01 wiring audit, plan §12): no call site in the request path; not shipped. The live 38-char window is in app/stream_orchestrator.py.
"""
Low-latency SSE generator for AskMukthiGuru.
Features:
- 38-character lookahead safety filter (exact length of longest injection needle)
- Real-time <think> tag stripper (strips reasoning tokens before emission)
- WHATWG compliant multi-line SSE formatting with event, id, and data fields
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any, Optional


class LowLatencySSEGenerator:
    """Formats and filters streaming tokens for low-latency Server-Sent Events."""

    def __init__(self, lookahead_chars: int = 38):
        self.lookahead_chars = lookahead_chars
        self._buffer: str = ""
        self._in_think_block: bool = False
        self._seq: int = 0

    def strip_think_tags(self, text: str) -> str:
        """Strip <think>...</think> reasoning blocks from stream in real time."""
        result = []
        i = 0
        while i < len(text):
            if not self._in_think_block:
                idx = text.find("<think>", i)
                if idx != -1:
                    result.append(text[i:idx])
                    self._in_think_block = True
                    i = idx + len("<think>")
                else:
                    result.append(text[i:])
                    break
            else:
                idx = text.find("</think>", i)
                if idx != -1:
                    self._in_think_block = False
                    i = idx + len("</think>")
                else:
                    # Still in think block, discard everything
                    break
        return "".join(result)

    def format_event(self, event_type: str, data: Any, event_id: Optional[int] = None) -> str:
        """Format a single WHATWG-compliant Server-Sent Event."""
        payload = json.dumps(data) if not isinstance(data, str) else data
        lines = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        if event_type:
            lines.append(f"event: {event_type}")
        # Multi-line data formatting
        for data_line in payload.split("\n"):
            lines.append(f"data: {data_line}")
        return "\n".join(lines) + "\n\n"

    async def transform_stream(
        self,
        token_stream: AsyncGenerator[str, None],
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Filters tokens with a 38-char safety lookahead and strips think tags."""
        async for token in token_stream:
            # Strip think tags
            clean_token = self.strip_think_tags(token)
            if not clean_token:
                continue

            self._buffer += clean_token

            # If buffer exceeds lookahead window, emit safe prefix immediately
            if len(self._buffer) > self.lookahead_chars:
                emit_len = len(self._buffer) - self.lookahead_chars
                emit_chunk = self._buffer[:emit_len]
                self._buffer = self._buffer[emit_len:]

                yield self.format_event("token", {"text": emit_chunk}, event_id=self._seq)
                self._seq += 1

        # Flush remaining buffer at stream end
        if self._buffer:
            yield self.format_event("token", {"text": self._buffer}, event_id=self._seq)
            self._seq += 1
