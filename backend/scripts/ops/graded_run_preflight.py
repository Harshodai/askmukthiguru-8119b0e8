#!/usr/bin/env python3
"""Preflight for the graded clean-Docker run (plan items F1, F2, F3 run rule).

A graded number only means something if the stack under test is the commit under test.
Stage A/B/C of 2026-10-31 ran on a container that bind-mounted the live working tree,
carried a previous stage's env, and hit the OpenRouter spend cap mid-run. This script fails
(exit 1) unless ALL of these hold:

  1. the git working tree is clean (no modified, staged or untracked files);
  2. the running backend container has no bind mount over application code;
  3. the container started after HEAD was committed;
  4. every serving flag pinned in the graded override equals the container's real env;
  5. the Redis spend keys leave headroom for the run;
  6. (optional) the container log has no `spend limit` / `indeterminate` line.

    cd backend && .venv/bin/python -m scripts.ops.graded_run_preflight \\
        --override docker-compose.graded.yml [--need-usd 12] [--check-logs]

Read-only: it runs `git`, `docker inspect`, `docker exec ... printenv` and `redis-cli get`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

# Container paths that hold application code. A bind mount over any of them means the
# container runs the host's working tree, not the image.
CODE_DESTINATIONS = frozenset(
    {
        "/app/app",
        "/app/domain",
        "/app/rag",
        "/app/services",
        "/app/guardrails",
        "/app/routers",
        "/app/schemas",
        "/app/tests",
        "/app/benchmarks",
        "/app/tasks",
        "/app/ingest",
        "/app/evaluation",
        "/app/scripts",
        "/app/backend_scripts",
    }
)
SPEND_LIMIT_PATTERNS = (
    re.compile(r"spend limit", re.IGNORECASE),
    re.compile(r"indeterminate \(timeout/error\)", re.IGNORECASE),
)
# The two Redis keys of app/openrouter_budget.py (per UTC day / month).
DAY_KEY = "askmukthiguru:openrouter-spend:day:{date}"
MONTH_KEY = "askmukthiguru:openrouter-spend:month:{month}"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}: {self.detail}"


# ── pure checks (unit-tested) ────────────────────────────────────────────────


def check_git_clean(porcelain: str) -> Check:
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    if lines:
        head = "; ".join(ln.strip() for ln in lines[:5])
        return Check("git clean", False, f"{len(lines)} path(s) not committed: {head}")
    return Check("git clean", True, "no modified, staged or untracked files")


def check_no_code_binds(inspect_json: list[dict[str, Any]]) -> Check:
    mounts = (inspect_json[0].get("Mounts") if inspect_json else None) or []
    bad = sorted(
        m.get("Destination", "")
        for m in mounts
        if m.get("Type") == "bind" and m.get("Destination") in CODE_DESTINATIONS
    )
    if bad:
        return Check("no code bind mounts", False, "host code mounted at " + ", ".join(bad))
    return Check("no code bind mounts", True, "application code comes from the image")


def check_started_after_head(inspect_json: list[dict[str, Any]], head_epoch: float) -> Check:
    started = (((inspect_json or [{}])[0].get("State")) or {}).get("StartedAt", "")
    try:
        # Docker prints nanoseconds; trim to microseconds for fromisoformat.
        trimmed = re.sub(r"(\.\d{6})\d+", r"\1", started).replace("Z", "+00:00")
        started_epoch = datetime.fromisoformat(trimmed).timestamp()
    except ValueError:
        return Check("container newer than HEAD", False, f"unreadable StartedAt {started!r}")
    if started_epoch < head_epoch:
        return Check(
            "container newer than HEAD",
            False,
            f"started {datetime.fromtimestamp(started_epoch, UTC):%H:%M:%S}Z, before HEAD "
            f"{datetime.fromtimestamp(head_epoch, UTC):%H:%M:%S}Z; recreate it",
        )
    return Check("container newer than HEAD", True, "started after the last commit")


def check_env_pins(container_env: dict[str, str], pins: dict[str, str]) -> Check:
    wrong = {
        k: (container_env.get(k), v)
        for k, v in pins.items()
        if str(container_env.get(k, "")).strip().lower() != str(v).strip().lower()
    }
    if wrong:
        detail = "; ".join(f"{k}: container={a!r} override={b!r}" for k, (a, b) in wrong.items())
        return Check("env matches graded override", False, detail)
    return Check("env matches graded override", True, f"{len(pins)} pinned flag(s) equal")


def check_spend_headroom(
    day_spent: float | None,
    month_spent: float | None,
    day_cap: float,
    month_cap: float,
    need_usd: float,
) -> Check:
    if day_spent is None or month_spent is None:
        return Check("spend headroom", False, "Redis spend keys unreadable")
    day_left, month_left = day_cap - day_spent, month_cap - month_spent
    ok = day_left >= need_usd and month_left >= need_usd
    return Check(
        "spend headroom",
        ok,
        f"day ${day_spent:.2f}/${day_cap:.0f} (left ${day_left:.2f}), "
        f"month ${month_spent:.2f}/${month_cap:.0f} (left ${month_left:.2f}), "
        f"run needs ${need_usd:.2f}",
    )


def check_log_clean(log_text: str) -> Check:
    hits = [
        ln.strip()[:140]
        for ln in log_text.splitlines()
        if any(p.search(ln) for p in SPEND_LIMIT_PATTERNS)
    ]
    if hits:
        return Check("log has no spend-limit/indeterminate lines", False, f"{len(hits)}: {hits[0]}")
    return Check("log has no spend-limit/indeterminate lines", True, "clean")


def check_local_review_disabled(status_code: int | None, body: Any) -> Check:
    """Tier 3 item 5: the owner-only file-review API must not be live in a graded stack.

    The route is mounted unconditionally and fails closed inside itself, so a 404 is neither
    expected nor required. What must NOT happen is ``available: true``: that means the graded
    container is serving an owner-only preview API over local files.
    """
    if status_code is None:
        return Check("local review disabled", False, "status endpoint unreachable")
    if status_code in (401, 403, 404):
        return Check("local review disabled", True, f"HTTP {status_code}")
    if status_code == 200 and isinstance(body, dict) and body.get("available") is False:
        return Check(
            "local review disabled", True, f"available=false ({body.get('reason') or 'n/a'})"
        )
    available = body.get("available") if isinstance(body, dict) else None
    return Check(
        "local review disabled",
        False,
        f"HTTP {status_code} available={available!r} — route is live",
    )


def probe_local_review(base_url: str, timeout: float = 5.0) -> tuple[int | None, Any]:
    """GET the local-review status route. Read-only, never sends a query."""
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/api/first-person/local-review/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (localhost)
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:  # unreachable, non-JSON, timeout
        return None, None


def load_compose_yaml(path: Path) -> dict[str, Any]:
    """Parse a compose file, accepting Compose's ``!override`` / ``!reset`` merge tags."""
    import yaml

    class _ComposeLoader(yaml.SafeLoader):
        pass

    def _passthrough(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        return loader.construct_scalar(node)

    for tag in ("!override", "!reset"):
        _ComposeLoader.add_constructor(tag, _passthrough)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}  # noqa: S506


