"""Golden-set evaluator.

NOTE (2026-09-16): evaluation/bench.py is the consolidated golden-bank
runner (one CLI, one schema). This script stays for its RAGAS-library
faithfulness/answer_relevancy/context_precision/context_recall metrics,
which bench.py does not compute.

Calls the deployed backend for each question,
runs RAGAS faithfulness, answer_relevancy, context_precision, and
context_recall, and enforces an answer-source diversity guard. Exits
non-zero when any threshold fails so the GitHub Actions gate blocks the
deploy.

Usage:
  python backend/evaluation/run_golden_eval.py \
    --dataset backend/evaluation/golden_dataset.json \
    --out eval_report.json \
    --faithfulness-min 0.88 \
    --relevancy-min 0.80 \
    --context-precision-min 0.72 \
    --context-recall-min 0.72 \
    --min-distinct-sources 2 \
    --release-artifact
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.config import settings  # noqa: E402
except ImportError:
    settings = None  # type: ignore

try:
    from evaluation.fp_rank_metrics import (
        average_precision_at_k,
        ndcg_at_k,
        reciprocal_rank,
    )
except ImportError:
    from backend.evaluation.fp_rank_metrics import (  # type: ignore
        average_precision_at_k,
        ndcg_at_k,
        reciprocal_rank,
    )


def call_backend(url: str, token: str | None, question: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"messages": [], "user_message": question}
    r = httpx.post(f"{url.rstrip('/')}/api/chat", json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


def diversity_violation(citations: list[dict], min_distinct: int) -> bool:
    if not citations:
        return False
    top = citations[:3]
    sources = {c.get("source_id") or c.get("video_id") or c.get("url") for c in top}
    return len([s for s in sources if s]) < min_distinct


def classify_question(item: dict[str, Any]) -> str:
    """Categorize item into: faq, comparative, multi_hop, distress_adjacent, indic_language, standard."""
    if item.get("question_class"):
        return str(item["question_class"])

    category = (item.get("category") or "").lower()
    intent = (item.get("expected_intent") or "").upper()
    query = (item.get("query") or item.get("question") or "").strip()

    # 1. Indic language check
    if category in ("multilingual", "indic_language", "indic") or item.get("language") in (
        "hi",
        "te",
        "ta",
        "kn",
        "mr",
    ):
        return "indic_language"
    if re.search(r"[\u0900-\u0D7F]", query):
        return "indic_language"

    # 2. Distress adjacent
    if intent in ("CRISIS", "DISTRESS") or category in ("distress", "crisis"):
        return "distress_adjacent"
    if any(
        w in query.lower()
        for w in ("suicid", "kill myself", "end my life", "hopeless", "depressed", "bipolar")
    ):
        return "distress_adjacent"

    # 3. Comparative
    if category in ("comparative", "comparison") or any(
        w in query.lower()
        for w in (" vs ", "versus", "difference between", "compare", "distinction between")
    ):
        return "comparative"

    # 4. Multi-hop
    if (
        category in ("multi_hop", "multihop", "relational")
        or item.get("is_multi_hop")
        or "relational" in category
    ):
        return "multi_hop"

    # 5. FAQ
    if category in ("faq", "factual", "practical_meditation") or item.get("is_faq"):
        return "faq"

    return "standard"


def evaluate_retrieval_hits(
    item: dict[str, Any],
    contexts: list[str],
    citations: list[dict[str, Any]] | None = None,
) -> list[bool]:
    """Evaluate whether each retrieved context contains gold reference sources or concepts."""
    if not contexts:
        return []

    if "hits" in item and isinstance(item["hits"], list):
        return [bool(h) for h in item["hits"]]

    must_mention = [m.lower().strip() for m in item.get("must_mention", []) if m]
    correct_sources = [
        str(s).lower().strip()
        for s in (item.get("correct_sources") or ([item["source"]] if item.get("source") else []))
        if s
    ]

    hits = []
    for idx, ctx in enumerate(contexts):
        ctx_lower = ctx.lower()
        is_hit = False

        # Source match check (via citations if available, or context text)
        if correct_sources:
            if citations and idx < len(citations):
                cit = citations[idx]
                cit_source = str(
                    cit.get("source_id")
                    or cit.get("video_id")
                    or cit.get("source_url")
                    or cit.get("url")
                    or ""
                ).lower()
                if any(cs in cit_source for cs in correct_sources):
                    is_hit = True
            if not is_hit and any(cs in ctx_lower for cs in correct_sources):
                is_hit = True

        # Concept match check
        if not is_hit and must_mention:
            if any(concept in ctx_lower for concept in must_mention):
                is_hit = True

        # Token-based match fallback for queries without explicit must_mention/sources
        if not is_hit and not must_mention and not correct_sources:
            query = item.get("query") or item.get("question") or ""
            if item.get("expected_intent") != "REFUSE" and len(query) > 5:
                words = [w.lower() for w in re.findall(r"\w{4,}", query)]
                if words and any(w in ctx_lower for w in words):
                    is_hit = True

        hits.append(is_hit)

    return hits


def _compute_item_concept_overlap(item: dict[str, Any], answer: str) -> float:
    must = item.get("must_mention", [])
    reject = item.get("reject_if", [])
    if not answer:
        return 0.0
    if item.get("expected_intent") == "REFUSE":
        if must and not any(r.lower() in answer.lower() for r in reject):
            return 1.0 if any(c.lower() in answer.lower() for c in must) else 0.0
        return 1.0 if not any(r.lower() in answer.lower() for r in reject) else 0.0
    if not must:
        return 1.0 if len(answer.strip()) > 0 else 0.0
    hits = sum(1 for c in must if c.lower() in answer.lower())
    return hits / len(must)


def generate_release_artifact(
    report: dict[str, Any],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate and optionally save release evaluation artifact (DE-5.5).

    Includes retrieval metrics, per-class breakdown, faithfulness, relevancy,
    citation correctness, and abstention stats.
    """
    timestamp = datetime.now(UTC).isoformat()
    artifact = {
        "timestamp": timestamp,
        "release_verdict": (
            "UNMEASURED"
            if report.get("judge_metrics_pass") is None
            else "PASS"
            if report.get("judge_metrics_pass")
            and report.get("diversity_pass")
            and report.get("questions_failed", 0) == 0
            else "FAIL"
        ),
        "questions_total": report.get("questions_total", 0),
        "questions_failed": report.get("questions_failed", 0),
        "scoring_method": report.get("scoring_method", "unknown"),
        "retrieval_metrics": report.get(
            "retrieval_metrics",
            {
                "mrr": report.get("mrr", 0.0),
                "map_at_5": report.get("map_at_5", 0.0),
                "map_at_10": report.get("map_at_10", 0.0),
                "ndcg_at_10": report.get("ndcg_at_10", 0.0),
            },
        ),
        "per_class_breakdown": report.get("per_class_breakdown", {}),
        "faithfulness": report.get("faithfulness"),
        "relevancy": report.get("answer_relevancy")
        if report.get("relevancy") is None
        else report.get("relevancy"),
        "answer_relevancy": report.get("answer_relevancy"),
        "citation_correctness": report.get(
            "citation_correctness",
            {
                "diversity_violations": report.get("diversity_violations", 0),
                "passed": report.get("diversity_pass", True),
            },
        ),
        "abstention_stats": report.get("abstention_stats", {}),
    }

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(artifact, indent=2))

    return artifact


