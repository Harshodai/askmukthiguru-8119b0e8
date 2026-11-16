#!/usr/bin/env python3
"""Graded-run capture with per-run evidence (plan item F4, 2026-10-31).

Stage A of 2026-10-31 left no backend log, so its errors, timeouts and budget state stayed
UNPROVEN. This runner keeps everything one graded run needs, in one directory per run id:

    <out-root>/<run-id>/manifest.json   commit, container id, image digest, StartedAt,
                                        pinned flags, spend before/after, validity verdict
    <out-root>/<run-id>/preflight.txt   the preflight output (the run aborts if it fails)
    <out-root>/<run-id>/rows.jsonl      one row per question, stamped with sha + container id
    <out-root>/<run-id>/backend.log     `docker logs` for the container, after the run

It refuses to start when that directory already holds a log (never overwrite evidence), and
it marks the run INVALID if the log contains `spend limit` or `indeterminate (timeout/error)`.

    cd backend && .venv/bin/python -m scripts.ops.graded_capture --run-id 20261101-stage-b
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

from scripts.ops.graded_run_preflight import (
    BACKEND,
    REPO,
    Check,
    check_log_clean,
    read_spend,
    run_preflight,
)

DEFAULT_OUT_ROOT = Path.home() / "mukthiguru_attribution_data" / "graded_runs"
FROZEN = BACKEND / "evaluation" / "datasets" / "first_person_bakeoff_2026-09-25.json"
UNANSWERABLE = REPO / "evals" / "first_person" / "unanswerable60_draft.jsonl"
BENCHMARK_FROZEN29 = REPO / "evals" / "first_person" / "frozen29.jsonl"
BENCHMARK_COMPOUND10 = REPO / "evals" / "first_person" / "compound10.jsonl"
BENCHMARK_OOC13 = REPO / "evals" / "first_person" / "ooc13.jsonl"
# INTENT_ROUTER_ added 2026-11-13 (audit H-14): its flags change routing and were invisible.
ENV_PREFIXES = ("FIRST_PERSON_", "OPENROUTER_", "CELERY_TASK", "LLM_PROVIDER", "INTENT_ROUTER_")


MAX_REASON_IDS = 10
RETRY_ATTEMPTS = 5  # per request, first try included
RETRY_BASE_S = 2.0
RETRY_CAP_S = 60.0


# ── pure helpers (unit-tested) ───────────────────────────────────────────────


def refuse_if_evidence_exists(run_dir: Path) -> None:
    """Evidence is never overwritten: a run id that already has a log or rows is spent."""
    for name in ("backend.log", "rows.jsonl", "manifest.json"):
        if (run_dir / name).exists():
            raise FileExistsError(f"{run_dir / name} already exists; use a new --run-id")


def stamp_row(row: dict[str, Any], *, sha: str, container_id: str, run_id: str) -> dict[str, Any]:
    return {**row, "sha": sha, "container_id": container_id, "run_id": run_id}


# H-26 (2026-11-15): a served citation kept only its URL, so a failed row could
# not be traced back to the point/span that produced it without text matching.
# The public /api/chat citation projection (``app/chat_engine.py``,
# ``app/orchestrator.py``) does not carry these identity fields yet, so the row
# records each one when it is present and null otherwise, and names the ones that
# were missing rather than guessing or backfilling.
CITATION_IDENTITY_FIELDS = (
    "point_id",
    "source_span_id",
    "start_ms",
    "end_ms",
    "completeness_status",
    "boundary_status",
)


def build_citation(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": c.get("text_snippet", ""),
        "speaker": c.get("speaker"),
        "speaker_verified": c.get("speaker_verified"),
        "url": c.get("url"),
        "t": c.get("timestamp_seconds"),
        **{field: c.get(field) for field in CITATION_IDENTITY_FIELDS},
    }


def unavailable_citation_fields(citations: list[dict[str, Any]]) -> list[str]:
    """Identity fields this API build did not return; empty when there is no citation."""
    return sorted(
        {field for c in citations for field in CITATION_IDENTITY_FIELDS if c.get(field) is None}
    )


def build_row(
    item: dict[str, Any],
    result: dict[str, Any],
    http: int,
    wall_seconds: float,
    *,
    transport_retries: int = 0,
    transport_failed: bool = False,
) -> dict[str, Any]:
    cits = result.get("citations") or []
    citations = [build_citation(c) for c in cits]
    return {
        **item,
        "http": http,
        "answer": result.get("response") or "",
        "route": result.get("route_decision"),
        "model_used": result.get("model_used"),
        "grounding": result.get("grounding_state"),
        "citations": citations,
        "citation_fields_unavailable": unavailable_citation_fields(citations),
        "notices": result.get("safety_notices") or [],
        # Server-side latency is what the p95 bar is read from; wall clock includes polling.
        "latency_ms": result.get("latency_ms"),
        "sec": round(wall_seconds, 1),
        # A refused or never-finished request says nothing about routing; the report excludes it.
        "transport_retries": transport_retries,
        "transport_failed": transport_failed,
    }


def file_fingerprint(path: Path) -> dict[str, Any]:
    """sha256 and row count of one input dataset file (audit H-16), so a changed input leaves a trace."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        rows = len(data["questions"] if isinstance(data, dict) else data)
    else:
        rows = sum(1 for line in text.splitlines() if line.strip())
    return {"sha256": hashlib.sha256(raw).hexdigest(), "rows": rows}


