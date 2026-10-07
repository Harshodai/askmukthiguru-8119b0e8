"""OKF load-time verbatim quote gate (P0, 2026-09-25).

`OKFStore.list_entries()` can optionally re-strip any quoted string (>= 8
words) that `services.transcript_verbatim.find_verbatim` cannot confirm is
the teacher's actual recorded words, behind `settings.okf_verbatim_quote_gate`
(default False per owner decision — built, not yet enabled). This must not
change any other `list_entries` invariant (DOCTRINE_TYPES, non-empty source,
OKFQualityFilter, staging/_scripts exclusion), which stay covered by
test_okf_doctrine_only.py and test_okf_pipeline_integrity.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from services.memory.okf_store import OKFStore

_VIDEO_ID = "vidLOADGATE1"
_VERBATIM_QUOTE = "Individual transformation is at the crux of our work together always."
_PARTIAL_QUOTE = (
    "Individual transformation is truly at the very crux of everyones work together always."
)
_FABRICATED_QUOTE = "The secret to eternal happiness is found only in silence and gold today."

_ENTRY_BODY = f"""## Quotes

> "{_VERBATIM_QUOTE}"

> "{_PARTIAL_QUOTE}"

> "{_FABRICATED_QUOTE}"

This entry exists only to exercise the OKF load-time verbatim quote gate.
"""


def _write_entry(okf_dir: Path) -> None:
    okf_dir.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        "type: teaching\n"
        'title: "Load Gate Probe"\n'
        f'source: "YouTube https://www.youtube.com/watch?v={_VIDEO_ID}"\n'
        "---\n\n"
        f"{_ENTRY_BODY}"
    )
    (okf_dir / "load_gate_probe.md").write_text(text, encoding="utf-8")


def _write_corpus(corpus_root: Path) -> None:
    video_dir = corpus_root / _VIDEO_ID
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / "canonical_segments.json").write_text(
        json.dumps(
            {
                "video_id": _VIDEO_ID,
                "segments": [
                    {
                        "segment_id": "seg_0000",
                        "start": 0.0,
                        "end": 5.0,
                        "text": _VERBATIM_QUOTE,
                        "verbatim_text": _VERBATIM_QUOTE,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def gated_store(tmp_path, monkeypatch):
    okf_dir = tmp_path / "okf"
    corpus_root = tmp_path / "corpus"
    _write_entry(okf_dir)
    _write_corpus(corpus_root)
    store = OKFStore(directory=okf_dir, corpus_root=corpus_root)
    yield store
    monkeypatch.setattr(settings, "okf_verbatim_quote_gate", False)


def test_flag_off_leaves_list_entries_output_unchanged(gated_store, monkeypatch):
    monkeypatch.setattr(settings, "okf_verbatim_quote_gate", False)
    entries = gated_store.list_entries()
    assert len(entries) == 1
    body = entries[0].body
    assert _VERBATIM_QUOTE in body
    assert _PARTIAL_QUOTE in body
    assert _FABRICATED_QUOTE in body


def test_flag_on_strips_fabricated_and_partial_keeps_verbatim(gated_store, monkeypatch):
    monkeypatch.setattr(settings, "okf_verbatim_quote_gate", True)
    entries = gated_store.list_entries()
    assert len(entries) == 1
    body = entries[0].body
    assert _VERBATIM_QUOTE in body
    assert _PARTIAL_QUOTE not in body
    assert _FABRICATED_QUOTE not in body


if __name__ == "__main__":  # ponytail: runnable self-check without pytest
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        okf_dir = tmp / "okf"
        corpus_root = tmp / "corpus"
        _write_entry(okf_dir)
        _write_corpus(corpus_root)
        store = OKFStore(directory=okf_dir, corpus_root=corpus_root)

        settings.okf_verbatim_quote_gate = False
        off_body = store.list_entries()[0].body
        assert _FABRICATED_QUOTE in off_body
        print("PASS flag off leaves quotes untouched")

        settings.okf_verbatim_quote_gate = True
        on_body = store.list_entries()[0].body
        assert _VERBATIM_QUOTE in on_body
        assert _FABRICATED_QUOTE not in on_body
        assert _PARTIAL_QUOTE not in on_body
        settings.okf_verbatim_quote_gate = False
        print("PASS flag on strips fabricated/partial, keeps verbatim")
    print("test_okf_load_gate self-check OK")