def score_golden_eval(
    items: list[dict[str, Any]],
    answers: list[str],
    contexts: list[list[str]] | None = None,
    refs: list[str] | None = None,
    questions: list[str] | None = None,
    args: argparse.Namespace | None = None,
    faithfulness_min: float = 0.88,
    concept_overlap_min: float = 0.88,
    relevancy_min: float = 0.80,
    context_precision_min: float = 0.72,
    context_recall_min: float = 0.72,
    min_distinct_sources: int = 2,
    diversity_violations: int = 0,
    failed: int = 0,
    item_citations: list[list[dict[str, Any]]] | None = None,
    item_hits: list[list[bool]] | None = None,
    item_statuses: list[str] | None = None,
) -> dict[str, Any]:
    if args is not None:
        faithfulness_min = getattr(args, "faithfulness_min", faithfulness_min)
        concept_overlap_min = getattr(args, "concept_overlap_min", concept_overlap_min)
        relevancy_min = getattr(args, "relevancy_min", relevancy_min)
        context_precision_min = getattr(args, "context_precision_min", context_precision_min)
        context_recall_min = getattr(args, "context_recall_min", context_recall_min)
        min_distinct_sources = getattr(args, "min_distinct_sources", min_distinct_sources)

    contexts = contexts or [[""] for _ in answers]
    refs = refs or ["" for _ in answers]
    questions = questions or ["" for _ in answers]

    # RAGAS scoring (deferred import so script runs without ragas in dev)
    scoring_method = "ragas"
    faithfulness_score: float | None = None
    relevancy_score: float | None = None
    context_precision_score: float | None = None
    context_recall_score: float | None = None
    concept_overlap_score: float | None = None
    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )  # type: ignore

        ds = Dataset.from_dict(
            {
                "question": questions,
                "answer": answers,
                "contexts": contexts,
                "reference": refs,
            }
        )
        result = evaluate(
            ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
        )
        faithfulness_score = float(result["faithfulness"])
        relevancy_score = float(result["answer_relevancy"])
        context_precision_score = float(result["context_precision"])
        context_recall_score = float(result["context_recall"])
    except Exception as e:
        print(f"[WARN] RAGAS unavailable ({e}); falling back to heuristic concept-overlap.")
        scoring_method = "concept_overlap_fallback"
        hits, total = 0, 0
        for it, ans in zip(items, answers, strict=False):
            must = it.get("must_mention", [])
            reject = it.get("reject_if", [])
            if it.get("expected_intent") == "REFUSE":
                total += 1
                if must and not any(r.lower() in ans.lower() for r in reject):
                    if any(c.lower() in ans.lower() for c in must):
                        hits += 1
            else:
                for c in must:
                    total += 1
                    if c.lower() in ans.lower():
                        hits += 1
        concept_overlap_score = hits / total if total else 0.0
        faithfulness_score = None
        relevancy_score = None
        context_precision_score = None
        context_recall_score = None

    if scoring_method == "ragas":
        faithfulness_pass: bool | str = (
            faithfulness_score >= faithfulness_min if faithfulness_score is not None else False
        )
        relevancy_pass: bool | str = (
            relevancy_score >= relevancy_min if relevancy_score is not None else False
        )
        context_precision_pass: bool | str = (
            context_precision_score >= context_precision_min
            if context_precision_score is not None
            else False
        )
        context_recall_pass: bool | str = (
            context_recall_score >= context_recall_min
            if context_recall_score is not None
            else False
        )
        concept_overlap_pass: bool | None = None
        judge_metrics_pass = (
            faithfulness_pass and relevancy_pass and context_precision_pass and context_recall_pass
        )
    else:
        faithfulness_pass = "unmeasured"
        relevancy_pass = "unmeasured"
        context_precision_pass = "unmeasured"
        context_recall_pass = "unmeasured"
        # SPEC-quality-observability: a heuristic is never a proxy pass for the
        # judge metrics. The overlap smoke check has its own threshold and its own
        # field; judge_metrics_pass stays None (unmeasured) so callers cannot read
        # a faithfulness pass out of it.
        concept_overlap_pass = concept_overlap_score >= concept_overlap_min
        judge_metrics_pass = None

    diversity_pass = diversity_violations == 0

    # 1. Retrieval Ranking Metrics (DE-5.3)
    all_hits: list[list[bool]] = []
    item_rr: list[float] = []
    item_ap5: list[float] = []
    item_ap10: list[float] = []
    item_ndcg10: list[float] = []
    item_concept_overlaps: list[float] = []

    for idx, it in enumerate(items):
        ctx_list = contexts[idx] if idx < len(contexts) else []
        cit_list = item_citations[idx] if item_citations and idx < len(item_citations) else None

        if item_hits and idx < len(item_hits):
            hits = item_hits[idx]
        elif "hits" in it:
            hits = it["hits"]
        else:
            hits = evaluate_retrieval_hits(it, ctx_list, cit_list)

        all_hits.append(hits)
        item_rr.append(reciprocal_rank(hits))
        item_ap5.append(average_precision_at_k(hits, k=5))
        item_ap10.append(average_precision_at_k(hits, k=10))
        item_ndcg10.append(ndcg_at_k(hits, k=10))

        ans = answers[idx] if idx < len(answers) else ""
        item_concept_overlaps.append(_compute_item_concept_overlap(it, ans))

    total_items = len(items)
    mrr_score = round(sum(item_rr) / total_items, 4) if total_items else 0.0
    map_at_5_score = round(sum(item_ap5) / total_items, 4) if total_items else 0.0
    map_at_10_score = round(sum(item_ap10) / total_items, 4) if total_items else 0.0
    ndcg_at_10_score = round(sum(item_ndcg10) / total_items, 4) if total_items else 0.0

    retrieval_metrics = {
        "mrr": mrr_score,
        "map_at_5": map_at_5_score,
        "map_at_10": map_at_10_score,
        "ndcg_at_10": ndcg_at_10_score,
    }

    # 2. Per-Query-Class Breakdown (DE-5.4)
    classes: dict[str, list[int]] = {}
    for idx, it in enumerate(items):
        q_class = classify_question(it)
        classes.setdefault(q_class, []).append(idx)

    per_class_breakdown: dict[str, dict[str, Any]] = {}
    for cls, idxs in sorted(classes.items()):
        cls_count = len(idxs)
        cls_rr = [item_rr[j] for j in idxs]
        cls_ap5 = [item_ap5[j] for j in idxs]
        cls_ap10 = [item_ap10[j] for j in idxs]
        cls_ndcg10 = [item_ndcg10[j] for j in idxs]
        cls_overlaps = [item_concept_overlaps[j] for j in idxs]

        per_class_breakdown[cls] = {
            "count": cls_count,
            "mrr": round(sum(cls_rr) / cls_count, 4) if cls_count else 0.0,
            "map_at_5": round(sum(cls_ap5) / cls_count, 4) if cls_count else 0.0,
            "map_at_10": round(sum(cls_ap10) / cls_count, 4) if cls_count else 0.0,
            "ndcg_at_10": round(sum(cls_ndcg10) / cls_count, 4) if cls_count else 0.0,
            "generation_scores": {
                "faithfulness": faithfulness_score,
                "answer_relevancy": relevancy_score,
                "concept_overlap": round(sum(cls_overlaps) / cls_count, 4) if cls_count else 0.0,
            },
        }

    # 3. Citation correctness and Abstention stats
    total_answered = max(0, total_items - failed)
    valid_citations_rate = (
        round(max(0, total_answered - diversity_violations) / total_answered, 4)
        if total_answered > 0
        else 1.0
    )
    citation_correctness = {
        "diversity_violations": diversity_violations,
        "valid_citations_rate": valid_citations_rate,
        "passed": diversity_violations == 0,
    }

    # Abstention stats
    expected_refusals = [
        idx
        for idx, it in enumerate(items)
        if it.get("expected_intent") == "REFUSE" or it.get("answerable") is False
    ]
    answerable_items = [
        idx
        for idx, it in enumerate(items)
        if it.get("expected_intent") != "REFUSE" and it.get("answerable") is not False
    ]

    def _is_refusal(idx: int) -> bool:
        if item_statuses and idx < len(item_statuses):
            if item_statuses[idx] in ("abstained", "refused", "weak_match"):
                return True
        ans = (answers[idx] if idx < len(answers) else "").lower()
        if not ans.strip():
            return True
        refusal_markers = (
            "cannot assist",
            "cannot fulfill",
            "i apologize",
            "unable to",
            "outside the scope",
            "not appropriate",
            "i cannot",
        )
        return any(m in ans for m in refusal_markers)

    expected_refusal_count = len(expected_refusals)
    refusals_abstained = sum(1 for idx in expected_refusals if _is_refusal(idx))
    false_refusals = sum(1 for idx in answerable_items if _is_refusal(idx))

    abstention_stats = {
        "expected_refusal_count": expected_refusal_count,
        "expected_refusal_abstained": refusals_abstained,
        "expected_refusal_rate": (
            round(refusals_abstained / expected_refusal_count, 4) if expected_refusal_count else 1.0
        ),
        "false_refusal_count": false_refusals,
        "false_refusal_rate": (
            round(false_refusals / len(answerable_items), 4) if answerable_items else 0.0
        ),
    }

    report = {
        "questions_total": len(items),
        "questions_failed": failed,
        "scoring_method": scoring_method,
        "note": (
            None
            if scoring_method == "ragas"
            else (
                "concept_overlap_fallback: RAGAS is uninstalled or judge LLM API key is not configured in CI. "
                "Faithfulness, answer_relevancy, context_precision, and context_recall are unmeasured (None), "
                "and only concept_overlap_score (% of must_mention concepts present without reject_if tokens) "
                "is evaluated."
            )
        ),
        "concept_overlap_score": concept_overlap_score if scoring_method != "ragas" else None,
        "concept_overlap_pass": concept_overlap_pass,
        "faithfulness": faithfulness_score,
        "answer_relevancy": relevancy_score,
        "context_precision": context_precision_score,
        "context_recall": context_recall_score,
        "diversity_violations": diversity_violations,
        "faithfulness_pass": faithfulness_pass,
        "relevancy_pass": relevancy_pass,
        "context_precision_pass": context_precision_pass,
        "context_recall_pass": context_recall_pass,
        "diversity_pass": diversity_pass,
        "judge_metrics_pass": judge_metrics_pass,
        "retrieval_metrics": retrieval_metrics,
        "mrr": mrr_score,
        "map_at_5": map_at_5_score,
        "map_at_10": map_at_10_score,
        "ndcg_at_10": ndcg_at_10_score,
        "per_class_breakdown": per_class_breakdown,
        "citation_correctness": citation_correctness,
        "abstention_stats": abstention_stats,
        "thresholds": {
            "faithfulness_min": faithfulness_min,
            "concept_overlap_min": concept_overlap_min,
            "relevancy_min": relevancy_min,
            "context_precision_min": context_precision_min,
            "context_recall_min": context_recall_min,
            "min_distinct_sources": min_distinct_sources,
        },
    }
    return report


