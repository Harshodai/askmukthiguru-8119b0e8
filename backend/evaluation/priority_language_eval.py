"""Reproducible launch gate for AskMukthiGuru's six priority languages.

This evaluator checks observable contracts only.  It does not ask an LLM to
self-grade tone or translation quality.  A language-qualified reviewer records
those judgments separately in the review artifact referenced by ``--review``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.language_router import LanguageRouter

PRIORITY_LANGUAGES = ("en", "hinglish", "hi", "te", "ta", "kn")
DEFAULT_DATASET = Path(__file__).with_name("datasets") / "priority_languages_v1.json"


def load_dataset(path: Path) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("version") != "priority-languages-v1":
        raise ValueError("unsupported priority-language dataset version")
    items = dataset.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("dataset must contain non-empty items")
    return dataset


def validate_dataset(dataset: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    coverage: dict[str, int] = defaultdict(int)
    ids: set[str] = set()
    for item in dataset["items"]:
        item_id = item.get("id")
        language = item.get("language")
        if not isinstance(item_id, str) or not item_id:
            errors.append("case has no id")
            continue
        if item_id in ids:
            errors.append(f"duplicate id: {item_id}")
        ids.add(item_id)
        if language not in PRIORITY_LANGUAGES:
            errors.append(f"{item_id}: unsupported language {language!r}")
            continue
        coverage[language] += 1
        if item.get("expected_router_primary") != language:
            errors.append(f"{item_id}: expected_router_primary must equal language")
        if not isinstance(item.get("text"), str) or len(item["text"].strip()) < 12:
            errors.append(f"{item_id}: text is missing or too short")
        if not any(item.get(key) for key in ("expects_guidance", "expects_crisis_safe")):
            errors.append(f"{item_id}: must declare a practical or crisis expectation")
    for language in PRIORITY_LANGUAGES:
        if coverage[language] < 2:
            errors.append(f"{language}: needs at least grounded and safety-sensitive coverage")
    return errors


def call_backend(backend_url: str, token: str | None, item: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        {
            "messages": [],
            "user_message": item["text"],
            "language": item["language"],
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(backend_url.rstrip("/") + "/api/chat", data=payload, headers=headers)
    try:
        with urlopen(request, timeout=45) as response:  # nosec B310 -- configured benchmark launch target
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc


def check_response(item: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    answer = response.get("response") or response.get("content") or ""
    evidence = response.get("answer_evidence")
    plan = response.get("guidance_plan")
    citations = response.get("citations") or []
    failures: list[str] = []

    if not isinstance(answer, str) or len(answer.strip()) < 20:
        failures.append("response_missing_or_too_short")
    if item.get("requires_source_evidence"):
        if not isinstance(evidence, dict) or evidence.get("source_count", 0) < 1:
            failures.append("source_evidence_missing")
        if not citations:
            failures.append("citations_missing")
    if item.get("expects_guidance"):
        if not isinstance(plan, dict):
            failures.append("guidance_plan_missing")
        else:
            attribution = plan.get("attribution")
            if not isinstance(attribution, dict) or not attribution.get("label"):
                failures.append("guidance_attribution_missing")
            if attribution and attribution.get("teacher_name"):
                failures.append("teacher_impersonation_risk")
            if not plan.get("action_step") and not plan.get("reflection_prompt"):
                failures.append("practical_next_step_missing")
    if item.get("expects_crisis_safe"):
        if plan is not None:
            failures.append("crisis_guidance_plan_must_be_null")
        if not response.get("blocked") and not response.get("response"):
            failures.append("crisis_response_missing")

    return {
        "id": item["id"],
        "language": item["language"],
        "passed": not failures,
        "failures": failures,
        "tone_review_required": bool(item.get("tone_review_required")),
        "latency_ms": response.get("latency_ms"),
        "evidence_support_label": evidence.get("evidence_support_label")
        if isinstance(evidence, dict)
        else None,
    }


def load_review(path: Path | None) -> dict[str, bool]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    reviews = data.get("reviews", data)
    if not isinstance(reviews, dict):
        raise ValueError("review artifact must contain an object of case ids to booleans")
    return {str(case_id): value is True for case_id, value in reviews.items()}


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    dataset = load_dataset(args.dataset)
    fixture_errors = validate_dataset(dataset)
    if fixture_errors:
        return {"fixture_errors": fixture_errors, "passed": False}, 2
    if args.validate_fixtures:
        return {
            "dataset_version": dataset["version"],
            "cases": len(dataset["items"]),
            "languages": list(PRIORITY_LANGUAGES),
            "fixture_errors": [],
            "passed": True,
        }, 0

    reviews = load_review(args.review)
    router = LanguageRouter()
    cases: list[dict[str, Any]] = []
    for item in dataset["items"]:
        route = router.detect(item["text"])
        router_ok = route.primary.value == item["expected_router_primary"]
        started = time.monotonic()
        try:
            response = call_backend(args.backend_url, args.token, item)
            row = check_response(item, response)
        except RuntimeError as exc:
            row = {
                "id": item["id"],
                "language": item["language"],
                "passed": False,
                "failures": ["request_failed"],
                "error": str(exc),
                "tone_review_required": bool(item.get("tone_review_required")),
                "latency_ms": None,
                "evidence_support_label": None,
            }
        row["router_primary"] = route.primary.value
        if not router_ok:
            row["failures"].append("router_mismatch")
            row["passed"] = False
        row["wall_clock_ms"] = round((time.monotonic() - started) * 1000)
        row["tone_review_approved"] = reviews.get(item["id"])
        cases.append(row)

    by_language: dict[str, dict[str, Any]] = {}
    for language in PRIORITY_LANGUAGES:
        rows = [row for row in cases if row["language"] == language]
        by_language[language] = {
            "cases": len(rows),
            "passed": sum(row["passed"] for row in rows),
            "failed": sum(not row["passed"] for row in rows),
            "tone_reviews_approved": sum(row["tone_review_approved"] is True for row in rows),
            "tone_reviews_pending": sum(row["tone_review_approved"] is not True for row in rows),
        }
    contract_pass = all(row["passed"] for row in cases)
    reviews_pass = args.allow_pending_tone_reviews or all(
        row["tone_review_approved"] is True for row in cases if row["tone_review_required"]
    )
    report = {
        "dataset_version": dataset["version"],
        "generated_at_unix": int(time.time()),
        "backend_url": args.backend_url,
        "contract_pass": contract_pass,
        "tone_review_pass": reviews_pass,
        "passed": contract_pass and reviews_pass,
        "by_language": by_language,
        "cases": cases,
    }
    return report, 0 if report["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--backend-url", default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("BACKEND_TOKEN"))
    parser.add_argument("--review", type=Path, help="JSON reviewer approvals keyed by fixture id")
    parser.add_argument("--out", type=Path, help="write the JSON report to this path")
    parser.add_argument("--allow-pending-tone-reviews", action="store_true")
    parser.add_argument("--validate-fixtures", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, exit_code = run(args)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
