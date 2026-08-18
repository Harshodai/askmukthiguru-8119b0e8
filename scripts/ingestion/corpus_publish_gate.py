#!/usr/bin/env python3
"""Fail-closed write-audit-publish gate for the transcript corpus.

The gate never mutates the source corpus. It consumes a completed deterministic
corpus audit, refuses publication when structural/integrity issues exist, and
writes a release snapshot atomically only when every package is in an allowed
trust state. The default allowed states intentionally exclude needs_review,
sound_only, unavailable, and dead_lettered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    from alignment_contract import validate_alignment_evidence
except ImportError:
    from scripts.ingestion.alignment_contract import validate_alignment_evidence

GATE_VERSION = "1.0.0"
DEFAULT_ALLOWED_STATES = {"trusted", "trusted_after_review"}
CANONICAL_FILES = (
    "transcript.md",
    "quality_report.json",
    "canonical_segments.json",
    "correction_ledger.json",
    "artifact_manifest.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_sha(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return os.getenv("GIT_SHA", "unknown-sha")


def validate_audit(audit: Dict[str, Any], allowed_states: Set[str]) -> List[str]:
    errors: List[str] = []
    summary = audit.get("summary") or {}
    if summary.get("issue_package_count", 0) != 0:
        errors.append("audit_issue_package_count_nonzero")
    if summary.get("manifest_artifact_hash_mismatch_packages", 0) != 0:
        errors.append("manifest_artifact_hash_mismatches_present")
    if summary.get("manifest_raw_hash_mismatch_packages", 0) != 0:
        errors.append("manifest_raw_hash_mismatches_present")
    packages = audit.get("packages")
    if not isinstance(packages, list) or not packages:
        errors.append("audit_packages_missing_or_empty")
        return errors
    for package in packages:
        video_id = package.get("video_id", "unknown")
        if not package.get("package_ok"):
            errors.append("package_not_ok:" + str(video_id))
        state = package.get("quality_state")
        if state not in allowed_states:
            errors.append("package_state_not_publishable:%s=%s" % (video_id, state))
    return errors


def collect_package_record(pkg: Path, audit_package: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    quality = read_json(pkg / "quality_report.json")
    segments_payload = read_json(pkg / "canonical_segments.json")
    manifest = read_json(pkg / "artifact_manifest.json")
    if manifest.get("video_id") not in (None, pkg.name):
        errors.append("manifest_video_id_mismatch")
    if quality.get("video_id") not in (None, pkg.name):
        errors.append("quality_video_id_mismatch")
    if quality.get("quality_state") != audit_package.get("quality_state"):
        errors.append("audit_quality_state_mismatch")
    manifest_artifacts = manifest.get("artifacts", {})
    artifacts: Dict[str, Dict[str, Any]] = {}
    for filename in CANONICAL_FILES[:-1]:
        file_path = pkg / filename
        entry = manifest_artifacts.get(filename) if isinstance(manifest_artifacts, dict) else None
        if not file_path.is_file():
            errors.append("missing_canonical:" + filename)
            continue
        if not isinstance(entry, dict) or not entry.get("sha256"):
            errors.append("manifest_entry_missing:" + filename)
        else:
            actual = sha256_file(file_path)
            if actual != entry.get("sha256"):
                errors.append("manifest_hash_mismatch:" + filename)
        artifacts[filename] = {"sha256": sha256_file(file_path), "byte_size": file_path.stat().st_size}
    raw_attempts = manifest.get("raw_source_attempts", [])
    if isinstance(raw_attempts, list):
        for attempt in raw_attempts:
            if not isinstance(attempt, dict) or not attempt.get("raw_path"):
                errors.append("raw_attempt_malformed")
                continue
            raw_path = pkg / str(attempt["raw_path"])
            if not raw_path.is_file():
                errors.append("raw_source_missing:" + str(attempt["raw_path"]))
            elif attempt.get("sha256") and sha256_file(raw_path) != attempt.get("sha256"):
                errors.append("raw_source_hash_mismatch:" + str(attempt["raw_path"]))
    errors.extend(validate_alignment_evidence(
        quality,
        segments_payload,
        quality.get("quality_state") in DEFAULT_ALLOWED_STATES,
    ))
    return {
        "video_id": pkg.name,
        "quality_state": quality.get("quality_state"),
        "quality_score": quality.get("quality_score"),
        "source_url": manifest.get("source_url"),
        "artifact_manifest_hash": manifest.get("manifest_hash"),
        "artifacts": artifacts,
        "errors": errors,
    }


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def gate_failure(errors: List[str]) -> None:
    from collections import Counter
    error_types = Counter(error.split(":", 1)[0] for error in errors)
    raise SystemExit(json.dumps({
        "publishable": False,
        "gate_version": GATE_VERSION,
        "error_count": len(errors),
        "error_type_counts": dict(sorted(error_types.items())),
        "error_samples": errors[:25],
    }, indent=2))


def build_release(repo: Path, corpus: Path, audit_path: Path, allowed_states: Set[str]) -> Dict[str, Any]:
    audit = read_json(audit_path)
    errors = validate_audit(audit, allowed_states)
    if errors:
        gate_failure(errors)
    package_records = []
    audit_by_id = {str(x.get("video_id")): x for x in audit.get("packages", [])}
    for package in sorted(p for p in corpus.iterdir() if p.is_dir()):
        if package.name not in audit_by_id:
            continue
        package_records.append(collect_package_record(package, audit_by_id[package.name]))
    package_errors = [f"{x['video_id']}:{err}" for x in package_records for err in x.get("errors", [])]
    if package_errors:
        gate_failure(package_errors)
    release = {
        "gate_version": GATE_VERSION,
        "publishable": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(repo),
        "audit_sha256": sha256_file(audit_path),
        "corpus_root": str(corpus),
        "allowed_quality_states": sorted(allowed_states),
        "package_count": len(package_records),
        "packages": package_records,
    }
    canonical = json.dumps(release, sort_keys=True, ensure_ascii=False).encode("utf-8")
    release["release_sha256"] = hashlib.sha256(canonical).hexdigest()
    return release


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed transcript corpus write-audit-publish gate")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-state", action="append", dest="allowed_states")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    allowed = set(args.allowed_states or DEFAULT_ALLOWED_STATES)
    release = build_release(args.repo.resolve(), args.corpus.resolve(), args.audit.resolve(), allowed)
    if not args.check_only:
        atomic_write_json(args.output.resolve(), release)
    print(json.dumps({
        "publishable": True,
        "gate_version": GATE_VERSION,
        "package_count": release["package_count"],
        "release_sha256": release["release_sha256"],
        "output": None if args.check_only else str(args.output.resolve()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
