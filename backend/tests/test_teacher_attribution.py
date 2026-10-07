"""Regression tests for services/teacher_attribution.py.

Guards the 2026-09-24 root-cause fix: a text MENTION of a teacher's name must
never assign attribution or emit a `teacher:` tag/teacher_id -- only the
SOURCE (title/speaker/source_url, or an explicit registry entry) may.
"""

import pytest

from services.teacher_attribution import (
    EXTERNAL_TEACHER_SOURCE_REGISTRY,
    resolve_teacher_attribution,
)

NO_EXTERNAL_CASES = [
    ("digital platforms", "", ""),
    ("the demon Mahishasura", "", ""),
    ("Sri Krishnaji", "", ""),
    ("oneness", "", ""),
    ("Deeksha", "", ""),
    ("grammar", "", ""),
    ("my friend Isha called today", "", ""),
    ("Krishna consciousness is a Vedic concept", "", ""),
    ("Kalki is an avatar in some traditions", "", ""),
]


@pytest.mark.parametrize("title,speaker,url", NO_EXTERNAL_CASES)
def test_no_false_external_attribution(title, speaker, url):
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url=url, title=title, speaker=speaker, chunks=[title]
    )
    for external in ("sadhguru", "amma_bhagavan", "iskcon"):
        assert f"teacher:{external}" not in tags, f"{title!r} falsely tagged teacher:{external}"
    assert teacher_id not in ("sadhguru", "amma_bhagavan", "iskcon"), (
        f"{title!r} falsely got teacher_id={teacher_id}"
    )
    for external in ("sadhguru", "amma_bhagavan", "iskcon"):
        assert external not in attributed, f"{title!r} falsely attributed {external}"


def test_preethaji_talk_mentioning_sadhguru_stays_preethaji():
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=abc",
        title="Preethaji on Inner Suffering",
        speaker="Sri Preethaji",
        chunks=["Sadhguru has spoken about similar themes in his own tradition."],
    )
    assert teacher_id == "preethaji"
    assert "preethaji" in attributed and "krishnaji" in attributed
    assert "mentions:sadhguru" in tags
    assert "teacher:sadhguru" not in tags


def test_krishnaji_title_signal():
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=xyz",
        title="Beautiful State with Sri Krishnaji",
        speaker="Sri Krishnaji",
    )
    assert teacher_id == "krishnaji"
    assert "teacher:sri_krishnaji" in tags
    assert "krishnaji" in attributed and "preethaji" in attributed


def test_ekam_channel_gives_ekam():
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=org1",
        title="Weekly Satsang",
        speaker="Ekam / O&O Academy",
    )
    assert teacher_id == "ekam"
    assert "teacher:ekam" in tags
    assert attributed == ["preethaji", "krishnaji"]


def test_default_no_signal_is_shared_lineage():
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=noop",
        title="On the Nature of Suffering",
    )
    assert teacher_id == "preethaji_krishnaji"
    assert attributed == ["preethaji", "krishnaji"]


def test_registered_external_source_gives_that_teacher(monkeypatch):
    monkeypatch.setitem(
        EXTERNAL_TEACHER_SOURCE_REGISTRY,
        "https://youtube.com/watch?v=registered-sadhguru",
        "sadhguru",
    )
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=registered-sadhguru",
        title="Some unrelated title",
    )
    assert teacher_id == "sadhguru"
    assert attributed == ["sadhguru"]
    assert "teacher:sadhguru" in tags


def test_unregistered_source_never_gets_external_id_from_mention_alone():
    tags, teacher_id, attributed = resolve_teacher_attribution(
        source_url="https://youtube.com/watch?v=not-registered",
        title="Some talk",
        chunks=["Amma Bhagavan is a teacher some seekers know of."],
    )
    assert teacher_id != "amma_bhagavan"
    assert "teacher:amma_bhagavan" not in tags
    assert "mentions:amma_bhagavan" in tags


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
