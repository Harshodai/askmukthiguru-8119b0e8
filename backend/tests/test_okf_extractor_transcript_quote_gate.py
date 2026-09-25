"""OKF entries must quote the teacher's actual recorded words.

Complements test_okf_fabricated_quote_gate.py (which catches a quote that
merely restates the entry's own LLM-written summary). This gate is ground-
truth: before a staged entry is written, any quoted string (>=8 words) that
services.transcript_verbatim.find_verbatim can't confirm is in the video's
transcript is stripped, not staged.
"""

import scripts.extract_okf_from_stores as extractor


def _fake_find_verbatim(verbatim_substring: str):
    """Returns a find_verbatim stand-in: any quote containing
    `verbatim_substring` is "verbatim", everything else is "not_found"."""

    def _fn(quote, video_id=None, **kwargs):
        status = "verbatim" if verbatim_substring in quote else "not_found"
        return {
            "status": status,
            "video_id": video_id,
            "start": 0.0 if status == "verbatim" else None,
            "end": 1.0 if status == "verbatim" else None,
            "score": 1.0 if status == "verbatim" else 0.0,
        }

    return _fn


def test_strip_fabricated_quotes_removes_not_found_keeps_verbatim(monkeypatch):
    monkeypatch.setattr(extractor, "find_verbatim", _fake_find_verbatim("genuinely spoke these words"))
    body = (
        "## Quotes\n"
        '> "The teacher genuinely spoke these words during the discourse today."\n\n'
        '> "This fabricated sentence was never actually said by anyone at all."\n'
    )
    cleaned, removed = extractor._strip_fabricated_quotes(body, video_id="abc123")
    assert removed == 1
    assert "genuinely spoke these words" in cleaned
    assert "fabricated sentence was never actually said" not in cleaned
    # The now-empty quote line is dropped, not left as a bare "> ".
    assert not any(line.strip() in ("", ">") for line in cleaned.splitlines() if line.strip("> \t") == "")


def test_partial_match_is_dropped_not_shown_as_teacher_words(monkeypatch):
    """A ~70%-overlap paraphrase is not the teacher's exact words."""
    monkeypatch.setattr(
        extractor, "find_verbatim", lambda quote, video_id=None, **kw: {"status": "partial", "score": 0.8}
    )
    body = '> "The teacher almost said these exact words during the long discourse."\n'
    cleaned, removed = extractor._strip_fabricated_quotes(body, video_id="abc123")
    assert removed == 1
    assert "almost said these exact words" not in cleaned


def test_strip_fabricated_quotes_no_video_id_is_a_no_op():
    body = '> "Any quote at all, verbatim status unknown without a video_id here."\n'
    cleaned, removed = extractor._strip_fabricated_quotes(body, video_id=None)
    assert removed == 0
    assert cleaned == body


def test_short_quotes_are_never_checked(monkeypatch):
    """Under the 8-word floor, a quote is left alone regardless of find_verbatim."""
    calls = []

    def _fail_if_called(quote, video_id=None, **kwargs):
        calls.append(quote)
        return {"status": "not_found", "video_id": video_id, "start": None, "end": None, "score": 0.0}

    monkeypatch.setattr(extractor, "find_verbatim", _fail_if_called)
    body = '## Quotes\n> "the Beautiful State"\n'
    cleaned, removed = extractor._strip_fabricated_quotes(body, video_id="abc123")
    assert removed == 0
    assert cleaned.strip() == body.strip()
    assert calls == []


def test_write_okf_entry_end_to_end_strips_fabricated_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "find_verbatim", _fake_find_verbatim("genuinely spoke these words"))
    body = (
        "## Quotes\n"
        '> "The teacher genuinely spoke these words during the discourse today."\n\n'
        '> "This fabricated sentence was never actually said by anyone at all."\n'
    )
    path = extractor._write_okf_entry(
        title="Transcript Quote Gate Probe",
        type_="teaching",
        body=body,
        source="YouTube https://youtube.com/watch?v=abc123",
        video_id="abc123",
        directory=tmp_path,
    )
    content = path.read_text(encoding="utf-8")
    assert "genuinely spoke these words" in content
    assert "fabricated sentence was never actually said" not in content
