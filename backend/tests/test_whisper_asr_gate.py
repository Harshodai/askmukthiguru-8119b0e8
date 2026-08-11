"""ASR gate fail-closed regression test.

services.whisper_local_service._apply_asr_gate is deliberately fail-closed
(§6.1 backstop): ANY error importing or calling
services.asr_gate.reject_transcript aborts the transcript (returns None)
instead of letting a degenerate decoder-loop transcript reach the LLM
corrector and ingestion.
"""

from services.whisper_local_service import _apply_asr_gate


def test_asr_gate_error_is_fail_closed(monkeypatch):
    """A gate malfunction must abort the transcript, not skip the gate."""

    def _boom(_text: str):
        raise RuntimeError("asr_gate internal failure")

    monkeypatch.setattr("services.asr_gate.reject_transcript", _boom)

    assert _apply_asr_gate("video-123", "some transcript text") is None