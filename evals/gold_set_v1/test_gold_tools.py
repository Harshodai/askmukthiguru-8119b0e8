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
import make_task_files  # noqa: E402
import score_gold  # noqa: E402
import three_rater  # noqa: E402

COLS = [
    "pair_id",
    "relevance_0_3",
    "complete_yes_no",
    "speaker_is_teacher_yes_no_unsure",
    "risk_yes_no",
    "notes",
]


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
    a = sheet(
        tmp_path / "a.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 1, "no", "yes", "no"),
            ("p3", 2, "yes", "unsure", "no"),
        ],
    )
    b = sheet(
        tmp_path / "b.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 2, "no", "yes", "no"),
            ("p4", 0, "yes", "no", "yes"),
        ],
    )
    out, dis = tmp_path / "labels.jsonl", tmp_path / "dis.csv"
    assert score_gold.main([str(a), str(b), "--out", str(out), "--disagreements", str(dis)]) == 0
    report = capsys.readouterr().out
    assert '"overlap_pairs": 2' in report and "pending adjudication: 1" in report
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert set(labels) == {"p1", "p3", "p4"}  # p2 disagrees and is unadjudicated -> not exported
    assert labels["p1"] == {
        "id": "p1",
        "relevance": 3,
        "complete": True,
        "risk": False,
        "speaker_is_teacher": "yes",
        "n_annotators": 2,
        "source": "human",
    }
    assert labels["p4"]["risk"] is True and labels["p4"]["n_annotators"] == 1

    rows = list(csv.DictReader(dis.open()))
    assert [r["pair_id"] for r in rows] == ["p2"]
    rows[0].update(
        {f"adj_{d}": rows[0][f"a_{d}"] for d in score_gold.DIMS} | {"adj_relevance_0_3": "2"}
    )
    with dis.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                "--adjudicated",
                str(dis),
                "--out",
                str(out),
                "--disagreements",
                str(tmp_path / "dis2.csv"),
            ]
        )
        == 0
    )
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert labels["p2"]["relevance"] == 2


def test_score_gold_reads_excel_bom(tmp_path):
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no")])
    a.write_bytes(b"\xef\xbb\xbf" + a.read_bytes())  # Excel "CSV UTF-8" export
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no")])
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                "--out",
                str(tmp_path / "o.jsonl"),
                "--disagreements",
                str(tmp_path / "d.csv"),
            ]
        )
        == 0
    )


def test_score_gold_rejects_blank_cells(tmp_path):
    a = sheet(tmp_path / "a.csv", [("p1", "", "yes", "yes", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no")])
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                "--out",
                str(tmp_path / "o.jsonl"),
                "--disagreements",
                str(tmp_path / "d.csv"),
            ]
        )
        == 1
    )
    with (tmp_path / "a.csv").open("w", newline="") as fh:  # SKIPPED with blank cells is allowed
        csv.writer(fh).writerows([COLS, ["p1", "", "", "", "", "SKIPPED distressing"]])
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                "--out",
                str(tmp_path / "o.jsonl"),
                "--disagreements",
                str(tmp_path / "d.csv"),
            ]
        )
        == 0
    )
    assert json.loads((tmp_path / "o.jsonl").read_text())["n_annotators"] == 1


def write_fit_inputs(tmp_path: Path, n_q: int, n_bad_low: int) -> tuple[Path, Path]:
    """n_q questions x 2 ranks. Rank-0: top (n_q - n_bad_low) by score are correct, the lowest are wrong."""
    labels, scores = [], []
    for i in range(n_q):
        for rank in (0, 1):
            pid = f"q{i}_r{rank}"
            good = rank == 0 and i >= n_bad_low
            labels.append(
                {
                    "id": pid,
                    "relevance": 3 if good else 1,
                    "complete": True,
                    "risk": False,
                    "speaker_is_teacher": "yes",
                    "n_annotators": 2,
                    "source": "human",
                }
            )
            scores.append(
                {
                    "pair_id": pid,
                    "cand_rank": rank,
                    "dense_cosine": i / n_q + (0 if rank == 0 else -1),
                }
            )
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
    assert (
        fit_threshold.main(
            ["--labels", str(lp), "--scores", str(sp), "--unit", "top1", "--profile-out", str(prof)]
        )
        == 0
    )
    p = json.loads(prof.read_text())
    assert p["n_selected"] == 400 and p["precision"] == 1.0 and p["ucb_risk"] <= 0.01
    assert p["threshold"] == pytest.approx(100 / 500) and p["unit"] == "top1"


