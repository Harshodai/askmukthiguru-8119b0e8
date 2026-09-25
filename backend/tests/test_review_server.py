"""
Unit tests for evaluation.gold.review_server.
"""

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluation.gold import review_server
from evaluation.gold.review_server import app

client = TestClient(app)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_transcript(base_dir: Path, video_id: str, words: list[dict]) -> None:
    tdir = base_dir / "transcripts_B"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / f"{video_id}.json").write_text(json.dumps(words), encoding="utf-8")


def _row(**overrides) -> dict:
    row = {
        "question_id": "Q001", "question_text": "What is fear?", "clip_id": "c1",
        "video_id": "abcdefghijk", "start": "10.0", "end": "12.0",
        "text": "Fear is the movement of thought.",
        "judge_a": "", "judge_b": "", "adjudicated": "",
        "equivalent_group": "", "clip_quality": "",
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def _reset_server_state():
    """Every test gets a clean module-level _CSV_PATH/_JUDGE_ROLE — these
    tests would otherwise leak state into each other via shared globals."""
    yield
    review_server._CSV_PATH = None
    review_server._JUDGE_ROLE = None
    review_server._TRANSCRIPT_DIRS = []


def test_review_server_endpoints(tmp_path: Path):
    test_csv = tmp_path / "test_relevance.csv"
    rows = [
        {
            "question_id": "Q001",
            "question_text": "What is fear?",
            "clip_id": "c1",
            "video_id": "vid123",
            "start": "10.0",
            "end": "25.0",
            "text": "Fear is the movement of thought.",
            "judge_a": "",
            "judge_b": "",
            "adjudicated": "",
            "equivalent_group": "",
            "clip_quality": "",
        }
    ]
    _write_csv(test_csv, rows)

    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    # Test GET UI
    ui_resp = client.get("/")
    assert ui_resp.status_code == 200
    assert "AskMukthiGuru" in ui_resp.text

    # Test GET /api/rows
    rows_resp = client.get("/api/rows")
    assert rows_resp.status_code == 200
    data = rows_resp.json()
    assert len(data) == 1
    assert data[0]["question_id"] == "Q001"
    assert data[0]["judge_a"] == ""

    # Test POST /api/judge
    judge_resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "judge_a", "value": "yes", "clip_quality": "clean"},
    )
    assert judge_resp.status_code == 200

    # Verify CSV was written
    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["judge_a"] == "yes"
        assert reader[0]["clip_quality"] == "clean"


def test_arbitrary_column_overwrite_rejected(tmp_path: Path):
    """JudgmentUpdate.judge must reject anything outside
    judge_a/judge_b/adjudicated — a request naming 'text' or 'question_text'
    must not be able to overwrite sheet content."""
    test_csv = tmp_path / "relevance.csv"
    rows = [{
        "question_id": "Q001", "question_text": "What is fear?", "clip_id": "c1",
        "video_id": "vid123", "start": "10.0", "end": "25.0",
        "text": "Fear is the movement of thought.",
        "judge_a": "", "judge_b": "", "adjudicated": "",
        "equivalent_group": "", "clip_quality": "",
    }]
    _write_csv(test_csv, rows)
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "text", "value": "SOMETHING ELSE ENTIRELY"},
    )
    assert resp.status_code == 422

    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["text"] == "Fear is the movement of thought."


def test_judge_b_rows_have_no_judge_a_column(tmp_path: Path):
    """Blindness: judge b's /api/rows response must not leak judge_a."""
    test_csv = tmp_path / "relevance.csv"
    rows = [{
        "question_id": "Q001", "question_text": "What is fear?", "clip_id": "c1",
        "video_id": "vid123", "start": "10.0", "end": "25.0",
        "text": "Fear is the movement of thought.",
        "judge_a": "yes", "judge_b": "", "adjudicated": "",
        "equivalent_group": "", "clip_quality": "",
    }]
    _write_csv(test_csv, rows)
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "b"

    resp = client.get("/api/rows")
    assert resp.status_code == 200
    data = resp.json()
    assert "judge_a" not in data[0]
    assert "adjudicated" not in data[0]
    assert "judge_b" in data[0]


def test_judge_b_cannot_write_judge_a(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    rows = [{
        "question_id": "Q001", "question_text": "What is fear?", "clip_id": "c1",
        "video_id": "vid123", "start": "10.0", "end": "25.0",
        "text": "Fear is the movement of thought.",
        "judge_a": "", "judge_b": "", "adjudicated": "",
        "equivalent_group": "", "clip_quality": "",
    }]
    _write_csv(test_csv, rows)
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "b"

    resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "judge_a", "value": "yes"},
    )
    assert resp.status_code == 403

    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["judge_a"] == ""


