import csv
import importlib.util
from pathlib import Path

_P = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "generate_speaker_label_workbook.py"
_spec = importlib.util.spec_from_file_location("gen_workbook", _P)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_label_column_is_empty_even_if_source_has_labels(tmp_path):
    src = tmp_path / "s.csv"
    src.write_text(
        "point_id,video_id,start_s,end_s,guru_id,score,margin,floor,band,LABEL(teacher_correct? y/n)\n"
        "a,v1,1.0,2.0,krishnaji,0.44,0.33,0.49,near,y\n"
        "b,v2,3.0,4.0,preethaji,0.9,0.5,0.49,far,n\n"
    )
    dst = tmp_path / "out.csv"
    assert mod.build(src, dst) == 2
    rows = list(csv.DictReader(dst.open()))
    assert all(r[mod.LABEL_COL] == "" for r in rows)
    assert "MACHINE (not a label): score" in rows[0]
    assert "reviewed" not in dst.name


def test_script_name_has_no_reviewed():
    assert "reviewed" not in _P.name


def test_no_reviewed_csv_carries_unattributed_human_labels():
    """A filled LABEL column in a *reviewed*.csv must name a human reviewer (invariant 3:
    never fit on AI labels). Machine verdicts belong in a MACHINE_REVIEW column."""
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "audits"
    bad = []
    for path in root.rglob("*reviewed*.csv"):
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        label_cols = [c for c in rows[0] if c.upper().startswith("LABEL") or c.upper().startswith("HUMAN TEACHER")]
        reviewer_cols = [c for c in rows[0] if "reviewer" in c.lower()]
        for col in label_cols:
            filled = [r for r in rows if (r.get(col) or "").strip()]
            unattributed = [r for r in filled if not any((r.get(c) or "").strip() for c in reviewer_cols)]
            if unattributed:
                bad.append(f"{path.relative_to(root)}:{col} ({len(unattributed)} rows)")
    assert not bad, f"human label column filled without a reviewer: {bad}"
