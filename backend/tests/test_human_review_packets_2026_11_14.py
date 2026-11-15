"""Pins for `scripts/ops/build_human_review_packets.py` (2026-11-14).

Five human gates had no packet, so nobody could close one without hand-assembling the rows. The
generator assembles them from repo data; these pins hold the properties that make a packet usable
as a record:

* every decision column exists and is empty (an unsigned row is unreviewed, never approved);
* the samples are reproducible (same seed + same source ⇒ same rows) and the seed is recorded;
* the helpline packet covers every registry group, not a hardcoded two;
* the rights packet is one row per registered asset.

No network and no LLM: the generator reads files only.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "build_human_review_packets.py"
GRADED_ROWS = (
    Path.home() / "mukthiguru_attribution_data" / "graded_runs" / "20261114-graded-7" / "rows.jsonl"
)


def _load():
    spec = importlib.util.spec_from_file_location("build_human_review_packets", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hpp = _load()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_helplines_cover_every_registry_group_and_leave_the_call_date_blank(tmp_path) -> None:
    assert hpp.helpline_packet(tmp_path) >= 14
    rows = _rows(tmp_path / "03-helplines.csv")
    assert {r["group"] for r in rows} == {"crisis_helplines", "domestic_violence_helplines"}
    assert all(not r["live_call_made_yyyy_mm_dd"] for r in rows)
    assert all(not r["caller"] for r in rows)


def test_rights_packet_is_one_row_per_registered_asset(tmp_path) -> None:
    manifest = json.loads(hpp.RIGHTS.read_text(encoding="utf-8"))
    assert hpp.rights_packet(tmp_path) == len(manifest["assets"])
    rows = _rows(tmp_path / "04-rights-signoff.csv")
    assert all(not r["decision_approve_exclude_hold"] for r in rows)


def test_gold_packet_keeps_the_machine_labels_and_asks_for_human_ones(tmp_path) -> None:
    assert hpp.gold_packet(tmp_path) == 303
    rows = _rows(tmp_path / "05-gold-labels.csv")
    assert all(r["machine_relevance_0_3"] for r in rows)
    assert all(not r["human_relevance_0_3"] for r in rows)
    # Three states, not two: `annotator_B.csv` covers 101 of the 303 pair ids, so the other
    # 202 are `only_in_a`, never `differs`.
    states = {r["machine_agreement_ab"] for r in rows}
    assert states == {"same", "only_in_a"}, states
    assert sum(1 for r in rows if r["machine_agreement_ab"] == "same") == 101
    assert sum(1 for r in rows if r["machine_agreement_ab"] == "only_in_a") == 202


def test_answer_sample_is_seeded_and_reproducible(tmp_path) -> None:
    if not GRADED_ROWS.is_file():
        import pytest

        pytest.skip("graded rows file not present on this machine")
    hpp.answer_sample_packet(tmp_path, GRADED_ROWS, seed=20261114)
    first = (tmp_path / "06-answer-sample.csv").read_text(encoding="utf-8")
    hpp.answer_sample_packet(tmp_path, GRADED_ROWS, seed=20261114)
    assert (tmp_path / "06-answer-sample.csv").read_text(encoding="utf-8") == first
    assert "seed=20261114" in (tmp_path / "06-answer-sample.seed.txt").read_text(encoding="utf-8")
    assert all(
        not r["answers_the_question_yes_no"] for r in _rows(tmp_path / "06-answer-sample.csv")
    )


def test_answer_sample_only_draws_served_rows(tmp_path) -> None:
    if not GRADED_ROWS.is_file():
        import pytest

        pytest.skip("graded rows file not present on this machine")
    hpp.answer_sample_packet(tmp_path, GRADED_ROWS, seed=1)
    rows = _rows(tmp_path / "06-answer-sample.csv")
    assert rows and all(int(r["citation_count"]) >= 1 for r in rows)


def test_crisis_packet_quotes_the_served_text_not_a_paraphrase(tmp_path) -> None:
    probe = tmp_path / "probe.json"
    probe.write_text(
        json.dumps({"crisis_en": {"answer": "SERVED CRISIS COPY MARKER"}}), encoding="utf-8"
    )
    assert "written" in hpp.crisis_copy_packet(tmp_path, probe)
    text = (tmp_path / "01-clinician-crisis-copy.md").read_text(encoding="utf-8")
    assert "SERVED CRISIS COPY MARKER" in text
    assert "format_helplines_block" in text  # locators stay so the reviewer can find the source
    assert "(blank)" in text  # the decision column is visibly empty


def test_crisis_packet_without_a_probe_says_so(tmp_path) -> None:
    assert "no probe" in hpp.crisis_copy_packet(tmp_path, None)
