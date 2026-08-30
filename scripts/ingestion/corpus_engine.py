#!/usr/bin/env python3
"""
Mukthi Guru — Evidence-Preserving Corpus Engine
================================================
Manages per-video immutable artifact directory creation, canonical segment
representation, reversible correction ledger generation, quality evaluation,
and compatibility projections.

Artifact Structure per video in scripts/ingestion/corpus/<video_id>/:
  ├── raw_sources/
  │   └── {tier}/{language}/{filename}  (immutable raw VTT/SRT/JSON/XML/ASR)
  ├── canonical_segments.json          (timestamped segments with evidence)
  ├── transcript.md                    (human-readable Markdown + frontmatter)
  ├── quality_report.json              (deterministic quality evaluation)
  ├── correction_ledger.json           (reversible offset-addressed audit log)
  └── review_record.json               (DLQ/review metadata for non-trusted items)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from services.doctrine_terms import apply_corrections_with_ledger
except ImportError:
    apply_corrections_with_ledger = None

CORPUS_ROOT = Path(os.environ.get("MUKTHI_CORPUS_DIR", str(Path(__file__).resolve().parent / "corpus")))
PROJECTION_DIR = Path(os.environ.get("MUKTHI_TRANSCRIPTS_DIR", str(Path(__file__).resolve().parent / "transcripts")))
PIPELINE_VERSION = "2.0.0"

QualityState = Literal[
    "trusted",
    "trusted_after_review",
    "needs_review",
    "sound_only",
    "silence",
    "ambiguous",
    "unavailable",
    "dead_lettered",
]


class SpeakerEvidence(BaseModel):
    channel_or_publisher: str = "Ekam / O&O Academy"
    metadata_attribution: Optional[str] = "Sri Preethaji & Sri Krishnaji"
    detected_speaker: Optional[str] = None
    speaker_identity_source: Literal["metadata", "diarization", "human_review", "heuristic", "unknown"] = "metadata"
    speaker_role: Optional[Literal["teacher", "questioner", "translator", "narration", "unknown"]] = "teacher"
    speaker_role_source: Literal["metadata", "diarization", "human_review", "heuristic", "unknown"] = "metadata"
    confidence: Optional[float] = None
    confidence_kind: Literal["asr_model", "caption_source", "human_review", "heuristic"] = "caption_source"


class CanonicalSegment(BaseModel):
    segment_id: str
    start: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    end: float = Field(..., ge=0.0, description="End timestamp in seconds")
    text: str = Field(..., description="Segment text")
    source_tier: str = Field(..., description="manual_api | auto_api | ytdlp_subs | scrape_captions | local_whisper_audio | pilot_mock")
    language: str = "en"
    confidence: Optional[float] = None
    confidence_kind: Literal["asr_model", "caption_source", "human_review", "heuristic"] = "caption_source"
    speaker_evidence: SpeakerEvidence = Field(default_factory=SpeakerEvidence)
    is_non_speech: bool = False


class CorrectionLedgerEntry(BaseModel):
    rule_id: str
    segment_id: str
    char_start: int  # Half-open start index [char_start, char_end)
    char_end: int    # Half-open end index
    occurrence_index: int
    matched_text: str
    replacement: str
    original_segment_text: Optional[str] = None
    corrected_segment_text: Optional[str] = None
    original_segment_hash: str
    corrected_segment_hash: str
    source_artifact_ref: Optional[str] = None
    pipeline_version: str = PIPELINE_VERSION
    unicode_normalization: str = "NFC"
    review_status: str = "automated"
    reversal_tested: bool = True
    reason: str


class QualityReport(BaseModel):
    video_id: str
    quality_state: QualityState
    quality_score: float = Field(..., ge=0.0, le=1.0)
    duration_seconds: float
    speech_interval_coverage_estimate: float = Field(..., ge=0.0, le=1.0)
    coverage_reference: Literal["vad", "asr", "captions", "human_review"] = "vad"
    gap_seconds: float = 0.0
    overlap_seconds: float = 0.0
    duplicate_segment_seconds: float = 0.0
    coverage_confidence: Literal["low", "medium", "high"] = "high"
    caption_asr_agreement: Optional[float] = None  # None if single-source
    repetition_detected: bool = False
    hallucination_suspected: bool = False
    terminology_corrections_count: int = 0
    flags: list[str] = Field(default_factory=list)
    metrics_details: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReviewRecord(BaseModel):
    video_id: str
    quality_state: QualityState
    reason: str
    action_required: str
    replay_command: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArtifactEntry(BaseModel):
    rel_path: str
    byte_size: int
    mime_type: str
    sha256: str


class ArtifactManifest(BaseModel):
    manifest_version: str = "2.0.0"
    pipeline_version: str = PIPELINE_VERSION
    video_id: str
    source_url: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    final_quality_state: QualityState
    quality_score: float
    manifest_hash: str
    prior_manifest_hash: Optional[str] = None
    immutable_status: str = "enforced_by_policy"
    raw_source_attempts: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, ArtifactEntry] = Field(default_factory=dict)


class VideoCorpusManifest(BaseModel):
    video_id: str
    title: str
    duration_seconds: float
    source_url: str
    playlist_urls: list[str] = Field(default_factory=list)
    raw_source_hashes: dict[str, str] = Field(default_factory=dict)
    canonical_segment_count: int
    quality_state: QualityState
    pipeline_version: str = PIPELINE_VERSION
    manifest_hash: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def compute_sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_canonical_manifest_hash(video_id: str, transcript_hash: str, pipeline_version: str = PIPELINE_VERSION) -> str:
    """Canonical hash for idempotency and version tracking."""
    canonical_str = json.dumps({
        "pipeline_version": pipeline_version,
        "transcript_hash": transcript_hash,
        "video_id": video_id,
    }, sort_keys=True)
    return compute_sha256(canonical_str)


class CorpusEngine:
    def __init__(self, corpus_root: Path = CORPUS_ROOT, projection_dir: Path = PROJECTION_DIR):
        self.corpus_root = corpus_root
        self.projection_dir = projection_dir

    def get_video_dir(self, video_id: str) -> Path:
        d = self.corpus_root / video_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_raw_source(self, video_id: str, tier: str, language: str, filename: str, content: bytes | str) -> tuple[Path, str]:
        """Save raw source immutably. Refuses to overwrite matching SHA-256; versions if changed."""
        v_dir = self.get_video_dir(video_id)
        raw_dir = v_dir / "raw_sources" / tier / language
        raw_dir.mkdir(parents=True, exist_ok=True)

        target_path = raw_dir / filename
        data_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = compute_sha256(data_bytes)

        if target_path.exists():
            existing_hash = compute_sha256(target_path.read_bytes())
            if existing_hash == content_hash:
                # Exactly identical content, write-once preserved
                return target_path, content_hash
            # Versioned suffix if source payload differs
            version_suffix = f"_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = raw_dir / f"{stem}{version_suffix}{suffix}"

        target_path.write_bytes(data_bytes)
        return target_path, content_hash

    def evaluate_quality(
        self,
        video_id: str,
        segments: list[CanonicalSegment],
        duration_seconds: float = 0.0,
        detected_speech_duration: Optional[float] = None,
        asr_comparison_text: Optional[str] = None,
        review_completed: bool = False,
    ) -> QualityReport:
        """Deterministic Promotion Decision Matrix."""
        flags: list[str] = []

        if not segments:
            return QualityReport(
                video_id=video_id,
                quality_state="dead_lettered",
                quality_score=0.0,
                duration_seconds=duration_seconds,
                speech_interval_coverage_estimate=0.0,
                flags=["no_segments_extracted"],
            )

        # 1. Monotonicity & gap check
        is_monotonic = True
        total_segment_duration = 0.0
        for i in range(len(segments)):
            seg = segments[i]
            if seg.end < seg.start:
                is_monotonic = False
                flags.append(f"negative_duration_in_seg_{seg.segment_id}")
            if i > 0 and seg.start < segments[i - 1].start:
                is_monotonic = False
                flags.append(f"backward_timestamp_jump_at_seg_{seg.segment_id}")
            total_segment_duration += max(0.0, seg.end - seg.start)

        # 2. Coverage Estimate
        ref_duration = detected_speech_duration or duration_seconds or total_segment_duration
        coverage_estimate = min(1.0, total_segment_duration / ref_duration) if ref_duration > 0 else 1.0
        coverage_reference = "asr" if any(s.source_tier == "local_whisper_audio" for s in segments) else "captions"
        if coverage_estimate < 0.80:
            flags.append(f"low_speech_interval_coverage_estimate={coverage_estimate:.3f}")

        # 3. Repetition Check (5-gram loops >= 4)
        full_text = " ".join(s.text for s in segments if not s.is_non_speech)
        words = full_text.split()
        repetition_detected = False
        if len(words) >= 20:
            for n in range(len(words) - 19):
                gram = words[n:n + 5]
                gram_str = " ".join(gram)
                # Count non-overlapping occurrences
                count = len(re.findall(r"\b" + re.escape(gram_str) + r"\b", full_text, re.IGNORECASE))
                if count >= 4:
                    repetition_detected = True
                    flags.append(f"repetition_loop_detected: '{gram_str}' (count={count})")
                    break

        # 4. Check if sound-only or silence (supporting Indic scripts and Latin words)
        has_speech_words = bool(re.search(r"[\w]{3,}", full_text, re.UNICODE))
        if not has_speech_words or total_segment_duration == 0:
            quality_state: QualityState = "sound_only"
            score = 0.0
            return QualityReport(
                video_id=video_id,
                quality_state=quality_state,
                quality_score=score,
                duration_seconds=duration_seconds,
                speech_interval_coverage_estimate=coverage_estimate,
                flags=["audio_only_or_silence"],
            )

        # 5. Caption / ASR Agreement (conditional)
        caption_asr_agreement = None
        if asr_comparison_text:
            # Word-level Jaccard / token agreement proxy
            caption_words = set(re.findall(r"\w+", full_text.lower()))
            asr_words = set(re.findall(r"\w+", asr_comparison_text.lower()))
            if caption_words and asr_words:
                inter = len(caption_words & asr_words)
                union = len(caption_words | asr_words)
                caption_asr_agreement = inter / union if union > 0 else 0.0

        # 6. Quality Promotion State Machine
        score = 0.5
        if not is_monotonic:
            quality_state = "needs_review"
            score = 0.4
        elif repetition_detected:
            quality_state = "needs_review"
            score = 0.45
        elif caption_asr_agreement is not None:
            if caption_asr_agreement >= 0.70:
                quality_state = "trusted"
                score = 0.95
            else:
                quality_state = "needs_review"
                score = 0.60
                flags.append(f"caption_asr_disagreement (agreement={caption_asr_agreement:.2f})")
        else:
            # A single source is not trusted without explicit review. Mock
            # speech and materially incomplete timing are unsafe evidence.
            has_mock_speech = any(
                s.source_tier == "pilot_mock" and not s.is_non_speech
                for s in segments
            )
            if has_mock_speech:
                quality_state = "needs_review"
                score = 0.35
                flags.append("pilot_mock_speech_is_not_trusted_evidence")
            elif coverage_estimate < 0.80:
                quality_state = "needs_review"
                score = 0.50
            elif review_completed:
                quality_state = "trusted_after_review"
                score = 0.85
            else:
                quality_state = "needs_review"
                score = 0.70
                flags.append("single_source_requires_human_review")

        return QualityReport(
            video_id=video_id,
            quality_state=quality_state,
            quality_score=score,
            duration_seconds=duration_seconds,
            speech_interval_coverage_estimate=coverage_estimate,
            coverage_reference=coverage_reference,
            caption_asr_agreement=caption_asr_agreement,
            repetition_detected=repetition_detected,
            hallucination_suspected=repetition_detected,
            flags=flags,
            metrics_details={
                "segment_count": len(segments),
                "is_monotonic": is_monotonic,
                "total_segment_duration": total_segment_duration,
            },
        )

    def record_dead_letter(
        self,
        video_info: dict[str, Any],
        reason: str,
        quality_state: QualityState = "dead_lettered",
        raw_error: Optional[str] = None,
        duration_seconds: float = 0.0,
    ) -> VideoCorpusManifest:
        """Handle dead-lettered / private / rate-limited videos without throwing unhandled exceptions.

        Creates structured artifacts (quality_report.json, review_record.json,
        canonical_segments.json, correction_ledger.json, transcript.md, artifact_manifest.json, manifest.json)
        with quality_state set to 'dead_lettered' or 'unavailable'.
        """
        video_id = video_info.get("video_id") or "unknown_video"
        v_dir = self.get_video_dir(video_id)
        title = video_info.get("title") or video_id
        source_url = video_info.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        flags = [reason]
        if raw_error:
            flags.append(f"error_detail: {raw_error}")

        q_report = QualityReport(
            video_id=video_id,
            quality_state=quality_state,
            quality_score=0.0,
            duration_seconds=duration_seconds,
            speech_interval_coverage_estimate=0.0,
            flags=flags,
            metrics_details={"error": reason, "raw_error": raw_error or ""},
        )

        md_content = (
            f"# {title}\n\n"
            f"**Video ID:** `{video_id}`\n"
            f"**URL:** {source_url}\n"
            f"**Quality State:** {quality_state}\n"
            f"**Quality Score:** 0.00\n"
            f"**Status Reason:** {reason}\n"
            f"**Pipeline Version:** {PIPELINE_VERSION}\n"
            f"**Fetched:** {datetime.now(timezone.utc).isoformat()}\n\n"
            f"## Status\n\nVideo unavailable or extraction failed: {reason}\n"
        )
        stable_payload = json.dumps({
            "video_id": video_id,
            "quality_state": quality_state,
            "reason": reason,
        }, sort_keys=True)
        transcript_hash = compute_sha256(stable_payload)
        manifest_hash = compute_canonical_manifest_hash(video_id, transcript_hash)

        seg_file = v_dir / "canonical_segments.json"
        seg_file.write_text(json.dumps({"video_id": video_id, "segments": []}, indent=2))

        q_file = v_dir / "quality_report.json"
        q_file.write_text(q_report.model_dump_json(indent=2))

        ledg_file = v_dir / "correction_ledger.json"
        ledg_file.write_text(json.dumps([], indent=2))

        t_file = v_dir / "transcript.md"
        t_file.write_text(md_content, encoding="utf-8")

        rev = ReviewRecord(
            video_id=video_id,
            quality_state=quality_state,
            reason=reason,
            action_required=f"Inspect video status on YouTube ({reason})",
            replay_command=f"python3 scripts/ingestion/1_fetch_transcripts_local.py --video-id {video_id}",
        )
        (v_dir / "review_record.json").write_text(rev.model_dump_json(indent=2))

        artifacts_dict = {
            "canonical_segments.json": ArtifactEntry(
                rel_path="canonical_segments.json",
                byte_size=seg_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(seg_file.read_bytes()),
            ),
            "quality_report.json": ArtifactEntry(
                rel_path="quality_report.json",
                byte_size=q_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(q_file.read_bytes()),
            ),
            "correction_ledger.json": ArtifactEntry(
                rel_path="correction_ledger.json",
                byte_size=ledg_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(ledg_file.read_bytes()),
            ),
            "transcript.md": ArtifactEntry(
                rel_path="transcript.md",
                byte_size=t_file.stat().st_size,
                mime_type="text/markdown",
                sha256=compute_sha256(t_file.read_bytes()),
            ),
        }

        art_manifest = ArtifactManifest(
            manifest_version="2.0.0",
            pipeline_version=PIPELINE_VERSION,
            video_id=video_id,
            source_url=source_url,
            final_quality_state=quality_state,
            quality_score=0.0,
            manifest_hash=manifest_hash,
            raw_source_attempts=[{
                "tier": "unavailable",
                "raw_path": "none",
                "sha256": "",
                "status": "failed",
                "reason": reason,
            }],
            artifacts=artifacts_dict,
        )
        (v_dir / "artifact_manifest.json").write_text(art_manifest.model_dump_json(indent=2))

        manifest = VideoCorpusManifest(
            video_id=video_id,
            title=title,
            duration_seconds=duration_seconds,
            source_url=source_url,
            playlist_urls=video_info.get("playlist_urls", []),
            raw_source_hashes={},
            canonical_segment_count=0,
            quality_state=quality_state,
            manifest_hash=manifest_hash,
        )
        (v_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        return manifest

    def process_and_package_video(
        self,
        video_info: dict[str, Any],
        segments: list[CanonicalSegment],
        raw_source_path: Optional[Path] = None,
        raw_source_hash: str = "",
        duration_seconds: float = 0.0,
        asr_comparison_text: Optional[str] = None,
    ) -> VideoCorpusManifest:
        """Construct full artifact set: segments, quality report, correction ledger, markdown, and projection."""
        video_id = video_info["video_id"]
        v_dir = self.get_video_dir(video_id)

        # 1. Apply domain corrections with reversible ledger per segment
        all_ledger: list[CorrectionLedgerEntry] = []
        corrected_segments: list[CanonicalSegment] = []

        for seg in segments:
            orig_text = seg.text
            if apply_corrections_with_ledger:
                corr_text, ledger_items = apply_corrections_with_ledger(
                    orig_text, segment_id=seg.segment_id, pipeline_version=PIPELINE_VERSION
                )
                for item in ledger_items:
                    all_ledger.append(CorrectionLedgerEntry(**item))
            else:
                corr_text = orig_text

            corrected_segments.append(CanonicalSegment(
                segment_id=seg.segment_id,
                start=seg.start,
                end=seg.end,
                text=corr_text,
                source_tier=seg.source_tier,
                language=seg.language,
                confidence=seg.confidence,
                confidence_kind=seg.confidence_kind,
                speaker_evidence=seg.speaker_evidence,
                is_non_speech=seg.is_non_speech,
            ))

        # 2. Evaluate Quality
        q_report = self.evaluate_quality(
            video_id=video_id,
            segments=corrected_segments,
            duration_seconds=duration_seconds,
            asr_comparison_text=asr_comparison_text,
        )
        q_report.terminology_corrections_count = len(all_ledger)

        # 3. Assemble Clean Markdown Transcript (without inline timestamps to prevent Qdrant embedding distortion)
        title = video_info.get("title") or video_id
        speaker = (
            video_info.get("speaker")
            or (corrected_segments[0].speaker_evidence.metadata_attribution if corrected_segments else "Sri Preethaji & Sri Krishnaji")
            or "Sri Preethaji & Sri Krishnaji"
        )
        channel = video_info.get("uploader") or "Ekam / O&O Academy"
        source_url = video_info.get("url") or f"https://www.youtube.com/watch?v={video_id}"

        # Group spoken segments into natural paragraphs (~300-500 chars) on sentence endings
        spoken_segments = [s for s in corrected_segments if not s.is_non_speech and s.text.strip()]
        paragraphs: list[str] = []
        curr_para: list[str] = []
        curr_len = 0
        for seg in spoken_segments:
            text = seg.text.strip()
            curr_para.append(text)
            curr_len += len(text)
            if curr_len >= 350 and (text.endswith((".", "!", "?")) or text.endswith((". ", "! ", "? "))):
                p_text = " ".join(curr_para).strip()
                if p_text:
                    p_text = p_text[0].upper() + p_text[1:]
                    paragraphs.append(p_text)
                curr_para = []
                curr_len = 0
        if curr_para:
            p_text = " ".join(curr_para).strip()
            if p_text:
                p_text = p_text[0].upper() + p_text[1:]
                paragraphs.append(p_text)

        full_transcript_text = "\n\n".join(paragraphs) if paragraphs else ""
        transcript_hash = compute_sha256(full_transcript_text)
        manifest_hash = compute_canonical_manifest_hash(video_id, transcript_hash)

        md_content = (
            f"# {title}\n\n"
            f"**Video ID:** `{video_id}`\n"
            f"**URL:** {source_url}\n"
            f"**Speaker:** {speaker}\n"
            f"**Channel:** {channel}\n"
            f"**Quality State:** {q_report.quality_state}\n"
            f"**Quality Score:** {q_report.quality_score:.2f}\n"
            f"**Pipeline Version:** {PIPELINE_VERSION}\n"
            f"**Artifact Manifest Hash:** `{manifest_hash}`\n"
            f"**Transcript Hash:** `{transcript_hash}`\n"
            f"**Fetched:** {datetime.now(timezone.utc).isoformat()}\n\n"
            f"## Transcript\n\n{full_transcript_text}\n"
        )

        # 4. Save JSON and Markdown artifacts
        seg_file = v_dir / "canonical_segments.json"
        seg_file.write_text(
            json.dumps({"video_id": video_id, "segments": [s.model_dump() for s in corrected_segments]}, indent=2)
        )
        q_file = v_dir / "quality_report.json"
        q_file.write_text(q_report.model_dump_json(indent=2))

        ledg_file = v_dir / "correction_ledger.json"
        ledg_file.write_text(
            json.dumps([item.model_dump() for item in all_ledger], indent=2)
        )
        t_file = v_dir / "transcript.md"
        t_file.write_text(md_content, encoding="utf-8")

        # 5. Save ReviewRecord if not trusted
        if q_report.quality_state not in ["trusted", "trusted_after_review"]:
            rev = ReviewRecord(
                video_id=video_id,
                quality_state=q_report.quality_state,
                reason="; ".join(q_report.flags) or f"Quality state: {q_report.quality_state}",
                action_required="Manual inspection of timestamps/source audio before promotion",
                replay_command=f"python3 scripts/ingestion/1_fetch_transcripts_local.py --video-id {video_id}",
            )
            (v_dir / "review_record.json").write_text(rev.model_dump_json(indent=2))

        # 6. Compatibility Projection (strictly for trusted / trusted_after_review)
        if q_report.quality_state in ["trusted", "trusted_after_review"]:
            self.projection_dir.mkdir(parents=True, exist_ok=True)
            (self.projection_dir / f"{video_id}.md").write_text(md_content, encoding="utf-8")

        # 7. Generate Complete Artifact Manifest binding all files
        artifacts_dict = {
            "canonical_segments.json": ArtifactEntry(
                rel_path="canonical_segments.json",
                byte_size=seg_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(seg_file.read_bytes()),
            ),
            "quality_report.json": ArtifactEntry(
                rel_path="quality_report.json",
                byte_size=q_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(q_file.read_bytes()),
            ),
            "correction_ledger.json": ArtifactEntry(
                rel_path="correction_ledger.json",
                byte_size=ledg_file.stat().st_size,
                mime_type="application/json",
                sha256=compute_sha256(ledg_file.read_bytes()),
            ),
            "transcript.md": ArtifactEntry(
                rel_path="transcript.md",
                byte_size=t_file.stat().st_size,
                mime_type="text/markdown",
                sha256=compute_sha256(t_file.read_bytes()),
            ),
        }

        raw_rel_path = "none"
        if raw_source_path:
            try:
                raw_rel_path = str(raw_source_path.relative_to(v_dir))
            except Exception:
                raw_rel_path = str(raw_source_path)

        art_manifest = ArtifactManifest(
            manifest_version="2.0.0",
            pipeline_version=PIPELINE_VERSION,
            video_id=video_id,
            source_url=source_url,
            final_quality_state=q_report.quality_state,
            quality_score=q_report.quality_score,
            manifest_hash=manifest_hash,
            raw_source_attempts=[{
                "tier": corrected_segments[0].source_tier if corrected_segments else "unknown",
                "raw_path": raw_rel_path,
                "sha256": raw_source_hash,
                "status": "success" if corrected_segments else "failed",
            }],
            artifacts=artifacts_dict,
        )
        (v_dir / "artifact_manifest.json").write_text(art_manifest.model_dump_json(indent=2))

        # Legacy manifest for backwards compatibility
        raw_source_hashes = {str(raw_source_path): raw_source_hash} if raw_source_path else {}
        manifest = VideoCorpusManifest(
            video_id=video_id,
            title=title,
            duration_seconds=duration_seconds,
            source_url=source_url,
            playlist_urls=video_info.get("playlist_urls", []),
            raw_source_hashes=raw_source_hashes,
            canonical_segment_count=len(corrected_segments),
            quality_state=q_report.quality_state,
            manifest_hash=manifest_hash,
        )
        (v_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        return manifest