def test_fit_threshold_unsure_speaker_is_wrong_and_ai_labels_refused(tmp_path):
    assert (
        fit_threshold.is_correct(
            {"relevance": 3, "complete": True, "risk": False, "speaker_is_teacher": "unsure"}
        )
        == 0
    )
    lp = tmp_path / "ai.jsonl"
    lp.write_text(json.dumps({"id": "x", "relevance": 3, "complete": True, "risk": False}) + "\n")
    with pytest.raises(ValueError, match="not a human label"):
        fit_threshold.main(
            ["--labels", str(lp), "--scores", str(tmp_path / "s.csv"), "--unit", "pair"]
        )


def test_min_items_matches_299():
    assert fit_threshold.min_items(0.01, 0.05) == 299


def test_majority_vote():
    from evaluation.gold.agreement import majority_vote

    assert majority_vote(["3", "3", "1"]) == "3"  # 2/3 resolves
    assert majority_vote(["yes", "yes", "yes"]) == "yes"  # unanimous
    assert majority_vote(["yes", "no", "yes"]) == "yes"
    assert majority_vote(["yes", "no", "unsure"]) is None  # three-way split
    assert majority_vote(["0", "1", "2"]) is None  # no value holds 2/3
    with pytest.raises(ValueError):
        majority_vote([])


def test_three_rater_pairwise_numbers(tmp_path):
    """Hand-computed fixture: complete_yes_no over 5 triple-overlap pairs.

    a: Y Y Y Y N | b: Y Y Y N N | c: Y Y N N N.
    a_b: agree p1,p2,p3,p5, raw 4/5=0.8; pe=(4/5)(3/5)+(1/5)(2/5)=14/25
      -> k=(0.8-0.56)/0.44=6/11~=0.5455.
    a_c: agree p1,p2,p5, raw 3/5=0.6; pe=(4/5)(2/5)+(1/5)(3/5)=11/25
      -> k=(0.6-0.44)/0.56=2/7~=0.2857.
    b_c: agree p1,p2,p4,p5, raw 4/5=0.8; pe=(3/5)(2/5)+(2/5)(3/5)=12/25
      -> k=(0.8-0.48)/0.52=8/13~=0.6154.
    """
    y, n = "yes", "no"
    a = sheet(
        tmp_path / "a.csv",
        [
            ("p1", 2, y, y, n),
            ("p2", 2, y, y, n),
            ("p3", 2, y, y, n),
            ("p4", 2, y, y, n),
            ("p5", 2, n, y, n),
        ],
    )
    b = sheet(
        tmp_path / "b.csv",
        [
            ("p1", 2, y, y, n),
            ("p2", 2, y, y, n),
            ("p3", 2, y, y, n),
            ("p4", 2, n, y, n),
            ("p5", 2, n, y, n),
        ],
    )
    c = sheet(
        tmp_path / "c.csv",
        [
            ("p1", 2, y, y, n),
            ("p2", 2, y, y, n),
            ("p3", 2, n, y, n),
            ("p4", 2, n, y, n),
            ("p5", 2, n, y, n),
        ],
    )
    ra, ea = score_gold.read_sheet(a)
    rb, eb = score_gold.read_sheet(b)
    rc, ec = score_gold.read_sheet(c)
    assert not (ea or eb or ec)
    rep = score_gold.agreement_report_3(ra, rb, rc, sorted(set(ra) & set(rb) & set(rc)))
    comp = rep["complete_yes_no"]["pairs"]
    assert comp["a_b"]["raw_agreement"] == 0.8 and comp["a_b"]["kappa"] == 0.5455
    assert comp["a_c"]["raw_agreement"] == 0.6 and comp["a_c"]["kappa"] == 0.2857
    assert comp["b_c"]["raw_agreement"] == 0.8 and comp["b_c"]["kappa"] == 0.6154
    assert all(v["kappa_kind"] == "cohen" for v in comp.values())
    rel = rep["relevance_0_3"]["pairs"]  # unanimous 2s: quadratic path, perfect
    assert all(v["raw_agreement"] == 1.0 and v["kappa"] == 1.0 for v in rel.values())
    assert all(v["kappa_kind"] == "quadratic" for v in rel.values())


