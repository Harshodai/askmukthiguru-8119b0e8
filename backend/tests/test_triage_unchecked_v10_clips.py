"""Triage of v10 clips without a voice-window file (audits/scripts, read-only)."""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "triage_unchecked_v10_clips", _ROOT / "audits/scripts/triage_unchecked_v10_clips.py"
)
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)


def _span(tier="local_review_candidate", reason="verified", start=1000, end=5000, hashes=()):
    return {
        "tier": tier,
        "source_span_id": "s1",
        "start": start,
        "end": end,
        "hashes": set(hashes),
        "reason_code": reason,
        "cosine": 0.7,
        "margin": 0.5,
    }


def _clip(text="Be still.", start=1000, end=5000, **kw):
    return {"video_id": "v", "start_ms": start, "end_ms": end, "text": text, **kw}


def test_verified_clip_is_verified():
    assert triage.classify(_clip(), [_span()])["outcome"] == "verified"


def test_question_text_on_verified_span_needs_a_listen():
    assert (
        triage.classify(_clip("How do we find balance?"), [_span()])["outcome"] == "host_uncertain"
    )


def test_refused_span_is_host_uncertain():
    out = triage.classify(_clip(), [_span(reason="refused_guru_mismatch", tier="review_required")])
    assert out["outcome"] == "host_uncertain"


def test_no_overlapping_span_is_hold():
    assert triage.classify(_clip(), [_span(start=90000, end=95000)])["outcome"] == "hold"


def test_unserved_tier_is_hold():
    assert triage.classify(_clip(), [_span(tier="variant_candidate")])["outcome"] == "hold"


def test_transcript_hash_never_selects_the_span():
    out = triage.classify(_clip(start=50000, end=55000, transcript_hash="h"), [_span(hashes={"h"})])
    assert out["outcome"] == "hold"