def test_crash_mid_write_leaves_original_csv_intact(tmp_path: Path, monkeypatch):
    test_csv = tmp_path / "relevance.csv"
    rows = [{
        "question_id": "Q001", "question_text": "What is fear?", "clip_id": "c1",
        "video_id": "vid123", "start": "10.0", "end": "25.0",
        "text": "Fear is the movement of thought.",
        "judge_a": "", "judge_b": "", "adjudicated": "",
        "equivalent_group": "", "clip_quality": "",
    }]
    _write_csv(test_csv, rows)
    original_bytes = test_csv.read_bytes()

    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    def _boom(*args, **kwargs):
        raise OSError("simulated crash mid-replace")

    monkeypatch.setattr(review_server.os, "replace", _boom)

    with pytest.raises(OSError):
        review_server.write_csv_rows(test_csv, [{**rows[0], "judge_a": "yes"}])

    assert test_csv.read_bytes() == original_bytes
    # No leftover temp file in the directory.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(f".{test_csv.name}.")]
    assert leftovers == []


def test_html_injection_in_question_text_is_escaped(tmp_path: Path):
    """The rendered index page must never emit raw sheet text into
    innerHTML — a malicious question_text must not become executable
    markup. We can't execute the JS here, but we assert the page ships the
    escapeHtml() guard around the untrusted interpolations rather than the
    old unescaped innerHTML template."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "escapeHtml(r.question_text" in resp.text
    assert "escapeHtml(r.video_id" in resp.text


def test_non_loopback_host_refused_without_allow_remote():
    with pytest.raises(ValueError):
        review_server._validate_host("0.0.0.0", allow_remote=False)
    with pytest.raises(ValueError):
        review_server._validate_host("192.168.1.5", allow_remote=False)
    # Loopback is always fine.
    review_server._validate_host("127.0.0.1", allow_remote=False)
    # Explicit opt-in allows a non-loopback host.
    review_server._validate_host("0.0.0.0", allow_remote=True)


# --- Context endpoint (audio/context UI work) -----------------------------


def test_context_endpoint_returns_before_clip_after(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row(video_id="abcdefghijk", start="10.0", end="12.0")])

    words = [{"w": f"w{i}", "start": float(i), "end": float(i) + 0.9, "spk": "P"} for i in range(60)]
    _write_transcript(tmp_path, "abcdefghijk", words)

    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"
    review_server._TRANSCRIPT_DIRS = [tmp_path]

    resp = client.get("/api/context/0")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"before", "clip", "after"}
    assert len(data["clip"]) > 0
    assert all("spk" in w and "w" in w for w in data["clip"])
    assert len(data["before"]) <= 40
    assert len(data["after"]) <= 40


def test_context_endpoint_out_of_range_404(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row()])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    resp = client.get("/api/context/99")
    assert resp.status_code == 404


def test_malicious_video_id_yields_no_file_read_and_empty_context(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row(video_id="../../../../etc/passwd")])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"
    review_server._TRANSCRIPT_DIRS = [tmp_path]

    resp = client.get("/api/context/0")
    assert resp.status_code == 200
    assert resp.json() == {"before": [], "clip": [], "after": []}


def test_html_guards_video_id_before_building_player_url():
    """The player URL must never be built from an unvalidated video_id."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "VIDEO_ID_RE" in resp.text


# --- clip_quality blindness -------------------------------------------------


def test_judge_b_rows_have_no_clip_quality(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row(clip_quality="clean")])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "b"

    resp = client.get("/api/rows")
    assert resp.status_code == 200
    assert "clip_quality" not in resp.json()[0]


def test_judge_b_cannot_write_clip_quality(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row()])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "b"

    resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "judge_b", "value": "yes", "clip_quality": "fragment"},
    )
    assert resp.status_code == 403

    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["clip_quality"] == ""


def test_judge_a_can_write_valid_clip_quality(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row()])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "judge_a", "value": "yes", "clip_quality": "fragment"},
    )
    assert resp.status_code == 200

    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["clip_quality"] == "fragment"


def test_invalid_clip_quality_value_rejected(tmp_path: Path):
    test_csv = tmp_path / "relevance.csv"
    _write_csv(test_csv, [_row()])
    review_server._CSV_PATH = test_csv
    review_server._JUDGE_ROLE = "a"

    resp = client.post(
        "/api/judge",
        json={"row_index": 0, "judge": "judge_a", "value": "yes", "clip_quality": "not_a_real_value"},
    )
    assert resp.status_code == 422
