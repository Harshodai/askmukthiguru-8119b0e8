#!/usr/bin/env python3
"""Statistical Analysis of Oral Cadence and Acoustic Architecture.

Analyzes Sri Krishnaji and Sri Preethaji's speech patterns, pacing, pauses,
and rhetorical structure across the 657 `whisper_segments.json` files.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SegmentData:
    segment_id: str
    start: float
    end: float
    duration: float
    text: str
    word_count: int
    wpm: float
    avg_logprob: float
    no_speech_prob: float
    is_question: bool
    pause_after: Optional[float] = None


@dataclass
class VideoAnalysis:
    video_id: str
    title: str
    speaker_tag: str
    category: str
    total_duration_sec: float
    speech_duration_sec: float
    silence_duration_sec: float
    silence_percentage: float
    total_words: int
    total_segments: int
    pure_wpm: float  # total_words / (speech_duration / 60)
    effective_wpm: float  # total_words / (total_duration / 60)
    # Pause tiers
    pause_count_total: int
    pauses_sub_0_5s: int
    pauses_micro_0_5_to_1_2s: int  # breath & phrasing
    pauses_reflective_1_5_to_3_0s: int  # reflection / space after insight
    pauses_contemplative_gt_3_0s: int  # deep contemplative silence
    pauses_intermediate_1_2_to_1_5s: int
    pause_mean: float
    pause_median: float
    pause_p75: float
    pause_p90: float
    pause_max: float
    # Sentence/Segment length
    words_mean: float
    words_median: float
    words_p10: float
    words_p25: float
    words_p75: float
    words_p90: float
    words_max: int
    short_segments_pct: float  # <= 8 words
    medium_segments_pct: float  # 9-18 words
    long_segments_pct: float  # >= 19 words
    alternation_rate: float  # Frequency of Short -> Long or Long -> Short transitions
    # Questions & Rhetorical dynamics
    question_count: int
    question_rate_per_100w: float
    mean_pause_after_question: float
    mean_pause_after_statement: float
    median_pause_after_question: float
    median_pause_after_statement: float
    question_pause_ratio: float  # post-question pause / post-statement pause
    # Direct address
    direct_address_count: int
    direct_address_rate_per_100w: float


_QUESTION_RE = re.compile(
    r"\?|\b(?:can you|do you see|have you noticed|what happens|why do you|who is|is it not|are you)\b",
    re.IGNORECASE,
)
_DIRECT_ADDRESS_RE = re.compile(
    r"\b(?:you|your|yourself|notice|look|observe|see|listen|let us|feel)\b",
    re.IGNORECASE,
)


def classify_category(title: str, duration: float) -> str:
    title_lower = title.lower()
    if any(w in title_lower for w in ["meditation", "sadhana", "mantra", "tapas", "peace meditation"]):
        return "meditation"
    if any(w in title_lower for w in ["festival", "darshan", "celebration", "satsang"]):
        return "festival_satsang"
    if any(w in title_lower for w in ["interview", "frankly speaking", "conversation"]):
        return "dialogue_interview"
    if duration < 180:
        return "short_upadesha"
    return "discourse"


def classify_speaker(title: str, transcript_sample: str) -> str:
    title_lower = title.lower()
    if "preethaji" in title_lower and "krishnaji" not in title_lower:
        return "Sri Preethaji"
    if "krishnaji" in title_lower and "preethaji" not in title_lower:
        return "Sri Krishnaji"
    return "Sri Preethaji & Sri Krishnaji"


def analyze_video(
    video_id: str,
    corpus_root: str = "scripts/ingestion/corpus",
) -> Optional[VideoAnalysis]:
    v_dir = os.path.join(corpus_root, video_id)
    whisper_file = os.path.join(
        v_dir, "raw_sources", "local_whisper_audio", "en", "whisper_segments.json"
    )
    manifest_file = os.path.join(v_dir, "manifest.json")

    if not os.path.exists(whisper_file):
        return None

    try:
        with open(whisper_file, "r", encoding="utf-8") as f:
            raw_segs = json.load(f)
    except Exception:
        return None

    if not raw_segs or not isinstance(raw_segs, list):
        return None

    title = video_id
    total_duration = 0.0
    if os.path.exists(manifest_file):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                m_data = json.load(f)
                title = m_data.get("title", video_id)
                total_duration = float(m_data.get("duration_seconds", 0.0) or 0.0)
        except Exception:
            pass

    # Extract parsed segments
    parsed_segments: List[SegmentData] = []
    total_words = 0
    speech_duration = 0.0

    for s in raw_segs:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", 0.0))
        dur = max(0.0, end - start)
        text = (s.get("text") or "").strip()
        words = [w for w in text.split() if w]
        w_count = len(words)
        total_words += w_count
        speech_duration += dur
        wpm = (w_count / (dur / 60.0)) if dur > 0.1 else 0.0
        is_q = bool(_QUESTION_RE.search(text))

        parsed_segments.append(
            SegmentData(
                segment_id=s.get("segment_id", ""),
                start=start,
                end=end,
                duration=dur,
                text=text,
                word_count=w_count,
                wpm=wpm,
                avg_logprob=float(s.get("avg_logprob", 0.0) or 0.0),
                no_speech_prob=float(s.get("no_speech_prob", 0.0) or 0.0),
                is_question=is_q,
            )
        )

    if not parsed_segments:
        return None

    # Calculate actual total duration if not in manifest
    if total_duration <= 0.0:
        total_duration = parsed_segments[-1].end

    # Measure pauses between segments
    pauses: List[float] = []
    question_pauses: List[float] = []
    statement_pauses: List[float] = []

    for i in range(len(parsed_segments) - 1):
        gap = parsed_segments[i + 1].start - parsed_segments[i].end
        # Ignore negative gaps or clip to 0
        pause_val = max(0.0, gap)
        parsed_segments[i].pause_after = pause_val
        pauses.append(pause_val)

        if parsed_segments[i].is_question:
            question_pauses.append(pause_val)
        else:
            statement_pauses.append(pause_val)

    silence_duration = max(0.0, total_duration - speech_duration)
    silence_pct = (silence_duration / total_duration * 100.0) if total_duration > 0 else 0.0

    pure_wpm = (total_words / (speech_duration / 60.0)) if speech_duration > 0 else 0.0
    effective_wpm = (total_words / (total_duration / 60.0)) if total_duration > 0 else 0.0

    # Pause tiers
    c_sub_0_5 = sum(1 for p in pauses if p < 0.5)
    c_micro = sum(1 for p in pauses if 0.5 <= p < 1.2)
    c_inter = sum(1 for p in pauses if 1.2 <= p < 1.5)
    c_refl = sum(1 for p in pauses if 1.5 <= p <= 3.0)
    c_cont = sum(1 for p in pauses if p > 3.0)

    p_sorted = sorted(pauses) if pauses else [0.0]
    n_p = len(p_sorted)

    pause_mean = statistics.mean(pauses) if pauses else 0.0
    pause_med = statistics.median(pauses) if pauses else 0.0
    pause_p75 = p_sorted[int(0.75 * n_p)] if n_p > 1 else pause_med
    pause_p90 = p_sorted[int(0.90 * n_p)] if n_p > 1 else pause_med
    pause_max = max(pauses) if pauses else 0.0

    # Sentence / Segment lengths
    word_counts = [s.word_count for s in parsed_segments if s.word_count > 0]
    if not word_counts:
        word_counts = [0]
    w_sorted = sorted(word_counts)
    n_w = len(w_sorted)

    words_mean = statistics.mean(word_counts)
    words_med = statistics.median(word_counts)
    words_p10 = w_sorted[int(0.10 * n_w)]
    words_p25 = w_sorted[int(0.25 * n_w)]
    words_p75 = w_sorted[min(int(0.75 * n_w), n_w - 1)]
    words_p90 = w_sorted[min(int(0.90 * n_w), n_w - 1)]
    words_max = max(word_counts)

    # Short vs Long
    c_short = sum(1 for w in word_counts if w <= 8)
    c_med = sum(1 for w in word_counts if 9 <= w <= 18)
    c_long = sum(1 for w in word_counts if w >= 19)

    short_pct = (c_short / len(word_counts) * 100.0) if word_counts else 0.0
    med_pct = (c_med / len(word_counts) * 100.0) if word_counts else 0.0
    long_pct = (c_long / len(word_counts) * 100.0) if word_counts else 0.0

    # Alternation: how often does length jump between Short (<=10) and Long (>=15)?
    transitions = 0
    alternations = 0
    for i in range(len(word_counts) - 1):
        transitions += 1
        w1, w2 = word_counts[i], word_counts[i + 1]
        if (w1 <= 10 and w2 >= 14) or (w1 >= 14 and w2 <= 10):
            alternations += 1
    alternation_rate = (alternations / transitions * 100.0) if transitions > 0 else 0.0

    # Questions
    q_count = sum(1 for s in parsed_segments if s.is_question)
    q_rate_per_100w = (q_count / (total_words / 100.0)) if total_words > 0 else 0.0

    mean_pause_q = statistics.mean(question_pauses) if question_pauses else 0.0
    median_pause_q = statistics.median(question_pauses) if question_pauses else 0.0
    mean_pause_stmt = statistics.mean(statement_pauses) if statement_pauses else 0.0
    median_pause_stmt = statistics.median(statement_pauses) if statement_pauses else 0.0

    q_pause_ratio = (mean_pause_q / mean_pause_stmt) if mean_pause_stmt > 0 else 1.0

    # Direct address
    direct_address_matches = 0
    for s in parsed_segments:
        direct_address_matches += len(_DIRECT_ADDRESS_RE.findall(s.text))
    direct_address_rate = (
        (direct_address_matches / (total_words / 100.0)) if total_words > 0 else 0.0
    )

    category = classify_category(title, total_duration)
    speaker_tag = classify_speaker(title, "")

    return VideoAnalysis(
        video_id=video_id,
        title=title,
        speaker_tag=speaker_tag,
        category=category,
        total_duration_sec=round(total_duration, 2),
        speech_duration_sec=round(speech_duration, 2),
        silence_duration_sec=round(silence_duration, 2),
        silence_percentage=round(silence_pct, 2),
        total_words=total_words,
        total_segments=len(parsed_segments),
        pure_wpm=round(pure_wpm, 1),
        effective_wpm=round(effective_wpm, 1),
        pause_count_total=len(pauses),
        pauses_sub_0_5s=c_sub_0_5,
        pauses_micro_0_5_to_1_2s=c_micro,
        pauses_intermediate_1_2_to_1_5s=c_inter,
        pauses_reflective_1_5_to_3_0s=c_refl,
        pauses_contemplative_gt_3_0s=c_cont,
        pause_mean=round(pause_mean, 2),
        pause_median=round(pause_med, 2),
        pause_p75=round(pause_p75, 2),
        pause_p90=round(pause_p90, 2),
        pause_max=round(pause_max, 2),
        words_mean=round(words_mean, 1),
        words_median=round(words_med, 1),
        words_p10=round(words_p10, 1),
        words_p25=round(words_p25, 1),
        words_p75=round(words_p75, 1),
        words_p90=round(words_p90, 1),
        words_max=words_max,
        short_segments_pct=round(short_pct, 1),
        medium_segments_pct=round(med_pct, 1),
        long_segments_pct=round(long_pct, 1),
        alternation_rate=round(alternation_rate, 1),
        question_count=q_count,
        question_rate_per_100w=round(q_rate_per_100w, 2),
        mean_pause_after_question=round(mean_pause_q, 2),
        mean_pause_after_statement=round(mean_pause_stmt, 2),
        median_pause_after_question=round(median_pause_q, 2),
        median_pause_after_statement=round(median_pause_stmt, 2),
        question_pause_ratio=round(q_pause_ratio, 2),
        direct_address_count=direct_address_matches,
        direct_address_rate_per_100w=round(direct_address_rate, 2),
    )


def extract_rhetorical_sequences(
    corpus_root: str, target_videos: List[str]
) -> List[Dict[str, Any]]:
    """Extract concrete examples of Question -> Pause -> Insight sequence."""
    sequences = []
    for vid in target_videos:
        whisper_file = os.path.join(
            corpus_root, vid, "raw_sources", "local_whisper_audio", "en", "whisper_segments.json"
        )
        if not os.path.exists(whisper_file):
            continue
        try:
            with open(whisper_file) as f:
                segs = json.load(f)
        except Exception:
            continue

        for i in range(len(segs) - 1):
            text_i = segs[i].get("text", "").strip()
            if _QUESTION_RE.search(text_i) and len(text_i.split()) >= 4:
                start_next = float(segs[i + 1].get("start", 0.0))
                end_curr = float(segs[i].get("end", 0.0))
                gap = max(0.0, start_next - end_curr)
                next_text = segs[i + 1].get("text", "").strip()
                sequences.append(
                    {
                        "video_id": vid,
                        "question": text_i,
                        "pause_sec": round(gap, 2),
                        "insight_after": next_text,
                    }
                )
    return sequences


def run_comprehensive_corpus_analysis(
    corpus_root: str = "scripts/ingestion/corpus",
) -> Dict[str, Any]:
    video_dirs = [
        d
        for d in os.listdir(corpus_root)
        if os.path.isdir(os.path.join(corpus_root, d))
        and os.path.exists(
            os.path.join(
                corpus_root, d, "raw_sources", "local_whisper_audio", "en", "whisper_segments.json"
            )
        )
    ]
    print(f"Found {len(video_dirs)} whisper segment files to analyze across corpus.")

    all_analyses: List[VideoAnalysis] = []
    category_map: Dict[str, List[VideoAnalysis]] = defaultdict(list)

    for vid in video_dirs:
        res = analyze_video(vid, corpus_root)
        if res:
            all_analyses.append(res)
            category_map[res.category].append(res)

    print(f"Successfully parsed and computed cadence metrics for {len(all_analyses)} discourses.")

    # Representative target videos
    representative_vids = [
        "1_-cZz8YRFw",
        "MuxETIn04F8",
        "7lggUuJtZXY",
        "VOOf2kQpeMw",
        "nsUkTKmx2dI",
        "mAG-Q4DZ5Zs",
        "ClbKAXVvzzo",  # 42m Witness Consciousness
        "DmzZPgTh7_M",  # 28m Anger & Hard Truth
        "x-mTRlE0TC4",  # 28m Krishnaji Frankly Speaking
    ]

    rep_results = [a for a in all_analyses if a.video_id in representative_vids]

    # Global aggregate metrics
    tot_duration = sum(a.total_duration_sec for a in all_analyses)
    tot_speech = sum(a.speech_duration_sec for a in all_analyses)
    tot_silence = sum(a.silence_duration_sec for a in all_analyses)
    tot_words = sum(a.total_words for a in all_analyses)
    tot_segments = sum(a.total_segments for a in all_analyses)
    tot_pauses = sum(a.pause_count_total for a in all_analyses)

    tot_sub_0_5 = sum(a.pauses_sub_0_5s for a in all_analyses)
    tot_micro = sum(a.pauses_micro_0_5_to_1_2s for a in all_analyses)
    tot_inter = sum(a.pauses_intermediate_1_2_to_1_5s for a in all_analyses)
    tot_refl = sum(a.pauses_reflective_1_5_to_3_0s for a in all_analyses)
    tot_cont = sum(a.pauses_contemplative_gt_3_0s for a in all_analyses)

    global_pure_wpm = (tot_words / (tot_speech / 60.0)) if tot_speech > 0 else 0.0
    global_eff_wpm = (tot_words / (tot_duration / 60.0)) if tot_duration > 0 else 0.0
    global_silence_pct = (tot_silence / tot_duration * 100.0) if tot_duration > 0 else 0.0

    mean_pause_q_global = statistics.mean([a.mean_pause_after_question for a in all_analyses if a.mean_pause_after_question > 0])
    mean_pause_stmt_global = statistics.mean([a.mean_pause_after_statement for a in all_analyses if a.mean_pause_after_statement > 0])

    # Category summaries
    cat_summaries = {}
    for cat, analyses in category_map.items():
        cat_summaries[cat] = {
            "count": len(analyses),
            "pure_wpm_mean": round(statistics.mean([a.pure_wpm for a in analyses]), 1),
            "effective_wpm_mean": round(statistics.mean([a.effective_wpm for a in analyses]), 1),
            "silence_pct_mean": round(statistics.mean([a.silence_percentage for a in analyses]), 1),
            "pause_mean": round(statistics.mean([a.pause_mean for a in analyses]), 2),
            "short_pct_mean": round(statistics.mean([a.short_segments_pct for a in analyses]), 1),
            "long_pct_mean": round(statistics.mean([a.long_segments_pct for a in analyses]), 1),
            "alternation_mean": round(statistics.mean([a.alternation_rate for a in analyses]), 1),
            "question_pause_ratio": round(statistics.mean([a.question_pause_ratio for a in analyses]), 2),
        }

    # Rhetorical sequences
    sample_sequences = extract_rhetorical_sequences(corpus_root, representative_vids)

    results = {
        "global_corpus_summary": {
            "total_discourses_analyzed": len(all_analyses),
            "total_audio_hours": round(tot_duration / 3600.0, 2),
            "total_spoken_hours": round(tot_speech / 3600.0, 2),
            "total_silence_hours": round(tot_silence / 3600.0, 2),
            "global_silence_percentage": round(global_silence_pct, 2),
            "total_words_spoken": tot_words,
            "total_segments": tot_segments,
            "global_pure_wpm": round(global_pure_wpm, 1),
            "global_effective_wpm": round(global_eff_wpm, 1),
            "pause_breakdown": {
                "total_measured_pauses": tot_pauses,
                "continuous_under_0_5s_count": tot_sub_0_5,
                "continuous_under_0_5s_pct": round(tot_sub_0_5 / tot_pauses * 100.0, 1) if tot_pauses else 0,
                "micro_pauses_0_5_to_1_2s_count": tot_micro,
                "micro_pauses_0_5_to_1_2s_pct": round(tot_micro / tot_pauses * 100.0, 1) if tot_pauses else 0,
                "intermediate_1_2_to_1_5s_count": tot_inter,
                "intermediate_1_2_to_1_5s_pct": round(tot_inter / tot_pauses * 100.0, 1) if tot_pauses else 0,
                "reflective_pauses_1_5_to_3_0s_count": tot_refl,
                "reflective_pauses_1_5_to_3_0s_pct": round(tot_refl / tot_pauses * 100.0, 1) if tot_pauses else 0,
                "deep_contemplative_gt_3_0s_count": tot_cont,
                "deep_contemplative_gt_3_0s_pct": round(tot_cont / tot_pauses * 100.0, 1) if tot_pauses else 0,
            },
            "mean_words_per_segment": round(statistics.mean([a.words_mean for a in all_analyses]), 1),
            "median_words_per_segment": round(statistics.median([a.words_median for a in all_analyses]), 1),
            "short_segments_pct_mean": round(statistics.mean([a.short_segments_pct for a in all_analyses]), 1),
            "long_segments_pct_mean": round(statistics.mean([a.long_segments_pct for a in all_analyses]), 1),
            "alternation_rate_mean": round(statistics.mean([a.alternation_rate for a in all_analyses]), 1),
            "rhetorical_question_dynamics": {
                "mean_pause_after_question_sec": round(mean_pause_q_global, 2),
                "mean_pause_after_statement_sec": round(mean_pause_stmt_global, 2),
                "question_to_statement_pause_multiplier": round(mean_pause_q_global / mean_pause_stmt_global, 2)
                if mean_pause_stmt_global > 0
                else 1.0,
            },
        },
        "category_summaries": cat_summaries,
        "representative_discourses": [asdict(r) for r in rep_results],
        "sample_rhetorical_sequences": sample_sequences[:25],
    }

    out_file = os.path.join(os.path.dirname(__file__), "oral_cadence_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {out_file}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze oral cadence across corpus")
    parser.add_argument(
        "--corpus-root", default="scripts/ingestion/corpus", help="Path to corpus root"
    )
    args = parser.parse_args()

    results = run_comprehensive_corpus_analysis(args.corpus_root)

    print("\n" + "=" * 80)
    print("GLOBAL CORPUS SUMMARY (657 DISCOURSES)")
    print("=" * 80)
    g = results["global_corpus_summary"]
    print(f"Total Discourses Analyzed:  {g['total_discourses_analyzed']}")
    print(f"Total Audio Duration:       {g['total_audio_hours']} hours ({g['total_audio_hours']*60:.1f} minutes)")
    print(f"Spoken Speech Duration:     {g['total_spoken_hours']} hours")
    print(f"Silence Duration:           {g['total_silence_hours']} hours ({g['global_silence_percentage']}% silence)")
    print(f"Total Spoken Words:         {g['total_words_spoken']:,}")
    print(f"Global Pure Speaking WPM:   {g['global_pure_wpm']} WPM (while speaking)")
    print(f"Global Effective WPM:       {g['global_effective_wpm']} WPM (including pauses)")
    print(f"Segment Length:             Mean: {g['mean_words_per_segment']} words | Median: {g['median_words_per_segment']} words")
    print(f"Short Segments (<=8w):      {g['short_segments_pct_mean']}%")
    print(f"Long Segments (>=19w):      {g['long_segments_pct_mean']}%")
    print(f"Alternation Jump Rate:      {g['alternation_rate_mean']}% (short <-> long alternation)")
    print("\nPause Tiers:")
    pb = g["pause_breakdown"]
    print(f"  Continuous (<0.5s):       {pb['continuous_under_0_5s_count']:,} ({pb['continuous_under_0_5s_pct']}%)")
    print(f"  Micro-pauses (0.5-1.2s):  {pb['micro_pauses_0_5_to_1_2s_count']:,} ({pb['micro_pauses_0_5_to_1_2s_pct']}%) [Breath & Phrasing]")
    print(f"  Intermediate (1.2-1.5s):  {pb['intermediate_1_2_to_1_5s_count']:,} ({pb['intermediate_1_2_to_1_5s_pct']}%)")
    print(f"  Reflective (1.5-3.0s):    {pb['reflective_pauses_1_5_to_3_0s_count']:,} ({pb['reflective_pauses_1_5_to_3_0s_pct']}%) [Insight Resonance]")
    print(f"  Contemplative (>3.0s):    {pb['deep_contemplative_gt_3_0s_count']:,} ({pb['deep_contemplative_gt_3_0s_pct']}%) [Deep Stillness]")
    print("\nRhetorical Structure:")
    rq = g["rhetorical_question_dynamics"]
    print(f"  Pause after Question:     {rq['mean_pause_after_question_sec']}s")
    print(f"  Pause after Statement:    {rq['mean_pause_after_statement_sec']}s")
    print(f"  Question Pause Multiplier:{rq['question_to_statement_pause_multiplier']}x longer silence held after questions")

    print("\n" + "=" * 80)
    print("REPRESENTATIVE DISCOURSES")
    print("=" * 80)
    for r in results["representative_discourses"]:
        print(f"Video ID: {r['video_id']} | Category: {r['category']}")
        print(f"  Title: {r['title']}")
        print(f"  Duration: {r['total_duration_sec']}s | Silence: {r['silence_percentage']}%")
        print(f"  Pure WPM: {r['pure_wpm']} | Effective WPM: {r['effective_wpm']}")
        print(f"  Pauses: Micro(0.5-1.2s): {r['pauses_micro_0_5_to_1_2s']} | Reflective(1.5-3s): {r['pauses_reflective_1_5_to_3_0s']} | Contemplative(>3s): {r['pauses_contemplative_gt_3_0s']}")
        print(f"  Segments: Short(<=8w): {r['short_segments_pct']}% | Long(>=19w): {r['long_segments_pct']}% | Alternation: {r['alternation_rate']}%")
        print(f"  Questions: {r['question_count']} | Pause after Q: {r['mean_pause_after_question']}s vs Stmt: {r['mean_pause_after_statement']}s (Ratio: {r['question_pause_ratio']}x)")
        print("-" * 80)
