"""Build a normalized, reproducible manifest from the repository question bank.

This is a measurement-preparation utility. It does not call the backend, alter
routing, write caches, or mutate the source question bank.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


def load_question_bank(path: Path) -> dict[str, list[dict[str, Any]]]:
    spec = importlib.util.spec_from_file_location("askmukthiguru_question_bank", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load question bank: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queries = getattr(module, "QUERIES", None)
    if not isinstance(queries, dict):
        raise TypeError("question_bank.py must expose QUERIES as a dictionary")
    return queries


def category_stratum(category: str, item: dict[str, Any]) -> str:
    lowered = category.lower()
    if "guardrail" in lowered or "jailbreak" in lowered or "adversarial" in lowered:
        return "safety_governance"
    if "distress" in lowered or "emotional" in lowered or "safety" in lowered:
        return "safety_distress"
    if "malformed" in lowered or "micro_" in lowered:
        return "robustness_boundaries"
    if "multi_turn" in lowered or "followup" in lowered:
        return "conversation_followup"
    if "temporal" in lowered or "future_date" in lowered:
        return "temporal_out_of_corpus"
    if "citation" in lowered or "self_rag" in lowered or "cove" in lowered:
        return "grounding_citation"
    if "multilingual" in lowered or item.get("lang") not in (None, "en"):
        return "multilingual"
    if "latency" in lowered or "context_budget" in lowered:
        return "stress_context"
    if "doctrine" in lowered or lowered in {"cove", "self_rag"}:
        return "in_corpus_doctrine"
    if "infra" in lowered or "markdown" in lowered:
        return "privacy_injection"
    if item.get("expected_intent") in {"DISTRESS", "MEDICAL"}:
        return "safety_distress"
    return "general_qa"


def expected_policy(item: dict[str, Any]) -> str:
    if item.get("expected_intent") == "DISTRESS" or item.get("expected") in {
        "DISTRESS",
        "DISTRESS_OR_ERROR",
    }:
        return "safety_redirect_or_indeterminate"
    if item.get("expected") in {"refuse", "bounded_or_refuse", "refuse_or_bounded"}:
        return "refuse_or_bounded"
    if item.get("min_cites") or item.get("verified") or item.get("must_mention"):
        return "grounded_answer_or_honest_abstention"
    if item.get("expected") in {"LIVE_LOGISTICS"} or item.get("needs_web_search"):
        return "live_source_or_bounded_failure"
    if item.get("category", "").startswith(("memory_", "second_brain_")):
        return "privacy_scoped_memory_boundary"
    return "bounded_answer_or_honest_abstention"


def common_case(
    *,
    category: str,
    item: dict[str, Any],
    index: int,
    question: str,
    language: str,
    scenario: str | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    case_id = f"{category}-{index:04d}"
    if scenario is not None and turn_index is not None:
        case_id = f"{category}-{index:04d}-turn-{turn_index:02d}"
    return {
        "case_id": case_id,
        "source_bank": "backend/benchmarks/question_bank.py",
        "source_category": category,
        "benchmark_stratum": category_stratum(category, item),
        "question": question,
        "language": item.get("lang") or language,
        "scenario": scenario,
        "turn_index": turn_index,
        "expected_policy": expected_policy(item),
        "expected_intent": item.get("expected_intent"),
        "expected_outcome": item.get("expected"),
        "expected_tier": item.get("expected_tier"),
        "expected_route_family": item.get("expected_route_family"),
        "must_mention": item.get("must_mention") or [],
        "must_mention_any": item.get("must_mention_any") or [],
        "reject_if": item.get("reject_if") or [],
        "min_citations": item.get("min_cites", 0),
        "verified_source_expected": bool(item.get("verified", False)),
        "needs_web_search": bool(item.get("needs_web_search", False)),
        "severity": item.get("severity"),
        "layer": item.get("layer"),
        "cache_type": item.get("type"),
        "is_multi_turn": scenario is not None,
    }


def build_manifest(question_bank_path: Path) -> dict[str, Any]:
    queries = load_question_bank(question_bank_path)
    source_hash = hashlib.sha256(question_bank_path.read_bytes()).hexdigest()
    cases: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    excluded_categories: dict[str, str] = {}

    for category, items in queries.items():
        if not isinstance(items, list):
            excluded_categories[category] = "category_value_not_list"
            continue
        category_counts[category] = 0
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if "turns" in item:
                scenario = str(item.get("scenario") or f"scenario-{item_index:04d}")
                turns = item.get("turns")
                if not isinstance(turns, list):
                    continue
                for turn_index, turn in enumerate(turns, start=1):
                    if not isinstance(turn, dict) or not isinstance(turn.get("q"), str):
                        continue
                    merged = {**item, **turn}
                    cases.append(
                        common_case(
                            category=category,
                            item=merged,
                            index=item_index,
                            question=turn["q"],
                            language=str(merged.get("lang") or "en"),
                            scenario=scenario,
                            turn_index=turn_index,
                        )
                    )
                    category_counts[category] += 1
                continue
            question = item.get("q")
            if not isinstance(question, str):
                continue
            cases.append(
                common_case(
                    category=category,
                    item=item,
                    index=item_index,
                    question=question,
                    language=str(item.get("lang") or "en"),
                )
            )
            category_counts[category] += 1

    return {
        "manifest_version": "question-bank-latency-v1",
        "source_path": str(question_bank_path),
        "source_sha256": source_hash,
        "case_count": len(cases),
        "category_counts": category_counts,
        "excluded_categories": excluded_categories,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question-bank",
        default="backend/benchmarks/question_bank.py",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default="audit_work/question_bank_latency_manifest_v1.json",
        type=Path,
    )
    args = parser.parse_args()
    manifest = build_manifest(args.question_bank)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": manifest["case_count"],
                "category_count": len(manifest["category_counts"]),
                "source_sha256": manifest["source_sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
