"""Build a held-out retrieval evaluation matrix from benchmark JSON.

This runner is offline and credential-free. It measures supplied records and
optional golden labels; it never changes retrieval weights or production data.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return [row for row in payload["records"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _list_of_strings(value: Any) -> List[str]:
    values = value if isinstance(value, list) else ([value] if value else [])
    return [str(item) for item in values if item not in (None, "")]


def _evidence(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        record.get("provenance_context"),
        record.get("response", {}).get("provenance_context") if isinstance(record.get("response"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            bands = candidate.get("bands", candidate)
            if isinstance(bands, dict):
                rows: List[Dict[str, Any]] = []
                for values in bands.values():
                    if isinstance(values, list):
                        rows.extend(item for item in values if isinstance(item, dict))
                if rows:
                    return rows
    return []


def _predicted_entities(record: Dict[str, Any]) -> Set[str]:
    entities: Set[str] = set()
    for item in _evidence(record):
        entities.update(_list_of_strings(item.get("entity_ids")))
    response = record.get("response")
    if isinstance(response, dict):
        entities.update(_list_of_strings(response.get("provenance_entities_touched")))
    return entities


def _predicted_segments(record: Dict[str, Any]) -> List[str]:
    return [str(item["source_segment_id"]) for item in _evidence(record) if item.get("source_segment_id")]


def _dcg(relevances: Sequence[int]) -> float:
    return sum((2**rel - 1) / math.log2(index + 2) for index, rel in enumerate(relevances))


def ndcg_at_k(predicted: Sequence[str], expected: Set[str], k: int = 10) -> Optional[float]:
    if not expected:
        return None
    actual = [1 if value in expected else 0 for value in predicted[:k]]
    ideal = [1] * min(len(expected), k)
    denom = _dcg(ideal)
    return round(_dcg(actual) / denom, 4) if denom else 0.0


def _citation_correctness(record: Dict[str, Any], expected: Set[str]) -> Optional[float]:
    if not expected:
        return None
    citations = _list_of_strings(record.get("citations"))
    return round(sum(1 for value in citations if value in expected) / len(citations), 4) if citations else 0.0


def row_for(record: Dict[str, Any], golden: Dict[str, Any]) -> Dict[str, Any]:
    expected_entities = set(_list_of_strings(golden.get("expected_entities")))
    expected_segments = set(_list_of_strings(golden.get("expected_segments")))
    expected_sources = set(_list_of_strings(golden.get("expected_sources")))
    predicted_entities = _predicted_entities(record)
    entity_recall = round(len(expected_entities & predicted_entities) / len(expected_entities), 4) if expected_entities else None
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    response_text = json.dumps(response, ensure_ascii=False).lower()
    graph_timeout = bool(golden.get("graph_timeout") or "deadline exceeded" in response_text or "timed out" in response_text)
    faithfulness = record.get("faithfulness_score")
    return {
        "id": record.get("id"),
        "query_class": golden.get("query_class") or record.get("category"),
        "question": record.get("question"),
        "expected_entities": sorted(expected_entities),
        "predicted_entities": sorted(predicted_entities),
        "entity_recall": entity_recall,
        "expected_relation": golden.get("expected_relation"),
        "relevant_source_segments": sorted(expected_segments),
        "predicted_source_segments": _predicted_segments(record),
        "citation_correctness": _citation_correctness(record, expected_sources),
        "ndcg_at_k": ndcg_at_k(_predicted_segments(record), expected_segments),
        "faithfulness_score": faithfulness if isinstance(faithfulness, (int, float)) else None,
        "graph_timeout": graph_timeout,
        "latency_ms": record.get("latency_ms"),
        "citation_count": record.get("citation_count", 0),
        "grounding_state": record.get("grounding_state"),
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def nums(key: str) -> List[float]:
        return [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    latencies, faithfulness, recalls, ndcgs, citations = [nums(key) for key in ("latency_ms", "faithfulness_score", "entity_recall", "ndcg_at_k", "citation_correctness")]
    return {
        "rows": len(rows),
        "latency_ms_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "faithfulness_mean": round(statistics.mean(faithfulness), 4) if faithfulness else None,
        "entity_recall_mean": round(statistics.mean(recalls), 4) if recalls else None,
        "ndcg_at_k_mean": round(statistics.mean(ndcgs), 4) if ndcgs else None,
        "citation_correctness_mean": round(statistics.mean(citations), 4) if citations else None,
        "graph_timeout_rate": round(sum(1 for row in rows if row["graph_timeout"]) / len(rows), 4) if rows else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--golden", type=Path)
    args = parser.parse_args()
    payload = _load(args.input)
    golden_payload = _load(args.golden) if args.golden else {}
    golden_map = golden_payload.get("cases", golden_payload) if isinstance(golden_payload, dict) else {}
    rows = [row_for(record, golden_map.get(str(record.get("id")), {})) for record in _records(payload)]
    report = {"input": str(args.input), "golden": str(args.golden) if args.golden else None, "summary": summarize(rows), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {len(rows)} evaluation rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