def read_override_pins(path: Path) -> dict[str, str]:
    """The ``environment`` mapping of the backend service in the graded override."""
    data = load_compose_yaml(path)
    env = ((data.get("services") or {}).get("backend") or {}).get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return {str(k): str(v) for k, v in env.items()}


# ── side-effecting collection ────────────────────────────────────────────────


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=True, timeout=60
    ).stdout


def _redis_password() -> str:
    env_file = BACKEND / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("REDIS_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return ""


def read_spend(container: str = "mukthiguru-redis") -> tuple[float | None, float | None]:
    now = datetime.now(UTC)
    out: list[float | None] = []
    for key in (
        DAY_KEY.format(date=now.strftime("%Y-%m-%d")),
        MONTH_KEY.format(month=now.strftime("%Y-%m")),
    ):
        try:
            raw = _run(
                [
                    "docker",
                    "exec",
                    container,
                    "redis-cli",
                    "-a",
                    _redis_password(),
                    "--no-auth-warning",
                    "get",
                    key,
                ]
            ).strip()
            out.append(float(raw) if raw else 0.0)
        except Exception:
            out.append(None)
    return out[0], out[1]


def run_preflight(args: argparse.Namespace) -> list[Check]:
    checks: list[Check] = []
    checks.append(check_git_clean(_run(["git", "status", "--porcelain"], cwd=REPO)))
    inspect_json = json.loads(_run(["docker", "inspect", args.container]))
    checks.append(check_no_code_binds(inspect_json))
    head_epoch = float(_run(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=REPO).strip())
    checks.append(check_started_after_head(inspect_json, head_epoch))
    container_env = dict(
        line.split("=", 1)
        for line in _run(["docker", "exec", args.container, "printenv"]).splitlines()
        if "=" in line
    )
    pins = read_override_pins(Path(args.override))
    checks.append(check_env_pins(container_env, pins))
    day, month = read_spend()
    checks.append(
        check_spend_headroom(
            day,
            month,
            float(container_env.get("OPENROUTER_DAILY_BUDGET_USD", "10")),
            float(container_env.get("OPENROUTER_MONTHLY_BUDGET_USD", "40")),
            args.need_usd,
        )
    )
    if args.check_logs:
        checks.append(check_log_clean(_run(["docker", "logs", args.container])))
    status_code, body = probe_local_review(args.base_url)
    checks.append(check_local_review_disabled(status_code, body))
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--override", default=str(BACKEND / "docker-compose.graded.yml"))
    ap.add_argument("--container", default="mukthiguru-backend")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--need-usd", type=float, default=12.0)
    ap.add_argument("--check-logs", action="store_true")
    args = ap.parse_args()
    checks = run_preflight(args)
    for c in checks:
        print(c.line())
    failed = [c for c in checks if not c.ok]
    print(
        f"\npreflight: {'FAIL' if failed else 'PASS'} ({len(checks) - len(failed)}/{len(checks)})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