# Aliases for convenience / alternative imports
compute_eval_report = score_golden_eval
evaluate_golden_set = score_golden_eval


def main(cli_args: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--faithfulness-min", type=float, default=0.88)
    p.add_argument("--concept-overlap-min", type=float, default=0.88)
    p.add_argument("--relevancy-min", type=float, default=0.80)
    p.add_argument("--context-precision-min", type=float, default=0.72)
    p.add_argument("--context-recall-min", type=float, default=0.72)
    p.add_argument("--min-distinct-sources", type=int, default=2)
    p.add_argument(
        "--release-artifact",
        nargs="?",
        const="default",
        default=None,
        help="Generate release eval artifact JSON (path or default evals/reports/<date>-corpus-release-eval.json)",
    )
    p.add_argument(
        "--allow-unmeasured-judge",
        action="store_true",
        help="Exit 0 when RAGAS judge metrics are unmeasured but the concept-overlap smoke check "
        "passes. Without it, an unmeasured judge fails the gate (never a proxy pass).",
    )
    args = p.parse_args(cli_args)

    if settings is None or not settings.backend_url:
        print("BACKEND_URL not set, eval skipped", file=sys.stderr)
        return 1
    backend_url = settings.backend_url
    token = settings.backend_token

    items = json.loads(args.dataset.read_text())["items"]
    questions, answers, contexts, refs = [], [], [], []
    item_citations, item_statuses = [], []
    failed = 0
    diversity_violations = 0

    for it in items:
        question = it.get("question") or it.get("query")
        if not question:
            print(
                f"[FAIL] {it.get('id', '<unknown>')}: item has neither question nor query",
                file=sys.stderr,
            )
            failed += 1
            continue
        success = True
        try:
            resp = call_backend(backend_url, token, question)
        except Exception as e:
            print(f"[FAIL] {it['id']}: {e}", file=sys.stderr)
            failed += 1
            success = False

        if success:
            ans = resp.get("response") or resp.get("answer") or ""
            cites = resp.get("citations", [])
            ctx = [c.get("text") or c.get("snippet") or "" for c in cites] or [""]
            status = resp.get("status", "success")
        else:
            ans = ""
            cites = []
            ctx = [""]
            status = "failed"

        questions.append(question)
        answers.append(ans)
        contexts.append(ctx)
        item_citations.append(cites)
        item_statuses.append(status)
        must = it.get("must_mention", [])
        refs.append("The expected answer must cover: " + ", ".join(must) if must else question)
        if success and diversity_violation(cites, args.min_distinct_sources):
            diversity_violations += 1
            print(f"[DIVERSITY] {it['id']}: top-3 citations not diverse enough")

    report = score_golden_eval(
        items=items,
        answers=answers,
        contexts=contexts,
        refs=refs,
        questions=questions,
        args=args,
        diversity_violations=diversity_violations,
        failed=failed,
        item_citations=item_citations,
        item_statuses=item_statuses,
    )
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    if args.release_artifact is not None:
        if args.release_artifact == "default":
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            artifact_path = Path("evals/reports") / f"{date_str}-corpus-release-eval.json"
        else:
            artifact_path = Path(args.release_artifact)
        generate_release_artifact(report, output_path=artifact_path)
        print(f"[INFO] Release eval artifact written to {artifact_path}")

    judge_metrics_pass = report["judge_metrics_pass"]
    diversity_pass = report["diversity_pass"]

    if judge_metrics_pass is None:
        # Unmeasured: only the explicit opt-in may pass, and only if the overlap
        # smoke check (its own threshold) also passes.
        print(
            "[WARN] RAGAS judge metrics unmeasured; faithfulness/relevancy/context gates NOT evaluated",
            file=sys.stderr,
        )
        judge_ok = bool(args.allow_unmeasured_judge and report["concept_overlap_pass"])
    else:
        judge_ok = bool(judge_metrics_pass)

    if not (judge_ok and diversity_pass and failed == 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