def test_three_rater_majority_resolution_and_splits(tmp_path, capsys):
    a = sheet(
        tmp_path / "a.csv",
        [
            ("p1", 3, "yes", "yes", "no"),  # unanimous
            ("p2", 3, "yes", "yes", "no"),  # relevance majority 3
            ("p3", 2, "yes", "yes", "no"),  # speaker split
            ("p4", 0, "yes", "yes", "no"),  # relevance split
            ("p5", 3, "yes", "yes", "no"),  # single coverage
            ("p6", 1, "no", "yes", "yes"),  # a+b agree
            ("p7", 2, "yes", "yes", "no"),
        ],
    )  # a+b disagree
    b = sheet(
        tmp_path / "b.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 3, "yes", "yes", "no"),
            ("p3", 2, "yes", "no", "no"),
            ("p4", 1, "yes", "yes", "no"),
            ("p6", 1, "no", "yes", "yes"),
            ("p7", 1, "yes", "yes", "no"),
        ],
    )
    c = sheet(
        tmp_path / "c.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 1, "yes", "yes", "no"),
            ("p3", 2, "yes", "unsure", "no"),
            ("p4", 2, "yes", "yes", "no"),
        ],
    )
    out, dis = tmp_path / "labels.jsonl", tmp_path / "dis.csv"
    assert (
        score_gold.main([str(a), str(b), str(c), "--out", str(out), "--disagreements", str(dis)])
        == 0
    )
    report = capsys.readouterr().out
    assert '"overlap_pairs": 4' in report and '"n_raters": 3' in report
    assert "pending adjudication: 3" in report
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert set(labels) == {"p1", "p2", "p5", "p6"}  # p3/p4 splits + p7 pair-dispute pending
    assert labels["p1"]["n_annotators"] == 3
    assert labels["p2"] == {
        "id": "p2",
        "relevance": 3,
        "complete": True,
        "risk": False,
        "speaker_is_teacher": "yes",
        "n_annotators": 3,
        "source": "human",
    }
    assert labels["p5"]["n_annotators"] == 1 and labels["p6"]["n_annotators"] == 2
    for v in labels.values():
        assert set(v) == {
            "id",
            "relevance",
            "complete",
            "risk",
            "speaker_is_teacher",
            "n_annotators",
            "source",
        }

    rows = list(csv.DictReader(dis.open()))
    assert [r["pair_id"] for r in rows] == ["p3", "p4", "p7"]
    expected_cols = ["pair_id"] + [
        f"{s}_{d}" for d in score_gold.DIMS for s in ("a", "b", "c", "adj")
    ]
    assert list(rows[0]) == expected_cols  # c_* added, existing names/order kept
    by_id = {r["pair_id"]: r for r in rows}
    assert by_id["p7"]["c_relevance_0_3"] == ""  # partial overlap: blank third side
    assert by_id["p3"]["c_speaker_is_teacher_yes_no_unsure"] == "unsure"

    # Invalid adjudication stays pending; valid ones resolve (triplets n=3, pair n=2).
    rows[0]["adj_speaker_is_teacher_yes_no_unsure"] = "maybe"
    rows[1]["adj_relevance_0_3"] = "1"
    rows[2]["adj_relevance_0_3"] = "2"
    with dis.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=expected_cols)
        w.writeheader()
        w.writerows(rows)
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                str(c),
                "--adjudicated",
                str(dis),
                "--out",
                str(out),
                "--disagreements",
                str(tmp_path / "dis2.csv"),
            ]
        )
        == 0
    )
    assert "pending adjudication: 1" in capsys.readouterr().out
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert set(labels) == {"p1", "p2", "p4", "p5", "p6", "p7"}
    assert labels["p4"]["relevance"] == 1 and labels["p4"]["n_annotators"] == 3
    assert labels["p7"]["relevance"] == 2 and labels["p7"]["n_annotators"] == 2

    rows[0]["adj_speaker_is_teacher_yes_no_unsure"] = "no"
    with dis.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=expected_cols)
        w.writeheader()
        w.writerows(rows)
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                str(c),
                "--adjudicated",
                str(dis),
                "--out",
                str(out),
                "--disagreements",
                str(tmp_path / "dis3.csv"),
            ]
        )
        == 0
    )
    labels = {x["id"]: x for x in map(json.loads, out.read_text().splitlines())}
    assert labels["p3"]["speaker_is_teacher"] == "no" and labels["p3"]["n_annotators"] == 3


