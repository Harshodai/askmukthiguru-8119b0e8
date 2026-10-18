"""Unit and regression tests for Track 4: Batch Speaker Voice Verification & Attribution.

Covers:
1. `backend/ingest/verbatim/speaker_verify.py`:
   - `verify_clip_speaker`: acoustic confirmation logic, fail-closed guards, host 'O' rejection, competing teacher rejection.
   - `cluster_and_name_windows`: centroid naming, threshold floor, margin rule, small cluster abstention.
   - `relabel_turn_start_prefixes`: S1 turn-start prefix recovery without LLM.
2. `backend/services/attribution.py`:
   - `resolve_attribution_label` & `clean_wire_speaker`:
     - Explicit `speaker_verified is True` keeps teacher display name.
     - `speaker_verified is False` or `None` falls back to `shared in <channel>` or `unverified clip`.
     - Invariant L-FP-HYBRID-SCAFFOLD-1: never invent unverified credit.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ingest.verbatim.speaker_verify import (
    cluster_and_name_windows,
    relabel_turn_start_prefixes,
    verify_clip_speaker,
)
from services.attribution import clean_wire_speaker, resolve_attribution_label

# Synthetic 192-d normalized voiceprints for testing
np.random.seed(42)
_VP_P = np.zeros(192)
_VP_P[0] = 1.0
_VP_K = np.zeros(192)
_VP_K[1] = 1.0

_VOICEPRINTS = {"preethaji": _VP_P, "krishnaji": _VP_K}
_THRESHOLDS = {"P": 0.5721, "K": 0.5500}


def _dummy_speaker_result(
    win_lab: list[str], start: float = 0.0, hop: float = 1.0, ok: bool = True
) -> dict:
    return {
        "ok": ok,
        "t_centres": [start + i * hop for i in range(len(win_lab))],
        "win_lab": list(win_lab),
        "n_windows": len(win_lab),
    }


def _dummy_clip(
    speaker: str = "preethaji",
    start: float = 2.0,
    end: float = 6.0,
    text: str = "Suffering dissolves in awareness",
) -> dict:
    return {
        "speaker": speaker,
        "teacher_id": speaker,
        "start": start,
        "end": end,
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
    }


# ==============================================================================
# 1. Speaker Verification Acoustic Logic & Fail-Closed Guards
# ==============================================================================


class TestClipSpeakerVerification:
    def test_verify_passes_when_majority_windows_match_expected_teacher(self):
        res = _dummy_speaker_result(["P", "P", "P", "P", "P"])
        clip = _dummy_clip(speaker="preethaji", start=0.0, end=4.0)
        assert verify_clip_speaker(clip, res) is True

    def test_verify_passes_with_neutral_abstains_when_teacher_is_majority(self):
        res = _dummy_speaker_result(["K", "K", "K", "?", "?"])
        clip = _dummy_clip(speaker="krishnaji", start=0.0, end=4.0)
        assert verify_clip_speaker(clip, res) is True

    def test_verify_fails_closed_when_any_window_is_host_O(self):
        """Host speech ('O') in even one overlapping window must strictly fail closed."""
        res = _dummy_speaker_result(["P", "P", "O", "P", "P"])
        clip = _dummy_clip(speaker="preethaji", start=0.0, end=4.0)
        assert verify_clip_speaker(clip, res) is False

    def test_verify_fails_closed_when_competing_teacher_is_detected(self):
        """A window from the competing teacher ('K' for a Preethaji clip) fails closed."""
        res = _dummy_speaker_result(["P", "P", "K", "P"])
        clip = _dummy_clip(speaker="preethaji", start=0.0, end=3.0)
        assert verify_clip_speaker(clip, res) is False

    def test_verify_fails_closed_when_abstains_outnumber_confirmations(self):
        res = _dummy_speaker_result(["P", "?", "?", "?", "?"])
        clip = _dummy_clip(speaker="preethaji", start=0.0, end=4.0)
        assert verify_clip_speaker(clip, res) is False

    def test_verify_fails_closed_on_missing_or_corrupt_result(self):
        clip = _dummy_clip()
        assert verify_clip_speaker(clip, None) is False
        assert verify_clip_speaker(clip, {}) is False
        assert verify_clip_speaker(clip, {"ok": False}) is False
        assert verify_clip_speaker(clip, {"ok": True, "t_centres": [1.0], "win_lab": []}) is False


# ==============================================================================
# 2. Window Naming, Clustering, & Turn-Start Prefix Recovery
# ==============================================================================


class TestSpeakerClusteringAndPrefixRecovery:
    def test_cluster_and_name_windows_names_preethaji_correctly(self):
        t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        # 5 identical Preethaji embeddings (dimension 192)
        e = np.tile(_VP_P, (5, 1))
        res = cluster_and_name_windows(t, e, _VOICEPRINTS, _THRESHOLDS)
        assert res["n_windows"] == 5
        assert set(res["win_lab"]) == {"P"}
        assert res["time_share"]["teacher_P"] == 1.0

    def test_cluster_and_name_windows_names_krishnaji_correctly(self):
        t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        e = np.tile(_VP_K, (5, 1))
        res = cluster_and_name_windows(t, e, _VOICEPRINTS, _THRESHOLDS)
        assert res["n_windows"] == 5
        assert set(res["win_lab"]) == {"K"}
        assert res["time_share"]["teacher_K"] == 1.0

    def test_cluster_and_name_windows_abstains_on_small_clusters(self):
        # < 5 windows abstains as "?" regardless of cosine similarity
        t = np.array([0.0, 1.0, 2.0])
        e = np.tile(_VP_P, (3, 1))
        res = cluster_and_name_windows(t, e, _VOICEPRINTS, _THRESHOLDS)
        assert set(res["win_lab"]) == {"?"}

    def test_relabel_turn_start_prefixes_recovers_opening_words(self):
        """Turn-start prefix recovery: 'It[O] is[O] meditation[P]...' -> 'It[P] is[P] meditation[P]...'"""
        words = [
            {"w": "It", "start": 0.0, "end": 0.2, "spk": "O"},
            {"w": "is", "start": 0.2, "end": 0.4, "spk": "O"},
            {"w": "a", "start": 0.4, "end": 0.6, "spk": "P"},
            {"w": "sacred", "start": 0.6, "end": 1.0, "spk": "P"},
            {"w": "truth.", "start": 1.0, "end": 1.5, "spk": "P"},
        ]
        relabelled = relabel_turn_start_prefixes(words)
        assert [w["spk"] for w in relabelled] == ["P", "P", "P", "P", "P"]


# ==============================================================================
# 3. Attribution Layer & Binding Invariant L-FP-HYBRID-SCAFFOLD-1
# ==============================================================================


class TestAttributionLayerAudit:
    def test_verified_teacher_keeps_display_name(self):
        assert (
            resolve_attribution_label("Sri Krishnaji", speaker_verified=True, channel="Times Now")
            == "Sri Krishnaji"
        )
        assert (
            resolve_attribution_label("Sri Preethaji", speaker_verified=True, channel="Curly Tales")
            == "Sri Preethaji"
        )
        assert (
            clean_wire_speaker("Sri Krishnaji", speaker_verified=True, channel="Times Now")
            == "Sri Krishnaji"
        )

    def test_unverified_clip_on_known_channel_downgrades_to_shared_in_channel(self):
        """Unverified teacher clip on any channel MUST downgrade to 'shared in <channel>'."""
        assert (
            resolve_attribution_label("Sri Krishnaji", speaker_verified=False, channel="Times Now")
            == "shared in Times Now"
        )
        assert (
            resolve_attribution_label("Sri Preethaji", speaker_verified=None, channel="Curly Tales")
            == "shared in Curly Tales"
        )
        assert (
            resolve_attribution_label(
                "Sri Preethaji", speaker_verified=None, channel="Sri Preethaji & Sri Krishnaji"
            )
            == "shared in Sri Preethaji & Sri Krishnaji"
        )

    def test_unverified_clip_without_channel_downgrades_to_unverified_clip(self):
        assert (
            resolve_attribution_label("Sri Krishnaji", speaker_verified=False, channel=None)
            == "unverified clip"
        )
        assert (
            resolve_attribution_label("Sri Preethaji", speaker_verified=None, channel="")
            == "unverified clip"
        )

    def test_clean_wire_speaker_never_emits_bare_teacher_name_for_unverified(self):
        """On the public wire, an unverified clip must NEVER emit bare 'Sri Krishnaji'."""
        assert (
            clean_wire_speaker("Sri Krishnaji", speaker_verified=False, channel="Times Now")
            == "shared in Times Now"
        )
        assert (
            clean_wire_speaker("Sri Preethaji", speaker_verified=None, channel=None)
            == "unverified clip"
        )
        assert clean_wire_speaker("Unknown") is None
        assert clean_wire_speaker("Unknown Channel") is None

    def test_non_teacher_speaker_passes_through_resolve_attribution_label(self):
        """resolve_attribution_label preserves non-teacher speakers like Host."""
        assert (
            resolve_attribution_label("Host", speaker_verified=None, channel="Times Now") == "Host"
        )
        # On the wire, unverified non-teacher is omitted (None) so UI does not surface raw text
        assert clean_wire_speaker("Host", speaker_verified=None, channel="Times Now") is None
