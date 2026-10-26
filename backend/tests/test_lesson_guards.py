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


def test_code_in_gold_set_dir_passes_but_data_does_not():
    assert g.publication_problem("evals/gold_set_v1/three_rater.py") is None
    assert g.publication_problem("evals/gold_set_v1/pairs.jsonl")
    # .py under a data-only dir can embed clip text, so the code exemption does not reach it
    assert g.publication_problem("data/transcripts/clips.py")
    assert g.publication_problem("evals/gold_set_v1/transcripts/clips.py")
    assert g.publication_problem("audio_archive/manifest.py")


def test_grandfathered_file_passes():
    assert g.publication_problem("backend/evaluation/gold/labeling_packet_150.csv") is None


def test_baseline_exempts_recorded_file_but_not_a_new_one(tmp_path, monkeypatch):
    """The baseline records pre-existing leaks; it must never approve a new file."""
    import hashlib

    (tmp_path / "scripts/guards").mkdir(parents=True)
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")

    known_content = '{"verbatim_text": "This leak was already committed."}'
    known = tmp_path / "export_known.json"
    known.write_text(known_content)
    known_sha = hashlib.sha256(known_content.encode("utf-8")).hexdigest()

    baseline = tmp_path / "baseline.txt"
    baseline.write_text(f"# recorded, not approved\n{known_sha}  export_known.json\n")
    monkeypatch.setattr(g, "BASELINE", baseline)

    assert g.publication_problem("export_known.json") is None

    new = tmp_path / "export_new.json"
    new.write_text('{"verbatim_text": "This one is new."}')
    assert g.publication_problem("export_new.json")


def test_ordinary_file_passes():
    assert g.publication_problem("backend/app/config.py") is None


def test_clip_text_csv_blocked(tmp_path, monkeypatch):
    (tmp_path / "scripts/guards").mkdir(parents=True)
    f = tmp_path / "a.csv"
    f.write_text("id,clip_text\n1,hello\n")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    assert g.publication_problem("a.csv")


def test_unredacted_json_and_home_path_blocked(tmp_path, monkeypatch):
    (tmp_path / "scripts/guards").mkdir(parents=True)
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")

    f1 = tmp_path / "export.json"
    f1.write_text('{"verbatim_text": "This is unredacted teacher speech."}')
    assert g.publication_problem("export.json")

    f2 = tmp_path / "export_redacted.json"
    f2.write_text('{"redacted": true, "verbatim_text": "[REDACTED]"}')
    assert g.publication_problem("export_redacted.json") is None

    f3 = tmp_path / "config.json"
    f3.write_text('{"path": "/Users/developer/code/project"}')
    assert g.publication_problem("config.json")


def test_unredacted_record_after_the_first_64kb_is_blocked(tmp_path, monkeypatch):
    """The whole file is inspected; truncation used to exempt everything later."""
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    filler = '{"id": "%s", "note": "padding"}\n'
    lines = [filler % ("x" * 200) for _ in range(400)]
    lines.append('{"verbatim_text": "late unredacted teacher speech"}\n')
    (tmp_path / "big.jsonl").write_text("".join(lines))
    assert g.publication_problem("big.jsonl")


def test_redaction_is_checked_per_jsonl_record(tmp_path, monkeypatch):
    """A redacted first record must not exempt an unredacted later record."""
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    f = tmp_path / "mixed.jsonl"
    f.write_text(
        '{"redacted": true, "verbatim_text": "[REDACTED]"}\n'
        '{"verbatim_text": "this one is not redacted"}\n'
    )
    assert g.publication_problem("mixed.jsonl")


def test_fully_redacted_jsonl_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    f = tmp_path / "clean.jsonl"
    f.write_text(
        '{"verbatim_text": "[REDACTED]", "start_ms": 0}\n'
        '{"verbatim_text": "[REDACTED]", "start_ms": 1000}\n'
    )
    assert g.publication_problem("clean.jsonl") is None


def test_home_path_in_jsonl_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "ALLOW", tmp_path / "none.txt")
    f = tmp_path / "paths.jsonl"
    f.write_text('{"id": "a"}\n{"source": "/Users/developer/data/x.json"}\n')
    assert g.publication_problem("paths.jsonl")


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


def _stop(tmp_path, stdin="{}"):
    import subprocess

    script = Path(__file__).resolve().parents[2] / "scripts/guards/stop_check.sh"
    return subprocess.run(
        ["bash", str(script)], cwd=tmp_path, input=stdin, capture_output=True, text=True
    )


def _git(tmp_path, *args):
    import subprocess

    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_stop_hook_blocks_commit_on_branch_with_no_upstream(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a").write_text("x")
    _git(tmp_path, "add", "a")
    _git(tmp_path, "commit", "-qm", "c")
    r = _stop(tmp_path)
    assert r.returncode == 2 and "1 unpushed" in r.stderr


def test_stop_hook_allows_clean_tree_and_honours_active_flag(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a").write_text("x")
    _git(tmp_path, "add", "a")
    _git(tmp_path, "commit", "-qm", "c")
    assert _stop(tmp_path, '{"stop_hook_active": true}').returncode == 0
