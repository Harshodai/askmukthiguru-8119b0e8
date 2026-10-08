"""WP4: the chat bridge routes teacher names through the same rule as the
frontend's resolveAttributionLabel (L-NO-INVENTED-CREDIT-1, L-PROVENANCE-ISVERBATIM-1).

``is_verbatim`` is not speaker verification: a verbatim third-party clip whose
payload says speaker "Sri Krishnaji" must not be written into answer markdown
as a bare ``**Sri Krishnaji**``, nor stamped ``speaker_verified``.
"""

import hashlib

import pytest

from app.pipeline.stages.first_person_bridge import _eligible_citations
from services.quote_fidelity import sources_from_payloads
from services.quote_weaver import QuoteWeaverService

_TEXT = "Suffering arises from resisting what is."


def _clip(**over):
    clip = {
        "point_id": "clip_p1",
        "video_id": "vid_abc123",
        "start_ms": 65000,
        "end_ms": 78000,
        "timestamp_seconds": 65,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "transcript_hash": hashlib.sha256(_TEXT.encode("utf-8")).hexdigest(),
        "verbatim_text": _TEXT,
        "source_url": "https://www.youtube.com/watch?v=vid_abc123&t=65s",
        "video_title": "The Nature of Mind",
        "is_verbatim": True,
    }
    clip.update(over)
    return clip


def _weave(clip):
    return QuoteWeaverService().weave(
        "what is suffering", [clip], [], sources=sources_from_payloads([clip])
    )


@pytest.mark.unit
def test_resolve_attribution_label_mirrors_frontend_rule() -> None:
    from services.attribution import resolve_attribution_label as r

    assert r("Sri Krishnaji", speaker_verified=True, channel="Some Vlog") == "Sri Krishnaji"
    assert r("Sri Krishnaji", speaker_verified=False, channel="Ekam") == "Sri Krishnaji"
    assert r("Sri Krishnaji", speaker_verified=None, channel="Some Vlog") == "shared in Some Vlog"
    assert r("Sri Krishnaji", speaker_verified=None, channel="Unknown Channel") == "unverified clip"
    assert r("Sri Krishnaji", speaker_verified=None, channel=None) == "unverified clip"
    assert r("Host", speaker_verified=None, channel="Some Vlog") == "Host"
    assert r("", speaker_verified=True, channel="Ekam") is None
    # explicit False beats even the route gate
    assert r("Sri Krishnaji", speaker_verified=False, channel=None, route_gated=True) == "unverified clip"


@pytest.mark.unit
def test_weaver_does_not_write_bare_teacher_name_for_third_party_verbatim_clip() -> None:
    res = _weave(_clip(channel="Some Vlog"))
    assert res.passed_gate
    assert "**Sri Krishnaji**" not in res.text
    assert "**shared in Some Vlog**" in res.text
    # the quote itself is untouched
    assert _TEXT in res.text


@pytest.mark.unit
def test_weaver_downgrades_explicit_speaker_verified_false() -> None:
    res = _weave(_clip(speaker_verified=False))
    assert "**Sri Krishnaji**" not in res.text
    assert "**unverified clip**" in res.text


@pytest.mark.unit
def test_weaver_keeps_teacher_name_for_teacher_channel_or_explicit_verification() -> None:
    assert "**Sri Krishnaji**" in _weave(_clip(channel="Ekam")).text
    assert "**Sri Krishnaji**" in _weave(_clip(channel="Some Vlog", speaker_verified=True)).text
    # route-gated clip with no contrary evidence keeps today's behaviour
    assert "**Sri Krishnaji**" in _weave(_clip()).text


@pytest.mark.unit
def test_bridge_does_not_stamp_speaker_verified_on_third_party_clip() -> None:
    citation = {
        "speaker": "Sri Krishnaji",
        "is_verbatim": True,
        "channel": "Some Vlog",
        "source_url": "https://www.youtube.com/watch?v=vid_abc123&t=65s",
        "verbatim_text": _TEXT,
    }
    (out,) = _eligible_citations([citation])
    assert out.get("speaker_verified") is not True

    (ok,) = _eligible_citations([{**citation, "channel": "Ekam"}])
    assert ok["speaker_verified"] is True

    (denied,) = _eligible_citations([{**citation, "channel": None, "speaker_verified": False}])
    assert denied.get("speaker_verified") is not True
