"""
Mukthi Guru — Evidence-Grounded Multi-Video Synthesis & Native Media Composition Engine.

Inspired by master composite teaching formats (e.g. Sadhguru composite master edits,
Netflix Dynamic Sizzles mega-asset architecture, and Ontology-Driven GraphRAG).

Provides:
  1. MediaSegment & CompositionManifest domain data models for multi-source clips.
  2. Dual Serving Modalities:
     - Modality A: YouTube Reference Cards with timestamped links and audio strips.
     - Modality B: Native Video Composition Engine (programmatic FFmpeg filter graph
       generation with click-free 50ms audio cross-fades, video scaling, and
       spiritual diagram / slide overlays for guided practice cues).
  3. Ontology-Guided Pedagogical Sequencing (Obstacle -> Shift -> Practice -> State).
  4. FirstPersonVideoJudge (Multimodal / LLM-as-a-judge for narrative continuity,
     transition cleanliness, and verbatim integrity).
  5. Content-Based Next Teachings Recommendations (Netflix-style recommendation layer).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaSegment:
    """One discrete video/audio segment to be played or stitched."""

    clip_id: str
    video_id: str
    source_url: str
    start_ms: int
    end_ms: int
    speaker: str
    verbatim_text: str
    role: str = "teaching"  # "obstacle", "insight_shift", "practice_invitation", "guided_action", "reflection"
    visual_asset_url: Optional[str] = None
    speaker_verified: bool = False
    rights_cleared: bool = False
    guru_id: str = "unknown"

    def __post_init__(self) -> None:
        if not self.clip_id.strip() or not self.video_id.strip() or not self.source_url.strip():
            raise ValueError("MediaSegment requires clip_id, video_id, and source_url")
        if not self.speaker.strip() or not self.verbatim_text.strip():
            raise ValueError("MediaSegment requires an attributed speaker and verbatim text")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("MediaSegment timestamps must satisfy 0 <= start_ms < end_ms")
        if not isinstance(self.speaker_verified, bool) or not isinstance(self.rights_cleared, bool):
            raise TypeError("MediaSegment speaker_verified and rights_cleared must be booleans")

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    @property
    def start_s(self) -> float:
        return round(self.start_ms / 1000.0, 3)

    @property
    def end_s(self) -> float:
        return round(self.end_ms / 1000.0, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "video_id": self.video_id,
            "source_url": self.source_url,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "speaker": self.speaker,
            "verbatim_text": self.verbatim_text,
            "role": self.role,
            "visual_asset_url": self.visual_asset_url,
            "speaker_verified": self.speaker_verified,
            "rights_cleared": self.rights_cleared,
            "guru_id": self.guru_id,
        }


@dataclass(frozen=True)
class VisualOverlay:
    """Static or animated visual overlay (e.g. spiritual diagram / slide)."""

    asset_url: str
    start_ms: int
    end_ms: int
    position: str = "center"  # "center", "lower_third", "fullscreen"
    animation: str = "ken_burns"  # "ken_burns", "fade_in", "static"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompositionManifest:
    """Complete specification for rendering or stitching a composite answer."""

    composition_id: str
    query: str
    title: str
    segments: list[MediaSegment]
    modality: str = "youtube_cards"  # "youtube_cards" or "stitched_mp4"
    total_duration_ms: int = 0
    audio_crossfade_ms: int = 50
    video_resolution: tuple[int, int] = (1920, 1080)
    video_fps: int = 30
    visual_overlays: list[VisualOverlay] = field(default_factory=list)
    output_format: str = "mp4"

    def __post_init__(self) -> None:
        if not self.total_duration_ms and self.segments:
            self.total_duration_ms = sum(s.duration_ms for s in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "query": self.query,
            "title": self.title,
            "modality": self.modality,
            "segments": [s.to_dict() for s in self.segments],
            "total_duration_ms": self.total_duration_ms,
            "audio_crossfade_ms": self.audio_crossfade_ms,
            "video_resolution": list(self.video_resolution),
            "video_fps": self.video_fps,
            "visual_overlays": [o.to_dict() for o in self.visual_overlays],
            "output_format": self.output_format,
        }


@dataclass(frozen=True)
class CompositionVerdict:
    """Evaluation verdict from FirstPersonVideoJudge."""

    status: str  # "COMPOSITE_APPROVED", "FALLBACK_TO_TOP_SINGLE", "ABSTAIN"
    narrative_continuity_score: float  # 1.0 to 5.0
    transition_cleanliness_score: float  # 1.0 to 5.0
    verbatim_integrity_score: float  # 1.0 to 5.0
    reason: str
    selected_segment_ids: tuple[str, ...] = ()

    @property
    def is_approved(self) -> bool:
        return self.status == "COMPOSITE_APPROVED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "narrative_continuity_score": self.narrative_continuity_score,
            "transition_cleanliness_score": self.transition_cleanliness_score,
            "verbatim_integrity_score": self.verbatim_integrity_score,
            "reason": self.reason,
            "selected_segment_ids": list(self.selected_segment_ids),
            "is_approved": self.is_approved,
        }


# ---------------------------------------------------------------------------
# Pedagogical Role Classification & Ontology Sequencing
# ---------------------------------------------------------------------------

_ROLE_KEYWORDS = {
    "practice_invitation": (
        r"\b(?:let\s+us|let's|close\s+your\s+eyes|breathe|inhale|exhale|sit\s+comfortably|"
        r"move\s+into\s+meditation|observe\s+the\s+breath|step\s+\d|soul\s+sync|ekam\s+meditation)\b"
    ),
    "reflection": (r"\b(?:ask\s+yourself|reflect|contemplate|inward\s+journey|wonder|ponder)\b"),
    "guided_action": (
        r"\b(?:practice|chant|focus|visualize|connect|open\s+your\s+heart|deeksha|blessing)\b"
    ),
    "obstacle": (
        r"\b(?:suffering|anxiety|fear|loneliness|conflict|division|struggle|problem|"
        r"pain|depression|unconscious|ego|hurt|anger|distress|resistance)\b"
    ),
    "insight_shift": (
        r"\b(?:understand|realize|see|witness|observer|shift|consciousness|"
        r"beautiful\s+state|truth|wisdom|dissolve|freedom|clarity|awaken)\b"
    ),
}

_ROLE_ORDER = {
    "obstacle": 1,
    "insight_shift": 2,
    "guided_action": 3,
    "practice_invitation": 4,
    "reflection": 5,
    "teaching": 6,
}


def classify_segment_role(text: str) -> str:
    """Classify the pedagogical role of a clip based on its spiritual teaching function."""
    clean = text.lower()
    for role in ("practice_invitation", "reflection", "guided_action", "obstacle", "insight_shift"):
        pattern = _ROLE_KEYWORDS[role]
        if re.search(pattern, clean, re.IGNORECASE):
            return role
    return "teaching"


def sequence_clips_by_ontology(
    clips: Sequence[dict[str, Any]],
    query: str = "",
) -> list[dict[str, Any]]:
    """Sort clips according to authentic spiritual pedagogical flow:

    Obstacle (Problem/Suffering) -> Insight/Shift (Understanding) ->
    Practice/Action (Meditation Invitation) -> Reflection/State.
    """
    if len(clips) <= 1:
        return list(clips)

    def _sort_key(c: dict[str, Any]) -> tuple[int, int]:
        role = c.get("role") or classify_segment_role(str(c.get("verbatim_text") or ""))
        order = _ROLE_ORDER.get(role, 99)
        # Secondary order preserves high relevance score first
        score = -int(c.get("score", 0) or 0)
        return (order, score)

    return sorted(clips, key=_sort_key)


# ---------------------------------------------------------------------------
# Composition Manifest Builder
# ---------------------------------------------------------------------------


def build_composition_manifest(
    query: str,
    clips: Sequence[dict[str, Any]],
    *,
    title: Optional[str] = None,
    modality: str = "youtube_cards",
    visual_overlays: Optional[Sequence[VisualOverlay | dict[str, Any]]] = None,
    audio_crossfade_ms: int = 50,
) -> CompositionManifest:
    """Construct an authoritative CompositionManifest from retrieved and gated clips."""
    manifest_id = (
        f"comp_{hashlib.sha256((query + str(len(clips))).encode('utf-8')).hexdigest()[:12]}"
    )
    comp_title = title or f"Teaching on {query[:40].strip()}..."

    # Ensure pedagogical ordering
    sequenced = sequence_clips_by_ontology(clips, query)

    segments: list[MediaSegment] = []
    for i, c in enumerate(sequenced):
        cid = str(c.get("point_id") or f"seg_{i}")
        vid = str(c.get("video_id") or "unknown")
        url = str(c.get("source_url") or (f"https://youtu.be/{vid}" if vid != "unknown" else ""))
        start_raw = c.get("audio_start_ms", c.get("start_ms"))
        end_raw = c.get("audio_end_ms", c.get("end_ms"))
        if start_raw is None or end_raw is None:
            raise ValueError(f"Clip {cid!r} is missing source start/end timestamps")
        start_ms = int(start_raw)
        end_ms = int(end_raw)
        speaker = str(c.get("speaker") or "").strip()
        text = str(c.get("verbatim_text") or "").strip()
        role = c.get("role") or classify_segment_role(text)
        vis_url = c.get("visual_asset_url")
        spk_raw = c.get("speaker_verified", False)
        rights_raw = c.get("rights_cleared", False)
        if not isinstance(spk_raw, bool) or not isinstance(rights_raw, bool):
            raise TypeError(f"Clip {cid!r} speaker_verified and rights_cleared must be booleans")
        spk_ok = spk_raw is True
        rights_ok = rights_raw is True
        guru_id = str(c.get("guru_id") or "unknown")

        segments.append(
            MediaSegment(
                clip_id=cid,
                video_id=vid,
                source_url=url,
                start_ms=start_ms,
                end_ms=end_ms,
                speaker=speaker,
                verbatim_text=text,
                role=role,
                visual_asset_url=vis_url,
                speaker_verified=spk_ok,
                rights_cleared=rights_ok,
                guru_id=guru_id,
            )
        )

    norm_overlays: list[VisualOverlay] = []
    if visual_overlays:
        for o in visual_overlays:
            if isinstance(o, VisualOverlay):
                norm_overlays.append(o)
            elif isinstance(o, dict):
                norm_overlays.append(
                    VisualOverlay(
                        asset_url=str(o["asset_url"]),
                        start_ms=int(o["start_ms"]),
                        end_ms=int(o["end_ms"]),
                        position=str(o.get("position", "center")),
                        animation=str(o.get("animation", "ken_burns")),
                    )
                )

    return CompositionManifest(
        composition_id=manifest_id,
        query=query,
        title=comp_title,
        segments=segments,
        modality=modality,
        audio_crossfade_ms=audio_crossfade_ms,
        visual_overlays=norm_overlays,
    )


# ---------------------------------------------------------------------------
# Native Video Stitching (FFmpeg Filter Graph Generation)
# ---------------------------------------------------------------------------


def generate_ffmpeg_concat_filter(
    manifest: CompositionManifest,
    output_path: str = "output.mp4",
) -> str:
    """Generate the exact FFmpeg command string with click-free audio crossfade

    and video standardization for native media composition.

    Architecture highlights:
      - Video standardization: 1920x1080 @ 30fps with aspect-ratio preserving padding.
      - Audio cross-fading: 50ms triangular crossfade (acrossfade=d=0.05:c1=tri:c2=tri)
        to eliminate audio clicks/pops at sentence boundaries.
      - Diagram / slide overlay support for practice guidance.
    """
    if not manifest.segments:
        raise ValueError("Cannot generate FFmpeg command for empty manifest")
    ineligible = [
        segment.clip_id
        for segment in manifest.segments
        if not segment.speaker_verified or not segment.rights_cleared
    ]
    if ineligible:
        raise ValueError(
            "Cannot render media with unverified speakers or uncleared rights: "
            + ", ".join(ineligible)
        )

    inputs: list[str] = []
    v_filters: list[str] = []
    a_filters: list[str] = []

    # Map inputs
    for idx, seg in enumerate(manifest.segments):
        inputs.extend(["-i", seg.source_url or f"video_{idx}.mp4"])

    # Additional visual overlay inputs
    overlay_start_idx = len(manifest.segments)
    for ov in manifest.visual_overlays:
        inputs.extend(["-loop", "1", "-i", ov.asset_url])

    # 1. Video trimming and scaling
    target_w, target_h = manifest.video_resolution
    fps = manifest.video_fps
    cf_s = round(manifest.audio_crossfade_ms / 1000.0, 3)

    for idx, seg in enumerate(manifest.segments):
        start_s = seg.start_s
        end_s = seg.end_s
        v_filters.append(
            f"[{idx}:v]trim=start={start_s}:end={end_s},setpts=PTS-STARTPTS,"
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{idx}];"
        )
        a_filters.append(
            f"[{idx}:a]atrim=start={start_s}:end={end_s},asetpts=PTS-STARTPTS[a{idx}];"
        )

    # 2. Audio crossfade chaining
    # Segments chain: [a0][a1]acrossfade...[a_mix1]; [a_mix1][a2]acrossfade...[a_mix2]
    if len(manifest.segments) == 1:
        last_a = "[a0]"
    else:
        last_a = "[a0]"
        for idx in range(1, len(manifest.segments)):
            next_mix = f"[amix_{idx}]" if idx < len(manifest.segments) - 1 else "[outa]"
            a_filters.append(f"{last_a}[a{idx}]acrossfade=d={cf_s}:c1=tri:c2=tri{next_mix};")
            last_a = next_mix

    # 3. Visual overlays
    v_labels = [f"[v{i}]" for i in range(len(manifest.segments))]
    for k, ov in enumerate(manifest.visual_overlays):
        ov_input_idx = overlay_start_idx + k
        # Find which segment this overlay belongs to
        ov_start_s = round(ov.start_ms / 1000.0, 3)
        ov_end_s = round(ov.end_ms / 1000.0, 3)
        target_v = v_labels[0]  # default to first segment if not specified
        v_filters.append(
            f"[{ov_input_idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[ov_{k}];"
            f"{target_v}[ov_{k}]overlay=(W-w)/2:(H-h)/2:enable='between(t,{ov_start_s},{ov_end_s})'[v_ov_{k}];"
        )
        v_labels[0] = f"[v_ov_{k}]"

    # 4. Video Concat
    v_concat_inputs = "".join(v_labels)
    v_concat = f"{v_concat_inputs}concat=n={len(manifest.segments)}:v=1:a=0[outv];"

    full_filter = "".join(v_filters) + "".join(a_filters) + v_concat
    # Strip trailing semicolon for FFmpeg
    if full_filter.endswith(";"):
        full_filter = full_filter[:-1]

    cmd_parts = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        f'"{full_filter}"',
        "-map",
        '"[outv]"',
        "-map",
        '"[outa]"' if len(manifest.segments) > 1 else '"[a0]"',
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_path,
    ]
    return " ".join(cmd_parts)


# ---------------------------------------------------------------------------
# Multimodal / LLM-as-a-Judge for Video Continuity (FirstPersonVideoJudge)
# ---------------------------------------------------------------------------


class FirstPersonVideoJudge:
    """Evaluates narrative continuity, transition cleanliness, and attribution integrity

    across multiple video segments being stitched together.
    """

    def __init__(self, llm_service: Optional[Any] = None) -> None:
        self.llm = llm_service

    async def judge_composition(
        self,
        manifest: CompositionManifest,
    ) -> CompositionVerdict:
        """Evaluate whether the composite manifest should be served as a unified video."""
        if not manifest.segments:
            return CompositionVerdict(
                status="ABSTAIN",
                narrative_continuity_score=0.0,
                transition_cleanliness_score=0.0,
                verbatim_integrity_score=0.0,
                reason="no_segments_in_manifest",
            )

        # Every modality, including a one-clip result, must pass the same
        # speaker and rights contract before it can be approved or rendered.
        ineligible_reasons: set[str] = set()
        eligible_segments = []
        for segment in manifest.segments:
            segment_ok = True
            if not segment.speaker_verified:
                ineligible_reasons.add("unverified_speaker")
                segment_ok = False
            if not segment.rights_cleared:
                ineligible_reasons.add("rights_not_cleared")
                segment_ok = False
            if segment_ok:
                eligible_segments.append(segment)

        if len(eligible_segments) != len(manifest.segments):
            reason = "source_gate:" + ",".join(sorted(ineligible_reasons))
            if eligible_segments:
                logger.info(
                    "[FirstPersonVideoJudge] Falling back to one eligible segment; "
                    "%d/%d segments failed source gates",
                    len(manifest.segments) - len(eligible_segments),
                    len(manifest.segments),
                )
                return CompositionVerdict(
                    status="FALLBACK_TO_TOP_SINGLE",
                    narrative_continuity_score=3.0,
                    transition_cleanliness_score=3.0,
                    verbatim_integrity_score=3.0,
                    reason=reason,
                    selected_segment_ids=(eligible_segments[0].clip_id,),
                )
            return CompositionVerdict(
                status="ABSTAIN",
                narrative_continuity_score=0.0,
                transition_cleanliness_score=0.0,
                verbatim_integrity_score=0.0,
                reason=reason,
                selected_segment_ids=(),
            )

        if len(manifest.segments) == 1:
            seg = manifest.segments[0]
            return CompositionVerdict(
                status="COMPOSITE_APPROVED",
                narrative_continuity_score=5.0,
                transition_cleanliness_score=5.0,
                verbatim_integrity_score=5.0,
                reason="single_source_sufficient",
                selected_segment_ids=(seg.clip_id,),
            )

        # Build prompt for LLM judge
        if self.llm is not None and hasattr(self.llm, "generate"):
            system_prompt = (
                "You are an expert video editor and spiritual discourse evaluator judging "
                "a multi-clip composite answer. Score three dimensions from 1.0 to 5.0:\n"
                "- narrative_continuity: Does the sequence flow logically as a coherent teaching?\n"
                "- transition_cleanliness: Are cut points natural without mid-sentence chops?\n"
                "- verbatim_integrity: Does each segment maintain authentic teacher voice?\n"
                'Reply with a JSON object: {"narrative_continuity": 4.5, "transition_cleanliness": 4.0, '
                '"verbatim_integrity": 5.0, "status": "COMPOSITE_APPROVED", "reason": "..."}'
            )
            segments_summary = "\n".join(
                f'[{i + 1}] ({s.speaker} - {s.role}): "{s.verbatim_text[:120]}..."'
                for i, s in enumerate(manifest.segments)
            )
            user_prompt = f"Query: {manifest.query}\nClips:\n{segments_summary}"

            try:
                res = self.llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
                if inspect.isawaitable(res):
                    res = await res
                raw = str(res).strip()
                # Parse JSON
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    required_fields = (
                        "narrative_continuity",
                        "transition_cleanliness",
                        "verbatim_integrity",
                        "status",
                    )
                    if any(field not in parsed for field in required_fields):
                        return self._fallback_to_single(
                            manifest,
                            reason="llm_judge_incomplete_response",
                        )
                    raw_scores = (
                        parsed["narrative_continuity"],
                        parsed["transition_cleanliness"],
                        parsed["verbatim_integrity"],
                    )
                    if any(
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        for value in raw_scores
                    ):
                        return self._fallback_to_single(
                            manifest,
                            reason="llm_judge_invalid_score_types",
                        )
                    narrative, transition, integrity = (float(value) for value in raw_scores)
                    status = str(parsed["status"]).strip().upper()
                    reason = str(parsed.get("reason") or "llm_judged")[:240]
                    scores = (narrative, transition, integrity)
                    if any(not math.isfinite(score) or not 1.0 <= score <= 5.0 for score in scores):
                        return self._fallback_to_single(
                            manifest,
                            reason="llm_judge_invalid_scores",
                        )
                    if status not in {"COMPOSITE_APPROVED", "FALLBACK_TO_TOP_SINGLE", "ABSTAIN"}:
                        return self._fallback_to_single(
                            manifest,
                            reason="llm_judge_invalid_status",
                            scores=scores,
                        )
                    selected_ids = (
                        tuple(s.clip_id for s in manifest.segments)
                        if status == "COMPOSITE_APPROVED"
                        else (manifest.segments[0].clip_id,)
                        if status == "FALLBACK_TO_TOP_SINGLE"
                        else ()
                    )
                    return CompositionVerdict(
                        status=status,
                        narrative_continuity_score=narrative,
                        transition_cleanliness_score=transition,
                        verbatim_integrity_score=integrity,
                        reason=reason,
                        selected_segment_ids=selected_ids,
                    )
            except Exception as e:
                logger.debug("[FirstPersonVideoJudge] LLM evaluation exception: %s", e)
                return self._fallback_to_single(
                    manifest,
                    reason="llm_judge_unavailable",
                )

        # A sentence-ending heuristic cannot certify multi-source narrative
        # continuity or verbatim integrity. Without a valid judge verdict, keep
        # only the best already-gated source instead of approving a composite.
        return self._fallback_to_single(
            manifest,
            reason="llm_judge_unavailable",
        )

    @staticmethod
    def _fallback_to_single(
        manifest: CompositionManifest,
        *,
        reason: str,
        scores: tuple[float, float, float] = (3.0, 3.0, 3.0),
    ) -> CompositionVerdict:
        return CompositionVerdict(
            status="FALLBACK_TO_TOP_SINGLE",
            narrative_continuity_score=scores[0],
            transition_cleanliness_score=scores[1],
            verbatim_integrity_score=scores[2],
            reason=reason,
            selected_segment_ids=(manifest.segments[0].clip_id,),
        )


# ---------------------------------------------------------------------------
# Content-Based Next Teachings Recommendations (Netflix-style)
# ---------------------------------------------------------------------------


def recommend_next_teachings(
    current_clips: Sequence[dict[str, Any]],
    available_pool: Optional[Sequence[dict[str, Any]]] = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Recommend 2-3 contextual next teachings/practices based on the concepts

    in the currently served clips (Netflix-style personalized discovery).
    """
    if not available_pool or not current_clips:
        return []

    used_video_ids = {str(c.get("video_id")) for c in current_clips}
    candidates = [c for c in available_pool if str(c.get("video_id")) not in used_video_ids]
    if not candidates:
        return []

    # Sort by relevance score, prioritizing practice invitations or complementary roles
    def _rec_score(c: dict[str, Any]) -> float:
        base = float(c.get("score", 0.0) or 0.0)
        text = str(c.get("verbatim_text") or "")
        if "meditation" in text.lower() or "practice" in text.lower():
            base += 0.5
        return base

    ranked = sorted(candidates, key=_rec_score, reverse=True)
    out: list[dict[str, Any]] = []
    for c in ranked[:limit]:
        out.append(
            {
                "video_id": c.get("video_id"),
                "title": c.get("title") or c.get("video_title") or "Related Teaching",
                "speaker": c.get("speaker"),
                "role": c.get("role") or classify_segment_role(str(c.get("verbatim_text") or "")),
                "url": f"https://youtu.be/{c.get('video_id')}" if c.get("video_id") else "",
                "preview_text": (str(c.get("verbatim_text") or "")[:140] + "..."),
            }
        )
    return out
