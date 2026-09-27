"""
Mukthi Guru — First-Person Selective Risk Calibration CLI (Phase 3)

Fits a SelectiveRiskCalibrator (SGR / Learn-then-Test) on human-adjudicated
gold evaluation labels using the exact score computed by FirstPersonPipeline
(score_kind="dense_cosine") against the target collection.

Outputs first_person_calibration.json matching all _PROFILE_REQUIRED_KEYS:
  - threshold: float
  - score_kind: "dense_cosine"
  - n: int
  - ucb_risk: float
  - target_risk: float
  - collection: str
  - fitted_at: ISO-8601 UTC

Guarantees:
  1. Scores are computed via FirstPersonPipeline.execute() with the exact query
     vectors (dense + sparse) and clip parameters used by the API route.
  2. B1 gold labels only: requires two agreeing judges or an authoritative
     adjudication. Single-judge pilot mode is behind an explicit flag and
     NEVER writes a loadable profile (exits with code 2).
  3. Rejects silver / synthetic / LLM-generated labels.
  4. Refuses to write a loadable profile if sample size is insufficient
     (n < 299 for 0 errors) or UCB risk > target_risk. Exits with code 2.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Optional

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from evaluation.gold.calibrator import SelectiveRiskCalibrator
from evaluation.gold.metrics import passage_hits_ranges

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def resolve_human_label(row: dict[str, str], allow_single_judge: bool = False) -> Optional[int]:
    """Resolve human label from a CSV row per B1 gold-set protocol.

    Precedence:
      1. Adjudicated label takes top precedence if non-empty.
      2. If unadjudicated, judge_a and judge_b must agree. Disagreement without
         adjudication is marked as disputed and returns None (cannot be used).
      3. If single judge evaluated (pilot), that judge is used ONLY if
         allow_single_judge is True. Otherwise returns None (strict B1 requirement).
      4. Any row marked as silver/synthetic/model-generated raises ValueError.

    Returns:
        1 for relevant / yes
        0 for irrelevant / no
        None if unlabeled or unresolved dispute
    """
    # Strict anti-contamination check (CLAUDE.md invariant 3)
    for key in ("author", "notes", "type", "source", "status", "silver_label"):
        val = str(row.get(key, "")).lower()
        if "silver" in val or "synthetic" in val or "llm_generated" in val:
            raise ValueError(
                f"Forbidden AI/silver label detected in row question_id={row.get('question_id')}: {key}='{val}'"
            )

    adjudicated = row.get("adjudicated", "").strip().lower()
    if adjudicated:
        if adjudicated in ("yes", "1", "true"):
            return 1
        elif adjudicated in ("no", "0", "false"):
            return 0
        return None

    ja = row.get("judge_a", "").strip().lower()
    jb = row.get("judge_b", "").strip().lower()

    if ja and jb:
        val_a = 1 if ja in ("yes", "1", "true") else (0 if ja in ("no", "0", "false") else None)
        val_b = 1 if jb in ("yes", "1", "true") else (0 if jb in ("no", "0", "false") else None)
        if val_a is not None and val_a == val_b:
            return val_a
        # Disputed without adjudication -> cannot use as gold evidence
        return None

    if allow_single_judge:
        single = ja or jb
        if single in ("yes", "1", "true"):
            return 1
        elif single in ("no", "0", "false"):
            return 0

    return None


def load_and_validate_gold_csv(
    csv_path: Path,
    allow_single_judge: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Loads gold relevance CSV and validates that all labels are human-authored.

    Returns:
        questions: list of distinct questions with question_id and question_text
        candidates_by_q: dict mapping question_id to list of evaluated candidate dicts
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    questions_map: dict[str, str] = {}
    candidates_by_q: dict[str, list[dict[str, Any]]] = {}

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q_id = row.get("question_id", "").strip()
            q_text = row.get("question_text", "").strip()
            if not q_id or not q_text:
                continue
            questions_map[q_id] = q_text

            label = resolve_human_label(row, allow_single_judge=allow_single_judge)
            if label is None:
                continue

            candidates_by_q.setdefault(q_id, []).append({
                "clip_id": row.get("clip_id", "").strip(),
                "video_id": row.get("video_id", "").strip(),
                "start": float(row.get("start", 0.0) or 0.0),
                "end": float(row.get("end", 0.0) or 0.0),
                "text": row.get("text", "").strip(),
                "label": label,
                "equivalent_group": row.get("equivalent_group", "").strip(),
            })

    questions = [{"question_id": qid, "question_text": qtext} for qid, qtext in questions_map.items()]
    return questions, candidates_by_q


def score_questions_with_pipeline(
    questions: list[dict[str, Any]],
    collection: str,
    pipeline: Optional[Any] = None,
    embedder: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Runs questions through FirstPersonPipeline.execute() matching the served API route.

    Builds query dense and sparse vectors via EmbeddingService, passes them to
    pipeline.execute(), and extracts the top-1 clip confidence and metadata.
    """
    if pipeline is None:
        from services.embedding_service import EmbeddingService
        from services.first_person_pipeline import FirstPersonPipeline
        from services.first_person_store import FirstPersonStore

        store = FirstPersonStore(collection=collection)
        embedder = EmbeddingService() if embedder is None else embedder
        pipeline = FirstPersonPipeline(store=store)
    elif embedder is None:
        embedder = getattr(pipeline, "_embedder", None)
        if embedder is None:
            from services.embedding_service import EmbeddingService
            embedder = EmbeddingService()

    # Score the raw top clip. An already-fitted profile would make execute() return only
    # clips above the OLD threshold, so citations[0] would stop being the top clip and
    # a re-fit would be scored against its own predecessor.
    pipeline._profile = None

    scored_items: list[dict[str, Any]] = []
    for q in questions:
        q_text = q["question_text"]

        # 1. Build dense and sparse query vectors exactly like the served API route
        # (backend/app/api/first_person.py:100-111)
        encoded = embedder.encode_single_full(q_text)
        dense_vec = encoded["dense"]
        raw_sparse = encoded.get("sparse") or {}
        sparse_vec = (
            {"indices": list(raw_sparse.keys()), "values": list(raw_sparse.values())}
            if raw_sparse
            else None
        )

        # 2. Call pipeline.execute() with identical parameters as the served route
        result = pipeline.execute(
            query=q_text,
            query_dense_vector=dense_vec,
            query_sparse_vector=sparse_vec,
            teacher_id="both",
            max_clips=3,
        )

        # 3. Read top-1 clip and its confidence directly from the pipeline result
        if not result.citations:
            scored_items.append({
                "question_id": q["question_id"],
                "score": 0.0,
                "top1_clip_id": None,
                "top1_video_id": None,
                "top1_start": None,
                "top1_end": None,
            })
            continue

        top_cit = result.citations[0]
        scored_items.append({
            "question_id": q["question_id"],
            "score": float(top_cit["confidence"]),
            "top1_clip_id": top_cit.get("point_id") or top_cit.get("clip_id"),
            "top1_video_id": top_cit.get("video_id"),
            "top1_start": float(top_cit.get("start_ms", 0)) / 1000.0 if top_cit.get("start_ms") is not None else None,
            "top1_end": float(top_cit.get("end_ms", 0)) / 1000.0 if top_cit.get("end_ms") is not None else None,
        })

    return scored_items


