"""Tests for the humanizer service."""

from services.humanizer import scrub, scrub_with_report


def test_scrub_removes_sycophantic_openers():
    out = scrub("Certainly! Great question! Hello")
    assert out == "Hello"


def test_scrub_removes_collab_artifacts():
    out = scrub("I hope this helps! Let me know if you'd like more.")
    assert out == ""


def test_scrub_removes_filler():
    out = scrub("It is important to note that X")
    assert out == "X"


def test_scrub_preserves_negative_parallelism():
    # "Not only X, but also Y" is a valid rhetorical device, not AI slop
    out = scrub("Not only X, but also Y")
    assert out == "Not only X, but also Y"


def test_scrub_preserves_meaning():
    out = scrub("This is a profound tapestry of teachings")
    assert "tapestry" in out.lower()


def test_scrub_empty():
    assert scrub("") == ""


def test_scrub_none():
    assert scrub(None) is None


def test_scrub_leading_capital():
    out = scrub("begin the teaching now")
    assert out[0].isupper()


def test_scrub_double_pass():
    out = scrub("Certainly! Great question! It is important to note that X")
    assert out == "X"


def test_scrub_with_report_tracks_changes():
    sample = "Certainly! Hello. I hope this helps!"
    cleaned, report = scrub_with_report(sample)
    assert report.changed is True
    assert report.original_len == len(sample)
    assert "Certainly" not in cleaned
    assert "sycophantic opener" in report.changes
