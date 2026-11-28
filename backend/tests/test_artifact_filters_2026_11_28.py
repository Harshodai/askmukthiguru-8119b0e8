"""Artifact filters (always on): defects rejected with a bounded code; clean clips pass."""

import pytest

from services import first_person_pipeline as fpp

BASE = (
    "When the mind is quiet we begin to see how much of our suffering comes from the stories "
    "we repeat about the past and the future, and that seeing itself brings real relief"
)

DEFECTS = {
    "artifact_asr_restart": [
        f"{BASE} and everything. everything. is held in that awareness today.",
        f"{BASE} and true compassion. passion. is what remains here today.",
        f"{BASE} and we are one too. too. in this awareness today.",
    ],
    "artifact_audience_address": [
        f"Please be seated with your eyes closed. {BASE} in every single moment.",
        f"From today you are beginning your contribution to world peace by doing Soul Sync. {BASE}.",
    ],
    "artifact_outcome_promise": [
        f"{BASE}, a magic potion to heal your heart of all its wounds.",
        f"{BASE}. Everything happens. Everything comes to you in time.",
    ],
    "artifact_short_question_tail": [f"{BASE}. What am I becoming?"],
}

CLEAN = [
    f"{BASE}.",
    "Peace arises from humility. Humility arises from wisdom. Wisdom arises from stillness, "
    "and stillness is where every honest seeker eventually learns to rest and simply listen.",
    f"{BASE}. Have you ever noticed how that feels in the body when you stop and breathe?",
    "In this Soul Sync practice, breathe slowly and let the attention rest on the heart, "
    "noticing each sensation without trying to change it, and stay with it gently for a while.",
]


def _clip(text: str) -> dict:
    return {"verbatim_text": text, "point_id": "p1"}


def _all_defects():
    return [(code, t) for code, texts in DEFECTS.items() for t in texts]


@pytest.mark.parametrize("code,text", _all_defects())
def test_rejects_with_code(code, text):
    assert fpp._artifact_problem(text) == code
    assert fpp._passes_content_quality_gate(_clip(text), gate_enabled=True) is False


@pytest.mark.parametrize("text", CLEAN)
def test_clean_passes(text):
    assert fpp._artifact_problem(text) is None
    assert fpp._passes_content_quality_gate(_clip(text), gate_enabled=True) is True


def test_reason_code_counted():
    from app.turn_trace import turn_trace_var

    class T:
        def __init__(self):
            self.c = []

        def bump(self, g):
            self.c.append(g)

    t = T()
    tok = turn_trace_var.set(t)
    try:
        fpp._passes_content_quality_gate(
            _clip(DEFECTS["artifact_asr_restart"][0]), gate_enabled=True
        )
    finally:
        turn_trace_var.reset(tok)
    assert t.c == ["artifact_asr_restart"]
