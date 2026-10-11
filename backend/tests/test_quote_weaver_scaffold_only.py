"""Hybrid mode: the LLM frames, code quotes (research: "ops, not text").

A rewritten chapter can swap words ("him" -> "Ravana") that the quote gate never
sees when the text has no quotation marks, so free-form output is rejected unless
the owner opts into rewrite mode. Framing calls are token-capped and cached.
"""

import hashlib

import pytest

from app.config import settings
from services import quote_weaver as qw
from services.quote_fidelity import sources_from_payloads
from services.quote_weaver import QuoteWeaverService

_TEXT = "Suffering arises from resisting what is, and peace begins when you stop resisting."


def _clip():
    return {
        "point_id": "p1",
        "video_id": "vid_abc123",
        "start_ms": 65000,
        "end_ms": 78000,
        "timestamp_seconds": 65,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "speaker_verified": True,
        "transcript_hash": hashlib.sha256(_TEXT.encode("utf-8")).hexdigest(),
        "verbatim_text": _TEXT,
        "video_title": "The Nature of Mind",
        "is_verbatim": True,
    }


class _FakeLLM:
    def __init__(self, out: str):
        self.out = out
        self.calls: list[dict] = []

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        return self.out


_SCAFFOLD = "OPENING: Sri Krishnaji observes:\nCONNECTIVE: NONE\nQUESTIONS:\n*What are you resisting right now?*"
_REWRITE = "Sri Krishnaji says suffering comes from fighting life. [1]\n\n---\n\n*What do you resist?*"


@pytest.fixture(autouse=True)
def _hybrid(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "hybrid")
    monkeypatch.setattr(settings, "first_person_editorial_rewrite_enabled", False)
    qw._SCAFFOLD_CACHE.clear()


def _weave(llm):
    clip = _clip()
    return QuoteWeaverService().weave(
        "what is suffering", [clip], [], llm_service=llm, sources=sources_from_payloads([clip])
    )


@pytest.mark.unit
def test_scaffold_output_keeps_quote_verbatim_and_never_sends_teaching_text():
    llm = _FakeLLM(_SCAFFOLD)
    res = _weave(llm)
    assert res.passed_gate and not res.fallback_used
    assert _TEXT in res.text
    assert _TEXT not in llm.calls[0]["user"] and _TEXT not in llm.calls[0]["system"]


@pytest.mark.unit
def test_free_form_rewrite_is_rejected_in_default_mode():
    res = _weave(_FakeLLM(_REWRITE))
    assert res.fallback_used
    assert "fighting life" not in res.text
    assert _TEXT in res.text


@pytest.mark.unit
def test_call_is_token_capped_and_deterministic():
    llm = _FakeLLM(_SCAFFOLD)
    _weave(llm)
    assert llm.calls[0]["max_tokens"] == settings.first_person_scaffold_max_tokens
    assert llm.calls[0]["temperature"] == 0.0


@pytest.mark.unit
def test_second_identical_request_is_served_from_cache():
    llm = _FakeLLM(_SCAFFOLD)
    _weave(llm)
    _weave(llm)
    assert len(llm.calls) == 1


@pytest.mark.unit
def test_cache_key_changes_when_clip_text_hash_changes():
    a = qw._scaffold_cache_key("q", [_clip()], False)
    changed = _clip() | {"transcript_hash": "0" * 64}
    assert a != qw._scaffold_cache_key("q", [changed], False)


@pytest.mark.unit
def test_strict_service_without_kwargs_still_works():
    class Strict:
        def generate(self, system_prompt, user_prompt):
            return _SCAFFOLD

    assert not _weave(Strict()).fallback_used


@pytest.mark.unit
def test_rewrite_mode_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "first_person_editorial_rewrite_enabled", True)
    llm = _FakeLLM(_REWRITE)
    _weave(llm)
    assert llm.calls[0]["max_tokens"] == 1200


@pytest.mark.unit
def test_default_is_scaffold_only_end_to_end_and_opt_in_flips(monkeypatch):
    """L-FP-HYBRID-SCAFFOLD-1 seam guard: default weave() never touches the
    editorial prompt path and rejects free-form LLM output; explicit opt-in
    flips to the rewrite path and serves it."""
    orig_editorial = qw._build_editorial_review_prompt
    orig_scaffold = qw._build_scaffolding_prompts
    editorial_calls: list = []
    scaffold_calls: list = []

    def _spy_editorial(query, clips, metadata=None):
        editorial_calls.append(query)
        return orig_editorial(query, clips, metadata=metadata)

    def _spy_scaffold(query, clips):
        scaffold_calls.append(query)
        return orig_scaffold(query, clips)

    monkeypatch.setattr(qw, "_build_editorial_review_prompt", _spy_editorial)
    monkeypatch.setattr(qw, "_build_scaffolding_prompts", _spy_scaffold)

    # Free-form chapter: no OPENING/CONNECTIVE/QUESTIONS fields, so the
    # default scaffold assembler must reject it; rewrite mode serves it.
    chapter = (
        "Sri Krishnaji illuminates the seeker's predicament:[1]\n\n"
        f"{_TEXT}\n\n"
        "---\n\n"
        "*What is the primary thought you are resisting right now?*\n\n"
        "*Can you rest in the space of observing awareness?*"
    )

    # Phase 1 — shipped defaults (hybrid, editorial OFF): scaffold prompts
    # only, editorial builder never invoked, free-form output rejected.
    res_default = _weave(_FakeLLM(chapter))
    assert scaffold_calls and not editorial_calls
    assert res_default.fallback_used
    assert res_default.gate_reason == "assertion_gate_or_timeout_fallback"
    assert _TEXT in res_default.text  # deterministic fallback keeps the verbatim quote
    assert "predicament" not in res_default.text and "illuminates" not in res_default.text

    # Phase 2 — explicit owner opt-in flips to the editorial rewrite path.
    qw._SCAFFOLD_CACHE.clear()
    scaffold_calls.clear()
    monkeypatch.setattr(settings, "first_person_editorial_rewrite_enabled", True)
    llm = _FakeLLM(chapter)
    res_optin = _weave(llm)
    assert editorial_calls and not scaffold_calls
    assert not res_optin.fallback_used and res_optin.passed_gate
    assert "predicament" in res_optin.text
    assert llm.calls[0]["max_tokens"] == 1200
