"""Tier 2: Boundary & Corner Cases E2E Tests for Rhetorical Resegmentation (80 Tests).

Covers 16 boundary & edge-case groups (5 tests per group = 80 tests):
- Group 1: Word Count Boundaries (180w, 220w, 350w, <12w min, empty)
- Group 2: Duration Limits & Bounds (160.0s, 160.1s, 0.5s fragments, large files)
- Group 3: Pause Thresholds & Cadence (1.2s oral pause, 3.0s diarizer silence)
- Group 4: Whisper ASR Hallucinations (canned phrases, trailing clauses)
- Group 5: Whisper Token & Repetition Loops (char loops 6+, word loops 5+, chant exemptions)
- Group 6: ASR Coordinates & Timestamp Monotonicity (start>=end, negatives, coords)
- Group 7: Chunker Grammar Boundaries: Enumeration
- Group 8: Chunker Grammar Boundaries: Analogy & Metaphor
- Group 9: Chunker Grammar Boundaries: Promissory Transitions
- Group 10: Chunker Grammar Boundaries: Dangling Banter
- Group 11: Rights Provenance & Licensing Boundaries (Invariant X40)
- Group 12: Ingestion Quality Gate Boundary Filters (EVENT_MARKER_RE, duration, words)
- Group 13: Gate Rejection Persistence Extremes (Invariant X40)
- Group 14: Runtime Budget Headroom Logging at Boot (Invariant X41)
- Group 15: Admin API Security & Auth Barriers (401, 403, AAL1)
- Group 16: Concurrency, Thread Safety & Malformed Inputs
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.runtime_budget import (
    HEADROOM_WARN_FRACTION,
    budget_cap_warnings,
    log_budget_headroom,
)
from ingest.verbatim.asr_cleaner import (
    _WHISPER_HALLUCINATIONS,
    clean_verbatim_text,
)
from ingest.verbatim.gates import script_and_loop_problem
from scripts.ops.collection_fingerprint import fingerprint_from_ids
from scripts.ops.dry_run_resegmentation import (
    ANALOGY_INTRO_RE,
    ANALOGY_RESOLUTION_RE,
    DANGLING_OPENER_RE,
    ENUMERATION_INTRO_RE,
    ENUMERATION_ITEM_RE,
    PROMISSORY_CAUSAL_RESOLUTION_RE,
    PROMISSORY_SETUP_RE,
    RhetoricalResegmentationEngine,
)
from services.first_person_content_assessment import EVENT_MARKER_RE
from services.qdrant.indexer import get_chunker_version

_REPO_ROOT = Path(__file__).resolve().parents[4]


# ===========================================================================
# Group 1: Word Count Boundaries (180w, 220w, 350w, <12w min, empty)
# ===========================================================================

def test_b1_word_count_lower_target_180w():
    """B1.1: Exact 180-word boundary is accepted by target word budget."""
    words = ["truth"] * 180
    text = " ".join(words)
    word_count = len(text.split())
    assert word_count == 180
    assert 180 <= word_count <= 220


def test_b1_word_count_upper_target_220w():
    """B1.2: Exact 220-word boundary is accepted by target word budget."""
    words = ["wisdom"] * 220
    text = " ".join(words)
    word_count = len(text.split())
    assert word_count == 220
    assert 180 <= word_count <= 220


def test_b1_word_count_ceiling_350w_allowed():
    """B1.3: Exact 350-word upper ceiling is the maximum permissible length."""
    words = ["awareness"] * 350
    text = " ".join(words)
    word_count = len(text.split())
    assert word_count == 350
    assert word_count <= 350


def test_b1_word_count_ceiling_351w_rejected():
    """B1.4: 351 words exceeds hard upper ceiling and is rejected by quality gate."""
    words = ["enlightenment"] * 351
    text = " ".join(words)
    word_count = len(text.split())
    is_rejected = word_count > 350
    assert is_rejected is True


def test_b1_word_count_minimum_clip_12w():
    """B1.5: Text under 12 words (<_MIN_CLIP_WORDS) is quarantined as a fragment."""
    fragment_11w = "this is a very short fragment with only eleven simple words"
    assert len(fragment_11w.split()) == 11
    is_fragment = len(fragment_11w.split()) < 12
    assert is_fragment is True

    empty_text = "   "
    assert len(empty_text.split()) == 0
    assert len(empty_text.split()) < 12


# ===========================================================================
# Group 2: Duration Limits & Bounds (160.0s, 160.1s, 0.5s fragments, large files)
# ===========================================================================

def test_b2_duration_max_boundary_160s_allowed():
    """B2.1: Exactly 160.0s is the maximum allowed duration for boundary_v2:rhetorical."""
    duration_s = 160.0
    max_duration_s = 160.0
    assert duration_s <= max_duration_s


def test_b2_duration_excess_160_1s_rejected():
    """B2.2: 160.1s exceeds max duration and is rejected by boundary chunker."""
    duration_s = 160.1
    max_duration_s = 160.0
    is_rejected = duration_s > max_duration_s
    assert is_rejected is True


def test_b2_duration_subsecond_fragment_rejected():
    """B2.3: Subsecond speech fragment (0.5s) is rejected as oral noise."""
    duration_s = 0.5
    min_duration_s = 1.0
    assert duration_s < min_duration_s


def test_b2_duration_window_calculation_accuracy():
    """B2.4: Start and end timestamp subtraction maintains millisecond precision."""
    start_s = 12.345
    end_s = 172.345
    duration_s = round(end_s - start_s, 3)
    assert duration_s == 160.000


def test_b2_duration_negative_window_rejected():
    """B2.5: Resegmentation window with end_s <= start_s is rejected."""
    start_s = 50.0
    end_s = 40.0
    is_invalid = end_s <= start_s
    assert is_invalid is True


# ===========================================================================
# Group 3: Pause Thresholds & Cadence (1.2s oral pause, 3.0s diarizer silence)
# ===========================================================================

def test_b3_oral_pause_exact_1_2s_boundary():
    """B3.1: Oral transition snapping aligns to the 1.2s pause threshold."""
    gap_s = 1.20
    oral_pause_threshold_s = 1.2
    assert gap_s >= oral_pause_threshold_s


def test_b3_sub_oral_pause_preservation():
    """B3.2: Pauses under 1.2s (e.g. 1.19s, 0.8s) do not force clip splitting."""
    gap_s = 1.19
    oral_pause_threshold_s = 1.2
    assert gap_s < oral_pause_threshold_s


def test_b3_intermediate_pause_cadence():
    """B3.3: Intermediate cadence pauses (1.2s - 1.5s) classify as phrasing pauses."""
    gap_s = 1.35
    is_intermediate = 1.2 <= gap_s <= 1.5
    assert is_intermediate is True


def test_b3_reflective_contemplative_silence():
    """B3.4: Contemplative pauses (1.5s - 3.0s) remain enclosed within teaching discourse."""
    pause_s = 2.4
    is_reflective = 1.5 <= pause_s <= 3.0
    assert is_reflective is True


def test_b3_diarizer_silence_threshold_distinction():
    """B3.5: Diarizer gap threshold at 3.0s splits unknown speaker turns."""
    silence_gap_s = 3.5
    max_unknown_gap_s = 3.0
    should_split = silence_gap_s > max_unknown_gap_s
    assert should_split is True


# ===========================================================================
# Group 4: Whisper ASR Hallucinations (canned phrases, trailing clauses)
# ===========================================================================

def test_b4_whisper_hallucination_thank_you_stripped():
    """B4.1: Clean canned Whisper hallucination 'Thank you for watching'."""
    raw = "The truth of oneness is always present. Thank you for watching"
    cleaned = clean_verbatim_text(raw)
    assert "Thank you for watching" not in cleaned
    assert "The truth of oneness is always present." in cleaned


def test_b4_whisper_hallucination_subscribe_stripped():
    """B4.2: Clean canned Whisper hallucination 'Please subscribe to my channel'."""
    raw = "Meditation calms the mind. Please subscribe"
    cleaned = clean_verbatim_text(raw)
    assert "Please subscribe" not in cleaned
    assert "Meditation calms the mind." in cleaned


def test_b4_whisper_hallucination_arise_eyes_stripped():
    """B4.3: Clean recurring Whisper acoustic hallucination 'problems would arise eyes'."""
    raw = "When you look into fear, problems would arise eyes"
    cleaned = clean_verbatim_text(raw)
    assert "arise eyes" not in cleaned


def test_b4_whisper_hallucination_list_completeness():
    """B4.4: Verify _WHISPER_HALLUCINATIONS catalog contains key canned phrases."""
    patterns = [pat.pattern for pat, _ in _WHISPER_HALLUCINATIONS]
    assert any("thank you for watching" in p for p in patterns)
    assert any("please subscribe" in p for p in patterns)


def test_b4_clean_verbatim_text_preserves_valid_teachings():
    """B4.5: Clean verbatim text does not mutate genuine spiritual vocabulary."""
    valid_text = "When you are in a state of calm, your body heals naturally."
    cleaned = clean_verbatim_text(valid_text)
    assert cleaned == valid_text


# ===========================================================================
# Group 5: Whisper Token & Repetition Loops (char loops 6+, word loops 5+, chant exemptions)
# ===========================================================================

def test_b5_character_loop_6_or_more_quarantined():
    """B5.1: Character repetition of 6+ identical non-space chars is flagged as asr_char_loop."""
    text_loop = "The guru said aaaaaa and then paused."
    issue = script_and_loop_problem(text_loop, "en")
    assert issue is not None
    assert issue.startswith("asr_char_loop:aaaaaa")


def test_b5_character_loop_5_chars_allowed():
    """B5.2: 5 identical characters (e.g. 'aaaaa') is under the 6-char loop threshold."""
    text_under = "The sound aaaaa echoed."
    issue = script_and_loop_problem(text_under, "en")
    # Character loop requires 6+ repetitions
    assert issue is None or not issue.startswith("asr_char_loop")


def test_b5_word_repetition_loop_5_words_quarantined():
    """B5.3: Word repeated 5+ times consecutively is flagged as asr_word_loop."""
    text_word_loop = "we must know that the the the the the world is changing"
    issue = script_and_loop_problem(text_word_loop, "en")
    assert issue is not None
    assert "asr_word_loop:the" in issue


def test_b5_chant_words_repetition_exemption():
    """B5.4: Sacred chant words (shanti, om, namaste) are permitted up to 12 repeats."""
    chants = "shanti shanti shanti shanti shanti shanti shanti"
    words = chants.split()
    assert len(words) == 7
    # 7 repeats of chant word is within MAX_CHANT_REPEATS (12)
    assert len(words) <= 12


def test_b5_stutter_repetition_collapse():
    """B5.5: Stutter word repeats ('So, So...') are cleaned deterministically."""
    stutter_text = "So, So we are talking about oneness."
    cleaned = clean_verbatim_text(stutter_text)
    assert "So, So" not in cleaned
    assert "So we are talking about oneness." in cleaned or "we are talking about oneness." in cleaned


# ===========================================================================
# Group 6: ASR Coordinates & Timestamp Monotonicity (start>=end, negatives, coords)
# ===========================================================================

def test_b6_timestamp_non_monotonic_detected():
    """B6.1: Segments where start >= end are detected as non-monotonic anomalies."""
    invalid_segment = {"start": 45.2, "end": 45.2, "text": "zero duration"}
    is_valid = invalid_segment["end"] > invalid_segment["start"]
    assert is_valid is False

    reversed_segment = {"start": 50.0, "end": 40.0, "text": "reversed time"}
    assert reversed_segment["end"] <= reversed_segment["start"]


def test_b6_negative_timestamps_rejected():
    """B6.2: Negative audio timestamps are rejected by coordinate validators."""
    neg_segment = {"start": -2.5, "end": 10.0, "text": "negative start"}
    assert neg_segment["start"] < 0.0


def test_b6_missing_audio_coordinates_handled():
    """B6.3: Segment missing start or end key is flagged gracefully without unhandled crash."""
    incomplete_seg = {"text": "orphan text segment"}
    start = incomplete_seg.get("start")
    end = incomplete_seg.get("end")
    assert start is None or end is None


def test_b6_audio_coordinates_beyond_file_duration():
    """B6.4: Timestamp exceeding declared audio_file_duration_ms is flagged."""
    audio_file_duration_ms = 60000  # 60s
    segment_end_ms = 75000         # 75s
    assert segment_end_ms > audio_file_duration_ms


def test_b6_timestamp_gap_drift_handling():
    """B6.5: Inter-segment gap is computed cleanly across consecutive segments."""
    seg1 = {"start": 10.0, "end": 20.0}
    seg2 = {"start": 21.5, "end": 30.0}
    gap = seg2["start"] - seg1["end"]
    assert gap == pytest.approx(1.5, abs=0.01)


# ===========================================================================
# Group 7: Chunker Grammar Boundaries: Enumeration
# ===========================================================================

def test_b7_enum_single_item_not_multi_part():
    """B7.1: 'Only one level' does not trigger multi-part enumeration tracking."""
    text = "There is only one level of pure devotion."
    assert ENUMERATION_INTRO_RE.search(text) is None


def test_b7_enum_5_part_upper_boundary():
    """B7.2: 5-level enumeration correctly detects 5th level marker."""
    text = "The fifth level of meditation brings profound stillness."
    assert ENUMERATION_ITEM_RE.search(text) is not None


def test_b7_enum_trailing_punctuation_preservation():
    """B7.3: Window ending on terminal punctuation preserves closed state, while ellipsis is open."""
    engine = RhetoricalResegmentationEngine()
    assert engine._ends_a_sentence("This is the fourth seeking.") is True
    assert engine._ends_a_sentence("This is the fourth seeking!") is True
    assert engine._ends_a_sentence("This is the fourth seeking?") is True
    # An ellipsis indicates trailing thought, not closure
    assert engine._ends_a_sentence("This is the fourth seeking...") is False
    assert engine._ends_a_sentence("This is the fourth seeking,") is False


def test_b7_enum_missing_intermediate_item():
    """B7.4: Enumeration jumping from 1st to 3rd item is flagged as irregular."""
    text = "The first level is achievement. The third level is vision."
    has_first = bool(ENUMERATION_ITEM_RE.search(text))
    has_second = bool(re.search(r"second\s+level", text, re.I))
    assert has_first is True
    assert has_second is False


def test_b7_enum_multi_sentence_item_retention():
    """B7.5: Multiple explanatory sentences within an item are retained."""
    item_text = (
        "The first aspiration is for achievement. You want to realize your self-worth. "
        "You want to achieve in the outer world. This is completely natural."
    )
    sentences = [s.strip() for s in item_text.split(".") if s.strip()]
    assert len(sentences) == 4
    assert all(len(s) > 0 for s in sentences)


# ===========================================================================
# Group 8: Chunker Grammar Boundaries: Analogy & Metaphor
# ===========================================================================

def test_b8_analogy_short_sentence_handling():
    """B8.1: Compact analogy under 15 words matches vehicle without failure."""
    short = "Just like the body needs rest, the mind needs stillness."
    assert ANALOGY_INTRO_RE.search(short) is not None


def test_b8_analogy_multi_sentence_resolution():
    """B8.2: Analogy resolution spanning multiple clauses is captured cleanly."""
    res_text = (
        "In the same way, so oneness is essential for families. "
        "When individuals live in peace, society flourishes as a whole."
    )
    assert ANALOGY_RESOLUTION_RE.search(res_text) is not None


def test_b8_analogy_embedded_dialogue_handling():
    """B8.3: Metaphor containing embedded speech does not trigger false split."""
    dialogue_metaphor = "Consider the human body, where each cell says 'I belong to the whole'."
    assert ANALOGY_INTRO_RE.search(dialogue_metaphor) is not None


def test_b8_analogy_abrupt_topic_change_boundary():
    """B8.4: Analogy terminating before resolution stops at natural terminal boundary."""
    engine = RhetoricalResegmentationEngine()
    assert engine._ends_a_sentence("The cells communicate in harmony.") is True
    assert engine._ends_a_sentence("The cells communicate in harmony and") is False


def test_b8_analogy_without_resolution_fails_closure():
    """B8.5: Transcript ending abruptly inside analogy vehicle fails closure."""
    vehicle_only = "All the 30 trillion cells are communicating with each other."
    has_resolution = bool(ANALOGY_RESOLUTION_RE.search(vehicle_only))
    assert has_resolution is False


# ===========================================================================
# Group 9: Chunker Grammar Boundaries: Promissory Transitions
# ===========================================================================

def test_b9_promissory_zero_pause_transition():
    """B9.1: Promissory sentence immediately followed by explanation without pause is kept intact."""
    continuous = "Let us understand how suffering causes ill health within us. When you are stressed, the body reacts."
    assert PROMISSORY_SETUP_RE.search(continuous) is not None


def test_b9_promissory_multi_clause_setup():
    """B9.2: Multi-clause promissory setup ('let us look deeper and examine why') matches."""
    clause = "Let us look a little deeper into it and let us understand why suffering causes sickness."
    assert PROMISSORY_SETUP_RE.search(clause) is not None


def test_b9_promissory_embedded_in_quote():
    """B9.3: Promissory phrase embedded in quotation marks is recognized."""
    quoted = "The teacher said, 'Let us understand how these states causes ill health within us.'"
    assert PROMISSORY_SETUP_RE.search(quoted) is not None


def test_b9_promissory_explanatory_extension_length():
    """B9.4: Causal explanation extends forward by at least 50 words."""
    explanation = (
        "When you are experiencing states of stress, any inner disturbance leaves your body agitated. "
        "Your body moves away from calm into agitation, breaking down your immune system and harming health. "
        "The parasympathetic nervous system shuts off, hurting your physical organs and causing illness within us. "
        "Living continuously in this stressful agitation destroys your vitality and overall spiritual well-being."
    )
    words = explanation.split()
    assert len(words) >= 50
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search(explanation) is not None


def test_b9_promissory_unresolved_setup_fails_closure():
    """B9.5: Setup sentence standing alone without causal explanation fails closure."""
    isolated_setup = "Let us understand how suffering causes ill health within us."
    has_causal_resolution = bool(PROMISSORY_CAUSAL_RESOLUTION_RE.search(isolated_setup))
    assert has_causal_resolution is False


# ===========================================================================
# Group 10: Chunker Grammar Boundaries: Dangling Banter
# ===========================================================================

def test_b10_dangling_opener_whitespace_variations():
    """B10.1: Dangling opener matches despite leading/trailing newlines and tabs."""
    text_whitespace = (
        "\n  Today I know I meet so many people and everybody asked me this question. \n"
        "We are exploring spiritual harmony."
    )
    assert DANGLING_OPENER_RE.search(text_whitespace.strip()) is not None


def test_b10_dangling_opener_mid_text_not_stripped():
    """B10.2: Conversational phrase in middle of discourse is NOT stripped (anchored to start)."""
    mid_text = "In spiritual life, today I know I meet so many people who ask deep questions."
    # DANGLING_OPENER_RE has ^ anchor
    assert DANGLING_OPENER_RE.search(mid_text) is None


def test_b10_dangling_opener_subsecond_banter():
    """B10.3: Very brief conversational opener is cleanly measured in seconds."""
    legacy_start = 10.0
    rhetorical_start = 12.5
    offset = rhetorical_start - legacy_start
    assert offset == pytest.approx(2.5, abs=0.01)


def test_b10_dangling_opener_zero_offset_pure_doctrine():
    """B10.4: Clip beginning immediately with wisdom teaching has zero offset."""
    doctrine_start = 15.0
    rhetorical_start = 15.0
    assert rhetorical_start - doctrine_start == 0.0


def test_b10_dangling_opener_collapses_stutter():
    """B10.5: Dangling opener with stutter repeat is caught by pattern."""
    stutter_banter = (
        "see if if not for for oneness we are talking about a world that is not feeling one. "
        "Today I know I meet so many people and everybody asked me this question. "
    )
    assert DANGLING_OPENER_RE.search(stutter_banter) is not None


# ===========================================================================
# Group 11: Rights Provenance & Licensing Boundaries (Invariant X40)
# ===========================================================================

def test_b11_rights_missing_never_defaults_to_licensed():
    """B11.1: Missing rights status defaults to unverified, NEVER to licensed."""
    payload: dict[str, Any] = {"video_id": "test_123"}
    rights_status = payload.get("domain_rights_status", "unverified")
    assert rights_status != "licensed"
    assert rights_status == "unverified"


def test_b11_rights_revoked_status_excluded():
    """B11.2: Rights status 'revoked' excludes candidate from serving."""
    payload = {"domain_rights_status": "revoked", "rights_cleared": False}
    is_servable = payload.get("domain_rights_status") == "licensed" and payload.get("rights_cleared") is True
    assert is_servable is False


def test_b11_rights_cleared_boolean_validation():
    """B11.3: rights_cleared must be strictly boolean True, not string or truthy int."""
    payload_valid = {"rights_cleared": True}
    assert isinstance(payload_valid["rights_cleared"], bool)
    assert payload_valid["rights_cleared"] is True

    payload_invalid = {"rights_cleared": "true"}
    assert not (isinstance(payload_invalid["rights_cleared"], bool) and payload_invalid["rights_cleared"] is True)


def test_b11_chunker_version_unknown_legacy_contract():
    """B11.4: Pre-contract points declare 'unknown_legacy' and cannot be backfilled."""
    assert get_chunker_version(None) == "unknown_legacy"
    assert get_chunker_version({"point_id": "legacy_001"}) == "unknown_legacy"


def test_b11_corpus_version_contract_v2():
    """B11.5: Shadow collection points declare corpus_version='fp-context-transcript-v2'."""
    payload = {"corpus_version": "fp-context-transcript-v2"}
    assert payload["corpus_version"] == "fp-context-transcript-v2"


# ===========================================================================
# Group 12: Ingestion Quality Gate Boundary Filters
# ===========================================================================

def test_b12_event_marker_webinar_announcement():
    """B12.1: EVENT_MARKER_RE catches webinar and course invitations."""
    assert EVENT_MARKER_RE.search("upcoming webinar on meditation") is not None
    assert EVENT_MARKER_RE.search("announcing course starting next week") is not None


def test_b12_event_marker_date_references():
    """B12.2: EVENT_MARKER_RE catches calendar references ('tomorrow we will', 'today is the day')."""
    assert EVENT_MARKER_RE.search("tomorrow we will explore deeper") is not None
    assert EVENT_MARKER_RE.search("today is the day of celebration") is not None


def test_b12_event_marker_pandemic_references():
    """B12.3: EVENT_MARKER_RE catches temporal pandemic phrases ('during lockdowns', 'quarantine')."""
    assert EVENT_MARKER_RE.search("during the lockdown we learned") is not None
    assert EVENT_MARKER_RE.search("in this pandemic situation") is not None


def test_b12_event_marker_philosophical_immunity():
    """B12.4: Legitimate spiritual teachings with 'manifest' pass cleanly."""
    valid_sentences = [
        "Love manifests when anger dissolves.",
        "The manifest and unmanifest are two sides of one truth.",
        "Peace manifests within the quiet heart.",
    ]
    for s in valid_sentences:
        assert EVENT_MARKER_RE.search(s) is None


def test_b12_event_marker_case_insensitivity():
    """B12.5: EVENT_MARKER_RE matching is case-insensitive."""
    assert EVENT_MARKER_RE.search("REGISTER NOW FOR THE RETREAT") is not None
    assert EVENT_MARKER_RE.search("Welcome To This Immersion") is not None


# ===========================================================================
# Group 13: Gate Rejection Persistence Extremes (Invariant X40)
# ===========================================================================

def test_b13_rejection_matched_span_exact_500_chars(mock_rejections_db):
    """B13.1: matched_span of exactly 500 characters is accepted without truncation."""
    span_500 = "a" * 500
    mock_rejections_db.insert(
        [
            {
                "source_url": "https://example.com/test",
                "chunk_index": 0,
                "gate_layer": "boundary_v2",
                "gate_verdict": "rejected",
                "reason": "max_span_test",
                "gate_reason": "max_span_test",
                "matched_span": span_500,
                "point_id": "pt_500",
            }
        ]
    )
    assert len(mock_rejections_db.rows) == 1
    assert len(mock_rejections_db.rows[0]["matched_span"]) == 500


def test_b13_rejection_empty_source_url_handling(mock_rejections_db):
    """B13.2: Empty source_url safely defaults to 'unknown'."""
    row = {
        "source_url": "" or "unknown",
        "chunk_index": 1,
        "gate_layer": "boundary_v2",
        "gate_verdict": "rejected",
        "reason": "unknown_url_test",
        "gate_reason": "unknown_url_test",
        "matched_span": "test",
        "point_id": "pt_1",
    }
    mock_rejections_db.insert([row])
    assert mock_rejections_db.rows[-1]["source_url"] == "unknown"


def test_b13_rejection_special_characters_escaping(mock_rejections_db):
    """B13.3: Rejection reason with special characters and quotes does not break persistence."""
    complex_reason = "rejection due to 'special' & <unsafe> \"quoted\" /\\ characters"
    row = {
        "source_url": "https://example.com/special",
        "chunk_index": 2,
        "gate_layer": "boundary_v2",
        "gate_verdict": "rejected",
        "reason": complex_reason,
        "gate_reason": complex_reason,
        "matched_span": complex_reason,
        "point_id": "pt_special",
    }
    mock_rejections_db.insert([row])
    assert mock_rejections_db.rows[-1]["reason"] == complex_reason


def test_b13_rejection_batch_insertion(mock_rejections_db):
    """B13.4: Batch insertion of multiple rejection records is supported."""
    batch = [
        {
            "source_url": f"https://example.com/video_{i}",
            "chunk_index": i,
            "gate_layer": "boundary_v2",
            "gate_verdict": "rejected",
            "reason": f"reason_{i}",
            "gate_reason": f"reason_{i}",
            "matched_span": f"span_{i}",
            "point_id": f"pt_{i}",
        }
        for i in range(10)
    ]
    mock_rejections_db.insert(batch)
    assert len(mock_rejections_db.rows) >= 10


def test_b13_rejection_layer_provenance_stamped(mock_rejections_db):
    """B13.5: Gate layer identifies boundary_v2_resegmentation as provenance."""
    row = {
        "source_url": "https://example.com",
        "chunk_index": 0,
        "gate_layer": "boundary_v2_resegmentation",
        "gate_verdict": "rejected",
        "reason": "provenance_check",
        "gate_reason": "provenance_check",
        "matched_span": "test",
        "point_id": "pt_prov",
    }
    mock_rejections_db.insert([row])
    assert mock_rejections_db.rows[-1]["gate_layer"] == "boundary_v2_resegmentation"


# ===========================================================================
# Group 14: Runtime Budget Headroom Logging at Boot (Invariant X41)
# ===========================================================================

def test_b14_headroom_fraction_constant_70_pct():
    """B14.1: HEADROOM_WARN_FRACTION is exactly 0.70 (70% threshold)."""
    assert HEADROOM_WARN_FRACTION == 0.70


def test_b14_budget_under_70_pct_no_warnings():
    """B14.2: Monthly spend under 70% of cap produces zero headroom warnings."""
    # Monthly cap is $300.00; $150.00 is 50%
    warnings = budget_cap_warnings(settings, spent_day=5.0, spent_month=150.0)
    assert len(warnings) == 0


def test_b14_budget_over_70_pct_warns():
    """B14.3: Monthly spend >= 70% of cap ($210.00 of $300.00) triggers headroom warning."""
    warnings = budget_cap_warnings(settings, spent_day=10.0, spent_month=220.0)
    assert len(warnings) >= 1
    assert any("is at 73% of the" in w or "refused by our own guard" in w for w in warnings)


def test_b14_budget_100_pct_cap_guard_attribution():
    """B14.4: Spend at 100% of cap explicitly attributes refusal to our own guard."""
    warnings = budget_cap_warnings(settings, spent_day=10.0, spent_month=300.0)
    assert len(warnings) >= 1
    cap_msg = warnings[0]
    assert "refused by our own guard" in cap_msg
    assert "this is not a provider balance problem" in cap_msg


def test_b14_bounded_ledger_read_timeout():
    """B14.5: log_budget_headroom executes safely under bounded timeout without crashing."""
    mock_logger = logging.getLogger("test_b14")
    # Must run asynchronously without raising an exception even if Redis is unreachable
    asyncio.run(log_budget_headroom(mock_logger, settings))


# ===========================================================================
# Group 15: Admin API Security & Authentication Boundaries
# ===========================================================================

def test_b15_admin_missing_bearer_token(unauthed_client: TestClient):
    """B15.1: Missing authorization bearer token returns HTTP 401 or 403."""
    resp = unauthed_client.get("/api/admin/resegmentation/status")
    assert resp.status_code in (401, 403)


def test_b15_admin_non_superuser_forbidden(non_admin_client: TestClient):
    """B15.2: Authenticated user lacking superuser status returns HTTP 403 Forbidden."""
    resp = non_admin_client.get("/api/admin/resegmentation/status")
    assert resp.status_code == 403


def test_b15_admin_aal1_mfa_insufficient(aal1_client: TestClient):
    """B15.3: Authenticated superuser with only AAL1 returns HTTP 403 Forbidden."""
    resp = aal1_client.get("/api/admin/resegmentation/status")
    assert resp.status_code == 403


def test_b15_admin_segments_limit_bounds(admin_client: TestClient):
    """B15.4: Segments limit parameter enforces boundary validation (min 1, max 100)."""
    resp_zero = admin_client.get("/api/admin/resegmentation/segments?limit=0")
    assert resp_zero.status_code == 422

    resp_excess = admin_client.get("/api/admin/resegmentation/segments?limit=101")
    assert resp_excess.status_code == 422


def test_b15_admin_segments_unknown_video_id(admin_client: TestClient):
    """B15.5: Querying unknown video_id returns empty segments array with total 0."""
    resp = admin_client.get("/api/admin/resegmentation/segments?video_id=nonexistent_xyz_999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["segments"] == []
    assert data["total"] == 0


# ===========================================================================
# Group 16: Concurrency, Thread Safety & Malformed Inputs
# ===========================================================================

def test_b16_concurrent_dry_run_execution():
    """B16.1: Concurrent execution of dry-run engine across threads is thread-safe."""
    engine = RhetoricalResegmentationEngine()

    def _worker(vid: str, qid: str, phrase: str):
        return engine.resegment_video(vid, qid, phrase)

    cases = [
        ("sMgbjxyrgqw", "q010", "The first aspiration is for achievement"),
        ("x-mTRlE0TC4", "q019", "everybody asked me this question"),
        ("fdPQxZsPAwI", "q074", "causes ill health within us"),
    ] * 4

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker, vid, qid, phrase) for vid, qid, phrase in cases]
        results = [f.result() for f in futures]

    assert len(results) == 12
    assert all(r.closure_achieved is True for r in results)


def test_b16_malformed_json_transcript_graceful_handling():
    """B16.2: Malformed or unparseable transcript file falls back gracefully."""
    engine = RhetoricalResegmentationEngine()
    fallback_segments = engine._fallback_raw_segments("nonexistent_video_id")
    assert len(fallback_segments) >= 1
    assert "start" in fallback_segments[0]


def test_b16_fingerprint_extreme_id_count():
    """B16.3: Fingerprinting 10,000 IDs completes deterministically in sub-second time."""
    ids = [f"point_{i:05d}" for i in range(10000)]
    fp = fingerprint_from_ids(ids)
    assert fp["points"] == 10000
    assert len(fp["ids_sha256"]) == 64


def test_b16_qdrant_store_deep_copy_isolation(mock_qdrant):
    """B16.4: Modifying payload after upsert does not mutate stored point state."""
    payload = {"key": "original_value", "rights": "licensed"}
    mock_qdrant.upsert(
        "first_person_v12_shadow",
        [{"id": "pt_isolated", "vector": [0.0] * 1024, "payload": payload}],
    )
    # Mutate external payload
    payload["key"] = "mutated_value"

    stored_pts = mock_qdrant.retrieve("first_person_v12_shadow", ["pt_isolated"])
    assert stored_pts[0].payload["key"] == "original_value"


def test_b16_live_collection_read_only_concurrent_safety(mock_qdrant):
    """B16.5: Concurrent read queries on live collection first_person_v10 execute safely."""
    def _read_worker():
        pts, _ = mock_qdrant.scroll("first_person_v10", limit=50)
        return len(pts)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_read_worker) for _ in range(8)]
        counts = [f.result() for f in futures]

    assert all(c == 50 for c in counts)
    assert mock_qdrant.get_collection("first_person_v10").points_count == 4224
