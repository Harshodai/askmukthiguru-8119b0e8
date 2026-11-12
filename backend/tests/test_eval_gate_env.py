"""NEW-LOV-08: the eval gate passes only secrets that the eval code reads.

`LOVABLE_API_KEY` is read by Supabase edge functions (set in Supabase, not in
GitHub). `backend/evaluation/run_golden_eval.py` never reads it, so passing it
to that step only widened the blast radius of a leaked job log.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "eval-gate.yml"
EVAL_DIR = REPO_ROOT / "backend" / "evaluation"


def _eval_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in EVAL_DIR.rglob("*.py"))


def test_every_env_name_passed_to_the_golden_eval_step_is_read_by_the_eval_code():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # The eval reads its settings through a pydantic Settings class, which matches
    # env names case-insensitively (BACKEND_TOKEN -> backend_token).
    source = _eval_source().lower()
    unread = []
    for job in data["jobs"].values():
        for step in job["steps"]:
            if "run_golden_eval.py" in str(step.get("run", "")):
                for name in step.get("env", {}):
                    if name.lower() not in source:
                        unread.append(name)
    assert not unread, (
        f"env passed to the golden eval but never read by backend/evaluation: {unread}"
    )