def test_two_rater_disagreements_have_no_third_rater_columns(tmp_path):
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 1, "no", "yes", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 2, "no", "yes", "no")])
    out, dis = tmp_path / "labels.jsonl", tmp_path / "dis.csv"
    assert score_gold.main([str(a), str(b), "--out", str(out), "--disagreements", str(dis)]) == 0
    with dis.open(newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["pair_id"] + [f"{s}_{d}" for d in score_gold.DIMS for s in ("a", "b", "adj")]
    assert not any(h.startswith("c_") for h in header)


def test_three_rater_refuses_identical_disagreements_and_adjudicated_paths(tmp_path, capsys):
    """The disagreements output must never truncate the adjudications input."""
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 1, "yes", "yes", "no")])
    c = sheet(tmp_path / "c.csv", [("p1", 2, "yes", "yes", "no")])
    adj = tmp_path / "adj.csv"
    adj.write_text("pair_id\n", encoding="utf-8")
    before = adj.read_bytes()
    rc = score_gold.main(
        [
            str(a),
            str(b),
            str(c),
            "--adjudicated",
            str(adj),
            "--disagreements",
            str(adj),
            "--out",
            str(tmp_path / "labels.jsonl"),
        ]
    )
    assert rc == 1
    assert adj.read_bytes() == before  # untouched
    assert "same file" in capsys.readouterr().out


