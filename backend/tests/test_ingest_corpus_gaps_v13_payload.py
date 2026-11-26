"""Payload for hand-listed v13 gap clips must fail closed on speaker verification."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "ingest_corpus_gaps_v13.py"
SPEC = importlib.util.spec_from_file_location("ingest_corpus_gaps_v13_under_test", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def test_new_clip_payload_fails_closed_on_speaker_and_keeps_rights() -> None:
    payload = MOD.build_clip_payload(MOD.NEW_CORPUS_CLIPS[0])
    assert payload["speaker_verified"] is False
    assert payload["speaker_verification_status"] == "pending_voice_check"
    # X40 rights fields untouched
    assert payload["rights_cleared"] is True
    assert payload["domain_rights_status"] == "licensed"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
