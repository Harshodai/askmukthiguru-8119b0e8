#!/usr/bin/env python3
"""
Apply Human Review Results from human_review_portal.html to Markdown Listen Sheets.

Usage:
    python scripts/ops/apply_human_review_results.py --input audits/evidence/human_review_results.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


def update_demoted_sheet(sheet_path: Path, results: dict) -> int:
    if not sheet_path.exists():
        print(f"Error: {sheet_path} does not exist", file=sys.stderr)
        return 0
    text = sheet_path.read_text(encoding="utf-8")
    updated_count = 0

    lines = text.splitlines()
    new_lines = []
    for line in lines:
        matched = False
        for point_id, data in results.items():
            if point_id in line:
                verdict = data.get("verdict", "")
                notes = data.get("notes", "")
                if verdict:
                    # Replace `[ PENDING ]` with the verdict
                    line = re.sub(r"`\[ PENDING \]`", f"`{verdict}`", line)
                    # If notes were provided and line ends with |, insert notes
                    if notes and line.strip().endswith("|"):
                        parts = line.split("|")
                        if len(parts) >= 11:
                            parts[-2] = f" {notes} "
                            line = "|".join(parts)
                    updated_count += 1
                    matched = True
                    break
        new_lines.append(line)

    sheet_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated_count


def update_served_sheet(sheet_path: Path, results: dict) -> int:
    if not sheet_path.exists():
        print(f"Error: {sheet_path} does not exist", file=sys.stderr)
        return 0
    text = sheet_path.read_text(encoding="utf-8")
    updated_count = 0

    lines = text.splitlines()
    new_lines = []
    for line in lines:
        matched = False
        for point_id, data in results.items():
            if point_id in line:
                voice = data.get("voice", "")
                boundary = data.get("boundary", "")
                notes = data.get("notes", "")
                if voice and boundary:
                    # Replace first `[ PENDING ]` with voice and second with boundary
                    # Example line has two `[ PENDING ]`
                    parts = line.split("`[ PENDING ]`")
                    if len(parts) == 3:
                        line = f"{parts[0]}`{voice}`{parts[1]}`{boundary}`{parts[2]}"
                    if notes and line.strip().endswith("|"):
                        p = line.split("|")
                        if len(p) >= 12:
                            p[-2] = f" {notes} "
                            line = "|".join(p)
                    updated_count += 1
                    matched = True
                    break
        new_lines.append(line)

    sheet_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=str, required=True, help="Path to exported JSON file from portal")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    demoted_results = data.get("demoted_clips", {})
    served_results = data.get("served_clips", {})

    repo_root = Path(__file__).resolve().parent.parent.parent
    demoted_sheet = repo_root / "audits" / "evidence" / "11_demoted_clips_listen_sheet.md"
    served_sheet = repo_root / "audits" / "evidence" / "50_served_clips_human_label_sheet.md"

    d_count = update_demoted_sheet(demoted_sheet, demoted_results)
    s_count = update_served_sheet(served_sheet, served_results)

    print(f"Successfully updated {d_count} demoted clip rows in {demoted_sheet.name}")
    print(f"Successfully updated {s_count} served clip rows in {served_sheet.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