def input_fingerprints(paths: list[Path]) -> dict[str, dict[str, Any]]:
    return {str(p.relative_to(REPO)): file_fingerprint(p) for p in paths if p.exists()}


def cache_proof(returncode: int, output: str) -> Check:
    """Caches must be *proven* empty before a graded run (step 1 of the plan's gate table).

    ``verify_cache_empty.py`` exits 0 empty, 1 cached, 2 unreachable. Unreachable is not empty,
    and a warm answer served from cache would be graded as if it came from this run.
    """
    text = output.strip().splitlines()
    detail = text[-1][:160] if text else f"exit {returncode}"
    return Check("caches proven empty", returncode == 0, f"exit {returncode}: {detail}")


def _run_cache_proof() -> Check:
    script = REPO / "scripts" / "ops" / "verify_cache_empty.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, timeout=180
        )
    except Exception as exc:  # never treat a broken prover as an empty cache
        return Check("caches proven empty", False, f"prover failed to run: {exc}")
    output = (proc.stdout or "") + (proc.stderr or "")
    return cache_proof(proc.returncode, output)


def validity(
    log_text: str,
    spend_before: tuple[Any, Any],
    spend_after: tuple[Any, Any],
    preflight_ok: bool,
    transport_failed_ids: list[str] | None = None,
) -> dict[str, Any]:
    """A run is valid only if the preflight passed and the log shows no blocked LLM calls or auth errors."""
    log = check_log_clean(log_text)
    reasons = []
    if not preflight_ok:
        reasons.append("preflight failed")
    if not log.ok:
        reasons.append(log.detail)
    if transport_failed_ids:
        shown = ", ".join(transport_failed_ids[:MAX_REASON_IDS])
        more = " ..." if len(transport_failed_ids) > MAX_REASON_IDS else ""
        reasons.append(
            f"{len(transport_failed_ids)} rows failed at transport after retries "
            f"(not 200/202, or job never completed): {shown}{more}"
        )
    return {
        "valid": not reasons,
        "reasons": reasons,
        "spend_before": {"day": spend_before[0], "month": spend_before[1]},
        "spend_after": {"day": spend_after[0], "month": spend_after[1]},
    }


# ── side effects ─────────────────────────────────────────────────────────────


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=True, timeout=120
    ).stdout


def _container_facts(container: str) -> dict[str, Any]:
    info = json.loads(_run(["docker", "inspect", container]))[0]
    env = dict(
        line.split("=", 1)
        for line in _run(["docker", "exec", container, "printenv"]).splitlines()
        if "=" in line
    )
    return {
        "container_id": info["Id"][:12],
        "image": info.get("Image"),
        "started_at": (info.get("State") or {}).get("StartedAt"),
        "flags": {
            k: (
                "***REDACTED***"
                if any(s in k.lower() for s in ("key", "secret", "token", "password"))
                else v
            )
            for k, v in sorted(env.items())
            if k.startswith(ENV_PREFIXES)
        },
    }


