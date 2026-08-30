#!/usr/bin/env python3
"""
Mukthi Guru — Capability-Based Ingestion Preflight Checker
===========================================================
Validates tool binaries, Python dependencies, and operational capabilities
before running local extraction, ASR, upload, or backup/reset stages.

Usage:
  python3 scripts/ops/preflight_check.py                 # check all profiles
  python3 scripts/ops/preflight_check.py --profile caption
  python3 scripts/ops/preflight_check.py --profile asr
  python3 scripts/ops/preflight_check.py --profile correction
  python3 scripts/ops/preflight_check.py --profile railway
  python3 scripts/ops/preflight_check.py --profile reset
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def check_python_version() -> bool:
    v = sys.version_info
    print(f"🐍 Python Interpreter: {sys.executable} (v{v.major}.{v.minor}.{v.micro})")
    if v.major != 3 or v.minor < 10:
        print("  ❌ Python 3.10+ required")
        return False
    print("  ✅ Python version supported")
    return True


def check_caption_profile() -> bool:
    print("\n🔍 Checking [Caption Profile] (Scraping, APIs, Video Tools)...")
    ok = True
    for mod in ["httpx", "youtube_transcript_api", "yt_dlp"]:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "installed")
            print(f"  ✅ {mod}: {ver}")
        except ImportError:
            print(f"  ❌ Missing Python package: {mod} (pip install {mod})")
            ok = False

    for bin_name in ["ffmpeg", "ffprobe"]:
        path = shutil.which(bin_name)
        if path:
            print(f"  ✅ Binary {bin_name}: {path}")
        else:
            print(f"  ⚠️  Binary {bin_name} not found in PATH (recommended for audio extraction)")

    node_path = shutil.which("node") or shutil.which("deno")
    if node_path:
        print(f"  ✅ JS Runtime (for yt-dlp sig challenges): {node_path}")
    else:
        print("  ⚠️  JS Runtime (node/deno) not found in PATH")

    return ok


def check_asr_profile() -> tuple[bool, str]:
    print("\n🎙️ Checking [ASR Profile] (Local Speech-to-Text)...")
    faster_whisper = False
    standard_whisper = False
    try:
        import faster_whisper
        ver = getattr(faster_whisper, "__version__", "installed")
        print(f"  ✅ faster-whisper: {ver} (CTranslate2 optimized)")
        faster_whisper = True
    except ImportError:
        print("  ℹ️  faster-whisper not installed")

    try:
        import whisper
        print("  ✅ openai-whisper: installed")
        standard_whisper = True
    except ImportError:
        print("  ℹ️  openai-whisper not installed")

    try:
        import torch
        has_cuda = torch.cuda.is_available()
        has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        dev = "CUDA" if has_cuda else ("MPS (Apple Silicon)" if has_mps else "CPU")
        print(f"  ✅ PyTorch: v{torch.__version__} (Device acceleration: {dev})")
    except ImportError:
        print("  ⚠️  PyTorch not installed")

    if faster_whisper:
        return True, "faster-whisper"
    if standard_whisper:
        return True, "openai-whisper"
    print("  ⚠️  No local ASR backend available (Tier 5 ASR will be disabled; caption tiers 1-4 active)")
    return False, "none"


def check_correction_profile() -> bool:
    print("\n📖 Checking [Correction Profile] (Doctrine Vocabulary & Reversible Ledger)...")
    ok = True
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from services.doctrine_terms import load_doctrine_terms
        terms = load_doctrine_terms()
        print(f"  ✅ doctrine_terms loaded: {len(terms)} canonical entities")
    except Exception as e:
        print(f"  ❌ doctrine_terms failed to load: {e}")
        ok = False

    try:
        import jellyfish
        print("  ✅ jellyfish: installed (derived phonetic lexicon active)")
    except ImportError:
        print("  ⚠️  jellyfish not installed (derived lexicon disabled, curated map active)")

    return ok


def check_railway_profile() -> bool:
    print("\n☁️ Checking [Railway Ingestion Profile]...")
    token = os.environ.get("MUKTHI_ADMIN_TOKEN", "").strip()
    if token:
        masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
        print(f"  ✅ MUKTHI_ADMIN_TOKEN: set ({masked})")
    else:
        print("  ⚠️  MUKTHI_ADMIN_TOKEN not set in environment (required for live Railway upload)")

    api_base = os.environ.get("RAILWAY_API_BASE", "https://askmukthiguru-8119b0e8-production.up.railway.app")
    print(f"  ℹ️  Target Railway API: {api_base}")
    return True


def check_reset_profile() -> bool:
    print("\n🛡️ Checking [Reset & Backup Profile]...")
    ok = True
    backup_dir = REPO_ROOT / "backups"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Backup directory accessible: {backup_dir}")
    except Exception as e:
        print(f"  ❌ Cannot write to backup directory {backup_dir}: {e}")
        ok = False

    neo4j_script = REPO_ROOT / "scripts" / "ops" / "backup_neo4j.py"
    qdrant_script = REPO_ROOT / "scripts" / "ops" / "backup_qdrant.py"
    reset_script = REPO_ROOT / "scripts" / "ops" / "backup_and_reset_knowledge_stores.py"

    for s, name in [(neo4j_script, "Neo4j Backup"), (qdrant_script, "Qdrant Backup"), (reset_script, "Reset Tool")]:
        if s.exists():
            print(f"  ✅ {name} script: {s.name}")
        else:
            print(f"  ❌ Missing script: {s}")
            ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--profile",
        choices=["all", "caption", "asr", "correction", "railway", "reset"],
        default="all",
        help="Capability profile to check (default: all)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("🛠️  MUKTHI GURU INGESTION PREFLIGHT CHECK")
    print(f"   Profile: {args.profile.upper()}")
    print("=" * 70)

    py_ok = check_python_version()
    if not py_ok:
        sys.exit(1)

    results = {}
    if args.profile in ["all", "caption"]:
        results["caption"] = check_caption_profile()
    if args.profile in ["all", "asr"]:
        asr_ok, _ = check_asr_profile()
        results["asr"] = asr_ok
    if args.profile in ["all", "correction"]:
        results["correction"] = check_correction_profile()
    if args.profile in ["all", "railway"]:
        results["railway"] = check_railway_profile()
    if args.profile in ["all", "reset"]:
        results["reset"] = check_reset_profile()

    print("\n" + "=" * 70)
    print("📊 PREFLIGHT SUMMARY")
    for prof, passed in results.items():
        status = "✅ READY" if passed else ("⚠️  OPTIONAL / DEGRADED" if prof in ["asr", "railway"] else "❌ FAILED")
        print(f"   - {prof.upper():<12}: {status}")
    print("=" * 70)

    # Hard failures on caption or correction
    if not results.get("caption", True) or not results.get("correction", True):
        print("\n❌ Preflight failed on required components. Fix missing dependencies before running.")
        sys.exit(1)

    print("\n✨ Preflight checks completed successfully!")


if __name__ == "__main__":
    main()
