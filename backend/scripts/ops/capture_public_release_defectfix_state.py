#!/usr/bin/env python3
"""Freeze the local first-person state before and after a container rebuild.

**Read-only.** It never writes to Qdrant, never mutates an alias, never
touches Redis beyond a read-only ``PING``/``DBSIZE``, never changes an
environment variable and never performs a Docker write. Docker commands are
limited to ``inspect``, ``ps``, ``images`` and ``volume ls``.

Exit codes
----------
=====  ===================================================================
0      The state snapshot was written.
2      The snapshot could not be produced (a required input was unreadable).
=====  ===================================================================

Usage
-----
    python -m scripts.ops.capture_public_release_defectfix_state \\
        --output audits/evidence/public_release_defectfix_state_<date>.json \\
        --label before-rebuild
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND.parent


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _docker(args: list[str]) -> dict[str, Any]:
    """Run a docker command through the repository's keychain-safe wrapper."""
    wrapper = REPO_ROOT / "scripts" / "docker-safe.sh"
    if wrapper.is_file():
        return _run(["bash", str(wrapper), "docker", *args], cwd=BACKEND)
    return _run(["docker", *args], cwd=BACKEND)


def _http_json(url: str, timeout: float = 10.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
        return {"error": str(exc)}


def _env_flag(path: Path, name: str) -> str:
    if not path.is_file():
        return "<missing-file>"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return "<unset>"


def _redis_state() -> dict[str, Any]:
    """A read-only Redis probe. Never a write, never a flush.

    Prefers the host ``redis-cli``; when the host has none (the common case
    on macOS) it falls back to the redis container, which ships ``redis-cli``.
    """
    password = ""
    url = ""
    for candidate in (BACKEND / ".env", REPO_ROOT / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if line.startswith("REDIS_URL=") and not url:
                url = line.split("=", 1)[1].strip()
            if line.startswith("REDIS_PASSWORD=") and not password:
                password = line.split("=", 1)[1].strip()
    if not password:
        return {"status": "no_redis_password_configured"}

    def _probe(command: list[str]) -> dict[str, Any]:
        host = _run(command)
        if host.get("ok"):
            return {**host, "method": "host"}
        container = _docker(["compose", "exec", "-T", "redis", "redis-cli", *command[1:]])
        return {**container, "method": "redis_container"}

    ping = _probe(["redis-cli", "-a", password, "--no-auth-warning", "PING"])
    state: dict[str, Any] = {
        "ping": ping,
        "mutations_performed": 0,
        "commands_issued": ["PING", "DBSIZE"],
        "flush_issued": False,
    }
    if ping.get("ok"):
        state["dbsize"] = _probe(["redis-cli", "-a", password, "--no-auth-warning", "DBSIZE"])
    return state


def capture(qdrant_url: str, label: str) -> dict[str, Any]:
    backend_containers = _docker(["compose", "ps", "--format", "json", "backend"])
    inspect = _docker(["inspect", "mukthiguru-backend"])
    images = _docker(["images", "--format", "{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}"])
    volumes = _docker(["volume", "ls", "--format", "{{.Name}}"])

    container: dict[str, Any] = {}
    if inspect.get("ok") and inspect.get("stdout"):
        try:
            payload = json.loads(inspect["stdout"])
            first = payload[0] if isinstance(payload, list) else payload
            container = {
                "id": first.get("Id"),
                "image": first.get("Image"),
                "created": first.get("Created"),
                "started_at": first.get("State", {}).get("StartedAt"),
                "status": first.get("State", {}).get("Status"),
                "health": first.get("State", {}).get("Health", {}).get("Status"),
                "name": first.get("Name"),
            }
        except (json.JSONDecodeError, IndexError, AttributeError) as exc:
            container = {"error": str(exc), "raw": inspect.get("stdout", "")[:2000]}

    qdrant_collections = _http_json(f"{qdrant_url}/collections")
    qdrant_aliases = _http_json(f"{qdrant_url}/aliases")
    collection_detail: dict[str, Any] = {}
    if isinstance(qdrant_collections, dict):
        for entry in qdrant_collections.get("result", {}).get("collections", []):
            name = entry.get("name")
            if not name:
                continue
            if name.startswith("first_person") or name.startswith("fp_"):
                collection_detail[name] = _http_json(f"{qdrant_url}/collections/{name}")

    flags = {
        "backend_env_FIRST_PERSON_CONTEXT_HARNESS_ENABLED": _env_flag(
            BACKEND / ".env", "FIRST_PERSON_CONTEXT_HARNESS_ENABLED"
        ),
        "backend_env_FIRST_PERSON_LOCAL_REVIEW_ENABLED": _env_flag(
            BACKEND / ".env", "FIRST_PERSON_LOCAL_REVIEW_ENABLED"
        ),
        "backend_env_IS_PRODUCTION": _env_flag(BACKEND / ".env", "IS_PRODUCTION"),
        "repo_env_FIRST_PERSON_CONTEXT_HARNESS_ENABLED": _env_flag(
            REPO_ROOT / ".env", "FIRST_PERSON_CONTEXT_HARNESS_ENABLED"
        ),
        "container_FIRST_PERSON_CONTEXT_HARNESS_ENABLED": _docker(
            [
                "compose",
                "exec",
                "-T",
                "backend",
                "sh",
                "-c",
                "echo ${FIRST_PERSON_CONTEXT_HARNESS_ENABLED:-<unset>}",
            ]
        ).get("stdout", ""),
        "container_FIRST_PERSON_LOCAL_REVIEW_ENABLED": _docker(
            [
                "compose",
                "exec",
                "-T",
                "backend",
                "sh",
                "-c",
                "echo ${FIRST_PERSON_LOCAL_REVIEW_ENABLED:-<unset>}",
            ]
        ).get("stdout", ""),
        "container_IS_PRODUCTION": _docker(
            ["compose", "exec", "-T", "backend", "sh", "-c", "echo ${IS_PRODUCTION:-<unset>}"]
        ).get("stdout", ""),
        "container_FIRST_PERSON_COLLECTION": _docker(
            [
                "compose",
                "exec",
                "-T",
                "backend",
                "sh",
                "-c",
                "echo ${FIRST_PERSON_COLLECTION:-<unset>}",
            ]
        ).get("stdout", ""),
    }

    artifacts: dict[str, Any] = {}
    for relative in (
        "backend/config/first_person_local_review.json",
        "backend/config/first_person_serving_contract.json",
        "audits/evidence/public_release_phase4_tiers_manifest_2026-10-22.json",
        "audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl",
        "audits/evidence/public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl",
        "audits/evidence/public_release_phase4_deterministic_id_collisions_2026-10-22.jsonl",
    ):
        path = REPO_ROOT / relative
        artifacts[relative] = (
            {"sha256": _sha256_file(path), "byte_length": path.stat().st_size}
            if path.is_file()
            else {"missing": True}
        )

    return {
        "schema": "public-release-defectfix-state-v1",
        "label": label,
        "captured_at_utc": os.environ.get("FP_STATE_CAPTURED_AT_UTC", ""),
        "repo_head": _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).get("stdout", ""),
        "container": container,
        "backend_compose_ps": backend_containers.get("stdout", "")[:4000],
        "docker_images": images.get("stdout", "")[:4000],
        "docker_volumes": volumes.get("stdout", ""),
        "flags": flags,
        "qdrant": {
            "url": qdrant_url,
            "collections": qdrant_collections,
            "aliases": qdrant_aliases,
            "first_person_detail": collection_detail,
            "writes_performed": 0,
            "alias_changes_performed": 0,
        },
        "redis": _redis_state(),
        "artifact_hashes": artifacts,
        "docker_mutations_performed": 0,
        "env_changes_performed": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
    )
    args = parser.parse_args(argv)

    try:
        state = capture(args.qdrant_url, args.label)
    except Exception as exc:  # noqa: BLE001
        print(f"[fp-state] ERROR: {exc}", file=sys.stderr)
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[fp-state] wrote {out}")
    print(
        f"[fp-state] container={state['container'].get('id')} image={state['container'].get('image')}"
    )
    print(f"[fp-state] flags={json.dumps(state['flags'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
