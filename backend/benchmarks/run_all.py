#!/usr/bin/env python3
"""
run_all.py — Unified Orchestrator for AskMukthiGuru Benchmark Suite.
Runs HTTP API ruthless benchmarks and native Ollama evaluators,
printing a final consolidated production-readiness dashboard.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path to enable package execution
sys.path.append(str(Path(__file__).parent.parent))

def check_docker():
    """Checks if the local stack is running on the expected Docker port."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect(("localhost", 8000))
        s.close()
        return True
    except Exception:
        return False

def print_banner():
    print("""
======================================================================
  🧘   MUKTHI GURU — UNIFIED BENCHMARK & READINESS SUITE   🧘  
======================================================================
""")

def run_script(script_name: str, args: list[str]) -> bool:
    script_path = Path(__file__).parent / script_name
    print(f"\n▶️ Running {script_name}...")
    t0 = time.time()
    try:
        # Run using current python interpreter
        cmd = [sys.executable, str(script_path)] + args
        subprocess.run(cmd, capture_output=False, check=True)
        elapsed = time.time() - t0
        print(f"✅ {script_name} finished successfully in {elapsed:.1f}s.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {script_name} failed with exit code {e.returncode}.")
        return False

def show_readiness_scorecard():
    report_path = Path("reports/ruthless_report.json")
    native_report_path = Path("reports/native_eval_report.json")

    print("\n" + "=" * 70)
    print("🏆   PRODUCTION-READINESS SCORECARD   🏆")
    print("=" * 70)

    score = 0.0
    verdict = "NOT CALCULATED"

    if report_path.exists():
        try:
            with open(report_path) as f:
                data = json.load(f)
            score = data.get("production_readiness_score", 0.0)
            verdict = data.get("verdict", "FAIL")
            print(f"📈  HTTP API Readiness Score : {score:.1%}")
        except Exception as e:
            print(f"⚠️  Could not parse ruthless report: {e}")
    else:
        print("⚠️  No HTTP API ruthless report found.")

    if native_report_path.exists():
        try:
            with open(native_report_path) as f:
                native_data = json.load(f)
            if native_data:
                avg_prec = sum(r.get("precision", 0) for r in native_data) / len(native_data)
                avg_faith = sum(r.get("faithfulness", 0) for r in native_data) / len(native_data)
                print(f"🎯  Native Context Precision : {avg_prec:.1%}")
                print(f"🔬  Native Faithfulness Score: {avg_faith:.1%}")
        except Exception as e:
            print(f"⚠️  Could not parse native evaluation report: {e}")
    else:
        print("⚠️  No native evaluation report found.")

    print("\n" + "─" * 70)
    if verdict == "PASS" or score >= 0.80:
        print("🎉  CONGRATULATIONS! THE SUITE IS 100% PRODUCTION READY  🎉")
    else:
        print("⚠️  PLATFORM NOT QUITE PRODUCTION READY YET. CHECK FAILING CATEGORIES.")
    print("=" * 70 + "\n")

import json


def main():
    print_banner()

    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:8000")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-key")
    args = parser.parse_args()

    # Preflight Check: Make sure backend is up
    if not check_docker() and not args.dry_run:
        print("🚨 ERROR: The FastAPI backend at http://localhost:8000 is not reachable.")
        print("   Please start your Docker containers or Supabase services first.")
        print("   Or run with --dry-run to bypass infrastructure requirements.")
        sys.exit(1)

    # Compile arguments
    ruthless_args = ["--endpoint", args.endpoint]
    if args.test_key:
        ruthless_args += ["--test-key", args.test_key]
    if args.dry_run:
        ruthless_args.append("--dry-run")

    native_args = ["--limit", "2" if args.dry_run else "10"]

    # 1. Run HTTP API Ruthless Benchmarks
    success_ruthless = run_script("ruthless_benchmark.py", ruthless_args)

    # 2. Run Native Ollama Ragas Evaluator
    success_native = run_script("native_eval.py", native_args)

    # 3. Print Final Consolidated Dashboard
    show_readiness_scorecard()

    if not success_ruthless or not success_native:
        sys.exit(1)

if __name__ == "__main__":
    main()
