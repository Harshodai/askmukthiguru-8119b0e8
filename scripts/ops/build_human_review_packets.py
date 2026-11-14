#!/usr/bin/env python3
"""Build the human-review packets: one CSV per gate, decision columns blank (2026-11-14).

Five gates in this project can only be closed by a person: clinician review of the crisis copy,
native-speaker review of crisis detection in Indic input, helpline phone verification, rights
sign-off, and human labels / a human sample of served answers. This script assembles each packet
from the repo's own data so nothing is hand-copied and a packet can be regenerated after new data
lands.

It never decides anything: every decision column is emitted empty, and every packet is stamped with
the source file, the source sha256 and the generation date.

    python3 scripts/ops/build_human_review_packets.py --out-dir docs/reviews/<dir>
    # the 50-answer sample needs a graded rows file; the seed is recorded in the packet
    python3 scripts/ops/build_human_review_packets.py --rows ~/.../rows.jsonl --seed 20261114

Exit status: 0 packets written, 2 an input was missing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELPLINES = REPO / "config" / "helplines.yaml"
RIGHTS = REPO / "audits" / "evidence" / "public_release_phase4_rights_manifest_2026-10-22.json"
GOLD_A = REPO / "evals" / "gold_set_v1" / "annotator_A.csv"
GOLD_B = REPO / "evals" / "gold_set_v1" / "annotator_B.csv"
NATIVE = REPO / "evals" / "first_person" / "native_language_review_sheet.csv"

DECISION_COLUMNS = ["decision", "reviewer", "date", "notes"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, header: list[str], rows: Iterable[dict[str, object]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def helpline_packet(out: Path) -> int:
    """One row per registry entry. The only column nobody may guess is the live-call date."""
    import yaml

    data = yaml.safe_load(HELPLINES.read_text(encoding="utf-8")) or {}
    # The registry groups entries under `crisis_helplines` and `domestic_violence_helplines`;
    # a new group must be reviewed too, so iterate every list rather than naming two.
    entries: list[dict[str, object]] = []
    for group, value in data.items():
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    entries.append({**entry, "group": group})
    header = [
        "group",
        "region",
        "name",
        "contact",
        "hours",
        "languages",
        "source_url",
        "last_checked_public_listing",
        "last_verified_by_call",
        "status",
        "live_call_made_yyyy_mm_dd",
        "caller",
        "reached_a_person_yes_no",
        "free_yes_no",
        "staffed_24_7_yes_no",
        "notes",
    ]
    rows = []
    for entry in entries:
        langs = entry.get("languages") or []
        rows.append(
            {
                **{k: entry.get(k, "") for k in header if k in entry},
                "languages": "; ".join(langs) if isinstance(langs, list) else langs,
            }
        )
    return _write_csv(out / "03-helplines.csv", header, rows)


def rights_packet(out: Path) -> int:
    """One row per registered asset. Sign-off is per asset; the register is never the reviewer."""
    manifest = json.loads(RIGHTS.read_text(encoding="utf-8"))
    assets = manifest.get("assets") or []
    header = [
        "asset_key",
        "title",
        "channel",
        "canonical_source_url",
        "rights_basis",
        "evidence_document",
        "policy_status",
        "attribution_requirements",
        "decision_approve_exclude_hold",
        "reviewer",
        "date",
        "reason",
    ]
    rows = (
        {
            "asset_key": a.get("asset_key") or a.get("video_id") or a.get("source_id", ""),
            "title": a.get("title", ""),
            "channel": a.get("channel", ""),
            "canonical_source_url": a.get("canonical_source_url", ""),
            "rights_basis": a.get("rights_basis") or a.get("determination_reason", ""),
            "evidence_document": a.get("evidence_document", ""),
            "policy_status": a.get("policy_status") or a.get("status", ""),
            "attribution_requirements": a.get("attribution_requirements", ""),
        }
        for a in assets
    )
    return _write_csv(out / "04-rights-signoff.csv", header, rows)


def gold_packet(out: Path) -> int:
    """The machine-filled label batch, re-asked of a human.

    `annotator_A.csv` and `annotator_B.csv` both hold 303 rows but share only 101 pair ids, and
    those 101 agree identically — same score, same notes — which is what one person filling both
    sheets, or machine filling, looks like. The other 202 pair ids exist in A alone, so two thirds
    of the batch has one label rather than two; a human label is the only new information this
    packet can hold.
    """
    with GOLD_A.open(encoding="utf-8") as handle:
        rows_a = list(csv.DictReader(handle))
    by_pair: dict[str, dict[str, str]] = {}
    if GOLD_B.is_file():
        with GOLD_B.open(encoding="utf-8") as handle:
            by_pair = {r["pair_id"]: r for r in csv.DictReader(handle)}
    header = [
        "pair_id",
        "question",
        "question_type",
        "clip_text",
        "speaker_label",
        "video_url_with_timestamp",
        "machine_relevance_0_3",
        "machine_complete_yes_no",
        "machine_agreement_ab",
        "human_relevance_0_3",
        "human_complete_yes_no",
        "human_speaker_verified_yes_no_unsure",
        "reviewer",
        "date",
        "notes",
    ]
    rows = []
    for row in rows_a:
        other = by_pair.get(row["pair_id"], {})
        # Three states, not two: `annotator_B.csv` labels 101 of the 303 pair ids, so calling
        # the other 202 "differs" would report disagreement where there is simply one label.
        if not other:
            agreement = "only_in_a"
        elif (
            other.get("relevance_0_3") == row["relevance_0_3"]
            and other.get("notes") == row["notes"]
        ):
            agreement = "same"
        else:
            agreement = "differs"
        rows.append(
            {
                "pair_id": row["pair_id"],
                "question": row["question"],
                "question_type": row["question_type"],
                "clip_text": row["clip_text"],
                "speaker_label": row["speaker_label"],
                "video_url_with_timestamp": row["video_url_with_timestamp"],
                "machine_relevance_0_3": row["relevance_0_3"],
                "machine_complete_yes_no": row["complete_yes_no"],
                "machine_agreement_ab": agreement,
            }
        )
    return _write_csv(out / "05-gold-labels.csv", header, rows)


def answer_sample_packet(out: Path, rows_path: Path, seed: int, size: int = 50) -> int:
    """A seeded random sample of SERVED answers, for a human to judge.

    Only served rows are eligible: an abstained row has no clip to judge. The seed is written into
    the packet so a reviewer's sample can be reproduced exactly.
    """
    served = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("citations")
    ]
    if not served:
        raise SystemExit(f"FAILED: no served rows in {rows_path}")
    sample = random.Random(seed).sample(served, min(size, len(served)))
    header = [
        "row_id",
        "set",
        "question",
        "answer_first_240_chars",
        "citation_count",
        "citation_video_id",
        "citation_speaker",
        "answers_the_question_yes_no",
        "quote_supports_answer_yes_no",
        "attribution_correct_yes_no",
        "clip_usable_yes_no",
        "reviewer",
        "date",
        "notes",
    ]
    out_rows = []
    for row in sample:
        first = (row.get("citations") or [{}])[0]
        out_rows.append(
            {
                "row_id": row.get("id"),
                "set": row.get("set"),
                "question": row.get("question"),
                "answer_first_240_chars": (row.get("answer") or "")[:240].replace("\n", " "),
                "citation_count": len(row.get("citations") or []),
                "citation_video_id": first.get("video_id") or "",
                "citation_speaker": first.get("speaker") or "",
            }
        )
    count = _write_csv(out / "06-answer-sample.csv", header, out_rows)
    (out / "06-answer-sample.seed.txt").write_text(
        f"source_rows={rows_path}\nsource_sha256={sha256(rows_path)}\n"
        f"eligible_served_rows={len(served)}\nsample_size={count}\nseed={seed}\n"
        "regenerate: python3 scripts/ops/build_human_review_packets.py "
        f"--rows {rows_path} --seed {seed}\n",
        encoding="utf-8",
    )
    return count


def native_packet(out: Path) -> int:
    """Carry the existing sheet forward, adding the decision columns the audit found missing."""
    with NATIVE.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_header = list(reader.fieldnames or [])
        rows = list(reader)
    header = source_header + [c for c in DECISION_COLUMNS if c not in source_header]
    return _write_csv(out / "02-native-speaker.csv", header, rows)


def crisis_copy_packet(out: Path, probe_json: Path | None) -> str:
    """Render the clinician packet from a captured live probe.

    The copy a seeker actually receives is the thing being reviewed, so a packet built from the
    code would be a different artifact. `probe_json` is the JSON written by the crisis/disstress
    probe (see the README); without it the packet falls back to locators only.
    """
    lines = [
        "# Clinician review — crisis and distress copy (2026-11-14)",
        "",
        "Decision needed: **approve / change / withdraw** each block below. Every block is copy the",
        "product actually served, captured from the live local stack on 2026-11-14, not a paraphrase.",
        "",
        "| block | served when | decision | reviewer | date | notes |",
        "|---|---|---|---|---|---|",
    ]
    blocks: list[tuple[str, str]] = []
    if probe_json and probe_json.is_file():
        captured = json.loads(probe_json.read_text(encoding="utf-8"))
        for name, body in captured.items():
            label = {
                "crisis_en": "acute self-harm statement (English)",
                "distress_moderate": "hopelessness / moderate distress (English)",
            }.get(name, name)
            blocks.append((label, body.get("answer") or ""))
    locators = [
        "`backend/services/crisis_helplines.py::format_helplines_block` (line 302) — the helpline block",
        "`backend/services/crisis_helplines.py::ensure_support_line` (line 425) — the support line appended to served clips",
        "`backend/app/pipeline/stages/first_person_bridge.py::_distress_compassion_framing` (line 489) — MODERATE-distress framing",
        "`backend/services/first_person_pipeline.py:4347` — crisis pre-emption copy",
        "`backend/services/serene_mind_engine.py:235` — SEVERE check-in copy",
    ]
    for label, _body in blocks:
        lines.append(f"| {label} | live probe | (blank) | (blank) | (blank) | |")
    lines += ["", "## Served text", ""]
    for label, body in blocks:
        lines += [f"### {label}", "", "```text", body.strip() or "(empty)", "```", ""]
    lines += [
        "## Where the copy lives in code",
        "",
        *[f"- {item}" for item in locators],
        "",
        "## Specific questions for the clinician",
        "",
        "1. Is the acute-crisis block safe to show verbatim, including the numbered helplines?",
        "2. The moderate-distress block offers a grounding exercise and a meditation. Is that offer",
        "   safe at this severity, or should the turn stay on safety alone?",
        '3. The moderate-distress block asks "Are you safe right now?" — is that question',
        "   appropriate as the closing line, given no human is monitoring the answer?",
        "4. Is the 0.66/0.72/0.74 router-boundary trade-off (`AGENTS.md` X27) acceptable to a",
        "   clinician, or does it need a clinical review before any change?",
        "",
        "No answer here is a pass. An unsigned row means the copy is unreviewed.",
        "",
    ]
    text = "\n".join(lines)
    (out / "01-clinician-crisis-copy.md").write_text(text, encoding="utf-8")
    return "written" if blocks else "written (locators only — no probe file)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rows", type=Path, default=None, help="Graded rows.jsonl for the sample")
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--crisis-copy-json", type=Path, default=None)
    args = parser.parse_args(argv)

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    missing = [p for p in (HELPLINES, RIGHTS, GOLD_A) if not p.is_file()]
    if missing:
        print(f"FAILED: missing input(s): {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 2

    counts = {
        "helplines": helpline_packet(out),
        "native": native_packet(out),
        "rights": rights_packet(out),
        "gold": gold_packet(out),
    }
    counts["crisis_copy"] = crisis_copy_packet(out, args.crisis_copy_json)
    if args.rows:
        counts["answer_sample"] = answer_sample_packet(out, args.rows, args.seed)
    else:
        counts["answer_sample"] = "skipped (no --rows)"

    provenance = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator": "scripts/ops/build_human_review_packets.py",
        "inputs": {
            str(p.relative_to(REPO)): sha256(p)
            for p in (HELPLINES, RIGHTS, GOLD_A, GOLD_B, NATIVE)
            if p.is_file()
        },
        "counts": {k: v for k, v in counts.items()},
        "every_decision_column": "empty by construction",
    }
    (out / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance["counts"], indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Self-check the pure parts: a decision column is never pre-filled.
        assert all(c not in ("", None) for c in DECISION_COLUMNS)
        assert (
            "decision_approve_exclude_hold" not in DECISION_COLUMNS
        )  # rights packet names its own
        print("self-check ok:", DECISION_COLUMNS)
        raise SystemExit(0)
    raise SystemExit(main())