def test_three_rater_disagreements_skip_adjudicated_pairs(tmp_path):
    """Pairs already adjudicated are resolved, not re-listed as pending."""
    a = sheet(tmp_path / "a.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 3, "yes", "yes", "no")])
    b = sheet(tmp_path / "b.csv", [("p1", 1, "yes", "yes", "no"), ("p2", 2, "yes", "yes", "no")])
    c = sheet(tmp_path / "c.csv", [("p1", 2, "yes", "yes", "no"), ("p2", 0, "yes", "yes", "no")])
    cols = ["pair_id"] + [f"{s}_{d}" for d in score_gold.DIMS for s in ("a", "b", "c", "adj")]
    adj = tmp_path / "adj.csv"
    with adj.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow({"pair_id": "p1", "adj_relevance_0_3": "3"})
    out, dis = tmp_path / "labels.jsonl", tmp_path / "dis.csv"
    assert (
        score_gold.main(
            [
                str(a),
                str(b),
                str(c),
                "--adjudicated",
                str(adj),
                "--out",
                str(out),
                "--disagreements",
                str(dis),
            ]
        )
        == 0
    )
    rows = list(csv.DictReader(dis.open()))
    assert [r["pair_id"] for r in rows] == ["p2"]  # p1 resolved by adjudication


def test_krippendorff_alpha_nominal_hand_computed():
    """5 items x 3 raters, nominal: o_YY=7 o_NN=4 o_YN=o_NY=2, n=15.
    D_o=4/15, D_e=108/210 -> alpha=1-14/27=13/27~=0.4815."""
    y, n = "yes", "no"
    items = [[y, y, y], [y, y, y], [y, y, n], [y, n, n], [n, n, n]]
    assert three_rater.krippendorff_alpha(items) == pytest.approx(13 / 27)
    assert three_rater.usable_items(items) == 5


def test_krippendorff_alpha_ordinal_weights_distance():
    assert three_rater.krippendorff_alpha([[0, 0], [1, 1], [2, 2], [3, 3]], "ordinal") == 1.0
    near = three_rater.krippendorff_alpha([[0, 0], [1, 2], [3, 3], [2, 2]], "ordinal")
    far = three_rater.krippendorff_alpha([[0, 0], [1, 3], [3, 3], [2, 2]], "ordinal")
    assert near > far  # rank distance: off-by-one costs less than off-by-two
    assert three_rater.krippendorff_alpha([["yes"] * 3] * 4) == 1.0  # no variance
    with pytest.raises(ValueError, match="level"):
        three_rater.krippendorff_alpha([["yes", "yes"]], level="interval")


def test_krippendorff_alpha_skips_single_label_items():
    y, n = "yes", "no"
    full = [[y, y, y], [y, y, n], [y, n, n]]
    with_missing = full + [[y, None, None], [None, None, None]]
    assert three_rater.usable_items(with_missing) == 3
    assert three_rater.krippendorff_alpha(with_missing) == pytest.approx(
        three_rater.krippendorff_alpha(full)
    )
    with pytest.raises(ValueError, match="2\\+ labels"):
        three_rater.krippendorff_alpha([[y, None, None], [None, None, n]])


def test_pairwise_kappa_drops_missing_and_majority_or_pending():
    y, n = "yes", "no"
    assert three_rater.pairwise_kappa([y, y, None], [y, n, y]) == 0.0
    with pytest.raises(ValueError, match="co-present"):
        three_rater.pairwise_kappa([None], [y])
    assert three_rater.majority_or_pending([y, y, n]) == y
    assert three_rater.majority_or_pending([y, n, "unsure"]) is None
    assert (
        three_rater.majority_or_pending(
            [y, n, "unsure"], adjudicated="unsure", allowed=(y, n, "unsure")
        )
        == "unsure"
    )
    assert (
        three_rater.majority_or_pending(
            [y, n, "unsure"], adjudicated="maybe", allowed=(y, n, "unsure")
        )
        is None
    )


def test_agreement_report_3_includes_alpha_over_union(tmp_path):
    a = sheet(
        tmp_path / "a.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 3, "yes", "yes", "no"),
            ("p3", 2, "yes", "yes", "no"),
        ],
    )
    b = sheet(
        tmp_path / "b.csv",
        [
            ("p1", 3, "yes", "yes", "no"),
            ("p2", 1, "yes", "yes", "no"),
            ("p3", 2, "yes", "yes", "no"),
        ],
    )
    c = sheet(tmp_path / "c.csv", [("p1", 3, "yes", "yes", "no"), ("p2", 2, "yes", "yes", "no")])
    ra, _ = score_gold.read_sheet(a)
    rb, _ = score_gold.read_sheet(b)
    rc, _ = score_gold.read_sheet(c)
    triple = sorted(set(ra) & set(rb) & set(rc))
    assert triple == ["p1", "p2"]
    rep = score_gold.agreement_report_3(ra, rb, rc, triple)
    assert rep["relevance_0_3"]["alpha_level"] == "ordinal"
    assert rep["complete_yes_no"]["alpha_level"] == "nominal"
    for _dim, entry in rep.items():  # p3 (2 of 3 present) enters alpha but not the pairs
        assert entry["alpha_n_items"] == 3 > entry["n"] == 2
        assert -1.0 <= entry["krippendorff_alpha"] <= 1.0
    assert rep["complete_yes_no"]["krippendorff_alpha"] == 1.0  # unanimous yes everywhere
    assert score_gold.alpha_items(ra, rb, rc, "relevance_0_3")[2] == [2, 2, None]


