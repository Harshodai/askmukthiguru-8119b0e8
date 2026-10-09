"""
Comprehensive verification test suite for Task 2:
- Hard Stop H4 (Spiritual / Miracle Promises Quarantine)
- Hard Stop H8 (Head-Fragment Clips & ASR Stutter Repair)
- Failure Injection FI-16 (YouTube 404 Video Availability Detection)
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.verbatim.boundaries import boundary_defects
from scripts.ops.quarantine_promise_clips import quarantine_promise_clips
from scripts.ops.repair_first_person_head_fragments import (
    execute_fragment_repairs,
    plan_clip_repair,
)
from services.first_person_pipeline import (
    FirstPersonPipeline,
    FirstPersonPipelineResult,
    _passes_integrity_gate,
)
from services.first_person_store import (
    BLOCKED_PROMISE_POINT_IDS,
    FirstPersonStore,
    _OUTCOME_PROMISE_CLIP_RE,
    make_first_person_point_id,
    validate_clip_entry,
)
from services.youtube_availability import (
    FAIL_OPEN_TIMEOUT_SECONDS,
    REDIS_KEY_YOUTUBE_AVAILABILITY,
    YouTubeAvailabilityService,
    is_youtube_video_available,
    is_youtube_video_available_async,
)


def _make_valid_clip(
    text: str = "When you observe your thoughts without judgment, inner freedom begins.",
    speaker: str = "Sri Preethaji",
    video_id: str = "valid_vid_123",
    start_ms: int = 10000,
    end_ms: int = 25000,
    **kwargs: Any,
) -> dict[str, Any]:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    clip = {
        "point_id": make_first_person_point_id(h, start_ms, end_ms),
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker": speaker,
        "transcript_hash": h,
        "verbatim_text": text,
        "first_person_eligible": True,
        "is_verbatim": True,
    }
    clip.update(kwargs)
    return clip


# ============================================================================
# 1. Hard Stop H4: Spiritual / Miracle Promises
# ============================================================================


class TestHardStopH4OutcomePromises:
    def test_outcome_promise_clip_re_matches(self):
        """Verify regex catches the forbidden outcome and miracle promises."""
        matches = [
            "your problems melt like ice in the heat of the sun and everything resolves",
            "we promise you that your problems melt like ice",
            "this is a guaranteed miracle for your family",
            "we guarantee a miracle in 21 days",
            "an instant miracle will unfold in your life",
            "a guaranteed outcome for your inner life",
            "guaranteed healing for physical ailments",
            "we promise you a miracle",
        ]
        for m in matches:
            assert _OUTCOME_PROMISE_CLIP_RE.search(m), f"Expected match for: {m}"

        benign = [
            "When you observe your inner state, suffering dissolves naturally.",
            "Live in a Beautiful State, connected with what is.",
            "The universe responds to your presence and truth.",
            "Notice the thoughts without fighting them.",
        ]
        for b in benign:
            assert not _OUTCOME_PROMISE_CLIP_RE.search(b), f"Did not expect match for: {b}"

    def test_integrity_gate_rejects_outcome_promise_text(self):
        """Integrity gate must reject any clip matching _OUTCOME_PROMISE_CLIP_RE."""
        text = "Only when you live in a Beautiful State, your problems melt like ice in the heat of the sun."
        clip = _make_valid_clip(text=text)
        assert _passes_integrity_gate(clip) is False

    def test_integrity_gate_rejects_blocked_promise_point_ids(self):
        """Integrity gate must reject any clip in BLOCKED_PROMISE_POINT_IDS (including mmpmX3-qfc4)."""
        clip = _make_valid_clip(video_id="mmpmX3-qfc4")
        assert _passes_integrity_gate(clip) is False

        clip_with_blocked_point = _make_valid_clip(point_id="mmpmX3-qfc4")
        assert _passes_integrity_gate(clip_with_blocked_point) is False

    def test_integrity_gate_passes_clean_clip(self):
        """Clean authentic spiritual clips pass the integrity gate."""
        clip = _make_valid_clip()
        with patch("services.first_person_pipeline.is_youtube_video_available", return_value=True):
            assert _passes_integrity_gate(clip) is True

    def test_store_validate_clip_entry_rejects_h4(self):
        """FirstPersonStore.validate_clip_entry must raise ValueError on H4 clips."""
        # 1. Text containing outcome promise
        bad_text = "Come and experience a guaranteed miracle today."
        bad_clip = _make_valid_clip(text=bad_text)
        with pytest.raises(ValueError, match="prohibited spiritual outcome or miracle promise"):
            validate_clip_entry(bad_clip)

        # 2. Video in BLOCKED_PROMISE_POINT_IDS
        blocked_video_clip = _make_valid_clip(video_id="mmpmX3-qfc4")
        with pytest.raises(ValueError, match="BLOCKED_PROMISE_POINT_IDS"):
            validate_clip_entry(blocked_video_clip)

    def test_quarantine_promise_clips_script(self):
        """Test quarantine_promise_clips script logic with mocked Qdrant client."""
        mock_client = MagicMock()

        # Mock scroll returning a point for mmpmX3-qfc4 and a promise clip
        point1 = MagicMock()
        point1.id = "p-mmpmX3"
        point1.payload = {
            "video_id": "mmpmX3-qfc4",
            "verbatim_text": "your problems melt like ice in the heat of the sun",
            "first_person_eligible": True,
        }

        # First scroll call for video_id filter, second for general scan
        mock_client.scroll.side_effect = [
            ([point1], None),
            ([point1], None),
        ]

        res = quarantine_promise_clips(
            collection="first_person_v7",
            video_id="mmpmX3-qfc4",
            client=mock_client,
            dry_run=False,
        )

        assert res["status"] == "success"
        assert res["quarantined_count"] >= 1
        mock_client.set_payload.assert_called_once()
        call_kwargs = mock_client.set_payload.call_args[1]
        assert call_kwargs["payload"]["first_person_eligible"] is False
        assert call_kwargs["payload"]["quarantine_reason"] == "outcome_promise_H4"


# ============================================================================
# 2. Hard Stop H8: Head-Fragment Clips & ASR Stutter
# ============================================================================


class TestHardStopH8HeadFragmentRepairs:
    def test_repairable_head_fragment_snaps_and_shifts(self):
        """A clip opening on a severed fragment (e.g. 'Changes. The truth is...') is repaired."""
        # 'Changes.' is a head fragment (defects contains 'head_fragment')
        bad_text = (
            "Changes. The truth is that when you observe your mind, "
            "peace arises naturally and you return to the Beautiful State."
        )
        tokens = bad_text.split()
        assert "head_fragment" in boundary_defects(tokens)

        payload = {
            "video_id": "vid_test",
            "start_ms": 10000,
            "end_ms": 30000,
            "speaker": "Sri Krishnaji",
            "verbatim_text": bad_text,
            "transcript_hash": hashlib.sha256(bad_text.encode("utf-8")).hexdigest(),
        }

        plan = plan_clip_repair("test-point-id", payload)
        assert plan["action"] == "repair"
        assert plan["repairable"] is True
        assert plan["new_start_ms"] > plan["old_start_ms"]
        assert plan["proposed_text"].startswith("The truth is")

        # Invariant checks:
        expected_hash = hashlib.sha256(plan["proposed_text"].encode("utf-8")).hexdigest()
        assert plan["new_hash"] == expected_hash
        assert plan["new_point_id"] == make_first_person_point_id(
            expected_hash, plan["new_start_ms"], plan["end_ms"]
        )

        # Repaired text no longer has head_fragment defect
        assert "head_fragment" not in boundary_defects(plan["proposed_text"].split())

        # Repaired clip passes integrity gate
        repaired_clip = plan["payload"]
        with patch("services.first_person_pipeline.is_youtube_video_available", return_value=True):
            assert _passes_integrity_gate(repaired_clip, boundary_guard_enabled=True) is True

    def test_unrepairable_clip_quarantines(self):
        """A clip where too few words survive after snap_to_sentences (<12 words) is quarantined."""
        short_fragment = "Changes. Peace is."
        payload = {
            "video_id": "vid_short",
            "start_ms": 5000,
            "end_ms": 7000,
            "speaker": "Sri Preethaji",
            "verbatim_text": short_fragment,
            "transcript_hash": hashlib.sha256(short_fragment.encode("utf-8")).hexdigest(),
        }

        plan = plan_clip_repair("short-point-id", payload, min_words=12)
        assert plan["action"] == "quarantine"
        assert plan["repairable"] is False
        assert plan["payload_update"]["first_person_eligible"] is False
        assert plan["payload_update"]["quarantine_reason"] == "unrepairable_head_fragment_H8"

    def test_clean_clip_needs_no_action(self):
        """A clip with no head_fragment defect needs no repair action."""
        clean_text = "When you observe the movement of thought, silence descends."
        payload = {
            "video_id": "vid_clean",
            "start_ms": 0,
            "end_ms": 10000,
            "speaker": "Sri Preethaji",
            "verbatim_text": clean_text,
            "transcript_hash": hashlib.sha256(clean_text.encode("utf-8")).hexdigest(),
        }
        plan = plan_clip_repair("clean-point-id", payload)
        assert plan["action"] == "none"

    def test_execute_fragment_repairs_39_and_4(self):
        """Simulate the 39 repairable and 4 unrepairable split on mock points."""
        mock_points = []

        # 39 repairable clips
        for i in range(39):
            text = (
                f"Changes. In discourse {i}, Sri Krishnaji teaches that observing "
                "the inner turbulence with quiet attention brings profound stillness and clarity."
            )
            mock_points.append(
                {
                    "id": f"repairable-{i}",
                    "payload": {
                        "video_id": f"vid_r_{i}",
                        "start_ms": 1000 * i,
                        "end_ms": 1000 * i + 15000,
                        "speaker": "Sri Krishnaji",
                        "verbatim_text": text,
                        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "first_person_eligible": True,
                    },
                }
            )

        # 4 unrepairable clips (too short to leave >=12 words after dropping head fragment)
        for i in range(4):
            text = f"Changes. State {i}."
            mock_points.append(
                {
                    "id": f"unrepairable-{i}",
                    "payload": {
                        "video_id": f"vid_u_{i}",
                        "start_ms": 2000 * i,
                        "end_ms": 2000 * i + 3000,
                        "speaker": "Sri Preethaji",
                        "verbatim_text": text,
                        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "first_person_eligible": True,
                    },
                }
            )

        # Run execute_fragment_repairs in dry-run mode
        res = execute_fragment_repairs(
            collection="first_person_v7",
            sample_points=mock_points,
            dry_run=True,
        )

        assert res["status"] == "success"
        assert res["total_head_fragment_clips"] == 43
        assert res["repairable_count"] == 39
        assert res["unrepairable_count"] == 4


# ============================================================================
# 3. Failure Injection FI-16: YouTube 404 Video Detection
# ============================================================================


class TestFailureInjectionFI16YouTubeAvailability:
    def setup_method(self):
        # Clear in-memory cache between tests
        service = YouTubeAvailabilityService()
        service.clear_caches()

    def test_oembed_200_available(self):
        """HTTP 200 response from oEmbed indicates video is available."""
        service = YouTubeAvailabilityService()
        service.clear_caches()

        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp

            assert service.is_available_sync("video_good_200") is True
            mock_get.assert_called_once()

    def test_oembed_404_unavailable(self):
        """HTTP 404 response from oEmbed indicates video is deleted / unavailable."""
        service = YouTubeAvailabilityService()
        service.clear_caches()

        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            assert service.is_available_sync("video_dead_404") is False
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_oembed_async_404_unavailable(self):
        """Async check also correctly returns False on 404."""
        service = YouTubeAvailabilityService()
        service.clear_caches()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            available = await service.is_available_async("video_dead_async_404")
            assert available is False

    def test_600ms_timeout_fails_open(self):
        """Network timeout (>600ms) fails open to True so serving is never blocked."""
        service = YouTubeAvailabilityService(timeout_seconds=FAIL_OPEN_TIMEOUT_SECONDS)
        service.clear_caches()

        with patch("httpx.Client.get", side_effect=httpx.TimeoutException("Read timed out")):
            # Must return True (fail-open)
            assert service.is_available_sync("video_timeout") is True

    def test_network_error_fails_open(self):
        """Network / DNS error fails open to True."""
        service = YouTubeAvailabilityService()
        service.clear_caches()

        with patch("httpx.Client.get", side_effect=httpx.NetworkError("DNS lookup failed")):
            assert service.is_available_sync("video_net_err") is True

    def test_two_tier_caching_memory_and_redis(self):
        """Verifies memory hit avoids HTTP, and Redis hit populates memory."""
        service = YouTubeAvailabilityService()
        service.clear_caches()

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("services.youtube_availability._get_redis", return_value=mock_redis):
            with patch("httpx.Client.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_get.return_value = mock_resp

                # 1. First call queries oEmbed and writes to memory and Redis
                res1 = service.is_available_sync("video_cache_test")
                assert res1 is True
                assert mock_get.call_count == 1
                mock_redis.set.assert_called_once_with(
                    f"{REDIS_KEY_YOUTUBE_AVAILABILITY}video_cache_test", "1", ex=86400
                )

                # 2. Second call hits Tier 1 memory cache (no HTTP call)
                res2 = service.is_available_sync("video_cache_test")
                assert res2 is True
                assert mock_get.call_count == 1

                # 3. Clear Tier 1 memory cache -> hits Tier 2 Redis
                service.clear_caches()
                mock_redis.get.return_value = "1"
                res3 = service.is_available_sync("video_cache_test")
                assert res3 is True
                assert mock_get.call_count == 1  # Still no new HTTP call!

    def test_integrity_gate_blocks_unavailable_video(self):
        """Integrity gate must block clips whose YouTube video is 404."""
        clip = _make_valid_clip(video_id="video_404_test")
        with patch("services.first_person_pipeline.is_youtube_video_available", return_value=False):
            assert _passes_integrity_gate(clip) is False

    def test_hero_clip_selection_rejects_unavailable_video(self):
        """FirstPersonPipeline confident / weak match hero clip drops unavailable video."""
        # Create pipeline with mocked store, weaver, and availability
        mock_store = MagicMock()
        mock_weaver = MagicMock()
        mock_serene = MagicMock()
        mock_serene.assess_distress.return_value = None

        pipeline = FirstPersonPipeline(
            store=mock_store,
            weaver=mock_weaver,
            serene_mind_engine=mock_serene,
        )

        test_clip = _make_valid_clip(video_id="dead_hero_vid")
        mock_store.search_hybrid.return_value = [test_clip]

        # Mock availability returning False
        with patch("services.first_person_pipeline.is_youtube_video_available", return_value=False):
            res = pipeline.execute(
                query="What is the beautiful state?",
                query_dense_vector=[0.1] * 1024,
            )
            # Clip is quarantined and pipeline abstains honestly
            assert res.status == "abstained"
            assert len(res.citations) == 0
