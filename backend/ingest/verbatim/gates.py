"""Stage: ASR-agreement gate.

Ported from `scripts/ops/build_first_person_index.py`'s ``MIN_ASR_AGREEMENT``
threshold and ``asr_agreement()`` reasoning: whisper-vs-parakeet word
agreement below this means the transcript may hold words never spoken (pilot
low: AK435vKMtlo at 0.064; bake-off videos span 0.855-0.941, so 0.80 only cuts
outliers). Provisional -- the owner can move it.

This module holds the pure threshold check on an already-computed
``vote_stage()`` result; it does not re-read any file, so it has no opinion on
where the agreement rate came from.
"""

from __future__ import annotations

from typing import Any, Optional

MIN_ASR_AGREEMENT = 0.80


def check_asr_agreement(vote_result: dict[str, Any], min_agreement: float = MIN_ASR_AGREEMENT) -> Optional[str]:
    """Return a quarantine reason string, or None if the video clears the gate."""
    if not vote_result.get("ok"):
        return "asr_agreement_unknown"
    rate = vote_result.get("agreement_rate")
    if not isinstance(rate, (int, float)):
        return "asr_agreement_unknown"
    if rate < min_agreement:
        return f"asr_agreement_low:{rate:.3f}"
    return None


def _self_check() -> None:
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.95}) is None
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.5}) == "asr_agreement_low:0.500"
    assert check_asr_agreement({"ok": False}) == "asr_agreement_unknown"
    assert check_asr_agreement({"ok": True}) == "asr_agreement_unknown"
    print("gates.py self-check OK")


if __name__ == "__main__":
    _self_check()