def evaluate_predictions_against_gold(
    predictions: list[dict[str, Any]],
    candidates_by_q: dict[str, list[dict[str, Any]]],
) -> tuple[list[float], list[int]]:
    """Compares top-1 predictions against gold candidate judgments to produce (scores, labels)."""
    scores: list[float] = []
    labels: list[int] = []

    for pred in predictions:
        qid = pred["question_id"]
        candidates = candidates_by_q.get(qid, [])
        if not candidates:
            continue

        score = float(pred["score"])
        top_vid = pred.get("top1_video_id")
        top_start = pred.get("top1_start")
        top_end = pred.get("top1_end")
        top_cid = pred.get("top1_clip_id")

        if not top_vid or top_start is None or top_end is None:
            # Retriever abstained or returned nothing
            scores.append(score)
            labels.append(0)
            continue

        pred_clip = {"video_id": top_vid, "start": top_start, "end": top_end}

        positive_candidates = [c for c in candidates if c["label"] == 1]
        if not positive_candidates:
            # Question is unanswerable; serving a clip is an error
            scores.append(score)
            labels.append(0)
            continue

        # Collect all positive clip_ids and equivalent groups (B1 protocol)
        pos_clip_ids = {c["clip_id"] for c in positive_candidates if c.get("clip_id")}
        pos_eq_groups = {c["equivalent_group"] for c in positive_candidates if c.get("equivalent_group")}

        # Any candidate in the question with a matching equivalent group is also an acceptable target
        for c in candidates:
            if c.get("equivalent_group") and c["equivalent_group"] in pos_eq_groups:
                if c.get("clip_id"):
                    pos_clip_ids.add(c["clip_id"])

        is_correct = False
        if top_cid and top_cid in pos_clip_ids:
            is_correct = True
        else:
            pos_ranges = [
                {"video_id": c["video_id"], "start": c["start"], "end": c["end"]}
                for c in candidates
                if c["label"] == 1 or (c.get("equivalent_group") and c["equivalent_group"] in pos_eq_groups)
            ]
            if passage_hits_ranges(pred_clip, pos_ranges, threshold=0.5):
                is_correct = True

        scores.append(score)
        labels.append(1 if is_correct else 0)

    return scores, labels


