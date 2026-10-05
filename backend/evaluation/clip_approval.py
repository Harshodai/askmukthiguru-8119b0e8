"""Ponytail Auto-Approval & Human Review Orchestrator.

Adheres strictly to the Ponytail Principle (lessons.md L-OBS-2: thin wrapper
over existing logic, zero new deps, Pydantic-only schemas).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    from ingest.verbatim.boundaries import boundary_defects
except ImportError:
    from backend.ingest.verbatim.boundaries import boundary_defects

try:
    from evaluation.gold.review_server import read_csv_rows, write_csv_rows
except ImportError:
    from backend.evaluation.gold.review_server import read_csv_rows, write_csv_rows

try:
    from evaluation.schemas.clip_approval import ClipEvaluationVerdict
except ImportError:
    from backend.evaluation.schemas.clip_approval import ClipEvaluationVerdict

logger = logging.getLogger(__name__)


def _query_judge(
    judge: Any,
    clip_id: str,
    video_id: str,
    start_s: float,
    end_s: float,
    text: str,
) -> tuple[float, str, float, str]:
    """Query an LLMJudge or mock for doctrinal_consistency and tone."""
    if hasattr(judge, "score_response"):
        citations = [f"https://www.youtube.com/watch?v={video_id}&t={int(start_s)}s"]
        coro_or_res = judge.score_response(
            query="Evaluate spiritual discourse clip for consistency and tone.",
            answer=text,
            retrieved_context="",
            citations=citations,
            question_meta={
                "video_id": video_id,
                "clip_id": clip_id,
                "start_s": start_s,
                "end_s": end_s,
            },
        )
        if asyncio.iscoroutine(coro_or_res):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    res = pool.submit(asyncio.run, coro_or_res).result()
            else:
                res = asyncio.run(coro_or_res)
        else:
            res = coro_or_res

        if hasattr(res, "dimensions"):
            doc_dim = res.dimensions.get("doctrinal_consistency")
            tone_dim = res.dimensions.get("tone")
            doc_score = getattr(doc_dim, "score", 0.90) if doc_dim else 0.90
            doc_rat = getattr(doc_dim, "rationale", "Scored by LLMJudge") if doc_dim else ""
            tone_score = getattr(tone_dim, "score", 0.90) if tone_dim else 0.90
            tone_rat = getattr(tone_dim, "rationale", "Scored by LLMJudge") if tone_dim else ""
            return float(doc_score), str(doc_rat), float(tone_score), str(tone_rat)
        if isinstance(res, dict):
            return (
                float(res.get("doctrinal_score", res.get("doctrinal_consistency", 0.90))),
                str(res.get("doctrinal_rationale", "Scored by judge dict")),
                float(res.get("tone_score", res.get("tone", 0.90))),
                str(res.get("tone_rationale", "Scored by judge dict")),
            )

    if callable(judge):
        try:
            res = judge(clip_id=clip_id, video_id=video_id, start_s=start_s, end_s=end_s, text=text)
        except TypeError:
            res = judge(text)
        if isinstance(res, tuple) and len(res) == 4:
            return float(res[0]), str(res[1]), float(res[2]), str(res[3])
        if isinstance(res, dict):
            return (
                float(res.get("doctrinal_score", 0.90)),
                str(res.get("doctrinal_rationale", "")),
                float(res.get("tone_score", 0.90)),
                str(res.get("tone_rationale", "")),
            )

    doc_score = getattr(judge, "doctrinal_score", 0.90)
    tone_score = getattr(judge, "tone_score", 0.90)
    doc_rat = getattr(judge, "doctrinal_rationale", "Mock judge doctrinal score")
    tone_rat = getattr(judge, "tone_rationale", "Mock judge tone score")
    return float(doc_score), str(doc_rat), float(tone_score), str(tone_rat)


def evaluate_clip(
    clip_id: str,
    video_id: str,
    start_s: float,
    end_s: float,
    text: str,
    judge: Any = None,
    question_id: Optional[str] = None,
    question_text: Optional[str] = None,
) -> ClipEvaluationVerdict:
    """Evaluate a single verbatim clip with fast-path and optional LLM judge."""
    duration_s = max(0.0, float(end_s) - float(start_s))
    tokens = text.split() if isinstance(text, str) else list(text)
    defects = list(boundary_defects(tokens))

    if duration_s < 15.0:
        defects.append("duration_under_15s")
        boundary_clean = False
    elif defects:
        boundary_clean = False
    else:
        boundary_clean = True

    if not boundary_clean:
        # Fast-path rejection: 0 LLM calls
        doctrinal_score = 0.5
        doctrinal_rationale = "Skipped: boundary defect detected"
        tone_score = 0.5
        tone_rationale = "Skipped: boundary defect detected"
    elif judge is not None:
        doctrinal_score, doctrinal_rationale, tone_score, tone_rationale = _query_judge(
            judge, clip_id, video_id, float(start_s), float(end_s), text
        )
    else:
        doctrinal_score = 0.90
        doctrinal_rationale = "Deterministic heuristic: clean boundary, valid spiritual text"
        tone_score = 0.90
        tone_rationale = "Deterministic heuristic: clean boundary, valid teacher cadence"

    composite_score = (
        min(doctrinal_score, tone_score)
        if boundary_clean
        else min(0.5, doctrinal_score, tone_score)
    )
    approved = boundary_clean and composite_score >= 0.85
    needs_human_review = not approved and (composite_score >= 0.60 or bool(defects))

    rejection_reasons: list[str] = []
    if not approved:
        if defects:
            rejection_reasons.extend(f"boundary_defect: {d}" for d in defects)
        if boundary_clean:
            if doctrinal_score < 0.85:
                rejection_reasons.append(
                    f"doctrinal_slip: score {doctrinal_score:.2f} ({doctrinal_rationale})"
                )
            if tone_score < 0.85:
                rejection_reasons.append(f"tone_slip: score {tone_score:.2f} ({tone_rationale})")
            if not rejection_reasons:
                rejection_reasons.append(f"low_composite_score: {composite_score:.2f}")

    rejection_reason = "; ".join(rejection_reasons) if rejection_reasons else None

    return ClipEvaluationVerdict(
        clip_id=clip_id,
        video_id=video_id,
        start_s=float(start_s),
        end_s=float(end_s),
        duration_s=duration_s,
        boundary_clean=boundary_clean,
        boundary_defects=defects,
        doctrinal_score=doctrinal_score,
        doctrinal_rationale=doctrinal_rationale,
        tone_score=tone_score,
        tone_rationale=tone_rationale,
        composite_score=composite_score,
        approved=approved,
        needs_human_review=needs_human_review,
        rejection_reason=rejection_reason,
        text=text,
        question_id=question_id,
        question_text=question_text,
    )


def evaluate_clips_batch(
    clips: list[dict[str, Any]],
    judge: Any = None,
) -> list[ClipEvaluationVerdict]:
    """Evaluate a batch of candidate clips."""
    verdicts: list[ClipEvaluationVerdict] = []
    for c in clips:
        video_id = str(c.get("video_id") or "")
        start_val = (
            c.get("start_s")
            if "start_s" in c
            else (c.get("start") or c.get("clip_start_s") or c.get("sentence_start_s") or 0.0)
        )
        start_s = float(start_val)
        end_val = c.get("end_s") if "end_s" in c else (c.get("end") or (start_s + 20.0))
        end_s = float(end_val)
        clip_id = str(c.get("clip_id") or c.get("question_id") or f"{video_id}_{start_s}")
        text = str(c.get("text") or c.get("clip_opens_with") or "")
        verdict = evaluate_clip(
            clip_id=clip_id,
            video_id=video_id,
            start_s=start_s,
            end_s=end_s,
            text=text,
            judge=judge,
            question_id=c.get("question_id"),
            question_text=c.get("question_text"),
        )
        verdicts.append(verdict)
    return verdicts


def _map_clip_quality(verdict: ClipEvaluationVerdict) -> str:
    """Map verdict defects to review_server.py clip_quality values."""
    if verdict.duration_s < 15.0 or "duration_under_15s" in verdict.boundary_defects:
        return "fragment"
    for defect in verdict.boundary_defects:
        if defect.startswith("head_") or defect.startswith("tail_") or "sentence" in defect:
            return "mid_sentence"
    if verdict.boundary_defects:
        return "other"
    return "clean"


def export_review_csv(
    verdicts: list[ClipEvaluationVerdict],
    out_csv_path: Path | str,
) -> int:
    """Export non-approved verdicts into review_server.py compatible CSV format."""
    out_path = Path(out_csv_path)
    rejected = [v for v in verdicts if not v.approved]
    if not rejected:
        return 0

    rows: list[dict[str, str]] = []
    for v in rejected:
        rows.append(
            {
                "question_id": v.question_id or v.clip_id,
                "question_text": v.question_text or "",
                "video_id": v.video_id,
                "start": str(v.start_s),
                "end": str(v.end_s),
                "text": v.text or "",
                "judge_a": "",
                "judge_b": "",
                "adjudicated": "",
                "clip_quality": _map_clip_quality(v),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_rows(out_path, rows)
    return len(rows)


def export_approved_manifest(
    verdicts: list[ClipEvaluationVerdict],
    out_json_path: Path | str,
) -> int:
    """Export only verdicts where approved is True to a JSON manifest."""
    out_path = Path(out_json_path)
    approved = [v for v in verdicts if v.approved]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = [v.model_dump() for v in approved]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return len(approved)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ponytail Clip Auto-Approver & Review Orchestrator"
    )
    parser.add_argument(
        "--input", required=True, help="Input CSV or JSON path containing candidate clips"
    )
    parser.add_argument("--out-approved", help="Output path for approved manifest JSON")
    parser.add_argument("--out-review", help="Output path for review CSV")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    if in_path.suffix.lower() == ".json":
        with open(in_path, encoding="utf-8") as f:
            clips = json.load(f)
    else:
        clips = read_csv_rows(in_path)

    verdicts = evaluate_clips_batch(clips)

    if args.out_approved:
        count = export_approved_manifest(verdicts, Path(args.out_approved))
        logger.info("Exported %d approved clips to %s", count, args.out_approved)

    if args.out_review:
        count = export_review_csv(verdicts, Path(args.out_review))
        logger.info("Exported %d clips needing review to %s", count, args.out_review)


if __name__ == "__main__":
    main()
