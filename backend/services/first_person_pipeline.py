"""
Mukthi Guru — First-Person Verbatim Pipeline (Phase F)

Executes the specialized verbatim-serving path behind FIRST_PERSON_MODE.
An answer is the teacher's own recorded words, served as a validated pointer
with exact seconds and speaker identity, never LLM-generated text.

Pipeline Flow:
  1. Crisis/Safety Pre-Check (fails closed to crisis helplines)
  2. Exact-Match Cache Check (exact query hash; strictly NO semantic cache)
  3. Hybrid Retrieval from FirstPersonStore (dense + sparse)
  4. Serve-time Integrity Gate (hash match, allowlisted speaker, no artifacts)
  5. Calibrated Confidence Decision (cosine of query vs top-1 clip):
       - No calibration profile: every non-empty answer is 'weak_match'
       - Confident (>= profile threshold): direct first-person teaching(s)
       - Below threshold: closest clip labeled 'Related, not a direct answer'
  6. Timestamped Citation Formatting & Exact-Cache Population
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import unicodedata
from typing import Any, Optional

import numpy as np

from app.config import settings
from app.metrics import (
    FIRST_PERSON_LATENCY_SECONDS,
    FIRST_PERSON_QUARANTINED_TOTAL,
    FIRST_PERSON_REQUESTS_TOTAL,
)
from services.crisis_helplines import format_helplines_block
from services.first_person_store import FirstPersonStore
from services.serene_mind_engine import DistressLevel, SereneMindEngine
from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)

# Exact cache TTL: 24 hours
EXACT_CACHE_TTL = 86400

# Required, validated keys on a calibration profile JSON.
_PROFILE_REQUIRED_KEYS = {
    "threshold",
    "score_kind",
    "n",
    "ucb_risk",
    "target_risk",
    "collection",
    "fitted_at",
}

# Product risk bound on confident answers (>=99% precision, one-sided 95%).
MAX_TARGET_RISK = 0.01

# Only a serve-time verified single-teacher recording may be quoted.
_ALLOWED_SPEAKERS = {"Sri Preethaji", "Sri Krishnaji"}


def load_calibration_profile(path: str, collection: str) -> Optional[dict[str, Any]]:
    """Load and validate a fitted calibration profile JSON.

    Returns None (logging a warning) unless the file exists, parses, carries
    all required keys, was fitted with cosine scoring against this exact
    collection, and its measured risk is within its own target.
    """
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[FirstPersonPipeline] Could not load calibration profile '%s': %s", path, e)
        return None

    if not _PROFILE_REQUIRED_KEYS.issubset(data.keys()):
        logger.warning(
            "[FirstPersonPipeline] Calibration profile '%s' missing required keys %s",
            path,
            _PROFILE_REQUIRED_KEYS - data.keys(),
        )
        return None
    if data.get("score_kind") != "dense_cosine":
        logger.warning(
            "[FirstPersonPipeline] Calibration profile score_kind '%s' != 'dense_cosine'; ignoring.",
            data.get("score_kind"),
        )
        return None
    if data.get("collection") != collection:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile collection '%s' != live collection '%s'; ignoring.",
            data.get("collection"),
            collection,
        )
        return None
    numeric = ("threshold", "ucb_risk", "target_risk")
    if not all(isinstance(data.get(k), (int, float)) and not isinstance(data.get(k), bool) for k in numeric):
        logger.warning("[FirstPersonPipeline] Calibration profile '%s' has non-numeric %s; ignoring.", path, numeric)
        return None
    # The product bound is 1% risk; a profile cannot relax it by declaring a looser target.
    if data["target_risk"] > MAX_TARGET_RISK:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile target_risk %s exceeds the %s product bound; ignoring.",
            data["target_risk"],
            MAX_TARGET_RISK,
        )
        return None
    if data["ucb_risk"] > data["target_risk"]:
        logger.warning(
            "[FirstPersonPipeline] Calibration profile ucb_risk %s exceeds target_risk %s; ignoring.",
            data.get("ucb_risk"),
            data.get("target_risk"),
        )
        return None
    return data


def _cosine_similarity(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    if not a or not b:
        return 0.0
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _passes_integrity_gate(clip: dict[str, Any]) -> bool:
    """Serve-time gate: hash match, allowlisted speaker, no extraction artifact.

    All three are required. A failing clip is never served.
    """
    verbatim_text = clip.get("verbatim_text") or ""
    transcript_hash = clip.get("transcript_hash") or ""
    speaker = clip.get("speaker")

    if hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest() != transcript_hash:
        return False
    if speaker not in _ALLOWED_SPEAKERS:
        return False
    if find_artifact(verbatim_text) is not None:
        return False
    return True


class FirstPersonPipelineResult:
    """Structured response container for first-person queries."""

    def __init__(
        self,
        answer_text: str,
        citations: list[dict[str, Any]],
        status: str,  # 'success', 'crisis_redirect', 'abstained', 'weak_match', 'error'
        is_direct_answer: bool,
        latency_ms: float,
        cached: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.answer_text = answer_text
        self.citations = citations
        self.status = status
        self.is_direct_answer = is_direct_answer
        self.latency_ms = latency_ms
        self.cached = cached
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_text": self.answer_text,
            "citations": self.citations,
            "status": self.status,
            "is_direct_answer": self.is_direct_answer,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
            "error": self.error,
        }


class FirstPersonPipeline:
    """
    Executes first-person verbatim retrieval, validation, and citation serving.
    """

    def __init__(
        self,
        store: Optional[FirstPersonStore] = None,
        redis_client: Optional[Any] = None,
        serene_mind_engine: Optional[SereneMindEngine] = None,
        calibration_profile: Optional[dict[str, Any]] = None,
    ) -> None:
        self._store = store or FirstPersonStore()
        self._redis = redis_client
        self._serene_mind = serene_mind_engine or SereneMindEngine()
        if calibration_profile is not None:
            self._profile = calibration_profile
        else:
            self._profile = load_calibration_profile(
                getattr(settings, "first_person_calibration_path", ""),
                self._store.collection,
            )

    def _get_exact_cache_key(self, query: str, teacher_id: Optional[str] = None) -> str:
        norm = unicodedata.normalize("NFKC", query).strip().lower()
        t_id = (teacher_id or "both").strip().lower()
        fitted_at = (self._profile or {}).get("fitted_at", "none")
        h = hashlib.sha256(
            f"{norm}:{t_id}:{self._store.collection}:{fitted_at}".encode("utf-8")
        ).hexdigest()
        return f"cache:first_person_exact:{h}"

    def check_exact_cache(self, query: str, teacher_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Query Redis for an exact cached answer. Bypasses semantic cache."""
        if not self._redis:
            return None
        key = self._get_exact_cache_key(query, teacher_id)
        try:
            val = self._redis.get(key)
            if val:
                data = json.loads(val.decode("utf-8") if isinstance(val, bytes) else val)
                # Re-run the integrity gate on cached citations before serving.
                for cit in data.get("citations", []):
                    if not _passes_integrity_gate(
                        {
                            "verbatim_text": cit.get("verbatim_text", ""),
                            "transcript_hash": cit.get("transcript_hash", ""),
                            "speaker": cit.get("speaker"),
                        }
                    ):
                        logger.warning("[FirstPersonPipeline] Cached citation failed integrity re-check; skipping cache.")
                        return None
                logger.info(f"[FirstPersonPipeline] Exact cache HIT for key {key}")
                return data
        except Exception as e:
            logger.warning(f"[FirstPersonPipeline] Redis exact cache lookup failed: {e}")
        return None

    def set_exact_cache(self, query: str, data: dict[str, Any], teacher_id: Optional[str] = None) -> None:
        """Store validated answer into Redis exact cache."""
        if not self._redis:
            return
        key = self._get_exact_cache_key(query, teacher_id)
        try:
            self._redis.set(key, json.dumps(data), ex=EXACT_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[FirstPersonPipeline] Redis exact cache set failed: {e}")

    def _log_and_count(
        self,
        status: str,
        latency_ms: float,
        confidence: float,
        n_quarantined: int,
        n_citations: int,
    ) -> None:
        FIRST_PERSON_REQUESTS_TOTAL.labels(status=status).inc()
        FIRST_PERSON_LATENCY_SECONDS.observe(latency_ms / 1000.0)
        logger.info(
            "[FirstPersonPipeline] status=%s latency_ms=%.1f confidence=%.4f n_quarantined=%d n_citations=%d",
            status,
            latency_ms,
            confidence,
            n_quarantined,
            n_citations,
        )

    def execute(
        self,
        query: str,
        query_dense_vector: list[float],
        query_sparse_vector: Optional[dict[str, Any]] = None,
        teacher_id: Optional[str] = None,
        max_clips: int = 3,
    ) -> FirstPersonPipelineResult:
        """
        Execute the end-to-end first-person verbatim serving pipeline.
        """
        start_time = time.monotonic()

        # Step 1: Crisis Pre-Check (Fails closed to safety redirect)
        # Same pre-emption rule as the chat DistressStage: assess_distress() >= SEVERE.
        # has_crisis_keywords is only a broad pre-screen ("does NOT mean the message is
        # actually crisis-level"); OR-ing it in redirected benign questions.
        distress_assessment = self._serene_mind.assess_distress(query)
        is_crisis = bool(distress_assessment and distress_assessment.level.value >= DistressLevel.SEVERE.value)
        if is_crisis:
            # N4: never log the seeker's words, only the level.
            logger.warning(
                "[FirstPersonPipeline] Crisis pre-emption (distress level %s).", distress_assessment.level.name
            )
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count("crisis_redirect", latency, 0.0, 0, 0)
            return FirstPersonPipelineResult(
                answer_text=format_helplines_block(),
                citations=[],
                status="crisis_redirect",
                is_direct_answer=False,
                latency_ms=latency,
            )

        # Step 2: Check Exact-Match Cache
        cached_data = self.check_exact_cache(query, teacher_id)
        if cached_data:
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count(
                cached_data["status"], latency, 0.0, 0, len(cached_data.get("citations", []))
            )
            return FirstPersonPipelineResult(
                answer_text=cached_data["answer_text"],
                citations=cached_data["citations"],
                status=cached_data["status"],
                is_direct_answer=cached_data["is_direct_answer"],
                latency_ms=latency,
                cached=True,
            )

        # Step 3: Retrieval from FirstPersonStore
        try:
            raw_clips = self._store.search_hybrid(
                query_dense_vector=query_dense_vector,
                query_sparse_vector=query_sparse_vector,
                teacher_id=teacher_id,
                limit=max_clips * 4,
                # spare videos: a clip the integrity gate quarantines is backfilled
                dedup_limit=max_clips * 2,
            )
        except Exception as e:
            logger.error(f"[FirstPersonPipeline] Hybrid retrieval failed: {e}")
            latency = (time.monotonic() - start_time) * 1000.0
            self._log_and_count("error", latency, 0.0, 0, 0)
            return FirstPersonPipelineResult(
                answer_text="An error occurred while retrieving first-person teachings.",
                citations=[],
                status="error",
                is_direct_answer=False,
                latency_ms=latency,
                error=str(e),
            )

        # Step 4: Serve-time Integrity Gate
        verified_clips: list[dict[str, Any]] = []
        n_quarantined = 0
        for clip in raw_clips:
            if _passes_integrity_gate(clip):
                verified_clips.append(clip)
            else:
                n_quarantined += 1
                FIRST_PERSON_QUARANTINED_TOTAL.inc()
                logger.warning(
                    f"[FirstPersonPipeline] Clip {clip.get('point_id')} for video {clip.get('video_id')} "
                    f"failed the serve-time integrity gate. Quarantined from serving."
                )

        verified_clips = verified_clips[:max_clips]

        # Step 5: Abstention check if zero verified clips
        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            logger.info("[FirstPersonPipeline] Zero verified clips found. Honest abstention.")
            self._log_and_count("abstained", latency, 0.0, n_quarantined, 0)
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
            )

        # Step 6: Calibrated Confidence Decision
        # One cosine per clip, reused by the confidence decision, the per-clip filter and the citation.
        clip_scores = [_cosine_similarity(query_dense_vector, c.get("passage_dense")) for c in verified_clips]
        top_clip = verified_clips[0]
        confidence = clip_scores[0]
        is_direct = self._profile is not None and confidence >= self._profile["threshold"]

        citations: list[dict[str, Any]] = []
        answer_parts: list[str] = []

        def _build_citation(clip: dict[str, Any], clip_confidence: float, provenance_kind: str) -> dict[str, Any]:
            sec = clip["start_ms"] // 1000
            video_id = clip["video_id"]
            return {
                "video_id": video_id,
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
                "timestamp_seconds": sec,
                "speaker": clip["speaker"],
                "teacher_id": clip.get("teacher_id"),
                "transcript_hash": clip["transcript_hash"],
                "verbatim_text": clip["verbatim_text"],
                "text_snippet": clip["verbatim_text"],
                # Always derived from the clip's own start: the stored source_url is the
                # plain video URL, which would open playback at 0:00.
                "source_url": f"https://www.youtube.com/watch?v={video_id}&t={sec}s",
                "video_url": clip.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
                "confidence": clip_confidence,
                "is_verbatim": True,
                "provenance_kind": provenance_kind,
                "caption_status": clip.get("caption_status") or "auto_transcript",
            }

        if is_direct:
            status = "success"
            # Each served clip must clear the threshold itself; the top clip's
            # confidence says nothing about clips 2 and 3.
            threshold = self._profile["threshold"]
            confident = [(c, score) for c, score in zip(verified_clips, clip_scores) if score >= threshold]
            for clip, score in confident:
                cit = _build_citation(clip, score, clip.get("provenance_kind", "speech_turn_clip"))
                citations.append(cit)
                answer_parts.append(f'"{clip["verbatim_text"]}"\n— {clip["speaker"]} ({clip["video_id"]}, {cit["timestamp_seconds"]}s)')
            final_text = "\n\n".join(answer_parts)
        else:
            status = "weak_match"
            cit = _build_citation(top_clip, confidence, "weak_match_fallback")
            citations.append(cit)
            final_text = (
                f'Related, not a direct answer:\n\n"{top_clip["verbatim_text"]}"\n'
                f'— {top_clip["speaker"]} ({top_clip["video_id"]}, {cit["timestamp_seconds"]}s)'
            )

        res = FirstPersonPipelineResult(
            answer_text=final_text,
            citations=citations,
            status=status,
            is_direct_answer=is_direct,
            latency_ms=0.0,
        )
        self.set_exact_cache(query, res.to_dict(), teacher_id)

        # Measured last so scoring, citation building and the cache write are all counted.
        res.latency_ms = (time.monotonic() - start_time) * 1000.0
        self._log_and_count(status, res.latency_ms, confidence, n_quarantined, len(citations))
        return res


if __name__ == "__main__":
    # ponytail: minimal self-check, not a full test suite (see tests/test_first_person_pipeline.py)
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine_similarity(None, [1.0]) == 0.0
    text = "Suffering is resistance to what is."
    good_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": good_hash, "speaker": "Sri Preethaji"}
    )
    assert not _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": "0" * 64, "speaker": "Sri Preethaji"}
    )
    assert not _passes_integrity_gate(
        {"verbatim_text": text, "transcript_hash": good_hash, "speaker": "Host"}
    )
    print("first_person_pipeline self-check ok")
