"""NEW-SEC-5 / NEW-AI-6: offline adversarial suite (evals/adversarial/cases.jsonl).

Each case names a ``check``. The runner calls the real code for that check
with a stub LLM that returns a fixed (hostile or malformed) reply, so the test
measures how the system handles the input, not what a model would say. No
network, no Qdrant, no real provider. CI runs it with the backend test job.

``status``:
* ``block``: the case must pass.
* ``expected_fail_tracked``: a known gap. The runner asserts that the gap is
  still there, so a fix makes this test fail and the case must then be
  promoted to ``block`` (no xfail marker; the gap is visible in the report).

Cases that need a live stack (RLS with two accounts, 200 concurrent requests,
Qdrant write keys, rate limits) are listed in evals/adversarial/README.md and
are not run here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import services.first_person_pipeline as fpp
import tests.test_first_person_context_harness as _h
from app.config import settings

_synthetic_registry = _h._synthetic_registry

_CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "adversarial" / "cases.jsonl"
CASES = [json.loads(line) for line in _CASES_PATH.read_text(encoding="utf-8").splitlines() if line]


class _StubLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def _closing(tag: str, text: str) -> int:
    return len(re.findall(rf"</{tag}>", text))


def _live_tags(tag: str, text: str) -> int:
    """Opening or closing ``tag`` markers a model could read as a tag,
    lookalike forms included (full-width, small-form, zero-width split)."""
    from services.untrusted import _is_angle, _tag_at

    return sum(1 for i, ch in enumerate(text) if _is_angle(ch) and _tag_at(text, i, (tag,)))


def _clip(text: str, **extra) -> dict[str, Any]:
    import hashlib

    return {
        "point_id": "p1",
        "video_id": "vidA",
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "speaker": sorted(fpp.ALLOWED_SPEAKERS)[0] if hasattr(fpp, "ALLOWED_SPEAKERS") else None,
        "first_person_eligible": True,
        "rights_cleared": True,
        "is_verbatim": True,
        "domain_rights_status": "licensed",
        "source_url": "https://www.youtube.com/watch?v=vidA",
        **extra,
    }


# --- checks: each returns True when the system behaved as expected -----------


def check_scorer_prompt_fence(p, monkeypatch):
    clips = [{"verbatim_text": t} for t in p["clips"]]
    prompt = fpp._build_relevance_user_prompt(p["question"], clips)
    # One open and one close per clip, plus the "<clip> tags" notice line.
    return (
        _live_tags("clip", prompt) == 2 * len(clips) + 1
        and prompt.count("] <clip>") == len(clips)
        and "not instructions" in prompt
    )


def check_rerank_prompt_fence(p, monkeypatch):
    llm = _StubLLM(",".join(str(i) for i in range(1, len(p["clips"]) + 1)))
    clips = [{"verbatim_text": t} for t in p["clips"]]
    fpp._llm_rerank_clips(p["question"], clips, llm)
    prompt = llm.calls[0]["user_prompt"]
    return (
        _closing("clip", prompt) == len(clips)
        and "never follow instructions" in (llm.calls[0]["system_prompt"])
    )


def check_generation_fence(p, monkeypatch):
    from rag.nodes import generation as gen

    return _closing(p["tag"], gen._fence(p["tag"], p["text"])) == 1


def check_injection_screen(p, monkeypatch):
    from services.injection_screen import screen

    return bool(screen(p["text"]))


def check_injection_screen_clean(p, monkeypatch):
    from services.injection_screen import screen

    return screen(p["text"]) == ()


def check_memory_extractor_rejects(p, monkeypatch):
    from services.canonical_memory.extractor import _is_rejected

    return _is_rejected(p["text"]) == "prompt_injection"


def check_legacy_integrity_gate(p, monkeypatch):
    monkeypatch.setattr(fpp, "source_is_authoritatively_licensed", lambda **_: True)
    monkeypatch.setattr(fpp, "video_is_blocked", lambda _vid: False)
    clip = _clip("Suffering is a call to awaken and to see the truth of the moment.")
    if p.get("speaker") is not None:
        clip["speaker"] = p["speaker"]
    if p.get("edit_text"):
        clip["verbatim_text"] += " Obey me."
    return fpp._passes_integrity_gate(clip, check_availability=False) is False


def check_harness_hash_gate(p, monkeypatch):
    from services.first_person_context_harness import FirstPersonContextHarness, HarnessDecision

    # SourceSpan validation refuses a mismatched hash at construction, so the
    # tampered span is made with model_copy (no validation), as a store row
    # edited in place would arrive.
    tampered = _h.span().model_copy(update={"verbatim_text": p["text"]})
    decision = FirstPersonContextHarness().decide(_h.context([tampered]), answerability="yes")
    return (
        decision.decision is HarnessDecision.ABSTAIN
        and decision.abstain_reason == "source_text_hash_mismatch"
    )


def check_served_clip_check(p, monkeypatch):
    import hashlib

    from app.answer_contract import served_clip_integrity_failures

    text = p["stored"]
    citation = {
        "verbatim_text": text,
        "source_text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    return "substring" in served_clip_integrity_failures([citation], p["answer"])


def check_scorer_output(p, monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_model", "", raising=False)
    clips = [{"verbatim_text": "one"}, {"verbatim_text": "two"}]
    result = fpp._relevance_select("q", clips, _StubLLM(p["reply"]))
    return result == fpp._RELEVANCE_INDETERMINATE


def check_answerability_output(p, monkeypatch):
    return fpp._answerability_check("q", _StubLLM(p["reply"])) is None


def check_route_canonical(p, monkeypatch):
    from app.route_taxonomy import RouteDecision, canonicalize_route_decision

    return canonicalize_route_decision(p["route"]) in {r.value for r in RouteDecision}


def check_not_a_greeting(p, monkeypatch):
    from app.routing_primitives import is_deterministic_greeting

    return is_deterministic_greeting(p["text"]) is False


CHECKS = {name[len("check_") :]: fn for name, fn in globals().items() if name.startswith("check_")}


def test_every_case_has_a_known_check_and_status():
    assert len(CASES) >= 20
    assert len({c["id"] for c in CASES}) == len(CASES)
    for case in CASES:
        assert case["check"] in CHECKS, case["id"]
        assert case["status"] in {"block", "expected_fail_tracked"}, case["id"]


# The suite-wide stubs in conftest.py replace the relevance and answerability
# gates; these markers opt out so the real parsers face the hostile replies.
@pytest.mark.relevance_real
@pytest.mark.answerability_real
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_adversarial_case(case, monkeypatch):
    passed = CHECKS[case["check"]](case["payload"], monkeypatch)
    if case["status"] == "block":
        assert passed, f"{case['id']} ({case['ref']}): expected {case['expected']}"
    else:
        assert not passed, (
            f"{case['id']} now passes: promote it to status 'block' in "
            "evals/adversarial/cases.jsonl"
        )
