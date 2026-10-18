"""X-1 local labelling tool (scripts/ops/local_label.py): the labels it records
feed the human gold set, so independence between annotators and durability of
what was saved are correctness properties, not conveniences."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TOOL = _REPO / "scripts" / "ops" / "local_label.py"

pytest.importorskip("flask")


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("local_label_under_test", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setenv("LABEL_USERS", "alice:pw-a,bob:pw-b")
    mod.TASKS = [
        {"pair_id": "p1", "question": "q one", "clip_text": "synthetic clip one"},
        {"pair_id": "p2", "question": "q two", "clip_text": "synthetic clip two"},
    ]
    mod.OUTDIR = tmp_path / "out"
    yield mod
    sys.modules.pop(spec.name, None)


def _auth(user: str, pw: str) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _label(client, user, pw, pid, relevance, notes="", csrf=None):
    return client.post(
        "/label",
        headers=_auth(user, pw),
        data={
            "pair_id": pid,
            "relevance_0_3": relevance,
            "complete_yes_no": "yes",
            "speaker_is_teacher_yes_no_unsure": "yes",
            "risk_yes_no": "no",
            "notes": notes,
        }
        | ({"csrf": csrf} if csrf is not None else {}),
    )


def _labelAuthed(client, tool, user, pw, pid, relevance, notes=""):
    return _label(client, user, pw, pid, relevance, notes, csrf=tool._CSRF_TOKEN)


def _exported(client, user, pw) -> dict[str, dict]:
    import csv
    import io

    body = client.get("/export", headers=_auth(user, pw)).get_data(as_text=True)
    return {row["pair_id"]: row for row in csv.DictReader(io.StringIO(body))}


def test_second_annotator_does_not_overwrite_the_first(tool):
    client = tool.app.test_client()
    _labelAuthed(client, tool, "alice", "pw-a", "p1", "3")
    _labelAuthed(client, tool, "bob", "pw-b", "p1", "0")
    assert _exported(client, "alice", "pw-a")["p1"]["relevance_0_3"] == "3"
    assert _exported(client, "bob", "pw-b")["p1"]["relevance_0_3"] == "0"


def test_export_leaves_unlabelled_rows_blank_for_that_annotator(tool):
    client = tool.app.test_client()
    _labelAuthed(client, tool, "alice", "pw-a", "p1", "2")
    assert _exported(client, "bob", "pw-b")["p1"]["relevance_0_3"] == ""


def test_note_mentioning_skipped_keeps_the_labels(tool):
    client = tool.app.test_client()
    _labelAuthed(client, tool, "alice", "pw-a", "p1", "2", notes="teacher skipped a line")
    row = _exported(client, "alice", "pw-a")["p1"]
    assert row["relevance_0_3"] == "2"


def test_skip_marker_at_start_blanks_the_row(tool):
    client = tool.app.test_client()
    client.post(
        "/label",
        headers=_auth("alice", "pw-a"),
        data={"pair_id": "p1", "notes": "SKIPPED audio missing", "csrf": tool._CSRF_TOKEN},
    )
    row = _exported(client, "alice", "pw-a")["p1"]
    assert row["relevance_0_3"] == "" and row["notes"].startswith("SKIPPED")


def test_corrupt_progress_file_raises_instead_of_reading_as_empty(tool):
    tool.OUTDIR.mkdir(parents=True)
    (tool.OUTDIR / "progress.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        tool._load_progress()


def test_old_shared_label_progress_file_is_refused(tool):
    tool.OUTDIR.mkdir(parents=True)
    (tool.OUTDIR / "progress.json").write_text(
        json.dumps({"p1": {"relevance_0_3": "3", "annotators": ["alice"]}}), encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        tool._load_progress()


def test_wrong_password_and_non_ascii_password_are_rejected_not_crashed(tool):
    client = tool.app.test_client()
    assert client.get("/", headers=_auth("alice", "nope")).status_code == 401
    assert client.get("/", headers=_auth("alice", "pässwörd")).status_code == 401


def test_gitignore_guard_refuses_tracked_paths_and_accepts_ignored_ones(tool):
    assert tool._is_gitignored(_REPO / "evals" / "gold_set_v1" / "out") is False
    assert tool._is_gitignored(_REPO / ".work" / "label_tasks" / "A") is True
    assert tool._is_gitignored(Path("/tmp/outside-the-repo")) is True


def test_gitignore_guard_accepts_documented_backend_relative_outdir(tool, monkeypatch):
    """The documented invocation runs from backend/ with a ../.work outdir:
    git must check the repo-relative path, not the literal ../ string."""
    monkeypatch.chdir(_REPO / "backend")
    assert tool._is_gitignored(Path("../.work/label_tasks/A")) is True
    assert tool._is_gitignored(Path("../evals/gold_set_v1/out")) is False


def test_label_without_csrf_token_is_rejected(tool):
    client = tool.app.test_client()
    resp = _label(client, "alice", "pw-a", "p1", "3")
    assert resp.status_code == 403
    resp = _label(client, "alice", "pw-a", "p1", "3", csrf="wrong-token")
    assert resp.status_code == 403
    assert _exported(client, "alice", "pw-a")["p1"]["relevance_0_3"] == ""


def test_export_never_leaks_prefilled_sheet_labels_to_another_rater(tool):
    tool.TASKS = [
        {
            "pair_id": "p1",
            "question": "q one",
            "clip_text": "synthetic clip one",
            "relevance_0_3": "3",
            "notes": "someone else's note",
        },
    ]
    client = tool.app.test_client()
    row = _exported(client, "bob", "pw-b")["p1"]
    assert row["relevance_0_3"] == "" and row["notes"] == ""
    assert row["question"] == "q one"


def test_validate_tasks_rejects_empty_and_duplicate_pair_ids(tool):
    with pytest.raises(SystemExit):
        tool._validate_tasks([{"pair_id": ""}])
    with pytest.raises(SystemExit):
        tool._validate_tasks([{"pair_id": "p1"}, {"pair_id": "p1"}])
    tool._validate_tasks([{"pair_id": "p1"}, {"pair_id": "p2"}])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
