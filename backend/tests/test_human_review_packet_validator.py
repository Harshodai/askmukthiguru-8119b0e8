"""Read-only human-gate provenance and unsigned-field contracts."""

from __future__ import annotations

import csv
import json

from scripts.ops.validate_human_review_packets import validate_packets


def _write_blank_fixture(packet_dir) -> None:
    (packet_dir / "PROVENANCE.json").write_text(json.dumps({"inputs": {}}), encoding="utf-8")
    (packet_dir / "01-clinician-crisis-copy.md").write_text(
        "| block | served when | decision | reviewer | date | notes |\n"
        "|---|---|---|---|---|---|\n"
        "| crisis | probe | (blank) | (blank) | (blank) | |\n",
        encoding="utf-8",
    )
    with (packet_dir / "02-native-speaker.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["decision", "reviewer", "date"])
        writer.writeheader()
        writer.writerow({"decision": "", "reviewer": "", "date": ""})
    for filename, fields in {
        "03-helplines.csv": [
            "live_call_made_yyyy_mm_dd",
            "caller",
            "reached_a_person_yes_no",
            "free_yes_no",
            "staffed_24_7_yes_no",
            "notes",
        ],
        "04-rights-signoff.csv": ["decision_approve_exclude_hold", "reviewer", "date", "reason"],
        "05-gold-labels.csv": [
            "human_relevance_0_3",
            "human_complete_yes_no",
            "human_speaker_verified_yes_no_unsure",
            "reviewer",
            "date",
            "notes",
        ],
        "06-answer-sample.csv": [
            "answers_the_question_yes_no",
            "quote_supports_answer_yes_no",
            "attribution_correct_yes_no",
            "clip_usable_yes_no",
            "reviewer",
            "date",
            "notes",
        ],
    }.items():
        with (packet_dir / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({field: "" for field in fields})


def test_validator_accepts_blank_packet_and_rejects_filled_decision(tmp_path) -> None:
    _write_blank_fixture(tmp_path)

    blank = validate_packets(tmp_path)
    assert blank["source_hashes_match"] is True
    assert blank["unsigned"] is True
    assert blank["errors"] == []

    packet = tmp_path / "02-native-speaker.csv"
    packet.write_text("decision,reviewer,date\napprove,Owner,2026-11-25\n", encoding="utf-8")
    filled = validate_packets(tmp_path)
    assert filled["unsigned"] is False
    assert any("filled decision fields" in error for error in filled["errors"])