def _items(
    include_frozen: bool,
    include_unanswerable: bool,
    include_benchmarks: bool = False,
    include_question_bank: bool = False,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if include_frozen:
        data = json.loads(FROZEN.read_text(encoding="utf-8"))
        for q in data["questions"] if isinstance(data, dict) else data:
            items.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "set": "frozen116",
                    "split": "tuning",  # all gate tuning used these 116; not a held-out set
                    "answerable": str(q.get("answerable")).lower() == "true",
                }
            )
    if include_unanswerable:
        for line in UNANSWERABLE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                x = json.loads(line)
                items.append(
                    {
                        "id": x["id"],
                        "question": x["question"],
                        "set": "unanswerable86",
                        "expected": x["expected"],
                        "scoring_group": x["scoring_group"],
                        "lang": x["lang"],
                    }
                )
    if include_benchmarks:
        for p, kind_default in [
            (BENCHMARK_FROZEN29, "on_topic"),
            (BENCHMARK_COMPOUND10, "compound"),
            (BENCHMARK_OOC13, "out_of_corpus"),
        ]:
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        b = json.loads(line)
                        items.append(
                            {
                                "id": b["id"],
                                "question": b["question"],
                                "set": "benchmark",
                                "kind": b.get("kind", kind_default),
                                "answerable": b.get("kind", kind_default) != "out_of_corpus",
                            }
                        )
    if include_question_bank:
        try:
            from benchmarks.question_bank import QUERIES
        except ImportError:
            import sys

            _backend_dir = str(BACKEND)
            if _backend_dir not in sys.path:
                sys.path.insert(0, _backend_dir)
            from benchmarks.question_bank import QUERIES

        _UNANSWERABLE_CATEGORIES = {
            "guardrails_input",
            "intent_traps",
            "silly_nonsense",
            "doctrine_traps",
            "boundary_probing",
            "adversarial_traps",
            "constitutional_adherence_traps",
            "malformed_input",
            "infra_probing",
            "multilingual_jailbreak_traps",
            "markdown_html_injection",
            "future_date_confabulation",
            "ruthless_safety_boundaries",
            "web_search_live_events",
        }
        for category, q_list in QUERIES.items():
            is_ans = category not in _UNANSWERABLE_CATEGORIES
            for idx, q_entry in enumerate(q_list):
                if isinstance(q_entry, dict):
                    if (
                        "turns" in q_entry
                        and isinstance(q_entry["turns"], list)
                        and q_entry["turns"]
                    ):
                        q_text = q_entry["turns"][0].get("q", "")
                    else:
                        q_text = q_entry.get("q", "")
                else:
                    q_text = str(q_entry)
                items.append(
                    {
                        "id": f"qb_{category}_{idx + 1:02d}",
                        "question": q_text,
                        "set": "question_bank",
                        "category": category,
                        "answerable": is_ans,
                    }
                )
    return items


