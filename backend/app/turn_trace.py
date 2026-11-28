"""Per-turn trace collector: ids, counts, scores and durations for ONE chat turn.

One mutable ``TurnTrace`` lives in a ContextVar (same pattern as
``token_accumulator_var``). It is created once per turn in
``PipelineCoordinator.execute`` and only ever MUTATED afterwards, so every asyncio
child task and every ``contextvars.copy_context()`` hop shares it. The sync
``run_llm_coroutine`` bridge does not carry context, so values written there are lost
(only offline tools and the legacy tail use it).

Rules, enforced here rather than left to call sites:
* Logging only. Nothing reads these values to decide anything.
* Never raises. Every method catches the specific exception tuple the answer-outcome
  emitter already uses; there is no broad ``except Exception``.
* No text. A value is an int, float, bool, None, or a short string made only of
  ``[A-Za-z0-9_.:-]`` (an id or a reason code). Anything else is dropped, so a sentence
  cannot be stored by accident.
* Stdlib only, so ``services/`` may import it (import-layer lint).
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from contextvars import ContextVar
from typing import Any

_SAFE_ERRORS = (RuntimeError, ValueError, TypeError, AttributeError, KeyError)
_SAFE_STR = re.compile(r"^[A-Za-z0-9_.:\-]{0,64}$")
_MAX_KEYS = 64
_MAX_SCORES = 12
_MAX_GATES = 24
_MAX_STAGES = 40


def _clean(value: Any) -> Any:
    """Return ``value`` if it is a safe scalar, else the sentinel ``_DROP``."""
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 2) if math.isfinite(value) else _DROP
    if isinstance(value, str) and _SAFE_STR.match(value):
        return value
    return _DROP


_DROP = object()


class TurnTrace:
    """Bounded, scalar-only facts about one turn. See module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.turn: dict[str, Any] = {}
        self.fp: dict[str, Any] = {}
        self.rejected: Counter[str] = Counter()
        self.scores: list[int] = []
        self.stage_ms: dict[str, float] = {}

    # -- writers: every one is total (never raises) --------------------------------

    def note(self, group: str, **kv: Any) -> None:
        try:
            target = self.fp if group == "fp" else self.turn
            with self._lock:
                for key, value in kv.items():
                    cleaned = _clean(value)
                    if cleaned is _DROP:
                        continue
                    if key in target or len(target) < _MAX_KEYS:
                        target[key] = cleaned
        except _SAFE_ERRORS:
            return

    def bump(self, gate: str, n: int = 1) -> None:
        try:
            name = re.sub(r"[^a-z0-9_]", "", str(gate).lower())[:32]
            if not name:
                return
            with self._lock:
                if name in self.rejected or len(self.rejected) < _MAX_GATES:
                    self.rejected[name] += int(n)
        except _SAFE_ERRORS:
            return

    def add_score(self, score: Any) -> None:
        try:
            value = int(score)
            if 0 <= value <= 3:
                with self._lock:
                    if len(self.scores) < _MAX_SCORES:
                        self.scores.append(value)
        except _SAFE_ERRORS:
            return

    def note_stage(self, name: Any, ms: Any) -> None:
        try:
            key = str(name)[:40]
            value = round(float(ms), 1)
            if value < 0 or not math.isfinite(value):
                return
            with self._lock:
                if key in self.stage_ms or len(self.stage_ms) < _MAX_STAGES:
                    self.stage_ms[key] = value
        except _SAFE_ERRORS:
            return

    def snapshot(self) -> dict[str, Any]:
        """A plain, JSON-serialisable copy. Never raises (returns {} on failure)."""
        try:
            with self._lock:
                return {
                    "turn": dict(self.turn),
                    "fp": dict(self.fp),
                    "rejected": dict(self.rejected),
                    "scores": list(self.scores),
                    "stage_ms": dict(self.stage_ms),
                }
        except _SAFE_ERRORS:
            return {}


turn_trace_var: ContextVar[TurnTrace | None] = ContextVar("turn_trace", default=None)


def turn_note(**kv: Any) -> None:
    """Record turn-level facts on the active trace; a no-op when none is active."""
    trace = turn_trace_var.get()
    if trace is not None:
        trace.note("turn", **kv)


def fp_note(**kv: Any) -> None:
    """Record first-person facts on the active trace; a no-op when none is active."""
    trace = turn_trace_var.get()
    if trace is not None:
        trace.note("fp", **kv)


def fp_reject(gate: str) -> None:
    """Count one candidate rejected by a named gate."""
    trace = turn_trace_var.get()
    if trace is not None:
        trace.bump(gate)


def fp_score(score: Any) -> None:
    """Append one relevance score (0 to 3)."""
    trace = turn_trace_var.get()
    if trace is not None:
        trace.add_score(score)


def stage_note(name: Any, ms: Any) -> None:
    trace = turn_trace_var.get()
    if trace is not None:
        trace.note_stage(name, ms)


def trace_active() -> bool:
    return turn_trace_var.get() is not None
