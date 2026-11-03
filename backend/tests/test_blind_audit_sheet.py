"""The V7 listening sheet must not leak the teacher, and scoring must round-trip."""

from __future__ import annotations

import importlib.util
import json
import wave
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "build_blind_audit_sheet.py"
_spec = importlib.util.spec_from_file_location("build_blind_audit_sheet", _SCRIPT)
sheet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet)


def _wav(path: Path, seconds: int = 30) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * seconds)


def _setup(tmp_path, monkeypatch):
    wav_dir = tmp_path / "wavs"
    wav_dir.mkdir()
    _wav(wav_dir / "vidA.wav")
    spans = [
        {"source_span_id": f"span{i}", "guru_id": "krishnaji" if i % 2 else "preethaji"}
        for i in range(6)
    ]
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"seed": "s", "spans": spans}))
    windows = {
        s["source_span_id"]: {
            "video_id": "vidA",
            "start_ms": 2000 + 3000 * i,
            "end_ms": 6000 + 3000 * i,
        }
        for i, s in enumerate(spans)
    }
    monkeypatch.setattr(sheet, "fetch_windows", lambda *a, **k: windows)
    return key, wav_dir


def _args(tmp_path, key, wav_dir):
    return SimpleNamespace(
        key=str(key),
        collection="c",
        qdrant_url="x",
        wav_dir=str(wav_dir),
        out_dir=str(tmp_path / "sheet"),
        key_out=str(tmp_path / "keydir"),
    )


def test_sheet_hides_teacher_and_keeps_key_apart(tmp_path, monkeypatch):
    key, wav_dir = _setup(tmp_path, monkeypatch)
    assert sheet.build(_args(tmp_path, key, wav_dir)) == 0
    files = {p.name for p in (tmp_path / "sheet").iterdir()}
    assert files == {f"{n:03d}.wav" for n in range(1, 7)} | {"answers.csv", "index.html"}
    text = (tmp_path / "sheet" / "answers.csv").read_text() + (
        tmp_path / "sheet" / "index.html"
    ).read_text()
    assert "vidA" not in text and "span0" not in text
    assert (tmp_path / "keydir" / "sheet_key.json").exists()


def test_score_round_trips_and_rejects_bad_answers(tmp_path, monkeypatch):
    key, wav_dir = _setup(tmp_path, monkeypatch)
    sheet.build(_args(tmp_path, key, wav_dir))
    answers = tmp_path / "sheet" / "answers.csv"
    answers.write_text(
        "clip,choice\n" + "".join(f"{n:03d}.wav,sri_krishnaji\n" for n in range(1, 7))
    )
    out = tmp_path / "reviews.jsonl"
    args = SimpleNamespace(
        key=str(key),
        answers=str(answers),
        key_map=str(tmp_path / "keydir" / "sheet_key.json"),
        out=str(out),
    )
    assert sheet.score(args) == 0
    assert len(out.read_text().splitlines()) == 6
    answers.write_text("clip,choice\n" + "".join(f"{n:03d}.wav,maybe\n" for n in range(1, 7)))
    assert sheet.score(args) == 2
