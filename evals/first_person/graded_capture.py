#!/usr/bin/env python3
"""Graded-run capture with per-run evidence and resilience (pacing & exponential backoff).

Ensures evaluators and graded test suites operate reliably against live backend rate limits:
- DEFAULT_MIN_INTERVAL_S = 4.0s pacing between chat queries to stay under the 20/min IP limit.
- Exponential backoff retry on HTTP 429 in _create_anonymous_session and chat execution calls
  (initial backoff 5s, backoff factor 2.0, max attempts 5) to prevent burst failures on crisis
  queries (e.g. ua85).
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
ENV_PREFIXES = ("FIRST_PERSON_", "OPENROUTER_", "CELERY_TASK", "LLM_PROVIDER", "INTENT_ROUTER_")

MAX_REASON_IDS = 10
RETRY_ATTEMPTS = 5  # per request, first try included
RETRY_BASE_S = 5.0  # initial backoff 5.0s on HTTP 429
BACKOFF_FACTOR = 2.0  # exponential backoff factor 2.0
RETRY_CAP_S = 60.0

# Backend chat limit is 20/minute per IP (settings.chat_rate_limit): 60/20 = 3.0 s plus margin.
# Paced at 4.0s to reliably prevent rate-limit bursts.
DEFAULT_MIN_INTERVAL_S = 4.0


# ── pure helpers (unit-tested) ───────────────────────────────────────────────


def refuse_if_evidence_exists(run_dir: Path) -> None:
    """Evidence is never overwritten: a run id that already has a log or rows is spent."""
    for name in ("backend.log", "rows.jsonl", "manifest.json"):
        if (run_dir / name).exists():
            raise FileExistsError(f"{run_dir / name} already exists; use a new --run-id")


def stamp_row(row: dict[str, Any], *, sha: str, container_id: str, run_id: str) -> dict[str, Any]:
    return {**row, "sha": sha, "container_id": container_id, "run_id": run_id}


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
    """Caches must be *proven* empty before a graded run (step 1 of the plan's gate table)."""
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
                    "split": "tuning",
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


def retry_wait(
    resp: Any,
    attempt: int,
    initial_backoff: float = RETRY_BASE_S,
    backoff_factor: float = BACKOFF_FACTOR,
) -> float | None:
    """Seconds to wait before retrying, or None when this response is not retryable.

    429 always retries; 503 only with a Retry-After header. Retry-After wins, else exponential backoff;
    every wait is capped at 60 s. Other 4xx/5xx are never retried.
    """
    after = resp.headers.get("retry-after") if hasattr(resp, "headers") and resp.headers else None
    if resp.status_code != 429 and not (resp.status_code == 503 and after is not None):
        return None
    try:
        wait = (
            float(after)
            if after is not None
            else initial_backoff * (backoff_factor**attempt)
        )
    except (ValueError, TypeError):  # an HTTP-date Retry-After or invalid: fall back to backoff
        wait = initial_backoff * (backoff_factor**attempt)
    return min(max(wait, 0.0), RETRY_CAP_S)


def request_with_retry(
    send: Any,
    sleep: Any = time.sleep,
    max_attempts: int = RETRY_ATTEMPTS,
    initial_backoff: float = RETRY_BASE_S,
    backoff_factor: float = BACKOFF_FACTOR,
) -> tuple[Any, int]:
    """Call ``send()`` up to max_attempts times; returns (last response, retries used)."""
    for attempt in range(max_attempts):
        r = send()
        wait = retry_wait(r, attempt, initial_backoff=initial_backoff, backoff_factor=backoff_factor)
        if wait is None or attempt == max_attempts - 1:
            return r, attempt
        sleep(wait)
    raise AssertionError("unreachable")


def _create_anonymous_session(
    client: Any,
    base: str,
    sleep: Any = time.sleep,
    max_attempts: int = RETRY_ATTEMPTS,
    initial_backoff: float = RETRY_BASE_S,
    backoff_factor: float = BACKOFF_FACTOR,
) -> tuple[Any, int]:
    """Mint an anonymous session token via POST /api/auth/anon-session with exponential backoff on HTTP 429."""
    return request_with_retry(
        lambda: client.post(base + "/api/auth/anon-session"),
        sleep=sleep,
        max_attempts=max_attempts,
        initial_backoff=initial_backoff,
        backoff_factor=backoff_factor,
    )


class Pacer:
    """Keeps consecutive calls at least ``interval_s`` apart (clock and sleep are injected)."""

    def __init__(
        self, interval_s: float, sleep: Any = time.sleep, clock: Any = time.monotonic
    ) -> None:
        self.interval_s, self._sleep, self._clock = interval_s, sleep, clock
        self._last: float | None = None

    def __call__(self) -> None:
        now = self._clock()
        if self._last is not None and now < self._last + self.interval_s:
            self._sleep(self._last + self.interval_s - now)
            now = self._last + self.interval_s
        self._last = now


def _ask(
    client: Any,
    base: str,
    token_box: dict[str, Any],
    question: str,
    sleep: Any = time.sleep,
    pace: Any = None,
    max_attempts: int = RETRY_ATTEMPTS,
    initial_backoff: float = RETRY_BASE_S,
    backoff_factor: float = BACKOFF_FACTOR,
) -> tuple[int, dict, int, bool]:
    """One question through /api/chat with an anonymous session (5 chats per session).

    Returns (http, result, transport_retries, completed). ``completed`` is False when the final
    status is not a success for its path or a 202 job never finished: a transport failure.
    """
    retries = 0
    if token_box.get("token") is None or token_box["used"] >= 4:
        r, n = _create_anonymous_session(
            client,
            base,
            sleep=sleep,
            max_attempts=max_attempts,
            initial_backoff=initial_backoff,
            backoff_factor=backoff_factor,
        )
        retries += n
        if r.status_code != 200:
            return r.status_code, {}, retries, False
        token_box.update(token=r.json()["token"], used=0)
    token_box["used"] += 1
    token = token_box["token"]
    headers = {"X-Session-Id": token}

    def _post_chat() -> Any:
        if pace is not None:
            pace()  # only chat POSTs are paced, never job polls
        return client.post(
            base + "/api/chat",
            json={"messages": [], "user_message": question, "session_id": token},
            headers=headers,
        )

    r, n = request_with_retry(
        _post_chat,
        sleep=sleep,
        max_attempts=max_attempts,
        initial_backoff=initial_backoff,
        backoff_factor=backoff_factor,
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
    ap.add_argument(
        "--min-interval-s",
        type=float,
        default=DEFAULT_MIN_INTERVAL_S,
        help="minimum seconds between consecutive chat POSTs (backend limit 20/minute)",
    )
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

    cache_check = _run_cache_proof()
    preflight_ns = argparse.Namespace(
        container=args.container,
        override=str(args.override),
        need_usd=args.need_usd,
        base_url=args.base_url,
        check_logs=False,
    )
    checks = list(run_preflight(preflight_ns)) + [cache_check]
    log_lines = [f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}" for c in checks]
    preflight_ok = all(c.ok for c in checks)
    (run_dir / "preflight.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    for line in log_lines:
        print(line)
    if not preflight_ok:
        print("PREFLIGHT FAILED: aborting before spending budget", file=sys.stderr)
        return 1

    facts = _container_facts(args.container)
    facts["cache_proof"] = cache_check.detail
    spend_before = read_spend()
    sha = _run(["git", "rev-parse", "HEAD"]).strip()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    items = _items(
        not args.no_frozen and not args.benchmarks_only and not args.question_bank_only,
        not args.no_unanswerable and not args.benchmarks_only and not args.question_bank_only,
        args.include_benchmarks or args.benchmarks_only,
        args.include_question_bank or args.question_bank_only,
    )
    total_q = len(items)
    print(f"[{started_at}] running {total_q} questions against {args.base_url}")

    rows_path = run_dir / "rows.jsonl"
    token_box: dict[str, Any] = {"token": None, "used": 0}
    transport_failed_ids: list[str] = []
    pace = Pacer(args.min_interval_s)

    with (
        httpx.Client(timeout=120.0) as client,
        rows_path.open("w", encoding="utf-8") as out,
    ):
        for i, item in enumerate(items, 1):
            t0 = time.time()
            http, result, retries, completed = _ask(
                client, args.base_url, token_box, item["question"], pace=pace
            )
            dt = time.time() - t0
            failed = not completed
            if failed:
                transport_failed_ids.append(item["id"])
            raw_row = build_row(
                item, result, http, dt, transport_retries=retries, transport_failed=failed
            )
            row = stamp_row(
                raw_row, sha=sha, container_id=facts["container_id"], run_id=args.run_id
            )
            out.write(json.dumps(row) + "\n")
            out.flush()
            route_or_fail = (
                row["route"] or ("AUTH_ERR" if http in (401, 403) else f"HTTP_{http}")
                if completed
                else f"FAIL_HTTP_{http}"
            )
            retry_note = f" r={retries}" if retries else ""
            print(
                f"[{i:03d}/{total_q}] {row['id']:<10} {route_or_fail:<22} "
                f"{row.get('latency_ms') or 0:>5}ms server  {row['sec']:>4.1f}s wall{retry_note}"
            )

    log_text = _run(["docker", "logs", args.container])
    (run_dir / "backend.log").write_text(log_text, encoding="utf-8")
    spend_after = read_spend()
    v = validity(
        log_text,
        spend_before,
        spend_after,
        preflight_ok,
        transport_failed_ids=transport_failed_ids,
    )

    inputs = [FROZEN, UNANSWERABLE]
    if args.include_benchmarks or args.benchmarks_only:
        inputs.extend([BENCHMARK_FROZEN29, BENCHMARK_COMPOUND10, BENCHMARK_OOC13])

    manifest = {
        "run_id": args.run_id,
        "commit": sha,
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": args.base_url,
        "min_interval_s": args.min_interval_s,
        "container": facts,
        "validity": v,
        "questions_attempted": len(items),
        "input_files": input_fingerprints(inputs),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"captured {len(items)} rows in {run_dir} (valid={v['valid']}"
        + (f" reasons={v['reasons']}" if not v["valid"] else "")
        + ")"
    )
    return 0 if v["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
