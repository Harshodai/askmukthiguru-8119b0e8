"""Synthetic-data tests for score_gold.py and fit_threshold.py.

    backend/.venv/bin/python3 -m pytest evals/gold_set_v1/test_gold_tools.py -q
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_threshold  # noqa: E402
import score_gold  # noqa: E402

COLS = ["pair_id", "relevance_0_3", "complete_yes_no", "speaker_is_teacher_yes_no_unsure", "risk_yes_no", "notes"]


def sheet(path: Path, rows: list[tuple]) -> Path:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows([(*r, "") for r in rows])
    return path


def test_weighted_kappa_perfect_and_ordinal():
    assert score_gold.weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0
    near = score_gold.weighted_kappa([0, 1, 2, 3, 3, 0], [0, 1, 2, 2, 3, 0])
    far = score_gold.weighted_kappa([0, 1, 2, 3, 3, 0], [0, 1, 2, 0, 3, 0])
    assert near > far  # an off-by-one costs less than an off-by-three


def test_score_gold_agreement_disagreements_and_export(tmp_path, capsys):
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 1, "no", "yes", "no"),
                                   ("p3", 2, "yes", "unsure", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 2, "no", "yes", "no"),
                                   ("p4", 0, "yes", "no", "yes")])
    out, dis = tmp_path / "labels.jsonl", tmp_path / "dis.csv"
    assert score_gold.main([str(a), str(b), "--out", str(out), "--disagreements", str(dis)]) == 0
    report = capsys.readouterr().out
    assert '"overlap_pairs": 2' in report and "pending adjudication: 1" in report
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert set(labels) == {"p1", "p3", "p4"}  # p2 disagrees and is unadjudicated -> not exported
    assert labels["p1"] == {"id": "p1", "relevance": 3, "complete": True, "risk": False,
                            "speaker_is_teacher": "yes", "n_annotators": 2, "source": "human"}
    assert labels["p4"]["risk"] is True and labels["p4"]["n_annotators"] == 1

    rows = list(csv.DictReader(dis.open()))
    assert [r["pair_id"] for r in rows] == ["p2"]
    rows[0].update({f"adj_{d}": rows[0][f"a_{d}"] for d in score_gold.DIMS} | {"adj_relevance_0_3": "2"})
    with dis.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert score_gold.main([str(a), str(b), "--adjudicated", str(dis), "--out", str(out),
                            "--disagreements", str(tmp_path / "dis2.csv")]) == 0
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert labels["p2"]["relevance"] == 2


def test_score_gold_reads_excel_bom(tmp_path):
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no")])
    a.write_bytes(b"\xef\xbb\xbf" + a.read_bytes())  # Excel "CSV UTF-8" export
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no")])
    assert score_gold.main([str(a), str(b), "--out", str(tmp_path / "o.jsonl"),
                            "--disagreements", str(tmp_path / "d.csv")]) == 0


def test_score_gold_rejects_blank_cells(tmp_path):
    a = sheet(tmp_path / "a.csv", [("p1", "", "yes", "yes", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no")])
    assert score_gold.main([str(a), str(b), "--out", str(tmp_path / "o.jsonl"),
                            "--disagreements", str(tmp_path / "d.csv")]) == 1
    with (tmp_path / "a.csv").open("w", newline="") as fh:  # SKIPPED with blank cells is allowed
        csv.writer(fh).writerows([COLS, ["p1", "", "", "", "", "SKIPPED distressing"]])
    assert score_gold.main([str(a), str(b), "--out", str(tmp_path / "o.jsonl"),
                            "--disagreements", str(tmp_path / "d.csv")]) == 0
    assert json.loads((tmp_path / "o.jsonl").read_text())["n_annotators"] == 1


def write_fit_inputs(tmp_path: Path, n_q: int, n_bad_low: int) -> tuple[Path, Path]:
    """n_q questions x 2 ranks. Rank-0: top (n_q - n_bad_low) by score are correct, the lowest are wrong."""
    labels, scores = [], []
    for i in range(n_q):
        for rank in (0, 1):
            pid = f"q{i}_r{rank}"
            good = rank == 0 and i >= n_bad_low
            labels.append({"id": pid, "relevance": 3 if good else 1, "complete": True, "risk": False,
                           "speaker_is_teacher": "yes", "n_annotators": 2, "source": "human"})
            scores.append({"pair_id": pid, "cand_rank": rank, "dense_cosine": i / n_q + (0 if rank == 0 else -1)})
    lp, sp = tmp_path / "l.jsonl", tmp_path / "s.csv"
    lp.write_text("".join(json.dumps(x) + "\n" for x in labels))
    with sp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pair_id", "cand_rank", "dense_cosine"])
        w.writeheader()
        w.writerows(scores)
    return lp, sp


def test_fit_threshold_insufficient(tmp_path, capsys):
    lp, sp = write_fit_inputs(tmp_path, n_q=200, n_bad_low=0)
    assert fit_threshold.main(["--labels", str(lp), "--scores", str(sp), "--unit", "top1"]) == 2
    assert "insufficient labels" in capsys.readouterr().out


def test_fit_threshold_finds_point_and_excludes_errors(tmp_path, capsys):
    lp, sp = write_fit_inputs(tmp_path, n_q=500, n_bad_low=100)
    prof = tmp_path / "p.json"
    assert fit_threshold.main(["--labels", str(lp), "--scores", str(sp), "--unit", "top1",
                               "--profile-out", str(prof)]) == 0
    p = json.loads(prof.read_text())
    assert p["n_selected"] == 400 and p["precision"] == 1.0 and p["ucb_risk"] <= 0.01
    assert p["threshold"] == pytest.approx(100 / 500) and p["unit"] == "top1"


def test_fit_threshold_unsure_speaker_is_wrong_and_ai_labels_refused(tmp_path):
    assert fit_threshold.is_correct({"relevance": 3, "complete": True, "risk": False,
                                     "speaker_is_teacher": "unsure"}) == 0
    lp = tmp_path / "ai.jsonl"
    lp.write_text(json.dumps({"id": "x", "relevance": 3, "complete": True, "risk": False}) + "\n")
    with pytest.raises(ValueError, match="not a human label"):
        fit_threshold.main(["--labels", str(lp), "--scores", str(tmp_path / "s.csv"), "--unit", "pair"])


def test_min_items_matches_299():
    assert fit_threshold.min_items(0.01, 0.05) == 299
