"""Regression tests for UT-04, UT-05, and UT-06 serving fixes:
1. UT-06: Unverified clips are strictly dropped and never served to public users.
2. UT-04 / UT-05: Spans with guru_id/teacher_id map strictly to single-teacher display labels.
"""

import pytest
from app.config import settings
from app.pipeline.stages.first_person_bridge import _eligible_citations
from services.first_person_pipeline import _speaker_verification
from services.quote_fidelity import canonical_speaker
from services.quote_weaver import _stored_label


def test_unverified_citation_is_dropped_when_verification_required(monkeypatch):
    """UT-06: When first_person_require_speaker_verified is True, unverified citations are dropped."""
    monkeypatch.setattr(settings, "first_person_require_speaker_verified", True)

    unverified_citation = {
        "source_url": "https://www.youtube.com/watch?v=vid123&t=10s",
        "verbatim_text": "Sample teaching text",
        "speaker": "Sri Preethaji",
        "speaker_verified": False,
        "is_verbatim": True,
    }
    verified_citation = {
        "source_url": "https://www.youtube.com/watch?v=vid123&t=20s",
        "verbatim_text": "Another sample teaching text",
        "speaker": "Sri Preethaji",
        "speaker_verified": True,
        "is_verbatim": True,
    }

    result = _eligible_citations([unverified_citation, verified_citation])
    assert len(result) == 1
    assert result[0]["verbatim_text"] == "Another sample teaching text"


def test_stored_label_resolves_to_individual_guru_when_channel_is_joint():
    """UT-04 / UT-05: When a clip's speaker is the joint channel name, guru_id maps to the single teacher."""
    clip_preethaji = {
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "guru_id": "preethaji",
    }
    clip_krishnaji = {
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "guru_id": "krishnaji",
    }

    assert _stored_label(clip_preethaji) == "Sri Preethaji"
    assert _stored_label(clip_krishnaji) == "Sri Krishnaji"


def test_canonical_speaker_maps_guru_codes_correctly():
    """D6 Fix: bare teacher codes map to individual guru identities."""
    assert canonical_speaker("preethaji") == "preethaji"
    assert canonical_speaker("krishnaji") == "krishnaji"
    assert canonical_speaker("sri preethaji") == "preethaji"
    assert canonical_speaker("sri krishnaji") == "krishnaji"
