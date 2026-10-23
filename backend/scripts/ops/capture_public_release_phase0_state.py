#!/usr/bin/env python3
"""Capture the read-only pre-mutation state for the v10 public-release remediation.

Records, without changing anything:

* git identity (branch, HEAD, origin/main) and the dirty-file inventory;
* byte hashes of the first-person source/test/doc files and of every artifact
  the Phase-1 reconciliation depends on;
* Docker context, running containers, image identity and container start time;
* the effective first-person environment (host env file *and* the running
  container);
* the Qdrant collection/alias census and the live ``first_person_v10`` shape;
* the serving-route configuration that the harness flag controls.

The output is the machine-readable Phase-0 evidence record required by
``.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`` (WP0).

It never mutates source, Qdrant, aliases, Redis or the environment.

Usage:
    python -m scripts.ops.capture_public_release_phase0_state \\
        --output audits/evidence/public_release_phase0_state_2026-10-21.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "capture-public-release-phase0-state-v1"
DOCKER_BIN = "/Users/harshodaikolluru/.docker/bin/docker"

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"

#: Source files whose byte identity decides whether the running stack matches
#: the worktree. Mirrors the first-person file list used by the earlier capture.
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
    "backend/guardrails/lightweight_handler.py",
    "backend/scripts/ops/audit_first_person_readiness.py",
    "backend/scripts/ops/audit_first_person_v10_strict.py",
    "backend/scripts/ops/build_first_person_context_index.py",
    "backend/scripts/ops/build_fp_context_from_v9.py",
    "backend/scripts/ops/build_full_corpus_v10.py",
    "backend/scripts/ops/reconcile_v10_ecapa_verdicts.py",
    "backend/scripts/ops/validate_fp_context_candidate.py",
    "backend/scripts/ops/verify_speakers_ecapa.py",
    "backend/tests/test_reconcile_v10_ecapa_verdicts.py",
)

#: Artifacts the Phase-1 reconciliation reads. Paths are repo-relative; the
#: attribution archive lives outside the repo and is recorded when present.
EVIDENCE_ARTIFACTS = (
    ".work/fp_context/v9_points.json",
    ".work/fp_context/speaker_verdicts.json",
    ".work/fp_context/speaker_report.json",
    ".work/fp_context/asr_manifest_existing.json",
    ".work/fp_context/speaker_manifest_existing.json",
    ".work/fp_context/rights_manifest_existing.json",
    ".work/fp_context/candidate_existing.jsonl",
    ".work/fp_context/source_spans_existing.jsonl",
    ".work/fp_context/manifest.jsonl",
    ".work/fp_context/report.json",
)

EXTERNAL_ARTIFACTS = ("/Users/harshodaikolluru/mukthiguru_attribution_data",)


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        out = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=180,
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


def _describe(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "present": False}
    info: dict[str, Any] = {
        "path": str(path),
        "present": True,
        "bytes": path.stat().st_size if path.is_file() else None,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
    }
    if path.is_file():
        info["sha256"] = _sha256(path)
    return info


def _git_state() -> dict[str, Any]:
    status = _run(["git", "status", "--porcelain=v1", "-uall"])
    entries: list[dict[str, Any]] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        code = line[:2]
        path = line[3:].strip()
        entry: dict[str, Any] = {"status": code.strip(), "path": path}
        local = REPO_ROOT / path
        if local.is_file():
            entry["sha256"] = _sha256(local)
            entry["bytes"] = local.stat().st_size
        entries.append(entry)
    return {
        "head": _run(["git", "rev-parse", "HEAD"]),
        "branch": _run(["git", "branch", "--show-current"]),
        "origin_main": _run(["git", "rev-parse", "origin/main"]),
        "remotes": _run(["git", "remote", "-v"]),
        "recent_log": _run(["git", "log", "--oneline", "-5"]).splitlines(),
        "worktrees": _run(["git", "worktree", "list"]).splitlines(),
        "dirty_count": len(entries),
        "dirty": sorted(entries, key=lambda item: item["path"]),
    }


def _docker_state() -> dict[str, Any]:
    containers = _run([DOCKER_BIN, "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    images = _run(
        [DOCKER_BIN, "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}"]
    )
    backend_image = ""
    for line in containers.splitlines():
        if line.startswith("mukthiguru-backend\t"):
            backend_image = line.split("\t")[1]
    return {
        "docker_binary": DOCKER_BIN,
        "contexts": _run([DOCKER_BIN, "context", "ls"]),
        "containers": containers.splitlines(),
        "images": images.splitlines(),
        "backend_image": backend_image,
        "backend_image_created": (
            _run([DOCKER_BIN, "image", "inspect", backend_image, "--format", "{{.Created}}"])
            if backend_image
            else ""
        ),
        "backend_container_started": _run(
            [DOCKER_BIN, "inspect", "mukthiguru-backend", "--format", "{{.State.StartedAt}}"]
        ),
        "backend_container_image_id": _run(
            [DOCKER_BIN, "inspect", "mukthiguru-backend", "--format", "{{.Image}}"]
        ),
    }


def _env_state() -> dict[str, Any]:
    def _parse(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.is_file():
            return values
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith(("FIRST_PERSON", "FP_")):
                values[key] = value.strip()
        return values

    container: dict[str, str] = {}
    for line in _run([DOCKER_BIN, "exec", "mukthiguru-backend", "env"]).splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith(("FIRST_PERSON", "FP_")):
            container[key] = value.strip()
    return {
        "backend_env_file": _describe(BACKEND / ".env"),
        "repo_root_env_file": _describe(REPO_ROOT / ".env"),
        "backend_env_file_values": _parse(BACKEND / ".env"),
        "repo_root_env_file_values": _parse(REPO_ROOT / ".env"),
        "container_values": container,
    }


def _qdrant_state(base_url: str) -> dict[str, Any]:
    def _get(path: str) -> Any:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=30) as response:  # nosec B310 -- operator-supplied http(s) base URL, read-only audit call
            return json.load(response)

    try:
        listing = _get("/collections")["result"]["collections"]
        collections = [entry["name"] for entry in listing]
        aliases = {
            name: _get(f"/collections/{name}/aliases")["result"]["aliases"] for name in collections
        }
        info = (
            _get("/collections/first_person_v10")["result"]
            if "first_person_v10" in collections
            else {}
        )
        global_aliases = _get("/aliases")["result"]["aliases"]
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "collections": sorted(collections),
        "per_collection_aliases": aliases,
        "global_aliases": global_aliases,
        "first_person_v10": {
            "status": info.get("status"),
            "points_count": info.get("points_count"),
            "indexed_vectors_count": info.get("indexed_vectors_count"),
            "segments_count": info.get("segments_count"),
            "optimizer_status": info.get("optimizer_status"),
            "vectors_config": info.get("config", {}).get("params", {}).get("vectors"),
            "payload_schema": info.get("config", {}).get("payload_schema"),
        },
    }


def _serving_route_state() -> dict[str, Any]:
    """The code-level facts that decide whether a harness answer can be served."""
    facts: dict[str, Any] = {}
    config = BACKEND / "app" / "config.py"
    if config.is_file():
        text = config.read_text(encoding="utf-8", errors="replace")
        facts["config_first_person_flags"] = sorted(
            line.strip()
            for line in text.splitlines()
            if "FIRST_PERSON" in line and "=" in line and not line.strip().startswith("#")
        )
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    artifacts = {relative: _describe(REPO_ROOT / relative) for relative in EVIDENCE_ARTIFACTS}
    external = {path: _describe(Path(path)) for path in EXTERNAL_ARTIFACTS}

    state = {
        "schema": "first-person-public-release-phase0-state-v1",
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "repo_root": str(REPO_ROOT),
        "git": _git_state(),
        "docker": _docker_state(),
        "env": _env_state(),
        "qdrant": _qdrant_state(args.qdrant_url),
        "serving_route": _serving_route_state(),
        "first_person_file_hashes": {
            relative: {
                "sha256": _sha256(REPO_ROOT / relative),
                "bytes": (REPO_ROOT / relative).stat().st_size
                if (REPO_ROOT / relative).is_file()
                else None,
            }
            for relative in FIRST_PERSON_FILES
        },
        "evidence_artifacts": artifacts,
        "external_artifacts": external,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}")
    print(f"head={state['git']['head']} dirty={state['git']['dirty_count']}")
    print(
        "harness env file="
        f"{state['env']['backend_env_file_values'].get('FIRST_PERSON_CONTEXT_HARNESS_ENABLED')}"
        f" container="
        f"{state['env']['container_values'].get('FIRST_PERSON_CONTEXT_HARNESS_ENABLED')}"
    )
    print(
        "collection="
        f"{state['env']['backend_env_file_values'].get('FIRST_PERSON_COLLECTION')}"
        f" aliases={state['qdrant'].get('global_aliases')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