def retry_wait(resp: Any, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when this response is not retryable.

    429 always retries; 503 only with a Retry-After header. Retry-After wins, else 2 s doubling;
    every wait is capped at 60 s. Other 4xx/5xx are never retried.
    """
    after = resp.headers.get("retry-after")
    if resp.status_code != 429 and not (resp.status_code == 503 and after is not None):
        return None
    try:
        wait = float(after) if after is not None else RETRY_BASE_S * 2**attempt
    except ValueError:  # an HTTP-date Retry-After: fall back to backoff
        wait = RETRY_BASE_S * 2**attempt
    return min(max(wait, 0.0), RETRY_CAP_S)


def request_with_retry(send: Any, sleep: Any = time.sleep) -> tuple[Any, int]:
    """Call ``send()`` up to RETRY_ATTEMPTS times; returns (last response, retries used)."""
    for attempt in range(RETRY_ATTEMPTS):
        r = send()
        wait = retry_wait(r, attempt)
        if wait is None or attempt == RETRY_ATTEMPTS - 1:
            return r, attempt
        sleep(wait)
    raise AssertionError("unreachable")


def _ask(
    client: Any,
    base: str,
    token_box: dict[str, Any],
    question: str,
    sleep: Any = time.sleep,
) -> tuple[int, dict, int, bool]:
    """One question through /api/chat with an anonymous session (5 chats per session).

    Returns (http, result, transport_retries, completed). ``completed`` is False when the final
    status is not a success for its path or a 202 job never finished: a transport failure.
    """
    retries = 0
    if token_box.get("token") is None or token_box["used"] >= 4:
        r, n = request_with_retry(lambda: client.post(base + "/api/auth/anon-session"), sleep)
        retries += n
        if r.status_code != 200:
            return r.status_code, {}, retries, False
        token_box.update(token=r.json()["token"], used=0)
    token_box["used"] += 1
    token = token_box["token"]
    headers = {"X-Session-Id": token}
    r, n = request_with_retry(
        lambda: client.post(
            base + "/api/chat",
            json={"messages": [], "user_message": question, "session_id": token},
            headers=headers,
        ),
        sleep,
    )
    retries += n
    if r.status_code == 202:
        job = r.json()["job_id"]
        deadline = time.time() + 110
        while time.time() < deadline:
            j = client.get(base + f"/api/jobs/{job}", headers=headers).json()
            if j.get("status") in ("completed", "failed"):
                return r.status_code, j.get("result") or {}, retries, True
            sleep(1.0)
        return r.status_code, {}, retries, False
    ok = r.status_code == 200
    return r.status_code, (r.json() if ok else {}), retries, ok


def main() -> int:
    import httpx

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    ap.add_argument("--override", default=str(BACKEND / "docker-compose.graded.yml"))
    ap.add_argument("--container", default="mukthiguru-backend")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--need-usd", type=float, default=12.0)
    ap.add_argument("--no-frozen", action="store_true")
    ap.add_argument("--no-unanswerable", action="store_true")
    ap.add_argument("--include-benchmarks", action="store_true", default=False)
    ap.add_argument("--benchmarks-only", action="store_true", default=False)
    ap.add_argument("--include-question-bank", action="store_true", default=False)
    ap.add_argument("--question-bank-only", action="store_true", default=False)
    args = ap.parse_args()

    run_dir = Path(args.out_root).expanduser() / args.run_id
    refuse_if_evidence_exists(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    pre = run_preflight(
        Namespace(
            override=args.override,
            container=args.container,
            base_url=args.base_url,
            need_usd=args.need_usd,
            check_logs=False,
        )
    )
    pre.append(_run_cache_proof())
    (run_dir / "preflight.txt").write_text(
        "\n".join(c.line() for c in pre) + "\n", encoding="utf-8"
    )
    preflight_ok = all(c.ok for c in pre)
    if not preflight_ok:
        print((run_dir / "preflight.txt").read_text(), file=sys.stderr)
        print(f"preflight FAILED; evidence in {run_dir}", file=sys.stderr)
        return 1

    sha = _run(["git", "rev-parse", "HEAD"], cwd=REPO).strip()
    facts = _container_facts(args.container)
    spend_before = read_spend()

    rows_path = run_dir / "rows.jsonl"
    token_box: dict[str, Any] = {"token": None, "used": 0}
    include_frozen = not args.no_frozen and not args.benchmarks_only and not args.question_bank_only
    include_unanswerable = (
        not args.no_unanswerable and not args.benchmarks_only and not args.question_bank_only
    )
    include_benchmarks = args.include_benchmarks or args.benchmarks_only
    include_qb = args.include_question_bank or args.question_bank_only
    items = _items(include_frozen, include_unanswerable, include_benchmarks, include_qb)

    transport_failed_ids: list[str] = []
    with httpx.Client(timeout=120) as client, rows_path.open("w", encoding="utf-8") as out:
        for item in items:
            t0 = time.time()
            http, result, retries, completed = _ask(
                client, args.base_url, token_box, item["question"]
            )
            if not completed:
                transport_failed_ids.append(str(item["id"]))
            row = stamp_row(
                build_row(
                    item,
                    result,
                    http,
                    time.time() - t0,
                    transport_retries=retries,
                    transport_failed=not completed,
                ),
                sha=sha,
                container_id=facts["container_id"],
                run_id=args.run_id,
            )
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()

    log_text = subprocess.run(
        ["docker", "logs", args.container], capture_output=True, text=True, timeout=120
    )
    (run_dir / "backend.log").write_text(log_text.stdout + log_text.stderr, encoding="utf-8")
    verdict = validity(
        log_text.stdout + log_text.stderr,
        spend_before,
        read_spend(),
        preflight_ok,
        transport_failed_ids,
    )
    read_files = [
        p
        for p, used in (
            (FROZEN, include_frozen),
            (UNANSWERABLE, include_unanswerable),
            (BENCHMARK_FROZEN29, include_benchmarks),
            (BENCHMARK_COMPOUND10, include_benchmarks),
            (BENCHMARK_OOC13, include_benchmarks),
        )
        if used
    ]
    manifest = {
        "run_id": args.run_id,
        "sha": sha,
        **facts,
        **verdict,
        "input_files": input_fingerprints(read_files),
        # Left null on purpose: this flow has no Qdrant client (only Redis and docker), and a
        # new client would change what a capture touches. Criteria want {points, ids_sha256}
        # of the served collection; fill it from a separate read-only step or when a client exists.
        "collection_fingerprint": None,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("run_id", "sha", "valid", "reasons")}, indent=2))
    return 0 if verdict["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
