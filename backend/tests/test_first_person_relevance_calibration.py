"""WS2 + WS3 (SOTA plan): hybrid sparse retrieval default and the calibrated relevance band.

Two independent contracts:

* ``first_person_context_use_sparse`` is ON by default, and the pipeline helper returns the
  sparse payload unchanged when it is on and ``None`` when an owner turns it off. The live
  fp-context collection carries a ``passage_sparse`` named vector, so this cannot silently
  become a dense-only path.
* The relevance rubric scores a foundational/parabolic teaching 2, and a 2 is served as
  ``weak_match`` — never as a direct answer (first-person serving invariant #1).
"""

from __future__ import annotations

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _RELEVANCE_JSON_SYSTEM_PROMPT,
    _RELEVANCE_PROMPT_VERSION,
    _RELEVANCE_RUBRIC_CORE,
    _RELEVANCE_SYSTEM_PROMPT,
    _context_sparse_query,
    _resolve_served_directness,
)

_SPARSE = {"indices": [1, 7, 42], "values": [0.9, 0.4, 0.2]}


# --------------------------------------------------------------------------- WS2


def test_sparse_context_retrieval_is_on_by_default():
    assert settings.first_person_context_use_sparse is True


def test_sparse_payload_is_forwarded_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "first_person_context_use_sparse", True)
    assert _context_sparse_query(_SPARSE) is _SPARSE


def test_sparse_payload_is_dropped_when_an_owner_disables_it(monkeypatch):
    monkeypatch.setattr(settings, "first_person_context_use_sparse", False)
    assert _context_sparse_query(_SPARSE) is None


def test_missing_sparse_weights_stay_none(monkeypatch):
    monkeypatch.setattr(settings, "first_person_context_use_sparse", True)
    assert _context_sparse_query(None) is None


# --------------------------------------------------------------------------- WS3


def test_relevance_prompt_version_bumped_for_the_new_rubric():
    assert _RELEVANCE_PROMPT_VERSION == "v3"


@pytest.mark.parametrize("prompt", [_RELEVANCE_SYSTEM_PROMPT, _RELEVANCE_JSON_SYSTEM_PROMPT])
def test_both_reply_grammars_share_the_calibrated_rubric(prompt: str):
    assert prompt.startswith(_RELEVANCE_RUBRIC_CORE)
    assert "foundational or parabolic answer" in prompt
    assert "scores 2, not 1" in prompt


@pytest.mark.parametrize("prompt", [_RELEVANCE_SYSTEM_PROMPT, _RELEVANCE_JSON_SYSTEM_PROMPT])
def test_calibration_did_not_drop_a_disqualifier(prompt: str):
    lowered = prompt.lower()
    for trap in (
        "announcement",
        "fragment",
        "mid-thought",
        "corona/lockdown",
        "self-harm",
        "another spiritual teacher",
    ):
        assert trap in lowered, trap


def test_score_two_is_never_direct():
    assert _resolve_served_directness(True, 2) is False
    assert _resolve_served_directness(True, 3) is True


def test_no_score_keeps_the_callers_verdict():
    assert _resolve_served_directness(True, None) is True
    assert _resolve_served_directness(False, 3) is False


def test_bad_score_fails_toward_related():
    assert _resolve_served_directness(True, "3") is True
    assert _resolve_served_directness(True, "not-a-score") is False


def test_relevance_minimum_default_is_three():
    # Owner decision 2026-11-16: the declared default is 3 (the env-resolved value
    # may differ locally, so assert the declaration, not the live setting).
    assert type(settings).model_fields["first_person_relevance_min_score"].default == 3
