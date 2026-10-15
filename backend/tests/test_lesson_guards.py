"""Guards for lessons that repeated (scripts/guards/lesson_guards.py)."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[2] / "scripts/guards/lesson_guards.py"
_s = importlib.util.spec_from_file_location("lesson_guards", _p)
g = importlib.util.module_from_spec(_s)
_s.loader.exec_module(g)


def test_new_audio_and_dump_blocked():
    assert g.publication_problem("x/clip.wav")
    assert g.publication_problem("backup/neo4j.dump")


def test_gold_and_transcript_paths_blocked():
    assert g.publication_problem("evals/gold_set_v2/pairs.csv")
    assert g.publication_problem("data/transcripts/abc.txt")


def test_grandfathered_file_passes():
    assert g.publication_problem("backend/evaluation/gold/labeling_packet_150.csv") is None


def test_ordinary_file_passes():
    assert g.publication_problem("backend/app/config.py") is None


def test_clip_text_csv_blocked(tmp_path, monkeypatch):
    (tmp_path / "scripts/guards").mkdir(parents=True)
    f = tmp_path / "a.csv"
    f.write_text("id,clip_text\n1,hello\n")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    assert g.publication_problem("a.csv")


def test_unqualified_claims_flagged():
    assert g.claim_problems("d.md", ["Status: PROD READY"])
    assert g.claim_problems("d.md", ["Verdict: GO for faculty"])
    assert g.claim_problems("d.md", ["ALL GREEN"])


def test_qualified_claims_pass():
    assert not g.claim_problems("d.md", ["Verdict stays NO-GO"])
    assert not g.claim_problems("d.md", ["PROD READY is UNPROVEN until the Mac run"])
    assert not g.claim_problems("d.md", ["ALL GREEN via `make test` on local Mac 2026-10-15"])
    assert not g.claim_problems("d.md", ["The 'PROD READY' claim was later shown false"])


def _fresh():
    _f = Path(__file__).resolve().parents[2] / "scripts/ops/check_stack_fresh.py"
    s = importlib.util.spec_from_file_location("check_stack_fresh", _f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_stack_fresh_verdicts():
    m = _fresh()
    assert m.verdict(10, 10, 5, 5)[0] == 0
    assert m.verdict(10, 10, 11, 5)[0] == 1  # code newer than image
    assert m.verdict(10, 10, 5, 11)[0] == 1  # .env newer than container start
    assert m.ts("2026-10-15T10:00:00.123456789Z") > m.ts("2026-10-15T10:00:00Z")
