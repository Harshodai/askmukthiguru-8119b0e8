#!/usr/bin/env python3
"""Final verification transcript with true exit codes (2026-10-21).

Every command is run, its exit code captured, and the transcript written to
one file. No pipeline swallows a failure: the exit code is read from the
process itself, not from a pipe.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKER = "/Users/harshodaikolluru/.docker/bin/docker"

COMMANDS: list[tuple[str, list[str], Path]] = [
    (
        "backend full suite (host venv, python 3.12)",
        [".venv/bin/python", "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider",
         "--no-header", "-rf", "--tb=line"],
        REPO / "backend",
    ),
    (
        "fp-context focused suite (runtime image)",
        [DOCKER, "exec", "mukthiguru-backend", "sh", "-lc",
         "cd /app && python -m pytest tests/test_first_person_context_contract.py "
         "tests/test_first_person_context_store.py tests/test_first_person_context_harness.py "
         "tests/test_first_person_context_red_team.py tests/test_first_person_context_serving.py "
         "tests/test_first_person_context_shadow_route.py tests/test_fp_context_builder_from_v9.py "
         "tests/test_validate_fp_context_candidate.py tests/test_model_routing_and_caching.py "
         "tests/test_repo_layout.py tests/test_guardrail_violence_intent_2026_10_21.py "
         "-q -p no:cacheprovider --no-header --tb=line"],
        REPO,
    ),
    (
        "guardrail / distress / crisis / safety sweep (host venv)",
        [".venv/bin/python", "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider",
         "--no-header", "--tb=line", "-k",
         "guardrail or distress or crisis or safety or ideation or wp2 or compound"],
        REPO / "backend",
    ),
    (
        "repo layout parity (host venv)",
        [".venv/bin/python", "-m", "pytest", "tests/test_repo_layout.py", "-q",
         "-p", "no:cacheprovider", "--no-header", "--tb=line"],
        REPO / "backend",
    ),
    (
        "compile check (changed backend modules)",
        [".venv/bin/python", "-m", "py_compile",
         "services/first_person_pipeline.py", "services/first_person_context_store.py",
         "services/first_person_context_harness.py", "services/first_person_context_selector.py",
         "domain/first_person_context.py", "guardrails/lightweight_handler.py",
         "app/config.py", "app/pipeline/stages/first_person_bridge.py",
         "scripts/ops/audit_first_person_v10_strict.py",
         "scripts/ops/capture_first_person_state.py"],
        REPO / "backend",
    ),
    (
        "ruff check (changed backend modules, from backend/)",
        [".venv/bin/python", "-m", "ruff", "check", "services/first_person_pipeline.py",
         "services/first_person_context_store.py", "guardrails/lightweight_handler.py",
         "tests/test_first_person_context_serving.py",
         "tests/test_guardrail_violence_intent_2026_10_21.py",
         "scripts/ops/audit_first_person_v10_strict.py",
         "scripts/ops/capture_first_person_state.py"],
        REPO / "backend",
    ),
    (
        "ruff check (repo-root ops scripts, from repo root)",
        ["backend/.venv/bin/python", "-m", "ruff", "check",
         "scripts/ops/first_person_live_matrix.py",
         "scripts/ops/first_person_final_verification.py",
         "scripts/ops/build_fp_context_from_v9.py",
         "scripts/ops/validate_fp_context_candidate.py",
         "scripts/ops/gate1_load_test.py"],
        REPO,
    ),
    (
        "git diff --check (whitespace/conflict markers)",
        ["git", "diff", "--check"],
        REPO,
    ),
    (
        "git status (worktree state)",
        ["git", "status", "--short", "--branch"],
        REPO,
    ),
]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "audits/evidence/final_verification.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    failed: list[str] = []
    for label, cmd, cwd in COMMANDS:
        printable = " ".join(cmd)
        print(f"=== {label} ===", flush=True)
        print(f"$ {printable}", flush=True)
        try:
            proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=3600)
            code = proc.returncode
            tail = (proc.stdout or "").strip().splitlines()[-25:]
            err = (proc.stderr or "").strip().splitlines()[-10:]
        except Exception as exc:  # noqa: BLE001
            code = 255
            tail = [f"<exception: {exc}>"]
            err = []
        for line in tail:
            print(line, flush=True)
        for line in err:
            print(f"stderr| {line}", flush=True)
        print(f"EXIT={code}", flush=True)
        print("", flush=True)
        lines.append(f"=== {label} ===\n$ {printable}\n" + "\n".join(tail + err) + f"\nEXIT={code}\n")
        if code != 0:
            failed.append(f"{label} (exit {code})")
    header = "First-person v5/v10 final verification — 2026-10-21\n"
    summary = header + ("ALL COMMANDS EXITED 0\n" if not failed else "FAILING COMMANDS:\n- " + "\n- ".join(failed) + "\n")
    out.write_text(summary + "\n" + "\n".join(lines), encoding="utf-8")
    print(summary)
    print(f"wrote {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
