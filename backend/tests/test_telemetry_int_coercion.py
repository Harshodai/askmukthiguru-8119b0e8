"""A float in an INTEGER column loses the whole telemetry row — and blinds alerting.

Measured live 2026-09-17:

    Telemetry Sink insert failed (1 consecutive):
    invalid input syntax for type integer: "108.43"

Postgres rejects a float for an integer column outright, so the entire
`chat_responses` insert is discarded. That is worse than one lost row:
`scripts/ops/hallucination_anomaly.py` reads this table, so a failing insert
makes the anomaly job read "no hallucinations" when the truth is "no data".
The sink's own error message says exactly that. Coercing at the sink covers
every caller rather than trusting each to pre-round its millisecond values.
"""

import pytest

from app.telemetry_sink import SupabaseTelemetrySink


@pytest.fixture
def sink():
    # Bypass __init__: it builds Supabase/Redis clients we neither have nor need.
    return SupabaseTelemetrySink.__new__(SupabaseTelemetrySink)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (108.43, 108),  # the exact live failure
        (108, 108),
        ("108.43", 108),  # already stringified upstream
        (0.4, 0),
        (None, None),
        ("abc", None),  # unusable -> drop the field, never the row
        (True, None),  # a bool is not a latency
    ],
)
def test_coerce_int_handles_every_shape(sink, raw, expected):
    assert sink._coerce_int(raw) == expected


def test_float_latency_does_not_reach_the_integer_column(sink):
    """The regression itself: a float latency must be an int by insert time."""
    coerced = sink._coerce_int(108.43)
    assert isinstance(coerced, int)
    assert not isinstance(coerced, float)


def test_unusable_value_is_dropped_not_raised(sink):
    """Telemetry must never raise into the request path it observes."""
    assert sink._coerce_int(object()) is None


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
