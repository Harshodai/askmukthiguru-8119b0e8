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
ENV_PREFIXES = ("FIRST_PERSON_", "OPENROUTER_", "CELERY_TASK", "LLM_PROVIDER")


# ── pure helpers (unit-tested) ───────────────────────────────────────────────


def refuse_if_evidence_exists(run_dir: Path) -> None:
    """Evidence is never overwritten: a run id that already has a log or rows is spent."""
    for name in ("backend.log", "rows.jsonl", "manifest.json"):
        if (run_dir / name).exists():
            raise FileExistsError(f"{run_dir / name} already exists; use a new --run-id")


def stamp_row(row: dict[str, Any], *, sha: str, container_id: str, run_id: str) -> dict[str, Any]:
    return {**row, "sha": sha, "container_id": container_id, "run_id": run_id}


def build_row(
    item: dict[str, Any], result: dict[str, Any], http: int, wall_seconds: float
) -> dict[str, Any]:
    cits = result.get("citations") or []
    return {
        **item,
        "http": http,
        "answer": result.get("response") or "",
        "route": result.get("route_decision"),
        "model_used": result.get("model_used"),
        "grounding": result.get("grounding_state"),
        "citations": [
            {
                "text": c.get("text_snippet", ""),
                "speaker": c.get("speaker"),
                "speaker_verified": c.get("speaker_verified"),
                "url": c.get("url"),
                "t": c.get("timestamp_seconds"),
            }
            for c in cits
        ],
        "notices": result.get("safety_notices") or [],
        # Server-side latency is what the p95 bar is read from; wall clock includes polling.
        "latency_ms": result.get("latency_ms"),
        "sec": round(wall_seconds, 1),
    }


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
    log_text: str, spend_before: tuple[Any, Any], spend_after: tuple[Any, Any], preflight_ok: bool
) -> dict[str, Any]:
    """A run is valid only if the preflight passed and the log shows no blocked LLM calls."""
    log = check_log_clean(log_text)
    reasons = []
    if not preflight_ok:
        reasons.append("preflight failed")
    if not log.ok:
        reasons.append(log.detail)
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
        "flags": {k: v for k, v in sorted(env.items()) if k.startswith(ENV_PREFIXES)},
    }


def _items(include_frozen: bool, include_unanswerable: bool) -> list[dict[str, Any]]:
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
    return items


def _ask(client: Any, base: str, token_box: dict[str, Any], question: str) -> tuple[int, dict]:
    """One question through /api/chat with an anonymous session (5 chats per session)."""
    if token_box.get("token") is None or token_box["used"] >= 4:
        for _ in range(25):
            r = client.post(base + "/api/auth/anon-session")
            if r.status_code == 200:
                token_box.update(token=r.json()["token"], used=0)
                break
            time.sleep(float(r.headers.get("retry-after", "8")) + 2)
        else:
            raise SystemExit("anon-session endpoint stayed rate limited")
    token_box["used"] += 1
    token = token_box["token"]
    headers = {"X-Session-Id": token}
    r = client.post(
        base + "/api/chat",
        json={"messages": [], "user_message": question, "session_id": token},
        headers=headers,
    )
    if r.status_code == 202:
        job = r.json()["job_id"]
        deadline = time.time() + 110
        while time.time() < deadline:
            j = client.get(base + f"/api/jobs/{job}", headers=headers).json()
            if j.get("status") in ("completed", "failed"):
                return r.status_code, j.get("result") or {}
            time.sleep(1.0)
        return r.status_code, {}
    return r.status_code, (r.json() if r.status_code == 200 else {})


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
    with httpx.Client(timeout=120) as client, rows_path.open("w", encoding="utf-8") as out:
        for item in _items(not args.no_frozen, not args.no_unanswerable):
            t0 = time.time()
            http, result = _ask(client, args.base_url, token_box, item["question"])
            row = stamp_row(
                build_row(item, result, http, time.time() - t0),
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
    verdict = validity(log_text.stdout + log_text.stderr, spend_before, read_spend(), preflight_ok)
    manifest = {"run_id": args.run_id, "sha": sha, **facts, **verdict}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("run_id", "sha", "valid", "reasons")}, indent=2))
    return 0 if verdict["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
