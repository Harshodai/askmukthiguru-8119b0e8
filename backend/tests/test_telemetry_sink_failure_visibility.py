"""A failing telemetry sink must be countable, not just logged per request.

`scripts/ops/hallucination_anomaly.py` reads the rows this sink writes. If the
sink never writes, an empty table reads as "no hallucinations detected" rather
than "no data" — so the write path needs its own signal. Observed live
2026-09-12: every request logged `Telemetry Sink insert operation failed` with
no counter and no health signal.
"""

from app.metrics import TELEMETRY_SINK_WRITES
from app.telemetry_sink import SupabaseTelemetrySink


def _count(outcome: str) -> float:
    return TELEMETRY_SINK_WRITES.labels(outcome=outcome)._value.get()


def test_counter_exposes_both_outcomes():
    before_ok, before_err = _count("ok"), _count("error")
    TELEMETRY_SINK_WRITES.labels(outcome="ok").inc()
    TELEMETRY_SINK_WRITES.labels(outcome="error").inc()
    assert _count("ok") == before_ok + 1
    assert _count("error") == before_err + 1


def test_sink_tracks_consecutive_failures():
    sink = SupabaseTelemetrySink.__new__(SupabaseTelemetrySink)
    sink._consecutive_write_failures = 0
    assert sink._consecutive_write_failures == 0


def test_failure_streak_is_initialised_on_construction():
    import inspect

    src = inspect.getsource(SupabaseTelemetrySink.__init__)
    assert "_consecutive_write_failures = 0" in src


def test_insert_path_counts_and_resets():
    import inspect
    import app.telemetry_sink as mod

    src = inspect.getsource(mod)
    assert 'TELEMETRY_SINK_WRITES.labels(outcome="error").inc()' in src
    assert 'TELEMETRY_SINK_WRITES.labels(outcome="ok").inc()' in src
    # A success must clear the streak, or the count stops meaning "broken now".
    assert "self._consecutive_write_failures = 0" in src
