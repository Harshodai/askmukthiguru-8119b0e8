#!/usr/bin/env python3
"""Generate a comprehensive Markdown report of answers and attribution from a graded run."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2] if Path(__file__).resolve().parents[1].name == "scripts" else Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

def generate_report(run_dir: Path, out_path: Path) -> None:
    rows_path = run_dir / "rows.jsonl"
    grades_path = run_dir / "grades.json"

    if not rows_path.exists():
        raise FileNotFoundError(f"Missing {rows_path}")

    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    grades = json.loads(grades_path.read_text(encoding="utf-8")) if grades_path.exists() else {}
    final_grades = grades.get("final", {})

    lines: list[str] = [
        "# Graded Run Answers & Attribution Evidence (2026-11-07)",
        "",
        f"**Run ID:** `{run_dir.name}`  ",
        f"**Total Questions Evaluated:** {len(rows)} (116 frozen tuning + 86 unanswerable)  ",
        "**Evaluation Stack:** Clean Docker image, zero code bind-mounts, pinned environment  ",
        "",
        "---",
        "",
        "## 1. Served First-Person Answers (Verbatim Teacher Clips)",
        "",
    ]

    served_rows = [r for r in rows if r.get("citations")]
    lines.append(f"Total clips served: **{len(served_rows)}**  ")
    lines.append("")

    for r in served_rows:
        qid = r["id"]
        g = final_grades.get(qid, {})
        lines.append(f"### `{qid}`: {r.get('question')}")
        lines.append(f"- **Route:** `{r.get('route')}`")
        lines.append(f"- **Latency:** {r.get('latency_ms')} ms ({r.get('sec')}s wall)")
        lines.append(f"- **Judge Verdict (Haiku 5.5):** `{g.get('verdict', 'unrated')}` (Harmful: `{g.get('harmful', False)}`)")
        if g.get("reasons"):
            lines.append("- **Judge Reasons:**")
            for reason in g["reasons"]:
                lines.append(f"  * {reason}")
        lines.append("")
        lines.append("**Answer Shown to Seeker:**")
        ans_quoted = "> " + (r.get("answer") or "").replace("\n", "\n> ")
        lines.append(ans_quoted)
        lines.append("")
        lines.append("**Citations & Attribution:**")
        for c in r.get("citations", []):
            lines.append(f"- **Speaker:** `{c.get('speaker')}` (Verified: `{c.get('speaker_verified')}`)")
            lines.append(f"- **Video URL:** [{c.get('url')}]({c.get('url')}) at {c.get('t')}s")
            snippet = c.get("text", "")[:300].replace("\n", " ")
            lines.append(f"- **Verbatim Snippet:** \"{snippet}...\"")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## 2. Frozen Tuning Set (116 Questions Summary)")
    lines.append("")
    lines.append("| ID | Question | Route | Citations | Latency (ms) | Answer Snippet |")
    lines.append("| :--- | :--- | :--- | :---: | :---: | :--- |")
    for r in rows:
        if r.get("set") == "frozen116":
            ans_preview = (r.get("answer") or "")[:70].replace("|", "-").replace("\n", " ")
            lines.append(f"| `{r['id']}` | {r['question'][:45]}... | `{r.get('route')}` | {len(r.get('citations', []))} | {r.get('latency_ms')} | {ans_preview}... |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Unanswerable & Safety Set (86 Questions Summary)")
    lines.append("")
    lines.append("| ID | Group | Expected | Route | Citations | Status |")
    lines.append("| :--- | :--- | :--- | :--- | :---: | :---: |")
    for r in rows:
        if r.get("set") == "unanswerable86":
            no_clip = len(r.get("citations", [])) == 0
            exp = r.get("expected")
            passed = no_clip
            status_str = "PASS" if passed else "FAIL"
            lines.append(f"| `{r['id']}` | `{r.get('scoring_group')}` | `{exp}` | `{r.get('route')}` | {len(r.get('citations', []))} | **{status_str}** |")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {out_path} ({out_path.stat().st_size} bytes)")

if __name__ == "__main__":
    run_dir = Path.home() / "mukthiguru_attribution_data" / "graded_runs" / "20261107-graded-clean-v2"
    out_file = REPO_ROOT / "audits" / "evidence" / "GRADED_RUN_ANSWERS_2026-11-07.md"
    generate_report(run_dir, out_file)
