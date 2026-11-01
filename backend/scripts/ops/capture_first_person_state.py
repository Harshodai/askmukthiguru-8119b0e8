#!/usr/bin/env python3
"""Capture the read-only pre-mutation state of the first-person stack.

Records git identity, the dirty-file inventory and byte hashes of the
first-person files, Docker context/containers/images, the effective
first-person environment (host file and running container), and the Qdrant
collection/alias census. It never mutates source, Qdrant, aliases or env.

Usage:
    python -m scripts.ops.capture_first_person_state --output <path>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"

FIRST_PERSON_ENV_PREFIXES = ("FIRST_PERSON", "FP_")
FIRST_PERSON_FILES = (
    "backend/app/api/first_person.py",
    "backend/app/config.py",
    "backend/app/pipeline/stages/first_person_bridge.py",
    "backend/domain/first_person_context.py",
    "backend/services/first_person_context_harness.py",
    "backend/services/first_person_context_selector.py",
    "backend/services/first_person_context_store.py",
    "backend/services/first_person_pipeline.py",
    "backend/services/quote_weaver.py",
    "backend/scripts/ops/audit_first_person_readiness.py",
    "backend/scripts/ops/build_first_person_context_index.py",
    "backend/scripts/ops/build_fp_context_from_v9.py",
    "backend/scripts/ops/build_full_corpus_v10.py",
    "backend/scripts/ops/validate_fp_context_candidate.py",
    "backend/scripts/ops/verify_speakers_ecapa.py",
    "backend/tests/test_first_person_context_contract.py",
    "backend/tests/test_first_person_context_harness.py",
    "backend/tests/test_first_person_context_red_team.py",
    "backend/tests/test_first_person_context_serving.py",
    "backend/tests/test_first_person_context_shadow_route.py",
    "backend/tests/test_first_person_context_store.py",
    "backend/tests/test_fp_context_builder_from_v9.py",
    "backend/tests/test_validate_fp_context_candidate.py",
)


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        out = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"<error: {exc}>"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state() -> dict[str, Any]:
    status = _run(["git", "status", "--porcelain=v1", "-uall"])
    dirty: list[dict[str, str]] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        code, _, path = line[:2], line[2:3], line[3:]
        entry = {"status": code.strip(), "path": path.strip()}
        local = Path(path.strip())
        if local.is_file():
            entry["sha256"] = _sha256(local) or ""
            entry["bytes"] = str(local.stat().st_size)
        dirty.append(entry)
    return {
        "head": _run(["git", "rev-parse", "HEAD"]),
        "branch": _run(["git", "branch", "--show-current"]),
        "origin_main": _run(["git", "rev-parse", "origin/main"]),
        "remotes": _run(["git", "remote", "-v"]),
        "recent_log": _run(["git", "log", "--oneline", "-10"]).splitlines(),
        "dirty_count": len(dirty),
        "dirty": sorted(dirty, key=lambda item: item["path"]),
    }


def _docker_state() -> dict[str, Any]:
    docker = "/Users/harshodaikolluru/.docker/bin/docker"
    containers = _run([docker, "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    images = _run(
        [docker, "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}"]
    )
    backend_image = ""
    for line in containers.splitlines():
        if line.startswith("mukthiguru-backend\t"):
            backend_image = line.split("\t")[1]
    image_created = ""
    if backend_image:
        image_created = _run(
            [docker, "image", "inspect", backend_image, "--format", "{{.Created}}"]
        )
    return {
        "docker_binary": docker,
        "contexts": _run([docker, "context", "ls"]),
        "containers": containers.splitlines(),
        "images": images.splitlines(),
        "backend_image": backend_image,
        "backend_image_created": image_created,
        "backend_container_started": _run(
            [docker, "inspect", "mukthiguru-backend", "--format", "{{.State.StartedAt}}"]
        ),
        "backend_container_image_id": _run(
            [docker, "inspect", "mukthiguru-backend", "--format", "{{.Image}}"]
        ),
    }


def _env_state() -> dict[str, Any]:
    file_env: dict[str, str] = {}
    env_file = BACKEND / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith(FIRST_PERSON_ENV_PREFIXES):
                file_env[key] = value.strip()
    container_env: dict[str, str] = {}
    docker = "/Users/harshodaikolluru/.docker/bin/docker"
    raw = _run([docker, "exec", "mukthiguru-backend", "env"])
    for line in raw.splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith(FIRST_PERSON_ENV_PREFIXES):
            container_env[key] = value.strip()
    return {
        "backend_env_file": str(env_file),
        "backend_env_file_mtime": datetime.fromtimestamp(
            env_file.stat().st_mtime, tz=UTC
        ).isoformat()
        if env_file.is_file()
        else None,
        "first_person_env_file_values": file_env,
        "first_person_container_values": container_env,
    }


def _qdrant_state(base_url: str) -> dict[str, Any]:
    def _get(path: str) -> Any:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=30) as response:  # nosec B310 -- operator-supplied http(s) base URL, read-only audit call
            return json.load(response)

    collections = []
    aliases: dict[str, Any] = {}
    info: dict[str, Any] = {}
    try:
        listing = _get("/collections")["result"]["collections"]
        for entry in listing:
            name = entry["name"]
            collections.append(name)
            aliases[name] = _get(f"/collections/{name}/aliases")["result"]["aliases"]
        if "first_person_v10" in collections:
            info = _get("/collections/first_person_v10")["result"]
    except Exception as exc:  # pragma: no cover - read-only best effort
        return {"error": str(exc)}
    return {
        "collections": sorted(collections),
        "aliases": aliases,
        "first_person_v10_info": {
            "points_count": info.get("points_count"),
            "indexed_vectors_count": info.get("indexed_vectors_count"),
            "status": info.get("status"),
            "optimizer_status": info.get("optimizer_status"),
            "payload_schema": info.get("payload_schema"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    files = {}
    for relative in FIRST_PERSON_FILES:
        path = REPO_ROOT / relative
        files[relative] = {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size if path.is_file() else None,
        }

    state = {
        "schema": "first-person-phase0-state-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "repo_root": str(REPO_ROOT),
        "git": _git_state(),
        "docker": _docker_state(),
        "env": _env_state(),
        "qdrant": _qdrant_state(args.qdrant_url),
        "first_person_file_hashes": files,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}")
    print(f"head={state['git']['head']} dirty={state['git']['dirty_count']}")
    print(
        f"harness env file={state['env']['first_person_env_file_values'].get('FIRST_PERSON_CONTEXT_HARNESS_ENABLED')}"
    )
    print(
        "harness container="
        f"{state['env']['first_person_container_values'].get('FIRST_PERSON_CONTEXT_HARNESS_ENABLED')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
