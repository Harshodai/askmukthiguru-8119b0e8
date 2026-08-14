"""Mukthi Guru — Telemetry Infrastructure

The per-stage event-bus (events.py/publisher.py/sinks.py) was deleted --
it was invoked on every request but every configured sink discarded the
event, so it did nothing. app/pipeline/pipeline_coordinator.py's `_stage()`
is now a no-op kept only because StageRunner calls it unconditionally.

prompt_cache_telemetry.py is a separate, unrelated module and stays.
"""
