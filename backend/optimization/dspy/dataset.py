"""Build DSPy training/eval examples from existing benchmark assets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OptimizationExample:
    question: str
    expected_terms: list[str]
    expected_sources: list[str]
    category: str
    response: str | None = None
    citations: list[str] | None = None
    score: float | None = None


def examples_from_question_bank(limit: int | None = None) -> list[OptimizationExample]:
    """Convert backend benchmark questions into compact optimization examples."""
    from benchmarks.question_bank import QUERIES

    examples: list[OptimizationExample] = []
    for category, items in QUERIES.items():
        for item in items:
            if not isinstance(item, dict) or not item.get("q"):
                continue
            examples.append(
                OptimizationExample(
                    question=str(item["q"]),
                    expected_terms=[str(x) for x in item.get("must_mention", [])],
                    expected_sources=[str(x) for x in item.get("expected_links", [])],
                    category=str(category),
                )
            )
            if limit and len(examples) >= limit:
                return examples
    return examples


def examples_from_benchmark_report(path: Path) -> list[OptimizationExample]:
    """Convert a ruthless benchmark JSON report into examples with observed outputs."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rows: list[dict[str, Any]] = data.get("results", [])
    examples = []
    for row in rows:
        query = row.get("query")
        if not query:
            continue
        examples.append(
            OptimizationExample(
                question=str(query),
                expected_terms=[],
                expected_sources=[],
                category=str(row.get("category", "benchmark")),
                response=row.get("response"),
                citations=[str(x) for x in row.get("citations", [])],
                score=float(row.get("score", 0) or 0),
            )
        )
    return examples


def write_jsonl(examples: list[OptimizationExample], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for example in examples:
            fh.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")
