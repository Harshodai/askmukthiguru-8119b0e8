"""
Regression tests for scripts/ingestion/parallel_corpus_extractor.py's two
D2 defects:

1. The token-bucket rate limiter / circuit breaker only gated the first
   network call; retries and the yt-dlp tiers bypassed it and never fed
   403/429 errors back into the breaker.
2. Resume trusted an existing artifact_manifest.json without re-verifying
   the canonical transcript it points at still passes the structural gate.

No network, no ASR: yt_dlp/YouTubeTranscriptApi/whisper are stubbed.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from scripts.ingestion import parallel_corpus_extractor as mod  # noqa: E402
from scripts.ingestion.corpus_engine import CorpusEngine  # noqa: E402
from services.transcript_verbatim import compute_verbatim_hash  # noqa: E402


# ---------------------------------------------------------------------------
# YouTubeRateLimiter — direct unit coverage of the token bucket + breaker.
# ---------------------------------------------------------------------------

def test_rate_limiter_trips_circuit_after_max_strikes():
    limiter = mod.YouTubeRateLimiter(rate=1000.0, capacity=1000.0, max_strikes=3, cooldown_s=60.0)
    limiter.record_error(429)
    limiter.record_error(429)
    assert limiter._circuit_open_until == 0.0  # not yet tripped
    limiter.record_error(429)
    assert limiter._circuit_open_until > 0.0  # tripped on the 3rd strike


def test_rate_limiter_success_resets_strikes():
    limiter = mod.YouTubeRateLimiter(rate=1000.0, capacity=1000.0, max_strikes=3, cooldown_s=60.0)
    limiter.record_error(429)
    limiter.record_error(429)
    limiter.record_success()
    assert limiter._strikes == 0
    limiter.record_error(429)
    assert limiter._circuit_open_until == 0.0  # only 1 strike since reset


def test_rate_limiter_ignores_non_rate_limit_status_codes():
    limiter = mod.YouTubeRateLimiter(max_strikes=1, cooldown_s=60.0)
    limiter.record_error(500)
    assert limiter._strikes == 0
    assert limiter._circuit_open_until == 0.0


# ---------------------------------------------------------------------------
# VideoProcessor._record_network_error — the shared helper every tier must use.
# ---------------------------------------------------------------------------

def _processor(tmp_path: Path) -> "mod.VideoProcessor":
    engine = CorpusEngine(corpus_root=tmp_path / "corpus", projection_dir=tmp_path / "projections")
    return mod.VideoProcessor(corpus_engine=engine, delay_min=0.0, delay_max=0.0)


def test_record_network_error_403(tmp_path: Path):
    p = _processor(tmp_path)
    p.rate_limiter = MagicMock()
    p._record_network_error("HTTP Error 403: Forbidden")
    p.rate_limiter.record_error.assert_called_once_with(403)


def test_record_network_error_429(tmp_path: Path):
    p = _processor(tmp_path)
    p.rate_limiter = MagicMock()
    p._record_network_error("429 Too Many Requests")
    p.rate_limiter.record_error.assert_called_once_with(429)


def test_record_network_error_ignores_unrelated_errors(tmp_path: Path):
    p = _processor(tmp_path)
    p.rate_limiter = MagicMock()
    p._record_network_error("connection reset by peer")
    p.rate_limiter.record_error.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 2 (yt-dlp subtitle scrape) must acquire() and feed the breaker on
# failure -- previously it did neither.
# ---------------------------------------------------------------------------

class _FakeYoutubeDLForbidden:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        raise RuntimeError("HTTP Error 403: Forbidden")


def test_tier2_acquires_token_and_records_403_on_failure(tmp_path: Path, monkeypatch):
    p = _processor(tmp_path)
    p.rate_limiter = MagicMock()

    monkeypatch.setattr(mod, "YouTubeTranscriptApi", None)  # skip Tier 1
    monkeypatch.setattr(mod, "yt_dlp", MagicMock(YoutubeDL=_FakeYoutubeDLForbidden))
    monkeypatch.setattr(mod, "get_node_path", lambda: "node")

    video = {"video_id": "v_tier2", "url": "https://www.youtube.com/watch?v=v_tier2", "title": "t"}
    ok, state, h = p.process_single_video(video, enable_whisper_fallback=False)

    assert ok is False
    assert state == "dead_lettered"
    # Called once for the pre-video acquire, once more for Tier 2's own call.
    assert p.rate_limiter.acquire.call_count >= 2
    p.rate_limiter.record_error.assert_any_call(403)


# ---------------------------------------------------------------------------
# Resume must re-verify, not blindly trust, an existing artifact manifest.
# ---------------------------------------------------------------------------

def test_resume_reextracts_when_existing_transcript_fails_verification(tmp_path: Path, monkeypatch):
    """An existing artifact_manifest.json pointing at a canonical_segments.json
    with zero segments (a hard per_video_checks failure) must NOT be trusted
    -- process_single_video must fall through to (attempted) re-extraction
    rather than returning the stale trusted result."""
    p = _processor(tmp_path)
    monkeypatch.setattr(mod, "YouTubeTranscriptApi", None)
    monkeypatch.setattr(mod, "yt_dlp", None)  # force straight to dead_lettered if re-extraction is attempted

    video_id = "v_stale"
    v_dir = p.engine.get_video_dir(video_id)
    (v_dir / "artifact_manifest.json").write_text(json.dumps({
        "final_quality_state": "trusted", "manifest_hash": "STALE_HASH",
    }))
    (v_dir / "canonical_segments.json").write_text(json.dumps({"segments": []}))

    video = {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "title": "t"}
    ok, state, h = p.process_single_video(video, enable_whisper_fallback=False)

    # If the stale manifest had been trusted, this would be (True, "trusted", "STALE_HASH").
    assert (ok, state, h) != (True, "trusted", "STALE_HASH")
    assert (ok, state, h) == (False, "dead_lettered", None)


def test_resume_trusts_manifest_when_transcript_still_passes_verification(tmp_path: Path, monkeypatch):
    """The happy path must be unaffected: a genuinely valid existing
    transcript is still trusted and skipped without re-extraction."""
    p = _processor(tmp_path)
    # If re-extraction were attempted it would explode on these Nones --
    # proves the manifest-trusted early return fired instead.
    monkeypatch.setattr(mod, "YouTubeTranscriptApi", None)
    monkeypatch.setattr(mod, "yt_dlp", None)

    video_id = "v_valid"
    v_dir = p.engine.get_video_dir(video_id)
    text = "The mind creates suffering through identification with thought."
    segs = [{"segment_id": "seg_0000", "start": 0.0, "end": 5.0, "text": text, "verbatim_text": text}]
    h = compute_verbatim_hash(segs)
    (v_dir / "canonical_segments.json").write_text(json.dumps({"segments": segs, "transcript_hash": h}))
    (v_dir / "artifact_manifest.json").write_text(json.dumps({
        "final_quality_state": "trusted", "manifest_hash": "GOOD_HASH",
    }))

    video = {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "title": "t"}
    ok, state, manifest_hash = p.process_single_video(video, enable_whisper_fallback=False)

    assert (ok, state, manifest_hash) == (True, "trusted", "GOOD_HASH")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