def pairs_file(path: Path, rows: list[tuple]) -> Path:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "question", "assignment"])
        w.writerows(rows)
    return path


def test_make_task_files_two_rater_honours_assignment(tmp_path):
    src = pairs_file(
        tmp_path / "pairs.csv",
        [(f"p{i}", f"q{i}", a) for i, a in enumerate(["A", "B", "A+B", "A", "B"])],
    )
    out = tmp_path / "out"
    assert (
        make_task_files.main(
            [str(src), "--raters", "A", "B", "--overlap", "1", "--out-dir", str(out)]
        )
        == 0
    )
    got_a = (out / "annotator_A.csv").read_text()
    got_b = (out / "annotator_B.csv").read_text()
    assert [r["pair_id"] for r in csv.DictReader(got_a.splitlines())] == ["p0", "p2", "p3"]
    assert [r["pair_id"] for r in csv.DictReader(got_b.splitlines())] == ["p1", "p2", "p4"]
    assert next(csv.reader(got_a.splitlines())) == ["pair_id", "question"]  # no assignment leak


def test_make_task_files_three_rater_shared_disjoint_deterministic(tmp_path):
    rows = [(f"p{i}", f"q{i}", "A+B" if i < 4 else ("A" if i % 2 else "B")) for i in range(10)]
    src = pairs_file(tmp_path / "pairs.csv", rows)
    outs = []
    for run in ("r1", "r2"):
        out = tmp_path / run
        assert (
            make_task_files.main(
                [
                    str(src),
                    "--raters",
                    "A",
                    "B",
                    "C",
                    "--overlap",
                    "4",
                    "--seed",
                    "7",
                    "--out-dir",
                    str(out),
                ]
            )
            == 0
        )
        outs.append(out)
    sheets = [
        {r["pair_id"] for r in csv.DictReader((o / f"annotator_{x}.csv").open())}
        for o in outs[:1]
        for x in "ABC"
    ]
    assert all({"p0", "p1", "p2", "p3"} <= s for s in sheets)  # 4 shared in every sheet
    rest = [s - {"p0", "p1", "p2", "p3"} for s in sheets]
    assert all(len(s) == 2 for s in rest) and not (
        rest[0] & rest[1] or rest[0] & rest[2] or rest[1] & rest[2]
    )  # disjoint
    assert set.union(*sheets) == {f"p{i}" for i in range(10)}  # lossless
    for x in "ABC":  # deterministic seed: byte-identical rerun
        assert (outs[0] / f"annotator_{x}.csv").read_bytes() == (
            outs[1] / f"annotator_{x}.csv"
        ).read_bytes()


