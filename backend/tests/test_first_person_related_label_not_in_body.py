"""Pin: directness is metadata, never answer-body text.

The "Related, not a direct answer" label used to be prefixed onto the response
body in two places:

* ``app/api/chat.py`` (verified breath-teaching endpoint) — prefixed onto the
  quoted passage;
* ``services/quote_weaver.py::_format_assembled_answer`` (continuous layout
  branch) — appended as its own block.

Both are now removed. The directness signal travels as metadata
(``is_direct_answer`` / ``verification_method`` on the route payload,
``status="weak_match"`` + ``verification["direct"]=False`` on pipeline results).

These tests are unit-level: no network, no Qdrant/Redis/Neo4j.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.api import chat as chat_module
from app.config import settings
from services.quote_weaver import _format_assembled_answer

LABEL = "Related, not a direct answer"

CLIP_TEXT = "Suffering arises whenever there is psychological resistance to the present moment."

VERIFIED_CLIP = {
    "point_id": "pt_101",
    "video_id": "hLg4WPG4ehE",
    "title": "The Beautiful State",
    "video_title": "The Beautiful State",
    "start_ms": 72000,
    "end_ms": 165000,
    "start_sec": 72,
    "end_sec": 165,
    "speaker": "Sri Krishnaji",
    "teacher_id": "krishnaji",
    "speaker_verified": True,
    "channel": "Ekam - World Centre for Enlightenment",
    "verbatim_text": CLIP_TEXT,
    "text_snippet": CLIP_TEXT,
    "source_url": "https://www.youtube.com/watch?v=hLg4WPG4ehE&t=72s",
}


def test_continuous_layout_body_has_no_related_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enabling the (currently off) continuous layout must not resurrect the label."""
    monkeypatch.setattr(settings, "first_person_continuous_layout_enabled", True)
    monkeypatch.setattr(settings, "first_person_framing_enabled", False)

    body = _format_assembled_answer([dict(VERIFIED_CLIP)], query="what is suffering?")

    assert LABEL not in body
    assert "Related, not a direct answer" not in body
    # The verbatim clip itself must survive untouched.
    assert CLIP_TEXT in body


def test_chat_teaching_endpoint_has_no_body_prefix() -> None:
    """Source-level pin (honest shortcut).

    Importing the route handler is heavy and the prefix is a literal in the
    module body, so we assert on the source: the prefix string must be gone and
    the additive metadata field must be present. This is a deliberate
    source-level pin, not a behavioural test.
    """
    source = inspect.getsource(chat_module)
    assert "Related, not a direct answer:\\n\\n" not in source
    assert 'teaching_parts = [f"“{quote}”"]' in source
    assert '"is_direct_answer": is_direct_answer' in source
    assert '"first_person_verbatim_clip_gate"' in source
    assert '"first_person_related_clip_gate"' in source


def test_chat_module_file_on_disk_matches_pin() -> None:
    """Same pin against the file bytes, so a stray cached module can't mask drift."""
    path = Path(chat_module.__file__).resolve()
    text = path.read_text(encoding="utf-8")
    assert "Related, not a direct answer" not in text