def load_pipeline_scores_file(
    file_path: Path,
    expected_collection: str,
) -> tuple[list[float], list[int]]:
    """Loads pre-computed pipeline scores file and strictly verifies collection and score_kind."""
    if not file_path.exists():
        raise FileNotFoundError(f"Pipeline scores file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("collection") != expected_collection:
        raise ValueError(
            f"Collection mismatch in pipeline scores file: '{data.get('collection')}' != live collection '{expected_collection}'"
        )
    if data.get("score_kind") != "dense_cosine":
        raise ValueError(
            f"score_kind mismatch in pipeline scores file: '{data.get('score_kind')}' != 'dense_cosine'"
        )

    items = data.get("scores") or data.get("items") or []
    if not items:
        raise ValueError("Pipeline scores file contains no scored items.")

    scores: list[float] = []
    labels: list[int] = []
    for item in items:
        scores.append(float(item["score"]))
        labels.append(int(item["label"]))

    return scores, labels


def run_calibration(
    csv_path: Path,
    collection: str,
    output_path: Path,
    diagnostic_path: Optional[Path] = None,
    target_risk: float = 0.01,
    delta: float = 0.05,
    allow_single_judge_pilot: bool = False,
    pipeline_scores_file: Optional[Path] = None,
    pipeline_instance: Optional[Any] = None,
    embedder_instance: Optional[Any] = None,
    dry_run: bool = False,
) -> int:
    """Core calibration routine.

    Returns:
        0 on success (profile written and validated).
        1 on invalid arguments or runtime errors.
        2 on insufficient sample size, risk bound failure, or single-judge pilot mode
          (loadable profile is strictly withheld).
    """
    if target_risk > 0.01:
        logger.error(f"target_risk {target_risk} exceeds maximum product bound 0.01 (>=99% precision required).")
        return 1

    # Step 1: Obtain scores and labels
    if pipeline_scores_file is not None:
        logger.info(f"Loading pipeline scores from {pipeline_scores_file} (collection={collection})")
        scores, labels = load_pipeline_scores_file(pipeline_scores_file, expected_collection=collection)
    else:
        logger.info(f"Loading and validating gold CSV from {csv_path} (allow_single_judge={allow_single_judge_pilot})")
        questions, candidates_by_q = load_and_validate_gold_csv(
            csv_path=csv_path,
            allow_single_judge=allow_single_judge_pilot,
        )
        logger.info(f"Found {len(questions)} distinct questions with valid human judgments.")
        if not questions:
            logger.error("No valid questions found with human judgments.")
            return 1

        logger.info(f"Scoring questions through FirstPersonPipeline.execute() against collection='{collection}'")
        predictions = score_questions_with_pipeline(
            questions=questions,
            collection=collection,
            pipeline=pipeline_instance,
            embedder=embedder_instance,
        )
        scores, labels = evaluate_predictions_against_gold(predictions, candidates_by_q)

    n_samples = len(labels)
    n_errors = sum(1 for y in labels if y == 0)
    logger.info(
        f"Calibration dataset assembled: n={n_samples}, errors={n_errors}, "
        f"empirical_precision={((n_samples - n_errors) / n_samples if n_samples else 0.0):.4f}"
    )

    if n_samples == 0:
        logger.error("No evaluated samples available for calibration.")
        return 1

    # Guard: Single-judge pilot mode must NEVER produce a loadable profile
    if allow_single_judge_pilot:
        logger.warning(
            "[RunCalibration] Running in single-judge pilot mode (--allow-single-judge-pilot). "
            "Per B1 protocol, single-judge data is for diagnostic inspection only and MUST NEVER "
            "produce a production-loadable profile."
        )
        if diagnostic_path is not None:
            diag_data = {
                "status": "single_judge_unadjudicated_pilot",
                "n": n_samples,
                "n_errors": n_errors,
                "collection": collection,
                "score_kind": "dense_cosine",
                "target_risk": target_risk,
                "delta": delta,
                "warning": "Single-judge pilot data cannot produce a loadable profile (B1 protocol requires two judges + adjudication)",
                "fitted_at": datetime.now(timezone.utc).isoformat(),
            }
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostic_path.write_text(json.dumps(diag_data, indent=2), encoding="utf-8")
            logger.info(f"[RunCalibration] Wrote uncalibrated pilot diagnostic to {diagnostic_path}")

        print("FAILED: Single-judge pilot data cannot produce a production-loadable profile. Diagnostic output only.")
        return 2

    # Step 2: Fit SelectiveRiskCalibrator (Learn-then-Test with Clopper-Pearson)
    calibrator = SelectiveRiskCalibrator(scores=scores, labels=labels)
    point = calibrator.find_operating_threshold(target_risk=target_risk, delta=delta)

    # Step 3: Handle Failure (Insufficient samples / UCB risk > target_risk)
    if point is None:
        logger.warning(
            f"[RunCalibration] No operating threshold satisfies UCB risk <= {target_risk} with delta={delta}. "
            f"Dataset has {n_samples} items. Clopper-Pearson exact bound requires n >= 299 for 0 errors."
        )
        if diagnostic_path is not None:
            diag_data = {
                "status": "insufficient_samples",
                "n": n_samples,
                "n_errors": n_errors,
                "collection": collection,
                "score_kind": "dense_cosine",
                "target_risk": target_risk,
                "delta": delta,
                "min_samples_needed": 299,
                "fitted_at": datetime.now(timezone.utc).isoformat(),
            }
            # Strictly omit 'threshold' so load_calibration_profile() will refuse it!
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostic_path.write_text(json.dumps(diag_data, indent=2), encoding="utf-8")
            logger.info(f"[RunCalibration] Wrote uncalibrated diagnostic report to {diagnostic_path} (loadable profile withheld).")

        print(f"FAILED: Insufficient samples to clear risk bound (n={n_samples} < 299). No profile written.")
        return 2

    # Step 4: Serialize and Validate Profile
    profile = calibrator.to_profile(
        point=point,
        collection=collection,
        target_risk=target_risk,
        score_kind="dense_cosine",
    )

    if dry_run:
        print(f"[Dry Run] Calibrated threshold: {profile['threshold']}")
        print(f"[Dry Run] Guaranteed precision: >= {1.0 - profile['ucb_risk']:.4f} (UCB risk: {profile['ucb_risk']})")
        print(f"[Dry Run] Coverage: {profile['coverage']:.4f} ({profile['n_selected']}/{profile['n']})")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    logger.info(f"[RunCalibration] Wrote calibrated profile to {output_path}")

    # Step 5: Verify with the actual serving pipeline's validator
    from services.first_person_pipeline import load_calibration_profile

    loaded = load_calibration_profile(str(output_path), collection)
    if loaded is None:
        logger.error("[RunCalibration] CRITICAL: Written profile failed load_calibration_profile validation!")
        output_path.unlink(missing_ok=True)
        return 1

    logger.info("[RunCalibration] Verified: written profile successfully loaded and validated by FirstPersonPipeline.")
    print(
        f"SUCCESS: Operating threshold={profile['threshold']} with guaranteed precision >={profile['precision']} "
        f"at UCB risk={profile['ucb_risk']} (n={profile['n']}, selected={profile['n_selected']})."
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru — First-Person Selective Risk Calibrator (Phase 3)")
    parser.add_argument("--csv", type=Path, required=True, help="Path to gold relevance CSV.")
    parser.add_argument("--collection", type=str, required=True, help="Target Qdrant collection name.")
    parser.add_argument("--output", type=Path, default=Path("data/first_person_calibration.json"), help="Output path for fitted calibration profile.")
    parser.add_argument("--diagnostic-output", type=Path, default=None, help="Optional output path for diagnostic summary when sample size is insufficient.")
    parser.add_argument("--target-risk", type=float, default=0.01, help="Target risk bound (default: 0.01, product bound is <= 0.01).")
    parser.add_argument("--delta", type=float, default=0.05, help="Statistical confidence parameter (default: 0.05).")
    parser.add_argument("--allow-single-judge-pilot", action="store_true", help="Permit single-judge labels for pilot diagnostics only (NEVER produces a loadable profile; exits with code 2).")
    parser.add_argument("--pipeline-scores-file", type=Path, default=None, help="Optional pre-computed pipeline scores file (must match collection and score_kind='dense_cosine').")
    parser.add_argument("--dry-run", action="store_true", help="Print precision-coverage curve without writing profile.")

    args = parser.parse_args(argv)

    return run_calibration(
        csv_path=args.csv,
        collection=args.collection,
        output_path=args.output,
        diagnostic_path=args.diagnostic_output,
        target_risk=args.target_risk,
        delta=args.delta,
        allow_single_judge_pilot=args.allow_single_judge_pilot,
        pipeline_scores_file=args.pipeline_scores_file,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