def test_make_task_files_refuses_filled_clobber_and_bad_overlap(tmp_path, capsys):
    src = tmp_path / "pairs.csv"
    with src.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "question", "assignment", "relevance_0_3"])
        w.writerow(["p0", "q0", "A+B", "3"])
    assert make_task_files.main([str(src), "--out-dir", str(tmp_path / "o")]) == 1
    assert "already filled" in capsys.readouterr().out

    src2 = pairs_file(tmp_path / "pairs2.csv", [("p0", "q0", "A+B")])
    out = tmp_path / "o2"
    assert make_task_files.main([str(src2), "--overlap", "2", "--out-dir", str(out)]) == 1
    assert "not --overlap 2" in capsys.readouterr().out

    src3 = pairs_file(tmp_path / "pairs3.csv", [("p0", "q0", "A"), ("p1", "q1", "B")])
    out3 = tmp_path / "o3"
    assert make_task_files.main([str(src3), "--overlap", "0", "--out-dir", str(out3)]) == 0
    assert make_task_files.main([str(src3), "--overlap", "0", "--out-dir", str(out3)]) == 1
    assert "exists" in capsys.readouterr().out  # no silent overwrite
    assert (
        make_task_files.main([str(src3), "--overlap", "0", "--out-dir", str(out3), "--force"]) == 0
    )


def test_make_task_files_preflight_writes_nothing_on_clobber(tmp_path, capsys):
    """A pre-existing annotator_B.csv must abort BEFORE annotator_A.csv is written."""
    rows = [(f"p{i}", f"q{i}", "A+B" if i < 2 else ("A" if i % 2 else "B")) for i in range(6)]
    src = pairs_file(tmp_path / "pairs.csv", rows)
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "annotator_B.csv"
    existing.write_text("pair_id,question\npX,qX\n", encoding="utf-8")
    before = existing.read_bytes()
    rc = make_task_files.main(
        [
            str(src),
            "--raters",
            "A",
            "B",
            "C",
            "--overlap",
            "2",
            "--seed",
            "7",
            "--out-dir",
            str(out),
        ]
    )
    assert rc == 1
    assert "exists" in capsys.readouterr().out
    assert not (out / "annotator_A.csv").exists()  # nothing written
    assert not (out / "annotator_C.csv").exists()
    assert existing.read_bytes() == before  # untouched
    assert (
        make_task_files.main(
            [
                str(src),
                "--raters",
                "A",
                "B",
                "C",
                "--overlap",
                "2",
                "--seed",
                "7",
                "--out-dir",
                str(out),
                "--force",
            ]
        )
        == 0
    )
    assert all((out / f"annotator_{r}.csv").exists() for r in "ABC")  # force rewrites all


def test_make_task_files_refuses_prefilled_notes(tmp_path, capsys):
    src = tmp_path / "pairs.csv"
    with src.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "question", "assignment", "notes"])
        w.writerow(["p0", "q0", "A", "someone already reviewed this"])
    assert make_task_files.main([str(src), "--out-dir", str(tmp_path / "o")]) == 1
    assert "already filled" in capsys.readouterr().out
    assert not (tmp_path / "o" / "annotator_A.csv").exists()

    blank = tmp_path / "pairs_blank.csv"  # blank notes still pass
    with blank.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "question", "assignment", "notes"])
        w.writerow(["p0", "q0", "A", ""])
        w.writerow(["p1", "q1", "B", ""])
    assert (
        make_task_files.main([str(blank), "--overlap", "0", "--out-dir", str(tmp_path / "o2")]) == 0
    )


def test_krippendorff_alpha_ordinal_uses_category_frequencies():
    """Hand-computed under Krippendorff's ordinal (cumulative-rank) metric.

    items [[0,0],[1,2],[0,2]]: totals n0=3, n1=1, n2=2, n=6;
    d01=(4-2)^2=4, d12=(3-1.5)^2=2.25, d02=(6-2.5)^2=12.25;
    D_o=(2*2.25+2*12.25)/6=29/6, D_e=180/30=6 -> alpha=1-29/36=7/36.
    Plain (c-k)^2 (the interval metric) would give 4/29 instead.
    """
    items = [[0, 0], [1, 2], [0, 2]]
    assert three_rater.krippendorff_alpha(items, "ordinal") == pytest.approx(7 / 36)
    assert three_rater.krippendorff_alpha(items, "ordinal") != pytest.approx(4 / 29)
    with pytest.raises(ValueError, match="totals"):
        three_rater._delta("ordinal", 0, 2)  # totals required, never silent
