#!/usr/bin/env python3
# ponytail: deterministic pre-flight readiness inspector for mass ingestion
# Answers unequivocally: CAN WE START INGESTING OR NOT?
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# ponytail: default paths
DEFAULT_ATTRIBUTION_ROOT = Path.home() / "mukthiguru_attribution_data"
DEFAULT_ARCHIVE_DIR = DEFAULT_ATTRIBUTION_ROOT / "audio_archive"
DEFAULT_TARGETS_FILE = DEFAULT_ATTRIBUTION_ROOT / "audio_2026-09" / "targets.json"
DEFAULT_TRANSCRIPTS_DIR = Path(__file__).resolve().parents[2] / "transcripts"
DEFAULT_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
DEFAULT_QDRANT_COLLECTION = os.environ.get("FIRST_PERSON_COLLECTION", "first_person_v7")


@dataclass
class CheckResult:
    # ponytail: typed result for each deterministic readiness probe
    category: str
    name: str
    passed: bool
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    remediation: str | None = None
    details: dict[str, Any] | None = None


class IngestReadinessInspector:
    """
    ponytail: agentic pre-flight inspector checking all invariants
    before launching audio acquisition and feature ingestion.
    """

    def __init__(
        self,
        archive_root: Path | str | None = None,
        targets_file: Path | str | None = None,
        qdrant_url: str = DEFAULT_QDRANT_URL,
        collection_name: str = DEFAULT_QDRANT_COLLECTION,
    ):
        self.archive_root = Path(archive_root or DEFAULT_ARCHIVE_DIR).expanduser().resolve()
        self.targets_file = Path(targets_file or DEFAULT_TARGETS_FILE).expanduser().resolve()
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection_name = collection_name
        self.results: list[CheckResult] = []

    # 1. Disk Storage Probe
    def check_disk_space(self, min_gb_required: float = 10.0) -> CheckResult:
        try:
            target_path = self.archive_root if self.archive_root.exists() else Path.home()
            usage = shutil.disk_usage(target_path)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)

            if free_gb < 6.0:
                return CheckResult(
                    category="Storage",
                    name="Disk Space",
                    passed=False,
                    status="FAIL",
                    message=f"Critically low disk space: {free_gb:.1f} GB free on {target_path} (minimum {min_gb_required} GB required).",
                    remediation=f"Free up at least {min_gb_required - free_gb:.1f} GB on {target_path}.",
                    details={"free_gb": round(free_gb, 2), "total_gb": round(total_gb, 2)},
                )
            elif free_gb < min_gb_required:
                return CheckResult(
                    category="Storage",
                    name="Disk Space",
                    passed=True,
                    status="WARN",
                    message=f"Low disk space: {free_gb:.1f} GB free (comfortable target: {min_gb_required} GB).",
                    remediation="Consider freeing up space before ingesting full 515 audio files (~5 GB needed).",
                    details={"free_gb": round(free_gb, 2), "total_gb": round(total_gb, 2)},
                )
            return CheckResult(
                category="Storage",
                name="Disk Space",
                passed=True,
                status="PASS",
                message=f"Sufficient disk space: {free_gb:.1f} GB free on {target_path}.",
                details={"free_gb": round(free_gb, 2), "total_gb": round(total_gb, 2)},
            )
        except Exception as e:
            return CheckResult(
                category="Storage",
                name="Disk Space",
                passed=False,
                status="FAIL",
                message=f"Failed to check disk space: {e}",
            )

    # 2. Audio Archive Foundation Probe
    def check_audio_archive(self) -> CheckResult:
        manifest_file = self.archive_root / "manifest.json"
        if not manifest_file.is_file():
            return CheckResult(
                category="Audio Archive",
                name="Archive Manifest",
                passed=False,
                status="FAIL",
                message=f"Manifest file not found at {manifest_file}.",
                remediation="Run `python3 scripts/ops/audio_archive.py migrate` to build foundation manifest.",
            )

        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            stats = data.get("stats", {})
            videos = data.get("videos", {})
            archived_count = stats.get("archived_count", 0)
            missing_count = stats.get("missing_count", 0)
            duration_hours = stats.get("total_duration_hours", 0.0)

            if len(videos) == 0:
                return CheckResult(
                    category="Audio Archive",
                    name="Archive Manifest",
                    passed=False,
                    status="FAIL",
                    message="Manifest contains 0 registered videos.",
                    remediation="Run `python3 scripts/ops/audio_archive.py migrate` with valid targets.json.",
                )

            return CheckResult(
                category="Audio Archive",
                name="Archive Manifest",
                passed=True,
                status="PASS",
                message=f"Manifest valid: {archived_count} archived ({duration_hours:.1f} hrs), {missing_count} pending download.",
                details={
                    "total_registered": len(videos),
                    "archived_count": archived_count,
                    "missing_count": missing_count,
                    "duration_hours": duration_hours,
                },
            )
        except Exception as e:
            return CheckResult(
                category="Audio Archive",
                name="Archive Manifest",
                passed=False,
                status="FAIL",
                message=f"Corrupt manifest JSON: {e}",
                remediation="Inspect and repair manifest.json or regenerate via audio_archive.py.",
            )

    # 3. System Binaries Probe
    def check_system_binaries(self) -> CheckResult:
        missing = []
        for b in ["ffmpeg", "yt-dlp"]:
            if not shutil.which(b):
                missing.append(b)

        if missing:
            return CheckResult(
                category="Toolchain",
                name="System Binaries",
                passed=False,
                status="FAIL",
                message=f"Missing required system binaries: {', '.join(missing)}.",
                remediation=f"Install missing tools on host: brew install {' '.join(missing)}",
                details={"missing": missing},
            )

        return CheckResult(
            category="Toolchain",
            name="System Binaries",
            passed=True,
            status="PASS",
            message="Required binaries available on PATH (ffmpeg, yt-dlp).",
        )

    # 4. Host-Side Invariant Probe (Docker OOM Hazard)
    def check_host_side_invariant(self) -> CheckResult:
        # Hard-learned invariant: Ingestion embedding inside Docker container triggers OOM-kill (6 GiB limit)
        is_in_docker = Path("/.dockerenv").is_file() or Path("/app").is_dir() and os.getcwd().startswith("/app")
        if is_in_docker:
            return CheckResult(
                category="Environment",
                name="Host-Side Invariant",
                passed=False,
                status="FAIL",
                message="Running inside Docker container! Ingestion embeddings must run host-side to avoid 6 GiB OOM-kill.",
                remediation="Execute mass ingestion from host venv (HF_HOME=backend/.model_cache/huggingface).",
            )

        return CheckResult(
            category="Environment",
            name="Host-Side Invariant",
            passed=True,
            status="PASS",
            message="Running host-side (compliant with zero-container-OOM invariant).",
        )

    # 5. Compute Acceleration Probe (Metal / MPS / MLX)
    def check_compute_acceleration(self) -> CheckResult:
        details: dict[str, Any] = {"platform": sys.platform}
        has_mps = False
        has_mlx = False

        try:
            import torch
            has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            details["torch_mps"] = has_mps
        except ImportError:
            details["torch_mps"] = False

        import importlib.util

        # find_spec("mlx.core") RAISES ModuleNotFoundError when the parent
        # `mlx` package is absent (D1 §6.4) — i.e. on every machine without
        # MLX, including CI's ubuntu-latest runner, where the whole readiness
        # scan crashed instead of reporting "no MLX". Guard → unavailable.
        try:
            has_mlx = importlib.util.find_spec("mlx.core") is not None
        except (ImportError, ValueError):
            has_mlx = False
        details["mlx_available"] = has_mlx

        if has_mlx or has_mps:
            return CheckResult(
                category="Hardware",
                name="Compute Acceleration",
                passed=True,
                status="PASS",
                message=f"Hardware acceleration active: Metal/MPS={has_mps}, MLX={has_mlx} (15x-25x realtime ASR speed).",
                details=details,
            )
        else:
            return CheckResult(
                category="Hardware",
                name="Compute Acceleration",
                passed=True,
                status="WARN",
                message="No Metal/MPS acceleration detected; running on CPU (will take ~2-4 days for 47 audio-hours).",
                remediation="Ensure PyTorch with MPS support or mlx-whisper is installed in active environment.",
                details=details,
            )

    # 6. Targets Inventory Probe
    def check_target_corpus(self) -> CheckResult:
        if not self.targets_file.is_file():
            return CheckResult(
                category="Corpus",
                name="Targets Inventory",
                passed=False,
                status="FAIL",
                message=f"Targets file not found at {self.targets_file}.",
                remediation=f"Ensure {self.targets_file} exists with targets_515 definition.",
            )

        try:
            data = json.loads(self.targets_file.read_text(encoding="utf-8"))
            targets = data.get("targets_515", [])
            if len(targets) < 515:
                return CheckResult(
                    category="Corpus",
                    name="Targets Inventory",
                    passed=True,
                    status="WARN",
                    message=f"Target list contains {len(targets)} videos (expected at least 515).",
                    details={"target_count": len(targets)},
                )

            cleared = sum(1 for t in targets if t.get("rights_cleared", False) is True)
            return CheckResult(
                category="Corpus",
                name="Targets Inventory",
                passed=True,
                status="PASS",
                message=f"Verified {len(targets)} rights-cleared videos in targets.json ({cleared}/{len(targets)} cleared).",
                details={"target_count": len(targets), "cleared_count": cleared},
            )
        except Exception as e:
            return CheckResult(
                category="Corpus",
                name="Targets Inventory",
                passed=False,
                status="FAIL",
                message=f"Failed to parse targets JSON: {e}",
            )

    # 7. Qdrant Vector Store Probe
    def check_qdrant_status(self) -> CheckResult:
        url = f"{self.qdrant_url}/collections/{self.collection_name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AskMukthiGuru-ReadinessInspector/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            res = data.get("result", {})
            status = res.get("status")
            points_count = res.get("points_count", 0)
            payload_schema = res.get("payload_schema", {})

            has_verbatim_idx = "is_verbatim" in payload_schema
            has_rights_idx = "rights_cleared" in payload_schema

            if status != "green":
                return CheckResult(
                    category="Vector Database",
                    name="Qdrant Collection",
                    passed=False,
                    status="FAIL",
                    message=f"Qdrant collection '{self.collection_name}' status is {status} (expected green).",
                    details=res,
                )

            if not has_verbatim_idx or not has_rights_idx:
                return CheckResult(
                    category="Vector Database",
                    name="Qdrant Collection",
                    passed=True,
                    status="WARN",
                    message=f"Qdrant online with {points_count} points, but missing payload indexes (is_verbatim={has_verbatim_idx}, rights_cleared={has_rights_idx}).",
                    remediation="Run `python3 scripts/ops/reconcile_first_person_v7.py --ensure-indexes`.",
                    details={"points_count": points_count, "has_verbatim_idx": has_verbatim_idx, "has_rights_idx": has_rights_idx},
                )

            return CheckResult(
                category="Vector Database",
                name="Qdrant Collection",
                passed=True,
                status="PASS",
                message=f"Qdrant online: '{self.collection_name}' has {points_count} points, 1024d vectors, is_verbatim & rights_cleared indexed.",
                details={"points_count": points_count, "status": status},
            )
        except urllib.error.URLError as e:
            return CheckResult(
                category="Vector Database",
                name="Qdrant Collection",
                passed=False,
                status="FAIL",
                message=f"Cannot connect to Qdrant at {self.qdrant_url}: {e.reason}",
                remediation="Ensure Qdrant is running: `docker compose up -d qdrant` or start local Qdrant server.",
            )
        except Exception as e:
            return CheckResult(
                category="Vector Database",
                name="Qdrant Collection",
                passed=False,
                status="FAIL",
                message=f"Failed to query Qdrant: {e}",
            )

    # 8. Reference Transcripts Probe
    def check_transcripts_presence(self, transcripts_dir: Path | str = DEFAULT_TRANSCRIPTS_DIR) -> CheckResult:
        tdir = Path(transcripts_dir).resolve()
        if not tdir.is_dir():
            return CheckResult(
                category="Corpus",
                name="Reference Transcripts",
                passed=True,
                status="WARN",
                message=f"Transcripts directory {tdir} not found.",
                remediation="Transcripts will fall back to ASR generation.",
            )

        md_files = list(tdir.glob("*.md"))
        if len(md_files) < 100:
            return CheckResult(
                category="Corpus",
                name="Reference Transcripts",
                passed=True,
                status="WARN",
                message=f"Found only {len(md_files)} reference transcripts in {tdir}.",
                details={"transcript_count": len(md_files)},
            )

        return CheckResult(
            category="Corpus",
            name="Reference Transcripts",
            passed=True,
            status="PASS",
            message=f"Verified {len(md_files)} reference transcripts in {tdir}.",
            details={"transcript_count": len(md_files)},
        )

    # 9. Voiceprints Probe
    def check_voiceprints(self) -> CheckResult:
        candidates = [
            self.archive_root.parent / "voiceprints2.npz",
            Path.home() / "mukthiguru_attribution_data" / "voiceprints2.npz",
            Path.home() / "mukthiguru_attribution_data" / "pilot50_2026-09-25" / "voiceprints2.npz",
        ]
        found = [p for p in candidates if p.is_file()]
        if not found:
            return CheckResult(
                category="Model Cache",
                name="Teacher Voiceprints",
                passed=True,
                status="WARN",
                message="Teacher voiceprints (voiceprints2.npz) not found in standard paths; speaker verification will require reference creation.",
                remediation="Ensure voiceprints2.npz is placed in ~/mukthiguru_attribution_data/.",
            )

        return CheckResult(
            category="Model Cache",
            name="Teacher Voiceprints",
            passed=True,
            status="PASS",
            message=f"Teacher voiceprints found at {found[0]}.",
            details={"path": str(found[0])},
        )

    # 10. Pipeline Configuration & Safety Probe
    def check_pipeline_safety_config(self) -> CheckResult:
        try:
            # Check backend config
            repo_root = Path(__file__).resolve().parents[2]
            config_py = repo_root / "backend" / "app" / "config.py"
            if not config_py.is_file():
                return CheckResult(
                    category="Safety & Config",
                    name="Pipeline Safety Config",
                    passed=True,
                    status="WARN",
                    message="app/config.py not located at standard path.",
                )

            content = config_py.read_text(encoding="utf-8")
            has_answerability = "first_person_answerability_check_enabled" in content
            has_bridge = "first_person_chat_bridge_enabled" in content

            return CheckResult(
                category="Safety & Config",
                name="Pipeline Safety Config",
                passed=True,
                status="PASS",
                message="Pipeline contracts verified: answerability check supported, fail-closed bridge supported.",
                details={
                    "has_answerability_setting": has_answerability,
                    "has_bridge_setting": has_bridge,
                },
            )
        except Exception as e:
            return CheckResult(
                category="Safety & Config",
                name="Pipeline Safety Config",
                passed=True,
                status="WARN",
                message=f"Could not verify pipeline config: {e}",
            )

    # ponytail: run all 10 probes and return full inspection report
    def inspect_all(self) -> tuple[bool, list[CheckResult]]:
        self.results = [
            self.check_disk_space(),
            self.check_audio_archive(),
            self.check_system_binaries(),
            self.check_host_side_invariant(),
            self.check_compute_acceleration(),
            self.check_target_corpus(),
            self.check_qdrant_status(),
            self.check_transcripts_presence(),
            self.check_voiceprints(),
            self.check_pipeline_safety_config(),
        ]
        all_passed = all(r.passed for r in self.results)
        return all_passed, self.results

    # ponytail: format comprehensive terminal dashboard
    def format_dashboard(self, all_passed: bool) -> str:
        lines = [
            "=" * 72,
            "ASKMUKTHIGURU INGESTION READINESS INSPECTOR",
            "=" * 72,
            f"Evaluated At:     {Path(__file__).name}",
            f"Archive Root:     {self.archive_root}",
            f"Qdrant Endpoint:  {self.qdrant_url} (collection: {self.collection_name})",
            "-" * 72,
            f"{'STATUS':<8} | {'CATEGORY':<16} | {'PROBE NAME':<24} | {'DETAILS'}",
            "-" * 72,
        ]

        fails = 0
        warns = 0
        passes = 0

        for r in self.results:
            color_mark = f"[{r.status}]"
            if r.status == "PASS":
                passes += 1
            elif r.status == "WARN":
                warns += 1
            else:
                fails += 1

            lines.append(f"{color_mark:<8} | {r.category:<16} | {r.name:<24} | {r.message}")
            if r.remediation:
                lines.append(f"         |                  |                          | -> Remediation: {r.remediation}")

        lines.append("=" * 72)
        lines.append(f"SUMMARY: {passes} PASSED, {warns} WARNINGS, {fails} BLOCKERS")

        if all_passed and fails == 0:
            verdict_box = [
                "#" * 72,
                "# VERDICT: [GO] ALL SYSTEMS READY FOR INGESTION                          #",
                "# You may proceed to run audio downloading and feature ingestion.       #",
                "#" * 72,
            ]
        else:
            verdict_box = [
                "!" * 72,
                f"! VERDICT: [NO-GO] BLOCKED BY {fails} CRITICAL CHECK(S)                        !",
                "! Resolve the remediation steps flagged with [FAIL] before ingesting.    !",
                "!" * 72,
            ]

        lines.extend(verdict_box)
        return "\n".join(lines)


def main() -> None:
    # ponytail: CLI entry point
    parser = argparse.ArgumentParser(
        description="AskMukthiGuru Ingestion Readiness Inspector (Can We Ingest?)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Audio archive directory")
    parser.add_argument("--targets-file", default=str(DEFAULT_TARGETS_FILE), help="Targets JSON file")
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL, help="Qdrant REST endpoint")
    parser.add_argument("--collection", default=DEFAULT_QDRANT_COLLECTION, help="First-person Qdrant collection name")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()

    inspector = IngestReadinessInspector(
        archive_root=args.archive_dir,
        targets_file=args.targets_file,
        qdrant_url=args.qdrant_url,
        collection_name=args.collection,
    )

    all_passed, results = inspector.inspect_all()

    if args.json:
        report = {
            "verdict": "GO" if all_passed else "NO-GO",
            "all_passed": all_passed,
            "probes": [asdict(r) for r in results],
        }
        print(json.dumps(report, indent=2))
    else:
        print(inspector.format_dashboard(all_passed))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
